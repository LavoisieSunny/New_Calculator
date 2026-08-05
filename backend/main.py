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

from dotenv import load_dotenv
load_dotenv()

from backend.calculator import (
    router as calculator_router,
    CompensationRequest,
    get_multiplier,
    get_future_prospect,
    get_deduction,
)
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

    # Warm up PaddleOCR eagerly to verify device and load the models at startup
    try:
        logger.info("Warming up PaddleOCR singletons...")
        from backend.ocr import get_ocr_instance
        get_ocr_instance(lang="en")
        get_ocr_instance(lang="hi")
        logger.info("PaddleOCR warm-up complete (both 'en' and 'hi' loaded).")
    except Exception as e:
        logger.error(f"PaddleOCR warm-up failed (non-fatal): {str(e)}")

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
    case_session_id: str | None = None

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
        logger_results = await asyncio.to_thread(
            semantic_search, request.message, limit=3, case_type_filter=case_filter, case_session_id_filter=request.case_session_id
        )
        
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
    case_session_id: str | None = None
    
    # Validation context fields
    ocr_text: str | None = None
    parsed_fields: dict | None = None
    calculator_result: dict | None = None
    is_justify: bool = False
    history: list | None = None

def _smart_truncate_ocr_for_chat(ocr_full: str, question_str: str = "", head: int = 6000, tail: int = 8000) -> str:
    """
    Builds the OCR text block sent to the LLM for ordinary (non-justify,
    non-case-summary) chat questions.

    Old logic was a blind first-N + last-M character window, which silently
    dropped whatever fell in the middle of long documents (e.g. respondent
    party details on page 3-4 of a 20-page scan). Fix: keep head+tail, but
    also scan the omitted middle for legally-relevant anchor keywords and
    splice matching context back in.
    """
    import re as _re

    if not ocr_full:
        return ""
    if len(ocr_full) <= head + tail:
        return ocr_full

    head_block = ocr_full[:head]
    tail_block = ocr_full[-tail:]
    middle_start = head
    middle_end = len(ocr_full) - tail
    middle = ocr_full[middle_start:middle_end]

    anchor_keywords = [
        r"respondent", r"non[- ]?applicant", r"appellant", r"claimant",
        r"owner", r"driver", r"insur", r"vehicle", r"registration",
        r"section\s+\d", r"policy", r"licen[cs]e",
    ]
    if question_str:
        extra_terms = _re.findall(r"[A-Za-z]{4,}", question_str)
        anchor_keywords.extend(_re.escape(t) for t in extra_terms)

    pattern = _re.compile("|".join(anchor_keywords), _re.IGNORECASE)

    snippets = []
    seen_spans = []
    window = 700
    for m in pattern.finditer(middle):
        start = max(0, m.start() - window // 2)
        end = min(len(middle), m.end() + window // 2)
        if seen_spans and start <= seen_spans[-1][1] + 200:
            seen_spans[-1] = (seen_spans[-1][0], max(seen_spans[-1][1], end))
        else:
            seen_spans.append((start, end))
        if len(seen_spans) >= 6:
            break

    for (s, e) in seen_spans:
        snippets.append(middle[s:e].strip())

    anchored_middle = ("\n\n[...]\n\n".join(snippets)) if snippets else ""

    parts = [head_block]
    if anchored_middle:
        parts.append("[... omitted, except the following relevant passages found further into the document ...]")
        parts.append(anchored_middle)
    else:
        parts.append("[... middle pages omitted ...]")
    parts.append(tail_block)

    return "\n\n".join(parts)


def _parse_amount_or_none(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if s == "" or s.lower() in ("nil", "n/a", "na", "none", "null", "not found", "-"):
        return None
    s = s.replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").strip()
    s = s.rstrip("/-").strip()
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _pct_or_none(val):
    """Parse a percentage-like value (e.g. '40', '40%', 40.0) to a float number of percent, or None."""
    n = _parse_amount_or_none(val)
    if n is None:
        return None
    return n


def _income_head_formula(is_death, monthly_income, multiplier, future_prospect_pct, deduction_pct, disability_pct=None):
    """
    Recomputes the income-driven compensation head (Loss of Dependency for death,
    Future Income Loss for injury) using the SAME formula as backend/calculator.py,
    given an arbitrary combination of parameters. Used purely to quantify how much
    of a Rs. gap is attributable to a single parameter differing, by swapping that
    one parameter and holding the rest constant — never to invent a value.
    """
    monthly_income = monthly_income or 0.0
    multiplier = multiplier or 0.0
    if is_death:
        fp = (future_prospect_pct or 0.0) / 100.0
        ded = (deduction_pct or 0.0) / 100.0
        annual = monthly_income * 12.0 * (1.0 + fp)
        return annual * (1.0 - ded) * multiplier
    else:
        disability_pct = disability_pct or 0.0
        annual = monthly_income * 12.0
        return annual * (disability_pct / 100.0) * multiplier


def _attribute_income_head_difference(pf, cr, is_death, tribunal_amt, calc_amt, inferred):
    """
    Produces a quantified, non-hardcoded explanation for a Rs. gap on the income-driven
    head (Loss of Dependency / Future Income Loss) by decomposing the calculator's own
    formula parameter-by-parameter (multiplier, future-prospects %, deduction %) and
    checking each one against:
      1. What the tribunal itself is recorded as having applied (OCR-extracted
         tribunal_multiplier / tribunal_future_prospect_percentage / tribunal_deduction_percentage),
         if that was found in the judgment text, OR
      2. The statutory Sarla Verma / Pranay Sethi standard for this case's own
         age / dependents / marital status / employment-type inputs, if the tribunal's
         own figure was not separately stated.
    Every number used is either the calculator's own applied parameter, an OCR-extracted
    tribunal figure, or a value derived from a published statutory table indexed by this
    case's own inputs — nothing case-specific is invented.
    """
    try:
        monthly_income = float(pf.get("monthly_income") or 0)
    except (TypeError, ValueError):
        monthly_income = 0.0
    if monthly_income <= 0 or calc_amt is None or tribunal_amt is None:
        return None

    total_gap = tribunal_amt - calc_amt  # signed: negative => tribunal lower than calc
    if abs(total_gap) < 1:
        return None

    try:
        age = int(float(pf.get("age") or 30))
    except (TypeError, ValueError):
        age = 30

    calc_multiplier = cr.get("multiplier")
    try:
        calc_multiplier = float(calc_multiplier)
    except (TypeError, ValueError):
        calc_multiplier = get_multiplier(age)

    expected_multiplier = get_multiplier(age)

    params = []  # (name, calc_value, reference_value, reference_source, unit)

    # Multiplier — reference: tribunal's own stated multiplier if OCR-extracted, else statutory slab.
    trib_mult = _pct_or_none(pf.get("tribunal_multiplier"))
    if trib_mult is not None and abs(trib_mult - calc_multiplier) > 1e-6:
        params.append(("multiplier", calc_multiplier, trib_mult, "tribunal's own stated multiplier (found in judgment text)", ""))
    elif trib_mult is None and abs(expected_multiplier - calc_multiplier) > 1e-6:
        params.append(("multiplier", calc_multiplier, expected_multiplier,
                        f"statutory Sarla Verma age-slab multiplier for age {age} (tribunal's own figure not stated in judgment)", ""))

    if is_death:
        calc_fp = cr.get("future_prospect_percentage")
        try:
            calc_fp = float(calc_fp)
        except (TypeError, ValueError):
            calc_fp = 0.0
        calc_ded = cr.get("deduction_percentage")
        try:
            calc_ded = float(calc_ded)
        except (TypeError, ValueError):
            calc_ded = 0.0

        try:
            dependents = int(float(pf.get("dependents") or 0))
        except (TypeError, ValueError):
            dependents = 0
        marital_status = str(pf.get("marital_status") or "married")
        try:
            future_type = int(float(pf.get("future_type") or 2))
        except (TypeError, ValueError):
            future_type = 2
        expected_fp = round(get_future_prospect(age, future_type) * 100)
        expected_ded = round(get_deduction(dependents, marital_status) * 100)

        trib_fp = _pct_or_none(pf.get("tribunal_future_prospect_percentage"))
        if trib_fp is not None and abs(trib_fp - calc_fp) > 1e-6:
            params.append(("future-prospects %", calc_fp, trib_fp, "tribunal's own stated future-prospects % (found in judgment text)", "%"))
        elif trib_fp is None and abs(expected_fp - calc_fp) > 1e-6:
            params.append(("future-prospects %", calc_fp, expected_fp,
                            f"statutory Pranay Sethi future-prospects % for age {age} (tribunal's own figure not stated in judgment)", "%"))

        trib_ded = _pct_or_none(pf.get("tribunal_deduction_percentage"))
        if trib_ded is not None and abs(trib_ded - calc_ded) > 1e-6:
            params.append(("deduction for personal/living expenses %", calc_ded, trib_ded, "tribunal's own stated deduction % (found in judgment text)", "%"))
        elif trib_ded is None and abs(expected_ded - calc_ded) > 1e-6:
            params.append(("deduction for personal/living expenses %", calc_ded, expected_ded,
                            f"statutory Sarla Verma deduction % for {dependents} dependents / {marital_status} claimant "
                            f"(tribunal's own figure not stated in judgment)", "%"))

        base_kwargs = dict(is_death=True, monthly_income=monthly_income, multiplier=calc_multiplier,
                            future_prospect_pct=calc_fp, deduction_pct=calc_ded)
    else:
        base_kwargs = dict(is_death=False, monthly_income=monthly_income, multiplier=calc_multiplier,
                            future_prospect_pct=None, deduction_pct=None,
                            disability_pct=float(pf.get("disability") or 0))

    if not params:
        return None

    bullet_lines = []
    explained_total = 0.0
    for (name, calc_val, ref_val, ref_source, unit) in params:
        swapped_kwargs = dict(base_kwargs)
        key_map = {"multiplier": "multiplier", "future-prospects %": "future_prospect_pct",
                   "deduction for personal/living expenses %": "deduction_pct"}
        swapped_kwargs[key_map[name]] = ref_val
        recomputed = _income_head_formula(**swapped_kwargs)
        baseline = _income_head_formula(**base_kwargs)
        delta = recomputed - baseline  # effect of moving calc -> reference value
        explained_total += delta
        direction = "increases" if delta > 0 else "decreases"
        bullet_lines.append(
            f"  - {name}: calculator used {calc_val:g}{unit}, vs {ref_source}: {ref_val:g}{unit}. "
            f"Using the {ref_source.split(' (')[0]} instead of the calculator's value {direction} the head by "
            f"Rs. {abs(round(delta)):,.0f}."
        )

    abs_gap = abs(total_gap)
    abs_explained = abs(explained_total)
    coverage_pct = (abs_explained / abs_gap * 100.0) if abs_gap > 0 else 0.0

    header = (
        f"Quantified parameter attribution (derived from the calculator's own formula, not invented): "
        f"the tribunal figure differs from the calculator figure by Rs. {round(abs_gap):,.0f}. "
        f"Recomputing the formula with each parameter swapped individually gives:"
    )

    if coverage_pct >= 90.0 and coverage_pct <= 115.0:
        tail = (
            f"Together these parameter differences (net effect Rs. {round(abs_explained):,.0f}) are "
            f"sufficient to account for essentially the entire observed gap of Rs. {round(abs_gap):,.0f}."
        )
    elif coverage_pct > 115.0:
        tail = (
            f"Note: the net effect of these parameter differences alone (Rs. {round(abs_explained):,.0f}) is "
            f"LARGER than the actual observed gap (Rs. {round(abs_gap):,.0f}). This means these parameter "
            f"differences are partially offset by something else in the calculation not captured above "
            f"(e.g. a different income figure or rounding actually used by the tribunal) — the identified "
            f"parameters are still the dominant, evidenced driver of the divergence, but the net figure "
            f"should not be read as an exact reconciliation."
        )
    elif abs_explained < 1:
        tail = (
            "None of the parameters checked against the tribunal's own stated figures or the statutory "
            "standard differ meaningfully, so this gap is not traceable to multiplier, future-prospects %, "
            "or deduction % — it likely reflects the Tribunal's discretionary assessment of the evidence, "
            "or a head/component the calculator does not separately model."
        )
    else:
        tail = (
            f"These accounted-for parameter differences explain approximately Rs. {round(abs_explained):,.0f} "
            f"({coverage_pct:.0f}%) of the Rs. {round(abs_gap):,.0f} gap; the remaining "
            f"Rs. {round(abs_gap - abs_explained):,.0f} is not traceable to a specific parameter in the "
            f"record and likely reflects the Tribunal's discretionary assessment of the evidence, or a "
            f"head/component the calculator does not separately model."
        )

    note = "" if not inferred else (
        " (Note: the tribunal amount used for this comparison was itself inferred by subtraction — "
        "see the reconciliation note above — so this attribution explains the inferred figure, not a "
        "directly OCR-extracted one.)"
    )

    return header + "\n" + "\n".join(bullet_lines) + "\n" + tail + note


def _build_headwise_comparison(pf, cr, is_death, tribunal_total=None):
    if is_death:
        head_defs = [
            ("Loss of Dependency", pf.get("tribunal_loss_of_dependency"), cr.get("loss_of_dependency")),
            ("Loss of Consortium", pf.get("tribunal_consortium"), cr.get("consortium")),
            ("Funeral Expenses", pf.get("tribunal_funeral"), cr.get("funeral_expenses")),
            ("Loss of Estate", pf.get("tribunal_estate"), cr.get("loss_estate")),
        ]
    else:
        head_defs = [
            ("Medical Expenses", pf.get("tribunal_medical"), cr.get("medical_expenses")),
            ("Future Medical Expenses", pf.get("tribunal_future_medical"), cr.get("future_medical_expenses")),
            ("Pain & Suffering", pf.get("tribunal_pain_suffering"), cr.get("pain_and_suffering")),
            ("Transportation", pf.get("tribunal_transport"), cr.get("transportation")),
            ("Special Diet", pf.get("tribunal_special_diet"), cr.get("special_diet")),
            ("Attender Charges", pf.get("tribunal_attender"), cr.get("attender_charges")),
            ("Loss of (Future) Income", pf.get("tribunal_loss_of_income"),
             cr.get("future_income_loss") or cr.get("loss_of_income")),
        ]

    rows = []
    for label, tribunal_raw, calc_raw in head_defs:
        rows.append({
            "label": label,
            "tribunal_amount": _parse_amount_or_none(tribunal_raw),
            "calculator_amount": _parse_amount_or_none(calc_raw),
            "inferred": False,
            "reconciliation_note": None,
        })

    # ── STEP A: SUBTRACTION-BASED RECONCILIATION ──────────────────────────
    if tribunal_total is not None:
        known_rows = [r for r in rows if r["tribunal_amount"] is not None]
        missing_rows = [r for r in rows if r["tribunal_amount"] is None]
        if len(missing_rows) == 1 and len(known_rows) == len(rows) - 1:
            known_sum = sum(r["tribunal_amount"] for r in known_rows)
            inferred_amt = tribunal_total - known_sum
            if inferred_amt > 0:
                target = missing_rows[0]
                target["tribunal_amount"] = round(inferred_amt, 2)
                target["inferred"] = True
                other_labels = ", ".join(f"{r['label']} Rs. {r['tribunal_amount']:,.0f}" for r in known_rows)
                target["reconciliation_note"] = (
                    f"This figure was NOT separately stated in the OCR text for '{target['label']}'. "
                    f"It is arithmetically inferred: Tribunal Total (Rs. {tribunal_total:,.0f}) minus every "
                    f"other awarded head that IS stated in the judgment ({other_labels}) = "
                    f"Rs. {inferred_amt:,.0f}. Present this as 'Inferred by subtraction from the tribunal "
                    f"total', not as a figure literally printed in the judgment."
                )
        elif len(missing_rows) > 1:
            known_sum = sum(r["tribunal_amount"] for r in known_rows)
            shortfall = tribunal_total - known_sum
            if abs(shortfall) > 1:
                for r in missing_rows:
                    r["reconciliation_note"] = (
                        f"Not individually inferable — {len(missing_rows)} heads are simultaneously missing "
                        f"from the OCR text, so the combined shortfall of Rs. {shortfall:,.0f} "
                        f"(Tribunal Total minus every head that IS stated) cannot be split between them "
                        f"without more information. State this combined shortfall rather than guessing a "
                        f"per-head split."
                    )

    lines = []
    for r in rows:
        label = r["label"]
        tribunal_amt = r["tribunal_amount"]
        calc_amt = r["calculator_amount"]

        if tribunal_amt is None and (calc_amt is None or calc_amt == 0):
            status = "NOT_COMPARABLE"
            diff_text = "N/A — this head was neither found in the tribunal record nor computed by the calculator."
        elif tribunal_amt is None:
            status = "TRIBUNAL_AMOUNT_MISSING"
            diff_text = (
                f"N/A — the tribunal's figure for this head could not be located in the OCR text. "
                f"Calculator estimate only: Rs. {calc_amt:,.0f}. Do not invent a tribunal figure."
            )
            if r["reconciliation_note"]:
                diff_text += " " + r["reconciliation_note"]
        elif calc_amt is None:
            status = "CALCULATOR_AMOUNT_MISSING"
            diff_text = (
                f"N/A — the calculator has no value for this head (input left blank). "
                f"Tribunal figure only: Rs. {tribunal_amt:,.0f}."
            )
        else:
            diff = abs(round(calc_amt) - round(tribunal_amt))
            status = "INFERRED_MATCH" if (diff == 0 and r["inferred"]) else (
                "MATCH" if diff == 0 else ("CALC_HIGHER" if calc_amt > tribunal_amt else "TRIBUNAL_HIGHER")
            )
            diff_text = f"Rs. {diff:,.0f}" if diff != 0 else "Rs. 0 (no variance)"

        r["status"] = status

        attribution = None
        if tribunal_amt is not None and calc_amt is not None and abs(round(calc_amt) - round(tribunal_amt)) > 0:
            if label in ("Loss of Dependency", "Loss of (Future) Income"):
                attribution = _attribute_income_head_difference(pf, cr, is_death, tribunal_amt, calc_amt, r["inferred"])
        r["attribution"] = attribution

        tribunal_disp = (
            (f"Rs. {tribunal_amt:,.0f} (INFERRED by subtraction — not literally printed in the judgment)"
             if r["inferred"] else f"Rs. {tribunal_amt:,.0f}")
            if tribunal_amt is not None else "Not stated in judgment / not extracted"
        )
        calc_disp = f"Rs. {calc_amt:,.0f}" if calc_amt is not None else "Not computed (input blank)"
        line = (
            f"- {label}:\n"
            f"    Tribunal (provided) amount: {tribunal_disp}\n"
            f"    Calculator (formula) amount: {calc_disp}\n"
            f"    Absolute difference (modulus): {diff_text}"
        )
        if r["inferred"] and r["reconciliation_note"]:
            line += f"\n    Reconciliation basis: {r['reconciliation_note']}"
        if attribution:
            line += f"\n    {attribution}"
        lines.append(line)

    text_block = "\n".join(lines)
    return text_block, rows


def _build_legal_reference_standards(pf, cr, is_death):
    try:
        age = int(float(pf.get("age") or 30))
    except (TypeError, ValueError):
        age = 30

    expected_multiplier = get_multiplier(age)

    lines = [
        f"Claimant/Deceased age used in workstation: {age} years.",
        f"Expected multiplier per Sarla Verma / Pranay Sethi age-slab table for age {age}: {expected_multiplier}.",
        f"Calculator's applied multiplier: {cr.get('multiplier', 'Unknown')}.",
    ]

    if is_death:
        try:
            dependents = int(float(pf.get("dependents") or 0))
        except (TypeError, ValueError):
            dependents = 0
        marital_status = str(pf.get("marital_status") or "married")
        try:
            future_type = int(float(pf.get("future_type") or 2))
        except (TypeError, ValueError):
            future_type = 2

        expected_future_pct = round(get_future_prospect(age, future_type) * 100)
        expected_deduction_ratio = get_deduction(dependents, marital_status)
        expected_deduction_pct = round(expected_deduction_ratio * 100)

        lines.extend([
            f"Dependents in workstation: {dependents}; Marital status: {marital_status}.",
            f"Expected future-prospects % per Pranay Sethi (age {age}, "
            f"{'permanent job' if future_type == 1 else 'self-employed/fixed wage'} assumption): "
            f"{expected_future_pct}%.",
            f"Calculator's applied future-prospects %: {cr.get('future_prospect_percentage', 'Unknown')}.",
            f"Expected deduction for personal/living expenses (Sarla Verma table, "
            f"{dependents} dependents, {marital_status}): {expected_deduction_pct}% "
            f"({'1/2' if abs(expected_deduction_ratio - 0.5) < 1e-6 else ('1/3' if abs(expected_deduction_ratio - 1/3) < 1e-6 else ('1/4' if abs(expected_deduction_ratio - 0.25) < 1e-6 else '1/5'))}).",
            f"Calculator's applied deduction %: {cr.get('deduction_percentage', 'Unknown')}.",
        ])

    lines.append(
        "IMPORTANT: These are the STANDARD/EXPECTED values derived from this case's own age, "
        "dependents, marital status and employment-type inputs — they are NOT necessarily what the "
        "tribunal actually applied. Cross-check the OCR text for the multiplier/percentage the tribunal "
        "actually used before citing a mismatch. If the tribunal's own figures are not stated in the "
        "judgment text, say so rather than assuming they match either value above."
    )

    return "\n".join(lines)


def is_case_summary_query(query: str) -> bool:

    if not query:
        return False
    q = query.lower().strip()
    
    summary_phrases = [
        "summarize the case", "summarise the case", "summarize case", "summarise case",
        "explain me about the case", "explain about the case", "explain the case", "explain this case", "explain case",
        "tell me about the case", "tell about the case", "tell me about case", "tell case",
        "give summary", "case summary", "summary of the case", "summary of case",
        "overview of the case", "overview of case", "case overview",
        "details of the case", "case details", "what is this case about",
        "what is the case about", "about the case", "brief of the case", "brief the case",
        "case background", "background of the case", "case info", "case information"
    ]
    if any(phrase in q for phrase in summary_phrases):
        return True
        
    import re
    if re.search(r'\b(summarize|summarise|explain|overview|brief|tell\s+me|details)\b.*\bcase\b', q):
        return True
    if re.search(r'\bcase\b.*\b(summary|overview|details|explanation|background)\b', q):
        return True
        
    return False

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
            
    is_summary_q = is_case_summary_query(question_str)
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
            asyncio.to_thread(semantic_search_rag, query="compensation awarded amount medical expenses pain suffering transport attender loss of income heads", limit=4, filename_filter=filename_filter, case_session_id_filter=request.case_session_id),
            asyncio.to_thread(semantic_search_rag, query="grounds of appeal enhancement disfiguration ear loss marriage prospects disability", limit=3, filename_filter=filename_filter, case_session_id_filter=request.case_session_id),
        )
        # Deduplicate by chunk text and merge
        seen_texts = set()
        search_results = []
        for r in results_award + results_grounds:
            t = r.get("text", "")[:100]
            if t not in seen_texts:
                seen_texts.add(t)
                search_results.append(r)
    elif is_summary_q:
        results_court, results_grounds = await asyncio.gather(
            asyncio.to_thread(semantic_search_rag, query="court tribunal appeal case number appellant respondents claim award", limit=4, filename_filter=filename_filter, case_session_id_filter=request.case_session_id),
            asyncio.to_thread(semantic_search_rag, query="grounds of appeal relief prayer enhancement exoneration liability arguments", limit=4, filename_filter=filename_filter, case_session_id_filter=request.case_session_id),
        )
        seen_texts = set()
        search_results = []
        for r in results_court + results_grounds:
            t = r.get("text", "")[:100]
            if t not in seen_texts:
                seen_texts.add(t)
                search_results.append(r)
    else:
        search_results = await asyncio.to_thread(
            semantic_search_rag,
            query=question_str,
            limit=5,
            filename_filter=filename_filter,
            case_session_id_filter=request.case_session_id
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

    # Retrieve relevant supporting documents chunks if case_session_id is active
    supporting_context = ""
    if request.case_session_id:
        supporting_results = await asyncio.to_thread(
            semantic_search_rag,
            query=question_str,
            limit=3,
            case_session_id_filter=request.case_session_id,
            doc_type_filter=["lower_court", "hospital_record", "other"]
        )
        if supporting_results:
            supp_blocks = []
            for res in supporting_results:
                text_block = res.get("text", "").strip()
                filename = res.get("filename", "unknown")
                doc_type = res.get("metadata", {}).get("doc_type", "supporting_doc")
                supp_blocks.append(f"[Supporting Doc ({doc_type}) - {filename}]:\n{text_block}")
            supporting_context = "\n\n".join(supp_blocks)
    
    # 3. Incorporate Workstation Context (Phase 8 state integration)
    chunks_combined = retrieved_chunks
    if supporting_context:
        chunks_combined = chunks_combined + "\n\n=== SUPPORTING DOCUMENTS CONTEXT ===\n\n" + supporting_context
    workstation_blocks = []
    if request.ocr_text:
        if request.is_justify or is_summary_q:
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
            ocr_for_llm = _smart_truncate_ocr_for_chat(ocr_full, question_str)
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

        # ── PRECOMPUTE PER-HEAD TRIBUNAL vs CALCULATOR COMPARISON (Python, never the LLM) ──
        headwise_comparison_block, headwise_rows = _build_headwise_comparison(
            pf, cr, is_death, tribunal_total=(tribunal_total if tribunal_total else None)
        )

        # ── PRECOMPUTE THE STATUTORY REFERENCE STANDARDS FOR THIS CASE'S OWN INPUTS ──
        legal_reference_block = _build_legal_reference_standards(pf, cr, is_death)

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
            f"\n=== PRECOMPUTED HEAD-WISE COMPARISON (Python-computed — copy these figures EXACTLY, "
            f"never recompute or alter them) ===\n"
            f"{headwise_comparison_block}\n"
            f"===\n"
            f"\n=== STATUTORY REFERENCE STANDARDS FOR THIS CASE (Sarla Verma / Pranay Sethi tables, "
            f"computed from this case's own age/dependents/marital-status/employment-type inputs) ===\n"
            f"{legal_reference_block}\n"
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
            "The tribunal amount, calculator amount, and absolute (modulus) difference for every "
            "head have ALREADY been computed in Python — see '=== PRECOMPUTED HEAD-WISE COMPARISON ===' "
            "above. You MUST reuse those exact figures verbatim. NEVER perform the subtraction yourself "
            "and NEVER print a negative difference — the block already gives you the absolute value.\n"
            "For each head, classify using the PRECOMPUTED status field:\n"
            "  TRIBUNAL_HIGHER → tribunal amount is more than the calculator estimate → label 'High'\n"
            "  CALC_HIGHER → tribunal amount is less than the calculator estimate → label 'Low'\n"
            "  MATCH → identical → label 'Adequate'\n"
            "  TRIBUNAL_AMOUNT_MISSING / CALCULATOR_AMOUNT_MISSING / NOT_COMPARABLE → label 'N/A'\n"
            "If claimant has no income (minor, student, homemaker, unemployed):\n"
            "  Income/dependency head → N/A (state reason, not 'no documentation')\n"
            "  Do NOT generate income-related root cause bullets for this claimant.\n\n"

            "STEP 5 — EXPLAIN EVERY NON-ZERO DIFFERENCE (this is the core deliverable).\n"
            "For every head where the precomputed absolute difference is greater than Rs. 0, you MUST\n"
            "give a specific, evidence-grounded reason the two figures diverge. Build the explanation\n"
            "using ONLY the following permitted sources, in this STRICT order of preference — always\n"
            "prefer the earliest source that is available for that head, and reuse its numbers verbatim:\n"
            "  (a) RECONCILIATION BASIS — if the head's row in '=== PRECOMPUTED HEAD-WISE COMPARISON ==='\n"
            "      carries a 'Reconciliation basis:' line, that head's tribunal figure was not literally\n"
            "      printed in the judgment but was arithmetically derived by subtracting every other known\n"
            "      awarded head from the tribunal's grand total. Report it exactly as 'Inferred by\n"
            "      subtraction: Rs. X' (never as if OCR found it directly) and copy the arithmetic shown.\n"
            "  (b) QUANTIFIED PARAMETER ATTRIBUTION — if the head's row carries a 'Quantified parameter\n"
            "      attribution' line, this is a Python-computed, formula-based decomposition of the gap\n"
            "      into the exact parameters (multiplier / future-prospects % / deduction %) that differ\n"
            "      between the calculator and either (i) the tribunal's own OCR-extracted figure for that\n"
            "      parameter, or (ii) the statutory Sarla Verma / Pranay Sethi standard for this case's own\n"
            "      age/dependents/marital-status/employment-type. Copy this block's bullets and its Rs.\n"
            "      figures verbatim — do not recompute, round differently, or drop the 'remaining portion\n"
            "      not traceable' sentence if present.\n"
            "  (c) An explicit statement in the OCR text of what evidence the tribunal accepted or\n"
            "      rejected for that head (e.g. no medical bills produced, disability certificate not\n"
            "      proved, income affidavit disbelieved, no attendant/caretaker evidence on record).\n"
            "  (d) An explicit ground of appeal (from STEP 2) disputing that head's quantum or basis.\n"
            "  (e) The calculator head simply was not claimed/proved before the tribunal at all (state\n"
            "      this only if the OCR text supports it, e.g. the head is entirely absent from the\n"
            "      award table).\n"
            "Sources (a) and (b) are pre-computed in Python specifically so you are not left guessing —\n"
            "use them whenever present, even if they only explain part of the gap; in that case also\n"
            "state the unexplained remainder using the language already provided in that block.\n"
            "If NONE of (a)-(e) is available for a head, you MUST write exactly: 'No specific reason is\n"
            "stated in the tribunal record for this variance; it likely reflects the Tribunal's\n"
            "discretionary assessment of the evidence on facts the calculator's standard formula does not\n"
            "capture.' Do NOT invent a case-specific reason that is not supported by the text — a generic\n"
            "but honest explanation is required over a fabricated specific one, and it should now be rare\n"
            "given (a) and (b) are computed for every head that qualifies.\n\n"

            "STEP 6 — LEGAL CAUTION.\n"
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
            "For EVERY head listed in '=== PRECOMPUTED HEAD-WISE COMPARISON ===' above, output exactly\n"
            "this shape (copy the Rs. figures and the difference verbatim from that block):\n"
            "- [Head Name]\n"
            "  Tribunal (provided) amount: Rs.[tribunal amount, or 'Not stated in judgment / not extracted']\n"
            "  Calculator (formula) amount: Rs.[calculator amount, or 'Not computed (input blank)']\n"
            "  Absolute difference: Rs.[precomputed modulus difference, or 'N/A' with the reason given "
            "in the precomputed block]\n"
            "  Classification: [Low/Adequate/High/N/A]\n"
            "  Why tribunal fixed this amount: [evidence accepted/rejected, from OCR — if unknown, say "
            "'Not explicitly stated in the judgment.']\n"
            "  Explanation of difference: [Follow STEP 5 exactly. Omit this line entirely if the "
            "absolute difference is Rs. 0.]\n\n"

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

    case_summary_instruction = (
        "\n=== CASE SUMMARY & EXPLANATION QUERY INSTRUCTIONS ===\n"
        "The user is asking to summarize, explain, or tell about the case.\n"
        "You MUST respond with a clean, structured analysis strictly using the following bold sections and bullet points:\n\n"
        "**Court & Case Details:**\n"
        "- **Court / Tribunal:** [Court or Tribunal name, e.g. High Court of M.P. / MACT Tribunal]\n"
        "- **Case / Appeal No.:** [Case or Appeal number from PDF, e.g. M.A. No. 2196/2025]\n"
        "- **Appellant:** [Appellant name/party, e.g. Claimant or Insurance Company]\n"
        "- **Respondents:** [List respondent parties, e.g. Driver, Owner, Insurance Company]\n\n"
        "**Case Type & Nature of Dispute:**\n"
        "- **Case Type:** [Injury / Death]\n"
        "- **Nature of Appeal:** [Claimant seeking enhancement of compensation / Insurer seeking reduction or exoneration]\n\n"
        "**Case Overview:**\n"
        "[A concise 2-3 sentence overview explaining the accident event, nature of injuries/death, tribunal decision, and core dispute.]\n\n"
        "**Key Grounds of Appeal (in Points):**\n"
        "- [Point 1: Main ground disputing liability, policy validity, or licence/permit breach]\n"
        "- [Point 2: Main ground disputing quantum, income assessment, or multiplier]\n"
        "- [Point 3: Main ground regarding missed heads, disfigurement, or pain & suffering]\n"
        "- [Point 4: Main ground regarding interest rate or calculation error]\n\n"
        "**Relief / Prayer Sought (in Points):**\n"
        "- [Point 1: Primary prayer requested, e.g. setting aside tribunal award or total exoneration of insurer]\n"
        "- [Point 2: Financial enhancement or reduction amount requested]\n"
        "- [Point 3: Interest rate or costs requested]\n\n"
        "**Compensation & Key Parameters:**\n"
        "- **Awarded Compensation:** ₹[Amount awarded from OCR text]\n"
        "- **Claim Amount / Enhancement Sought:** ₹[Claimed amount or Enhancement sought]\n"
        "- **Key Parameters:** [Age, Monthly Income, Disability % (if injury) or Dependents (if death)]\n"
    )

    system_instruction = (
        "You are a Motor Accident Claims Tribunal legal assistant.\n\n"
        "=== STRICTOR GROUNDING INSTRUCTIONS ===\n"
        "1. Use ONLY the supplied context (Retrieved Precedents and active Workstation details).\n"
        "2. Do NOT invent or hallucinate legal facts, precedents, or claims metrics.\n"
        "3. If the context does not contain the answer, clearly state that the information is missing.\n\n"
        "=== FACTUAL QUESTIONS ABOUT THE DOCUMENT (STRICT RULE) ===\n"
        "When the user asks what the PDF/document/judgment states, mentions, shows, or contains\n"
        "(e.g. 'what disability percentage is mentioned', 'what does the judgment say about X',\n"
        "'what age is given'), you MUST base your answer ONLY on the text under\n"
        "'[Current PDF Workstation OCR Text]' and the '=== RETRIEVED PRECEDENTS ===' chunks below --\n"
        "i.e. the actual text extracted from the PDF.\n"
        "You are FORBIDDEN from answering such questions using the\n"
        "'[Current PDF Workstation Parsed Fields]' block, even if it contains a number that looks\n"
        "relevant. That block only reflects whatever is currently typed into the calculator form on\n"
        "screen -- it may be blank, auto-filled by an imperfect heuristic, or hand-edited by the user.\n"
        "It is NOT proof that a number appears anywhere in the document, and you must never say\n"
        "phrases like 'this can be found in the parsed fields section' or 'under the disability field'\n"
        "-- those phrases describe the calculator form, not the document.\n"
        "Before stating any number, date, or name as a fact from the document, confirm it literally\n"
        "appears in the OCR text or retrieved context above. If it does not appear there, respond\n"
        "exactly: 'This is not explicitly mentioned in the uploaded document.'\n\n"
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
    elif is_summary_q:
        system_instruction += f"\n{case_summary_instruction}"

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
