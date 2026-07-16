import os
import sys
import asyncio
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MainApp")

# Add root folder to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.calculator import router as calculator_router, CompensationRequest
from backend.ocr import router as ocr_router
from backend.vector_db import semantic_search, get_qdrant_client, VECTOR_DB_INITIALIZED
from backend.evaluator import evaluate_compensation_precedents

app = FastAPI(
    title="Compensation Calculator & Centralized Qdrant Vector DB",
    description="Enterprise motor claims compensation dashboard with local Qdrant database indexing, batch PDF processing, and AI Legal Precedents Assistant.",
    version="2.0.0"
)

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing Compensation Calculator API startup sequence...")
    try:
        # Validate Ollama setup and model availability
        from backend.llm_client import validate_ollama_setup
        validate_ollama_setup()
        
        # Initialize Qdrant Client and collection safety dynamically
        get_qdrant_client()
    except Exception as e:
        logger.error(f"Startup check failed: {str(e)}")

    # Warm up PaddleOCR — commented out eager warm-up to avoid startup crashes.
    # It will initialize lazily on the first PDF upload.
    # try:
    #     logger.info("Warming up PaddleOCR singleton...")
    #     from backend.ocr import get_ocr_instance
    #     get_ocr_instance()
    #     logger.info("PaddleOCR warm-up complete.")
    # except Exception as e:
    #     logger.error(f"PaddleOCR warm-up failed (non-fatal): {str(e)}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================================================
# PYDANTIC SCHEMAS FOR CHAT & EVALUATIONS
# ======================================================

class ChatRequest(BaseModel):
    message: str
    case_type: str = "all"  # 'injury', 'death', or 'all'

class EvaluateRequest(BaseModel):
    params: dict
    calculated_amount: float

# ======================================================
# API ENDPOINTS
# ======================================================

app.include_router(calculator_router, prefix="/api/calculate", tags=["Calculation"])
app.include_router(ocr_router, prefix="/api/ocr", tags=["OCR"])

@app.get("/api/health")
async def health_check():
    """Returns server connection stats for Qdrant and Ollama embeddings!"""
    client = get_qdrant_client()
    from backend.vector_db import QDRANT_URL
    from config.llm import LLM_API_ENDPOINT, LLM_MODEL_NAME
    return {
        "status": "healthy",
        "message": "Compensation Calculator Server is running!",
        "qdrant_url": QDRANT_URL,
        "ollama_url": LLM_API_ENDPOINT,
        "embedding_model": "nomic-embed-text",
        "llm_model": LLM_MODEL_NAME,
        "vector_db": "online" if VECTOR_DB_INITIALIZED else "offline"
    }

@app.post("/api/search/chat")
async def legal_ai_chat(request: ChatRequest):
    """
    Receives user query, runs a semantic vector search across 
    100+ indexed PDF documents in Qdrant, and returns matching precedents 
    and summaries.
    """
    try:
        case_filter = None if request.case_type == "all" else request.case_type
        
        # 1. Perform semantic search
        logger_results = semantic_search(request.message, limit=3, case_type_filter=case_filter)
        
        if not logger_results:
            # Fallback chat response if Qdrant is empty
            return {
                "response": "Hello! I am your AI Legal Assistant. The Qdrant centralized database is connected and is awaiting PDF document uploads to learn from precedents.\n\nOnce you drop legal petitions, judgments, or prayers in the **PDF Library**, they will be automatically indexed, and I can semantically answer specific profile questions (e.g. searching by age, income, and disability) and retrieve precedents!",
                "precedents": []
            }
            
        # 2. Compile matches into a highly professional response
        response_text = f"Based on your query **\"{request.message}\"**, I searched the centralized Qdrant vector database and retrieved the most relevant precedent cases:\n\n"
        
        for idx, match in enumerate(logger_results):
            meta = match["metadata"]
            name = meta.get("name", "Unnamed Claimant")
            filename = match["filename"]
            score = match["score"]
            award_amount = meta.get("award_amount", "")
            
            response_text += f"{idx+1}. **{name}** (Precedent file: *{filename}*, Semantic Match: {score*100:.1f}%)\n"
            response_text += f"   - *Case Parameters:* Age {meta.get('age', 'N/A')} | Income Rs. {meta.get('monthly_income', 'N/A')}/pm"
            if meta.get("case_type") == "injury":
                response_text += f" | Disability {meta.get('disability', 'N/A')}%"
            if award_amount:
                response_text += f" | **Award Amount: Rs. {int(float(award_amount)):,}**"
            response_text += f"\n   - *Key Extract:* \"...{match['text'].strip()}...\"\n\n"
            
        response_text += "\nThese matching judgments can be applied immediately as defensible courtroom precedents. Let me know if you would like me to compile the formal claim brief or run a comparative mathematical benchmarking evaluation!"
        
        return {
            "response": response_text,
            "precedents": logger_results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Legal chat error: {str(e)}")

@app.post("/api/search/evaluate")
async def evaluate_precedents(request: EvaluateRequest):
    """
    Benchmarks the math engine's calculated sum against semantic matched Qdrant precedents.
    """
    try:
        evaluation = evaluate_compensation_precedents(request.params, request.calculated_amount)
        return {
            "success": True,
            "evaluation": evaluation
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Comparative evaluation failed: {str(e)}")

class PDFChatRequest(BaseModel):
    question: str | None = None
    message: str | None = None  # Backwards compatibility
    filename: str | None = None  # if provided, chats strictly with this PDF
    case_type: str = "all"  # 'injury', 'death', or 'all'
    
    # Validation context fields
    ocr_text: str | None = None
    parsed_fields: dict | None = None
    calculator_result: dict | None = None
    is_justify: bool = False
    history: list[dict] | None = None

async def prepare_pdf_chat_prompt(request: PDFChatRequest):
    from backend.vector_db import semantic_search_rag
    import json
    question_str = request.question or request.message
    if not question_str:
        raise HTTPException(status_code=400, detail="Missing 'question' or 'message' field.")

    cr = request.calculator_result or {}
    pf = request.parsed_fields or {}
    calculated_compensation = cr.get("final_amount") or cr.get("total_compensation") or 0.0
    try:
        calculated_compensation = float(calculated_compensation)
    except (TypeError, ValueError):
        calculated_compensation = 0.0
        
    has_populated_calculator = False
    if request.calculator_result and calculated_compensation > 0:
        has_populated_calculator = True
    elif pf.get("monthly_income") and float(pf.get("monthly_income")) > 0:
        has_populated_calculator = True

    if has_populated_calculator:
        calculator_instruction_block = (
            "According to the Compensation Calculator\n\n"
            "Calculated Compensation:\n"
            "₹[calculated_compensation]\n\n\n"
            "Comparison\n\n"
            "Difference:\n"
            "₹[Difference between Calculated Compensation and Awarded Compensation, calculated as calculated_compensation minus awarded_compensation]\n\n"
            "The calculator result is based on the currently populated fields and serves as an analytical estimate. The judicially awarded compensation remains ₹[awarded_compensation] unless modified by a court order.\n\n"
        )
    else:
        calculator_instruction_block = (
            "According to the Compensation Calculator\n\n"
            "Calculator has not been run with populated fields for this session.\n\n"
        )
        
    from backend.recalc_intent import run_recalculation
    if not request.is_justify:
        recalc_response = run_recalculation(
            question_str, request.parsed_fields, request.calculator_result
        )
        if recalc_response is not None:
            return None, None, [], recalc_response
            
    case_filter = None if request.case_type == "all" else request.case_type
    
    # Determine filename filter
    filename_filter = request.filename
    if filename_filter == "all" or filename_filter == "":
        filename_filter = None

    # 1. Perform semantic vector search using the RAG helper
    if request.is_justify:
        # Use two targeted queries that will actually match the award table
        # and the grounds of appeal section in Qdrant chunks
        results_award, results_grounds = await asyncio.gather(
            asyncio.to_thread(semantic_search_rag, query="compensation awarded amount medical expenses pain suffering transport attender loss of income heads", limit=4, filename_filter=filename_filter),
            asyncio.to_thread(semantic_search_rag, query="grounds of appeal enhancement disfiguration ear loss marriage prospects disability", limit=3, filename_filter=filename_filter),
        )
        # Deduplicate by chunk text and merge
        seen_texts = set()
        search_results = []
        for r in results_award + results_grounds:
            t = r.get("text", "")[:100]
            if t not in seen_texts:
                seen_texts.add(t)
                search_results.append(r)
    else:
        search_results = await asyncio.to_thread(
            semantic_search_rag,
            query=question_str,
            limit=5,
            filename_filter=filename_filter
        )
    
    # 2. Construct context from retrieved points
    context_blocks = []
    precedents = []
    for idx, res in enumerate(search_results):
        text_block = res.get("text", "").strip()
        filename = res.get("filename", "unknown")
        context_blocks.append(f"[Context {idx+1} from {filename}]:\n{text_block}")
        
        precedents.append({
            "filename": filename,
            "score": res.get("score"),
            "text": text_block,
            "metadata": res.get("metadata", {})
        })
        
    retrieved_chunks = "\n\n".join(context_blocks)
    
    # 3. Incorporate Workstation Context (Phase 8 state integration)
    chunks_combined = retrieved_chunks
    workstation_blocks = []
    if request.ocr_text:
        if request.is_justify:
            ocr_full = request.ocr_text or ""
            ocr_len = len(ocr_full)
            if ocr_len <= 12000:
                ocr_for_llm = ocr_full
            else:
                ocr_for_llm = (
                    ocr_full[:4000]
                    + "\n\n[... middle pages omitted ...]\n\n"
                    + ocr_full[-8000:]
                )
            workstation_blocks.append(
                f"[Current PDF Workstation OCR Text]:\n{ocr_for_llm}"
            )
        else:
            ocr_full = request.ocr_text or ""
            if len(ocr_full) <= 8000:
                ocr_for_llm = ocr_full
            else:
                ocr_for_llm = (
                    ocr_full[:3000]
                    + "\n\n[... middle pages omitted ...]\n\n"
                    + ocr_full[-5000:]
                )
            workstation_blocks.append(
                f"[Current PDF Workstation OCR Text]:\n{ocr_for_llm}"
            )
    if request.parsed_fields:
        workstation_blocks.append(
            "[Current PDF Workstation Parsed Fields — CALCULATOR INPUT VALUES ONLY. "
            "These reflect whatever is currently typed into the left-hand form and may "
            "have been edited by the user; they are NOT necessarily what the tribunal "
            "found or what the PDF says. If the user asks a factual question about the "
            "case (e.g. 'what disability percentage does the judgment mention', "
            "'what medical expenses were claimed'), you MUST answer from the OCR text / "
            "retrieved PDF context above, not from this block. Only use this block when "
            "the question is specifically about the calculator's current inputs or "
            "outputs.]:\n"
            f"{json.dumps(request.parsed_fields, indent=2)}"
        )
    if request.calculator_result:
        workstation_blocks.append(f"[Current Deterministic Calculator Math Output]:\n{json.dumps(request.calculator_result, indent=2)}")
    
    if workstation_blocks:
        chunks_combined = "\n\n".join(workstation_blocks) + "\n\n=== RETRIEVED PRECEDENTS ===\n\n" + chunks_combined
        
    # 4. Construct System Prompt & User Prompt strictly following grounding and safety boundaries

    # Justify Compensation mode
    # Build explicit case facts summary for justify mode
    case_facts_summary = ""
    justify_block = ""
    if request.is_justify:
        pf = request.parsed_fields or {}
        cr = request.calculator_result or {}
        case_type_str = str(pf.get("case_type") or cr.get("case_type") or "injury").lower()
        is_death = (case_type_str == "death")

        # ── PRECOMPUTE VERDICT IN PYTHON (never let LLM compare numbers) ──
        try:
            tribunal_total = float(pf.get("award_amount") or 0)
        except (TypeError, ValueError):
            tribunal_total = 0
        try:
            calc_total = float(
                cr.get("final_amount") or cr.get("total_compensation") or 0
            )
        except (TypeError, ValueError):
            calc_total = 0

        if tribunal_total == 0 or calc_total == 0:
            math_relation = "unknown"
            precomputed_comparison = (
                "Tribunal total or calculator total not available in workstation. "
                "Determine verdict from OCR text only."
            )
        elif abs(tribunal_total - calc_total) < 1:
            math_relation = "equal"
            precomputed_comparison = (
                f"Tribunal awarded Rs. {tribunal_total:,.0f} which EQUALS "
                f"the calculator estimate of Rs. {calc_total:,.0f}. "
                f"If CLAIMANT filed the appeal: verdict is UNDER-COMPENSATED "
                f"(specific heads omitted in grounds of appeal). "
                f"If INSURANCE COMPANY filed: verdict is ADEQUATE on quantum "
                f"(this may be a liability/exoneration appeal — see grounds)."
            )
        elif tribunal_total < calc_total:
            math_relation = "tribunal_lower"
            diff = calc_total - tribunal_total
            precomputed_comparison = (
                f"Tribunal awarded Rs. {tribunal_total:,.0f}, which is "
                f"Rs. {diff:,.0f} LESS than the calculator estimate of "
                f"Rs. {calc_total:,.0f}."
            )
        else:
            math_relation = "tribunal_higher"
            diff = tribunal_total - calc_total
            precomputed_comparison = (
                f"Tribunal awarded Rs. {tribunal_total:,.0f}, which is "
                f"Rs. {diff:,.0f} MORE than the calculator estimate of "
                f"Rs. {calc_total:,.0f}."
            )
        # ─────────────────────────────────────────────────────────────────

        # ── BUILD CASE_FACTS_SUMMARY (death vs injury fields) ─────────────
        if is_death:
            calc_fields_summary = (
                f"Calculator Loss of Dependency: Rs. {cr.get('loss_of_dependency', 'Unknown')}\n"
                f"Calculator Consortium: Rs. {cr.get('consortium', 0)}\n"
                f"Calculator Funeral Expenses: Rs. {cr.get('funeral_expenses', 0)}\n"
                f"Calculator Loss of Estate: Rs. {cr.get('loss_estate', cr.get('loss_of_estate', 0))}\n"
                f"Future Prospect %: {cr.get('future_prospect_percentage', 'Unknown')}\n"
                f"Deduction %: {cr.get('deduction_percentage', 'Unknown')}\n"
                f"Multiplier: {cr.get('multiplier', 'Unknown')}\n"
            )
        else:
            calc_fields_summary = (
                f"Calculator Medical: Rs. {cr.get('medical_expenses', 'Unknown')}\n"
                f"Calculator Pain & Suffering: Rs. {cr.get('pain_and_suffering', 'Unknown')}\n"
                f"Calculator Future Income Loss: Rs. {cr.get('future_income_loss', cr.get('loss_of_income', 'Unknown'))}\n"
                f"Calculator Transport: Rs. {cr.get('transportation', 0)}\n"
                f"Calculator Special Diet: Rs. {cr.get('special_diet', 0)}\n"
                f"Calculator Attender: Rs. {cr.get('attender_charges', 0)}\n"
                f"Calculator Future Medical: Rs. {cr.get('future_medical_expenses', 0)}\n"
                f"Multiplier: {cr.get('multiplier', 'Unknown')}\n"
            )

        case_facts_summary = (
            f"\n=== CASE PARAMETERS FROM WORKSTATION ===\n"
            f"Case Type: {case_type_str}\n"
            f"Claimant: {pf.get('name', 'Unknown')}\n"
            f"Age: {pf.get('age', 'Unknown')} years\n"
            f"Monthly Income (CALCULATOR INPUT — not a tribunal finding): "
            f"Rs. {pf.get('monthly_income', 'Unknown')}\n"
            f"Disability % (CALCULATOR INPUT ONLY — NOT a tribunal finding. "
            f"Do NOT report this as what the tribunal held): "
            f"{pf.get('disability', 'Unknown')}%\n"
            f"Tribunal Award Total: Rs. {pf.get('award_amount', 'Unknown')}\n"
            f"Calculator Estimated Total: Rs. {cr.get('final_amount', 'Unknown')}\n"
            f"{calc_fields_summary}"
            f"\n=== PRECOMPUTED VERDICT (USE EXACTLY AS WRITTEN) ===\n"
            f"MATH RELATION: {math_relation}\n"
            f"COMPARISON: {precomputed_comparison}\n"
            f"INSTRUCTION: Copy the COMPARISON sentence into Overall Verdict → Reason verbatim.\n"
            f"DO NOT rewrite or rephrase the comparison. DO NOT say 'less than' if amounts are equal.\n"
            f"===\n"
        )

        question_str = (
            "Analyse this motor accident compensation case. "
            "Provide a structured justification of whether the tribunal award is "
            "adequate, under-compensated, or over-compensated."
        )

        # ── HINDI TERMS: injury vs death ───────────────────────────────
        if is_death:
            hindi_terms_block = (
                "  आश्रितता की हानि / पोषण हानि  → Loss of Dependency\n"
                "  अंत्येष्टि व्यय / दाह संस्कार  → Funeral Expenses\n"
                "  सहचर्य / पत्नी क्षति           → Consortium\n"
                "  सम्पत्ति की हानि               → Loss of Estate\n"
                "  प्रेम और स्नेह की हानि          → Loss of Love & Affection\n"
                "  भावी संभावनाएं                  → Future Prospects\n"
                "  गुणांक                          → Multiplier\n"
            )
            head_analysis_hint = (
                "For DEATH cases, expected heads are:\n"
                "  Loss of Dependency, Consortium, Funeral Expenses, Loss of Estate,\n"
                "  Loss of Love & Affection. Check the judgment for each.\n"
            )
        else:
            hindi_terms_block = (
                "  शारीरिक एवं मानसिक पीड़ा       → Pain & Suffering\n"
                "  आवागमन एवं पोषिक आहार         → Transportation & Special Diet\n"
                "  सहायक पर व्यय                  → Attender Charges\n"
                "  चिकित्सा व्यय                  → Medical Expenses\n"
                "  आय की हानि                     → Loss of Income\n"
                "  विरूपता                        → Disfigurement\n"
                "  जीवन की सुख सुविधाओं की हानि   → Loss of Amenities\n"
                "  भविष्य में आय की हानि           → Future Income Loss\n"
                "  मद / राशि                      → Head / Amount (table columns)\n"
            )
            head_analysis_hint = (
                "For INJURY cases, expected heads are:\n"
                "  Medical Expenses, Pain & Suffering, Transportation, Special Diet,\n"
                "  Attender Charges, Loss of Income, Future Income Loss,\n"
                "  Disfigurement, Loss of Amenities. Check the judgment for each.\n"
            )

        # ── APPEAL TYPE DETECTION HINT ─────────────────────────────────
        appeal_type_hint = (
            "STEP 0 — IDENTIFY APPEAL TYPE FIRST.\n"
            "Read the memo of appeal to determine:\n"
            "  A. Who filed: Claimant (seeking enhancement) or Insurance company "
            "(seeking reduction or exoneration).\n"
            "  B. What type of appeal:\n"
            "     QUANTUM APPEAL: disputes the amount awarded per head.\n"
            "     LIABILITY APPEAL: insurance disputes whether it should pay at all "
            "(e.g. permit violation, driving licence breach, policy conditions). "
            "In a liability appeal, head-wise quantum analysis is secondary — "
            "the core issue is who bears the liability.\n"
            "  State the appeal type clearly before proceeding.\n\n"
        )

        justify_block = (
            "\n=== JUSTIFY COMPENSATION — INSTRUCTIONS ===\n\n"

            + appeal_type_hint +

            "STEP 1 — SCAN THE OCR TEXT FOR THE AWARD TABLE.\n"
            "The judgment award table is near the END of the document.\n"
            "Search for these Hindi terms to locate each row:\n"
            + hindi_terms_block +
            "The number immediately after or beside each Hindi term is the awarded amount.\n"
            "Record EVERY head including NIL/zero heads.\n\n"

            "STEP 2 — SCAN FOR GROUNDS OF APPEAL.\n"
            "Find the Grounds section. List every issue raised:\n"
            "  — Heads awarded too low\n"
            "  — Heads completely missed (disfigurement, ear/eye/limb loss,\n"
            "    loss of amenities, future treatment, marriage prospects,\n"
            "    consortium, love & affection)\n"
            "  — Interest rate or date disputes\n"
            "  — Income, disability, or liability evidence disputes\n"
            "  — Permit, licence, or policy breach arguments (liability appeals)\n\n"

            "STEP 3 — DISABILITY / DEPENDENCY FINDING.\n"
            "The Disability % in the workstation is a CALCULATOR INPUT — NOT a tribunal finding.\n"
            "Read the judgment to find what the tribunal ACTUALLY decided:\n"
            "  Injury: Was permanent disability proved? Was a disability certificate produced?\n"
            "  Death: Was income proved? What multiplier and deduction did the tribunal apply?\n"
            "Report only what the tribunal found. Never cite the workstation % as a tribunal finding.\n\n"

            "STEP 4 — CLASSIFICATION RULE.\n"
            "For each awarded head:\n"
            "  tribunal amount < calculator estimate → Low\n"
            "  tribunal amount == calculator estimate → Adequate\n"
            "  tribunal amount > calculator estimate → High\n"
            "  calculator estimate Unknown/0 or N/A → N/A\n"
            "If claimant has no income (minor, student, homemaker, unemployed):\n"
            "  Income/dependency head → N/A (state reason, not 'no documentation')\n"
            "  Do NOT generate income-related root cause bullets for this claimant.\n\n"

            "STEP 5 — LEGAL CAUTION.\n"
            "For Missed Heads and liability arguments:\n"
            "  Write: 'The appellant contends [exact argument from grounds].'\n"
            "  Do NOT write: 'This omission is unjustified.' or 'The tribunal erred.'\n\n"

            "CITATION RULE.\n"
            "Only cite legal sections/cases that appear word-for-word in the PDF.\n"
            "If none: 'No specific precedents cited in document.'\n\n"

            "=== OUTPUT FORMAT ===\n\n"

            "**Who Filed the Appeal:** "
            "[Claimant seeking enhancement / Insurance company seeking reduction/exoneration]\n\n"

            "**Appeal Type:** [Quantum appeal (disputes award amounts) / "
            "Liability appeal (disputes who should pay) / Both]\n\n"

            "**Overall Verdict:** [UNDER-COMPENSATED / ADEQUATE / OVER-COMPENSATED / "
            "LIABILITY DISPUTE (quantum not in dispute)]\n"
            "Reason: [Copy the COMPARISON sentence from PRECOMPUTED VERDICT verbatim. "
            "Then append any missed heads or liability grounds.]\n\n"

            "**Head-wise Analysis (Awarded Heads):**\n"
            + head_analysis_hint +
            "- [Head Name]: Rs.[amount from OCR] → [Low/Adequate/High/N/A]\n"
            "  Why tribunal fixed this amount: [evidence accepted/rejected]\n"
            "  Calculator estimate: Rs.[amount] or N/A\n\n"

            "**Missed Heads (Raised in Grounds but Not Awarded):**\n"
            "- [Head Name]\n"
            "  Appellant's argument: [from grounds of appeal]\n"
            "  Why not awarded: [tribunal's reason, or 'No reason given']\n"
            "If none: None.\n\n"

            "**Liability / Policy Grounds (if insurance liability appeal):**\n"
            "[Summarise each liability ground raised by insurance company: "
            "permit breach, licence breach, policy conditions, pay-and-recover order. "
            "State the appellant's argument and the tribunal's finding on each.]\n"
            "If not a liability appeal: Not applicable.\n\n"

            "**Disability / Dependency Finding:**\n"
            "[What the tribunal ACTUALLY found — not the workstation input value.]\n\n"

            "**Interest Awarded:**\n"
            "[Rate]% from [date from judgment].\n"
            "Dispute: [Appellant's argument on interest, or 'No dispute.']\n\n"

            "**Root Causes of Under/Over Compensation:**\n"
            "Each bullet must name a specific fact about THIS case:\n"
            "— specific injury or death circumstances\n"
            "— specific evidence missing or rejected\n"
            "— specific head not awarded and reason\n"
            "— claimant's age, occupation, and income status\n"
            "DO NOT write generic income bullets if claimant has no income.\n\n"

            "**Key Legal Provisions & Precedents Used:**\n"
            "[Verbatim from PDF only. If none: "
            "'No specific precedents cited in document.']\n\n"

            "FINAL RULE: Every tribunal Rs. figure must come from the OCR text. "
            "If not found: write 'Not found in OCR text' — never guess.\n"
        )

    system_instruction = (
        "You are a Motor Accident Claims Tribunal legal assistant.\n\n"
        "=== STRICTOR GROUNDING INSTRUCTIONS ===\n"
        "1. Use ONLY the supplied context (Retrieved Precedents and active Workstation details).\n"
        "2. Do NOT invent or hallucinate legal facts, precedents, or claims metrics.\n"
        "3. If the context does not contain the answer, clearly state that the information is missing.\n\n"
        "=== NEW COMPENSATION DATA MODEL & PRIORITY RULES ===\n"
        "Maintain separate concepts for the following compensation values and NEVER merge, mix, or overwrite them:\n"
        "- awarded_compensation: Amount awarded by the Tribunal/Court (extracted from PDF). E.g. 'Amount Awarded Rs.' indicates this.\n"
        "- claimed_compensation: Amount originally claimed (extracted from PDF). E.g. 'Claim before Tribunal' indicates this.\n"
        "- enhancement_sought: Additional amount requested in appeal (extracted from PDF). E.g. 'Appeal valued at' or 'Enhancement sought' indicates this.\n"
        "- calculated_compensation: Amount computed by the deterministic calculator (supplied in the active workstation context under [Current Deterministic Calculator Math Output]).\n\n"
        "If the PDF contains a tribunal award, use awarded_compensation first. Do NOT replace it with calculated_compensation.\n"
        "The Tribunal award is a judicial fact, whereas the calculator output is a computed estimate. Never overwrite judicially awarded compensation with calculator output.\n\n"
        "=== FORBIDDEN BEHAVIORS ===\n"
        "- NEVER say: 'Calculated amount is the source of truth'.\n"
        "- NEVER say: 'The deterministic calculator output supplied in the context is the absolute single source of truth' or 'the mathematical engine remains the ultimate source of truth'.\n"
        "- NEVER say: 'Compensation amount is ₹X' (only one figure) when multiple compensation figures exist.\n"
        "- NEVER overwrite judicially awarded compensation with calculator output.\n\n"
        "=== OUTPUT FORMATTING RULES ===\n"
        "- NEVER use Markdown headers (##, ###, etc.) anywhere in your response.\n"
        "- Use **bold** (double asterisks) for labels and emphasis instead of headers.\n"
        "- NEVER use LaTeX notation of any kind — no \\[ \\], no \\( \\), no \\text{...},\n"
        "  no \\frac, no square-bracket math blocks. This is a plain-text chat window\n"
        "  and LaTeX will render as broken raw text, not as a formula.\n"
        "- Write any arithmetic as plain text on one line, e.g.:\n"
        "  Rs. 1,06,600 + Rs. 10,000 = Rs. 1,16,600\n"
        "- Use Indian numbering format with commas (e.g. Rs. 1,06,600), not\n"
        "  Rs. 106,600.\n"
        "- Keep currency values on their own line or inline with **bold** labels,\n"
        "  never inside a math block.\n\n"
        "=== CHATBOT RESPONSE RULES ===\n"
        "When the user asks 'What is the compensation amount?' or questions about compensation, or when multiple compensation figures exist, you MUST separate the figures. NEVER answer with only one figure. Instead, respond strictly using the following REQUIRED RESPONSE FORMAT:\n\n"
        "According to the PDF (Judicial Record)\n\n"
        "Awarded Compensation:\n"
        "₹[awarded_compensation]\n\n"
        "Claim Amount:\n"
        "₹[claimed_compensation]\n\n"
        "Enhancement Sought:\n"
        "₹[enhancement_sought]\n\n\n"
        + calculator_instruction_block +
        "=== MATHEMATICAL INTEGRITY RULES ===\n"
        "- Under no circumstances should you compute, recalculate, or override mathematical values, multipliers, or final compensation totals.\n"
        "- You are only reached for this message because it was NOT a recalculation request (recalculation requests are intercepted and answered by the deterministic engine directly, above, before this prompt is built). Do not attempt to do the math yourself.\n"
    )
    
    if request.is_justify:
        system_instruction += f"\n{justify_block}"

    user_prompt = (
        f"{case_facts_summary}\n"
        f"Context:\n{chunks_combined}\n\n"
        f"Question:\n{question_str}"
    )
    
    return user_prompt, system_instruction, precedents, None

@app.post("/api/chat/pdf")
async def chat_with_pdf(request: PDFChatRequest):
    """
    RAG PDF Assistant: retrieves semantic chunks from Qdrant 
    and sends the constructed prompt to the configured LLM.
    """
    try:
        user_prompt, system_instruction, precedents, recalc_response = await prepare_pdf_chat_prompt(request)
        if recalc_response is not None:
            return recalc_response

        # 5. Generate LLM Response using configured provider (Ollama Qwen2.5:14b)
        from backend.llm_client import generate_response
        ai_response = await asyncio.to_thread(generate_response, user_prompt, system_instruction, None, request.history)
        
        return {
            "response": ai_response,
            "precedents": precedents
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM Chat failed: {str(e)}")

@app.post("/api/chat/pdf/stream")
async def chat_with_pdf_stream(request: PDFChatRequest):
    """
    RAG PDF Assistant: retrieves semantic chunks from Qdrant,
    constructs the prompt, and returns a SSE-compatible NDJSON response stream.
    """
    import json
    try:
        user_prompt, system_instruction, precedents, recalc_response = await prepare_pdf_chat_prompt(request)
        
        if recalc_response is not None:
            async def stream_recalc():
                # Yield full response in one NDJSON chunk
                yield json.dumps({
                    "message": {
                        "content": recalc_response["response"]
                    },
                    "recalculation": recalc_response["recalculation"]
                }) + "\n"
            from fastapi.responses import StreamingResponse
            return StreamingResponse(stream_recalc(), media_type="text/event-stream")

        from backend.llm_client import generate_response_stream
        from fastapi.responses import StreamingResponse
        import queue
        import threading

        q = queue.Queue()
        
        def producer():
            try:
                for token in generate_response_stream(user_prompt, system_instruction, request.history):
                    q.put(token)
            except Exception as ex:
                logger.error(f"Error in stream producer thread: {str(ex)}")
            finally:
                q.put(None)
                
        thread = threading.Thread(target=producer, daemon=True)
        thread.start()

        async def event_generator():
            while True:
                token = await asyncio.to_thread(q.get)
                if token is None:
                    break
                yield json.dumps({"message": {"content": token}}) + "\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM Chat Stream failed: {str(e)}")

@app.get("/api/qdrant/points")
async def get_qdrant_points():
    """
    Returns collection stats and points from local Qdrant database 
    for visual rendering in the embedded dashboard.
    """
    try:
        from backend.vector_db import get_qdrant_client, COLLECTION_NAME
        client = get_qdrant_client()
        if client is None:
            return {
                "success": False,
                "message": "Qdrant database is currently offline or uninitialized.",
                "collection_name": COLLECTION_NAME,
                "points_count": 0,
                "points": []
            }
            
        try:
            info = client.get_collection(COLLECTION_NAME)
            points_count = info.points_count
            status = info.status
            distance = info.config.params.vectors.distance
            if hasattr(distance, 'value'):
                distance = distance.value
            vector_size = info.config.params.vectors.size
        except Exception as e:
            return {
                "success": True,
                "message": f"Collection not loaded: {str(e)}",
                "collection_name": COLLECTION_NAME,
                "points_count": 0,
                "status": "not_created",
                "points": []
            }

        # Scroll points to get payloads (up to 100 points)
        points_list = []
        if points_count > 0:
            points, _ = client.scroll(
                collection_name=COLLECTION_NAME,
                limit=100,
                with_payload=True,
                with_vectors=False
            )
            for p in points:
                points_list.append({
                    "id": p.id,
                    "payload": p.payload
                })

        return {
            "success": True,
            "collection_name": COLLECTION_NAME,
            "points_count": points_count,
            "status": str(status),
            "distance": str(distance),
            "vector_size": vector_size,
            "points": points_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load database points: {str(e)}")

@app.delete("/api/qdrant/document/{filename:path}")
async def delete_qdrant_document(filename: str):
    """
    Deletes all points associated with a specific filename from the Qdrant database,
    and removes that file from the BATCH_QUEUE to update the dashboard UI.
    """
    try:
        # 1. Delete points from Qdrant
        from backend.vector_db import delete_document
        deleted = delete_document(filename)
        
        # 2. Remove from BATCH_QUEUE
        from backend.ocr import BATCH_QUEUE
        to_delete = []
        for file_id, item in BATCH_QUEUE.items():
            if item.get("filename") == filename:
                to_delete.append(file_id)
        
        for file_id in to_delete:
            BATCH_QUEUE.pop(file_id, None)
            
        message = (
            f"Successfully deleted document '{filename}' from Qdrant and queue."
            if deleted else
            f"No matching points found in Qdrant for '{filename}'."
        )
        return {
            "success": deleted,
            "filename": filename,
            "removed_from_queue": len(to_delete) > 0,
            "message": message
        }
    except Exception as e:
        logger.error(f"Error in delete_qdrant_document endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


# ======================================================
# STATIC FILES SERVING (MAPPED TO THE TABBED SPA)
# ======================================================

frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    print(f"Warning: Frontend directory '{frontend_dir}' not found.")
