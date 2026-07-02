# # backend/llm_client.py
# # backend/llm_client.py
# import json
# import logging
# import urllib.request
# import urllib.error
# import re
# from datetime import datetime

# from config.llm import LLM_PROVIDER, LLM_MODEL_NAME, LLM_API_KEY, LLM_API_ENDPOINT

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger("LLMClient")

# _MONTHS = {
#     "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
#     "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
#     "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
#     "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
# }


# def normalize_date_to_ddmmyyyy(raw_value):
#     """
#     Best-effort conversion of ANY human/LLM-supplied date string into a
#     strict 'DD-MM-YYYY' string (the format parser_heuristics.py, the
#     calculator, and the frontend's date converter all expect).

#     The system prompt *asks* the LLM to return DD-MM-YYYY, but local models
#     (Ollama/qwen etc.) frequently ignore that instruction and return
#     "10/04/2023", "2023-04-10", "10 April 2023", "10-Apr-2023", etc.
#     The frontend feeds this value into an <input type="date">, which the
#     browser silently rejects (leaving it blank) unless it converts cleanly
#     to "YYYY-MM-DD" — so an unnormalized date from the LLM is the single
#     biggest cause of "date fields not autofilling" after AI extraction.

#     Returns the original value unchanged (never raises) if it cannot be
#     confidently parsed as a date, so callers stay safe on unexpected input.
#     """
#     if raw_value is None:
#         return raw_value
#     val = str(raw_value).strip()
#     if not val:
#         return raw_value

#     # 1) Purely numeric, separator-delimited dates: DD-MM-YYYY, DD/MM/YYYY,
#     #    DD.MM.YYYY, or the ISO-ish YYYY-MM-DD / YYYY/MM/DD variants.
#     m = re.match(r'^(\d{1,4})[\-/\.](\d{1,2})[\-/\.](\d{1,4})$', val)
#     if m:
#         a, b, c = m.group(1), m.group(2), m.group(3)
#         try:
#             if len(a) == 4:  # YYYY-MM-DD style
#                 year, month, day = int(a), int(b), int(c)
#             else:  # DD-MM-YYYY style (day-first, standard in Indian legal docs)
#                 day, month, year = int(a), int(b), int(c)
#             datetime(year, month, day)  # validates the combination
#             return f"{day:02d}-{month:02d}-{year}"
#         except (ValueError, TypeError):
#             pass

#     # 2) Textual month dates: "10 April 2023", "10th April, 2023",
#     #    "April 10 2023", "10-Apr-2023", "Apr 10, 2023".
#     text = val.lower().replace(",", " ")
#     text = re.sub(r'(\d)(st|nd|rd|th)\b', r'\1', text)  # strip ordinal suffixes
#     tokens = [t for t in re.split(r'[\s\-/]+', text.strip()) if t]
#     day = month = year = None
#     for tok in tokens:
#         if tok in _MONTHS:
#             month = _MONTHS[tok]
#         elif re.fullmatch(r'\d{4}', tok):
#             year = int(tok)
#         elif re.fullmatch(r'\d{1,2}', tok) and day is None:
#             day = int(tok)
#     if day and month and year:
#         try:
#             datetime(year, month, day)
#             return f"{day:02d}-{month:02d}-{year}"
#         except (ValueError, TypeError):
#             pass

#     # Could not confidently parse — leave untouched rather than risk
#     # corrupting a legitimate value we didn't anticipate the shape of.
#     return raw_value


# def validate_ollama_setup() -> dict:
#     import urllib.request
#     import json
#     base_url = LLM_API_ENDPOINT if LLM_API_ENDPOINT else "http://localhost:11434"
#     url = f"{base_url.rstrip('/')}/api/tags"
#     stats = {
#         "connected": False,
#         "llm_model_available": False,
#         "embedding_model_available": False,
#         "models_found": []
#     }
#     logger.info(f"Validating Ollama connection at {base_url}...")
#     try:
#         req = urllib.request.Request(url, method="GET")
#         with urllib.request.urlopen(req, timeout=5.0) as response:
#             res_json = json.loads(response.read().decode("utf-8"))
#             stats["connected"] = True
            
#             # Parse models list
#             models = res_json.get("models", [])
#             for m in models:
#                 name = m.get("name", "")
#                 stats["models_found"].append(name)
                
#             # Verify LLM Model and Embedding Model availability
#             for model_name in stats["models_found"]:
#                 if "qwen2.5:14b" in model_name or LLM_MODEL_NAME in model_name:
#                     stats["llm_model_available"] = True
#                 if "nomic-embed-text" in model_name:
#                     stats["embedding_model_available"] = True
                    
#             logger.info(f"Ollama server is ONLINE at {base_url}. Models found: {stats['models_found']}")
#             if not stats["llm_model_available"]:
#                 logger.warning(f"Ollama model '{LLM_MODEL_NAME}' is missing!")
#             if not stats["embedding_model_available"]:
#                 logger.warning("Ollama embedding model 'nomic-embed-text' is missing!")
#     except Exception as e:
#         logger.error(f"Ollama startup connection failed at {base_url}: {str(e)}")
#     return stats

# def generate_response(prompt: str, system_instruction: str = None) -> str:
#     logger.info(f"Generating LLM response using provider '{LLM_PROVIDER}', model '{LLM_MODEL_NAME}'")
#     final_prompt = prompt
#     if system_instruction:
#         final_prompt = f"System Instruction:\n{system_instruction}\n\nUser Question:\n{prompt}"
#     try:
#         if LLM_PROVIDER == "gemini":
#             url = f"https://generativelanguage.googleapis.com/v1beta/models/{LLM_MODEL_NAME}:generateContent?key={LLM_API_KEY}"
#             headers = {"Content-Type": "application/json"}
#             payload = {"contents": [{"parts": [{"text": final_prompt}]}]}
#             if system_instruction:
#                 payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
#                 payload["contents"][0]["parts"][0]["text"] = prompt
#             req_body = json.dumps(payload).encode("utf-8")
#         elif LLM_PROVIDER == "ollama":
#             if "v1" in LLM_API_ENDPOINT:
#                 url = f"{LLM_API_ENDPOINT.rstrip('/')}/chat/completions"
#                 messages = []
#                 if system_instruction:
#                     messages.append({"role": "system", "content": system_instruction})
#                 messages.append({"role": "user", "content": prompt})
#                 payload = {"model": LLM_MODEL_NAME, "messages": messages, "temperature": 0.2}
#             else:
#                 url = f"{LLM_API_ENDPOINT.rstrip('/')}/api/chat"
#                 messages = []
#                 if system_instruction:
#                     messages.append({"role": "system", "content": system_instruction})
#                 messages.append({"role": "user", "content": prompt})
#                 payload = {"model": LLM_MODEL_NAME, "messages": messages, "stream": False, "options": {"temperature": 0.2}}
#             headers = {"Content-Type": "application/json"}
#             req_body = json.dumps(payload).encode("utf-8")
#         else:
#             url = f"{LLM_API_ENDPOINT.rstrip('/')}/chat/completions"
#             headers = {"Content-Type": "application/json"}
#             if LLM_API_KEY:
#                 headers["Authorization"] = f"Bearer {LLM_API_KEY}"
#             messages = []
#             if system_instruction:
#                 messages.append({"role": "system", "content": system_instruction})
#             messages.append({"role": "user", "content": prompt})
#             payload = {"model": LLM_MODEL_NAME, "messages": messages, "temperature": 0.2}
#             req_body = json.dumps(payload).encode("utf-8")

#         req = urllib.request.Request(url, data=req_body, headers=headers, method="POST")
#         with urllib.request.urlopen(req, timeout=300.0) as response:
#             res_body = response.read().decode("utf-8")
#             res_json = json.loads(res_body)
#             if LLM_PROVIDER == "gemini":
#                 candidates = res_json.get("candidates", [])
#                 if candidates:
#                     parts = candidates[0].get("content", {}).get("parts", [])
#                     if parts:
#                         return parts[0].get("text", "").strip()
#                 return ""
#             else:
#                 choices = res_json.get("choices", [])
#                 if choices:
#                     return choices[0].get("message", {}).get("content", "").strip()
#                 if "message" in res_json and "content" in res_json["message"]:
#                     return res_json["message"]["content"].strip()
#                 return ""
#     except urllib.error.HTTPError as he:
#         err_msg = he.read().decode("utf-8") if he.fp else str(he)
#         logger.error(f"LLM API HTTP Error ({he.code}): {err_msg}")
#         return f"Error connecting to LLM server: {he.reason}"
#     except Exception as e:
#         logger.error(f"Failed to generate LLM response: {str(e)}")
#         return f"Error communicating with LLM client: {str(e)}"

# def classify_case_type_by_ocr_text(ocr_text: str) -> str:
#     text_lower = ocr_text.lower()
#     injury_keywords = ["injury", "disability", "permanent disability", "partial disability", "bodily injury", "enhancement", "claimant injury"]
#     death_keywords = ["death", "deceased", "fatal", "died", "legal heirs", "widow", "death claim"]
#     injury_count = sum(text_lower.count(kw) for kw in injury_keywords)
#     death_count = sum(text_lower.count(kw) for kw in death_keywords)
#     logger.info(f"OCR case type keyword count: Injury = {injury_count}, Death = {death_count}")
#     if injury_count > death_count and injury_count >= 1:
#         return "injury"
#     elif death_count > injury_count and death_count >= 1:
#         return "death"
#     elif injury_count == death_count and injury_count >= 1:
#         injury_weight = sum(text_lower.count(kw) * 2 for kw in ["permanent disability", "partial disability", "bodily injury", "claimant injury"])
#         death_weight = sum(text_lower.count(kw) * 2 for kw in ["deceased", "legal heirs", "death claim", "widow"])
#         if injury_weight > death_weight:
#             return "injury"
#         elif death_weight > injury_weight:
#             return "death"
#     return None

# def _strip_devanagari_lines(text: str, threshold: float = 0.5) -> str:
#     """Remove lines that are predominantly Devanagari so LLM only sees English content."""
#     kept = []
#     for line in text.splitlines():
#         alpha = [ch for ch in line if ch.isalpha()]
#         if not alpha:
#             kept.append(line)
#             continue
#         deva = sum(1 for ch in alpha if '\u0900' <= ch <= '\u097F')
#         if (deva / len(alpha)) < threshold:
#             kept.append(line)
#     return "\n".join(kept)


# def extract_smart_context_for_llm(raw_ocr_text: str) -> str:
#     # Strip predominantly Hindi/Devanagari lines so the LLM only processes English text.
#     # Hindi award paragraphs cause the LLM to pick wrong values for English fields.
#     raw_ocr_text = _strip_devanagari_lines(raw_ocr_text)
#     if len(raw_ocr_text) <= 30000:
#         return raw_ocr_text
#     front_context = raw_ocr_text[:12000]
#     remainder_text = raw_ocr_text[12000:]
#     lines = remainder_text.split("\n")
#     high_value_keywords = [
#         "compensation", "multiplier", "dependency", "consortium",
#         "funeral", "monthly income", "disability", "earning", "quantum",
#         "award", "rs.", "rupees", "attender", "medical", "pain",
#         "future prospect", "interest", "loss of", "notional", "deduction"
#     ]
#     selected_chunks = []
#     i = 0
#     n = len(lines)
#     while i < n:
#         line_lower = lines[i].lower()
#         if any(kw in line_lower for kw in high_value_keywords):
#             start = max(0, i - 1)
#             end = min(n, i + 3)
#             chunk = "\n".join(lines[start:end])
#             selected_chunks.append(chunk)
#             i = end
#         else:
#             i += 1
#     selected_text = "\n\n... [Section Extract] ...\n\n".join(selected_chunks)
#     if len(selected_text) > 25000:
#         selected_text = selected_text[:25000] + "\n\n... [Truncated] ..."
#     end_context = raw_ocr_text[-8000:]

#     # For all cases, unconditionally extract and merge Cause Title, Prayer, and Grounds
#     extra_case_context = ""
#     try:
#         # Segment text into pages
#         pages_list = []
#         current_page_num = 1
#         current_page_lines = []
#         text_lines = raw_ocr_text.split("\n")
#         for line in text_lines:
#             line_strip = line.strip()
#             if line_strip.startswith("--- PAGE"):
#                 if current_page_lines:
#                     pages_list.append({
#                         "page_number": current_page_num,
#                         "lines": current_page_lines,
#                         "text": "\n".join(current_page_lines)
#                     })
#                 m = re.search(r'PAGE\s+(\d+)', line_strip, re.IGNORECASE)
#                 if m:
#                     current_page_num = int(m.group(1))
#                 current_page_lines = []
#             else:
#                 current_page_lines.append(line)
#         if current_page_lines or not pages_list:
#             pages_list.append({
#                 "page_number": current_page_num,
#                 "lines": current_page_lines,
#                 "text": "\n".join(current_page_lines)
#             })

#         from backend.parser_heuristics import detect_document_sections
#         sections_metadata = detect_document_sections(raw_ocr_text, pages_list)

#         claimant_sec = sections_metadata.get("claimant_section", {}).get("content", "").strip()
#         relief_sec = sections_metadata.get("relief_section", {}).get("content", "").strip()
#         grounds_sec = sections_metadata.get("grounds_section", {}).get("content", "").strip()

#         case_parts = []
#         if claimant_sec:
#             claimant_sec_trunc = claimant_sec if len(claimant_sec) <= 8000 else claimant_sec[:8000] + "\n... [Truncated Claimant Section] ..."
#             case_parts.append(f"=== CAUSE TITLE / CLAIMANT SECTION ===\n{claimant_sec_trunc}")
#         if relief_sec:
#             relief_sec_trunc = relief_sec if len(relief_sec) <= 8000 else relief_sec[:8000] + "\n... [Truncated Relief Section] ..."
#             case_parts.append(f"=== PRAYER / RELIEF CLAIMS SECTION ===\n{relief_sec_trunc}")
#         if grounds_sec:
#             grounds_sec_trunc = grounds_sec if len(grounds_sec) <= 8000 else grounds_sec[:8000] + "\n... [Truncated Grounds Section] ..."
#             case_parts.append(f"=== GROUNDS OF APPEAL SECTION ===\n{grounds_sec_trunc}")

#         if case_parts:
#             extra_case_context = "\n\n".join(case_parts)
#     except Exception as ex:
#         logger.error(f"Failed to extract case-specific context sections: {str(ex)}")

#     if extra_case_context:
#         return (
#             f"=== KEY CASE SECTIONS (CAUSE TITLE, PRAYER/RELIEF, GROUNDS OF APPEAL) ===\n\n"
#             f"{extra_case_context}\n\n"
#             f"=== FRONT PAGE METADATA ===\n\n"
#             f"{front_context}\n\n"
#             f"=== RELEVANT QUANTUM & COMPENSATION EXTRACTS ===\n\n"
#             f"{selected_text}\n\n"
#             f"=== FINAL JUDGMENT AWARD SECTIONS ===\n\n"
#             f"{end_context}"
#         )

#     return (
#         f"{front_context}\n\n"
#         f"=== RELEVANT QUANTUM & COMPENSATION EXTRACTS ===\n\n"
#         f"{selected_text}\n\n"
#         f"=== FINAL JUDGMENT AWARD SECTIONS ===\n\n"
#         f"{end_context}"
#     )

# def ai_data_recovery(raw_ocr_text: str) -> dict:
#     """
#     Invokes the LLM to parse raw OCR text and extract ALL legal claims fields
#     for both injury and death cases.
#     """
#     system_instruction = (
#         "You are an expert legal data extraction engine specializing in Indian Motor Accident Claims Tribunal (MACT) judgments.\n"
#         "Analyze the provided raw OCR text and extract ALL compensation parameters for both injury and death cases.\n"
#         "Return ONLY a clean valid JSON object. Every key maps to {\"value\": ..., \"confidence\": 0.0-1.0}.\n"
#         "Use null for value and 0.0 for confidence if a field is not found.\n"
#         "Do NOT write preamble, explanation, markdown fences, or comments. Return only the JSON.\n\n"

#         "Extract ALL of these fields:\n\n"

#         "IDENTITY FIELDS:\n"
#         "- case_type: 'injury' or 'death'\n"
#         "- claimant_name: full name of claimant/petitioner\n"
#         "- deceased_name: full name of the deceased (only for death cases)\n"
#         "- claimant_relationship_type: relationship of claimant to deceased e.g. 'Wife', 'Son', 'Mother' (only for death cases)\n"
#         "- father_name: father or husband name\n"
#         "- spouse_name: spouse name if mentioned\n"
#         "- dob: date of birth as DD-MM-YYYY\n"
#         "- age: integer age at time of accident\n"
#         "- occupation: job/profession of claimant or deceased\n"
#         "- monthly_income: monthly income as float (convert annual to monthly if needed; use notional if stated)\n"
#         "- dependents: number of dependents as integer\n"
#         "- marital_status: 'married', 'unmarried', or 'widowed'\n"
#         "- accident_date: DD-MM-YYYY\n"
#         "- accident_place: full location string\n"
#         "- vehicle_number: vehicle registration number\n"
#         "- insurance_company: name of insurance company\n"
#         "- fir_number: FIR/complaint number\n"
#         "- case_number: court case/petition number\n"
#         "- court_name: name of the tribunal/court\n"
#         "- judge_name: name of the judge\n"
#         "- decision_date: date of judgment as DD-MM-YYYY\n\n"

#         "IMPORTANT: In death cases, the claimant and deceased are different people. Do not mix them up.\n"
#         "- claimant_name is the legal heir/representative filing the case (e.g. wife/son/daughter/mother).\n"
#         "- deceased_name is the person who died in the accident.\n"
#         "- Ensure that age, father_name, and occupation are attributed to the correct person (deceased in death cases, claimant/injured in injury cases).\n\n"

#         "INJURY CASE HEADS (fill for injury cases):\n"
#         "- disability_percentage: float e.g. 35.0 (look for '35% disability', 'permanent disability 40%')\n"
#         "- medical_expenses: float (bills paid for treatment)\n"
#         "- future_medical_expenses: float\n"
#         "- pain_and_suffering: float (also called 'pain and agony')\n"
#         "- transportation: float (conveyance/transport charges)\n"
#         "- special_diet: float\n"
#         "- attender_charges: float (attendant/nursing charges)\n"
#         "- loss_of_income: float (loss of earnings during treatment)\n"
#         "- loss_of_amenities: float (loss of amenities of life)\n\n"

#         "DEATH CASE HEADS (fill for death cases):\n"
#         "- loss_of_dependency: float (main head — monthly income x multiplier x dependency ratio)\n"
#         "- loss_of_consortium: float (per-person standard rate per Pranay Sethi = Rs.40000. Do NOT use tribunal total award. If document shows 2,20,000 for 5 claimants, extract 40000 not 2,20,000)\n"
#         "- loss_of_estate: float (loss of estate of deceased)\n"
#         "- funeral_expenses: float (funeral/obsequies expenses)\n"
#         "- loss_of_love_affection: float (parental/filial consortium)\n\n"

#         "CALCULATION PARAMETERS:\n"
#         "- future_prospect: float percentage e.g. 25.0 or 40.0 (future prospects addition)\n"
#         "- multiplier: integer from Sarla Verma table (based on age)\n"
#         "- dependency_ratio: float e.g. 0.5 or 0.667 (deduction for personal expenses)\n"
#         "- interest_rate: float e.g. 7.5 (rate of interest awarded)\n"
#         "- total_compensation: float (total award amount)\n"
#         "- award_amount: float (final amount awarded by court)\n\n"

#         "RULES:\n"
#         "1. monetary values as plain floats with no Rs/commas/symbols\n"
#         "2. For monthly_income: if annual given divide by 12; if notional stated use that value.\n"
#         "   If the claimant's income appears in Hindi as a pleaded figure in the original\n"
#         "   petition (words like 'अभिवचनित' or 'मूल याचिका में...आय' near a 'रुपये प्रतिमाह'\n"
#         "   amount), prefer THAT pleaded figure over any oral-testimony figure ('मुख्य परीक्षण\n"
#         "   में बताया') or the tribunal's own notionally-assessed/minimum-wage figure\n"
#         "   ('निर्धारित', 'मानते हुए'). Never invent or estimate an income figure that is not\n"
#         "   explicitly stated in the text — if no income figure is present, return null.\n"
#         "3. disability_percentage: extract number from phrases like '40% permanent disability'\n"
#         "4. multiplier: look for 'multiplier of 17' or Sarla Verma table references\n"
#         "5. future_prospect: look for '25% future prospects' or '40% addition'\n"
#         "6. For death cases always try to fill loss_of_dependency, funeral_expenses, loss_of_consortium\n"
#         "7. confidence 0.95+ only when exact number found in text; 0.7-0.94 for inferred values\n"
#         "8. In death cases, NEVER default deceased_name to claimant_name. They are distinct individuals.\n"
#         "9. NEVER guess, round, or fabricate a numeric value merely to fill a field. If a field is not\n"
#         "   clearly and explicitly stated anywhere in the text, return null for its value and 0.0 for\n"
#         "   confidence rather than estimating. A missing field is far better than a wrong one.\n"
#         "10. For every date field (accident_date, decision_date, dob), return strictly DD-MM-YYYY.\n"
#         "    Convert whatever date format appears in the text (DD/MM/YYYY, 'DD Month YYYY', etc.)\n"
#         "    into DD-MM-YYYY. If a date is only partially legible or ambiguous, return null rather\n"
#         "    than guessing the missing part.\n"
#     )

#     smart_text = extract_smart_context_for_llm(raw_ocr_text)
#     prompt = f"Analyze this MACT court judgment and extract all fields:\n\n{smart_text}"
#     logger.info(f"Exact text being sent to LLM prompt (length={len(prompt)}):\n{prompt}")
#     logger.info(f"Exact system instruction being sent to LLM:\n{system_instruction}")

#     response = generate_response(prompt, system_instruction)

#     try:
#         json_match = re.search(r"\{.*\}", response, re.DOTALL)
#         if json_match:
#             raw_data = json.loads(json_match.group(0))
#         else:
#             raw_data = json.loads(response)

#         data = {}
#         confidence_scores = {}

#         for key, field_obj in raw_data.items():
#             if isinstance(field_obj, dict) and "value" in field_obj:
#                 val = field_obj.get("value")
#                 conf = field_obj.get("confidence", 1.0)
#             else:
#                 val = field_obj
#                 conf = 1.0 if val is not None else 0.0
#             data[key] = val
#             confidence_scores[key] = {"confidence": conf}

#         # ── Canonicalise every date field to strict DD-MM-YYYY ─────────────
#         # (see normalize_date_to_ddmmyyyy docstring for why this matters —
#         # without it, LLM dates that aren't already exactly DD-MM-YYYY get
#         # silently rejected by the frontend's <input type="date"> and the
#         # field appears to "not fill" at all.)
#         for _date_key in ("dob", "date_of_birth", "accident_date", "date_of_accident", "decision_date"):
#             if data.get(_date_key):
#                 data[_date_key] = normalize_date_to_ddmmyyyy(data[_date_key])

#         # ── Case type deterministic override ──────────────────────────────
#         ocr_evidence_case = classify_case_type_by_ocr_text(raw_ocr_text)
#         if ocr_evidence_case:
#             case_type_val = ocr_evidence_case
#             case_type_conf = 1.0
#             ocr_evidence_str = ocr_evidence_case.upper()
#             logger.info(f"Deterministic OCR Case Type overrides LLM: {case_type_val.upper()}")
#         else:
#             llm_case_obj = raw_data.get("case_type", {})
#             if isinstance(llm_case_obj, dict):
#                 case_type_val = llm_case_obj.get("value")
#                 case_type_conf = llm_case_obj.get("confidence", 0.0)
#             else:
#                 case_type_val = llm_case_obj
#                 case_type_conf = 1.0 if case_type_val else 0.0
#             if not case_type_val or case_type_val not in ["injury", "death"]:
#                 case_type_val = "death"
#                 case_type_conf = 0.5
#             ocr_evidence_str = "UNCLEAR"

#         data["case_type"] = case_type_val
#         confidence_scores["case_type"] = {"confidence": case_type_conf}

#         # ── Aliases for calculator field name compatibility ────────────────
#         aliases = [
#             # (source_key, alias_key)
#             ("accident_date",        "date_of_accident"),
#             ("dob",                  "date_of_birth"),
#             ("accident_place",       "place_of_accident"),
#             ("disability_percentage","disability"),
#             ("loss_of_consortium",   "consortium"),
#             ("loss_of_dependency",   "dependency"),
#             ("funeral_expenses",     "funeral"),
#             ("loss_of_estate",       "estate"),
#             ("loss_of_love_affection","love_affection"),
#             ("loss_of_amenities",    "amenities"),
#             ("future_prospect",      "future_prospects"),
#             ("total_compensation",   "total_award"),
#             ("award_amount",         "award"),
#         ]
#         if case_type_val == "injury":
#             aliases.extend([
#                 ("claimant_name", "name"),
#                 ("claimant_name", "injured_name")
#             ])
#         elif case_type_val == "death":
#             aliases.extend([
#                 ("deceased_name", "name"),
#                 ("deceased_name", "injured_name")
#             ])

#         for src, alias in aliases:
#             if src in data and data[src] is not None:
#                 if data.get(alias) is None or data.get(alias) == "":   # don't clobber an existing real value
#                     data[alias] = data[src]
#                     confidence_scores[alias] = confidence_scores.get(src, {"confidence": 0.8})

#         data["confidence_scores"] = confidence_scores
#         data["ocr_evidence_case"] = ocr_evidence_str

#         # ── Hindi "pleaded income" override ──────────────────────────────
#         try:
#             from backend.parser_heuristics import extract_hindi_narrative_income
#             hindi_income, hindi_ctx = extract_hindi_narrative_income(raw_ocr_text)
#             if hindi_income is not None:
#                 llm_val = data.get("monthly_income")
#                 llm_conf = confidence_scores.get("monthly_income", {}).get("confidence", 0.0)
#                 should_override = False
#                 reason = ""
#                 if llm_conf < 0.85:
#                     should_override = True
#                     reason = f"LLM monthly_income confidence ({llm_conf}) is below 0.85"
#                 elif llm_val is None or llm_val == 0 or llm_val == "":
#                     should_override = True
#                     reason = "LLM monthly_income is missing or zero"
#                 else:
#                     try:
#                         llm_float = float(llm_val)
#                         diff_ratio = abs(llm_float - hindi_income) / hindi_income
#                         if diff_ratio > 0.20:
#                             should_override = True
#                             reason = f"LLM monthly_income ({llm_float}) differs from Hindi pleaded income ({hindi_income}) by {diff_ratio:.1%}"
#                     except (ValueError, TypeError):
#                         should_override = True
#                         reason = f"LLM monthly_income ({llm_val}) is not a valid number"
#                 if should_override:
#                     logger.info(f"[HINDI OVERRIDE] Overwriting monthly_income from {llm_val} to {hindi_income}. Reason: {reason}. Context: {hindi_ctx}")
#                     data["monthly_income"] = hindi_income
#                     confidence_scores["monthly_income"] = {"confidence": 0.9}
#         except Exception as override_err:
#             logger.error(f"Failed to run Hindi narrative income override: {str(override_err)}")

#         logger.info(f"AI Data Recovery successful with structured confidences: {list(data.keys())}")
#         return data

#     except Exception as e:
#         logger.error(f"Failed to parse AI Data Recovery JSON: {str(e)}. Raw response: {response}")
#         return {"ai_recovery_error": str(e), "raw_response_preview": response[:300]}






# backend/llm_client.py
# backend/llm_client.py
import json
import logging
import urllib.request
import urllib.error
import re
from datetime import datetime
 
from config.llm import LLM_PROVIDER, LLM_MODEL_NAME, LLM_API_KEY, LLM_API_ENDPOINT
 
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LLMClient")
 
_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
 
 
def normalize_date_to_ddmmyyyy(raw_value):
    """
    Best-effort conversion of ANY human/LLM-supplied date string into a
    strict 'DD-MM-YYYY' string (the format parser_heuristics.py, the
    calculator, and the frontend's date converter all expect).
 
    The system prompt *asks* the LLM to return DD-MM-YYYY, but local models
    (Ollama/qwen etc.) frequently ignore that instruction and return
    "10/04/2023", "2023-04-10", "10 April 2023", "10-Apr-2023", etc.
    The frontend feeds this value into an <input type="date">, which the
    browser silently rejects (leaving it blank) unless it converts cleanly
    to "YYYY-MM-DD" — so an unnormalized date from the LLM is the single
    biggest cause of "date fields not autofilling" after AI extraction.
 
    Returns the original value unchanged (never raises) if it cannot be
    confidently parsed as a date, so callers stay safe on unexpected input.
    """
    if raw_value is None:
        return raw_value
    val = str(raw_value).strip()
    if not val:
        return raw_value
 
    # 1) Purely numeric, separator-delimited dates: DD-MM-YYYY, DD/MM/YYYY,
    #    DD.MM.YYYY, or the ISO-ish YYYY-MM-DD / YYYY/MM/DD variants.
    m = re.match(r'^(\d{1,4})[\-/\.](\d{1,2})[\-/\.](\d{1,4})$', val)
    if m:
        a, b, c = m.group(1), m.group(2), m.group(3)
        try:
            if len(a) == 4:  # YYYY-MM-DD style
                year, month, day = int(a), int(b), int(c)
            else:  # DD-MM-YYYY style (day-first, standard in Indian legal docs)
                day, month, year = int(a), int(b), int(c)
            datetime(year, month, day)  # validates the combination
            return f"{day:02d}-{month:02d}-{year}"
        except (ValueError, TypeError):
            pass
 
    # 2) Textual month dates: "10 April 2023", "10th April, 2023",
    #    "April 10 2023", "10-Apr-2023", "Apr 10, 2023".
    text = val.lower().replace(",", " ")
    text = re.sub(r'(\d)(st|nd|rd|th)\b', r'\1', text)  # strip ordinal suffixes
    tokens = [t for t in re.split(r'[\s\-/]+', text.strip()) if t]
    day = month = year = None
    for tok in tokens:
        if tok in _MONTHS:
            month = _MONTHS[tok]
        elif re.fullmatch(r'\d{4}', tok):
            year = int(tok)
        elif re.fullmatch(r'\d{1,2}', tok) and day is None:
            day = int(tok)
    if day and month and year:
        try:
            datetime(year, month, day)
            return f"{day:02d}-{month:02d}-{year}"
        except (ValueError, TypeError):
            pass
 
    # Could not confidently parse — leave untouched rather than risk
    # corrupting a legitimate value we didn't anticipate the shape of.
    return raw_value
 
 
def validate_ollama_setup() -> dict:
    import urllib.request
    import json
    base_url = LLM_API_ENDPOINT if LLM_API_ENDPOINT else "http://localhost:11434"
    url = f"{base_url.rstrip('/')}/api/tags"
    stats = {
        "connected": False,
        "llm_model_available": False,
        "embedding_model_available": False,
        "models_found": []
    }
    logger.info(f"Validating Ollama connection at {base_url}...")
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as response:
            res_json = json.loads(response.read().decode("utf-8"))
            stats["connected"] = True
            
            # Parse models list
            models = res_json.get("models", [])
            for m in models:
                name = m.get("name", "")
                stats["models_found"].append(name)
                
            # Verify LLM Model and Embedding Model availability
            for model_name in stats["models_found"]:
                if "qwen2.5:14b" in model_name or LLM_MODEL_NAME in model_name:
                    stats["llm_model_available"] = True
                if "nomic-embed-text" in model_name:
                    stats["embedding_model_available"] = True
                    
            logger.info(f"Ollama server is ONLINE at {base_url}. Models found: {stats['models_found']}")
            if not stats["llm_model_available"]:
                logger.warning(f"Ollama model '{LLM_MODEL_NAME}' is missing!")
            if not stats["embedding_model_available"]:
                logger.warning("Ollama embedding model 'nomic-embed-text' is missing!")
    except Exception as e:
        logger.error(f"Ollama startup connection failed at {base_url}: {str(e)}")
    return stats
 
def generate_response(prompt: str, system_instruction: str = None) -> str:
    logger.info(f"Generating LLM response using provider '{LLM_PROVIDER}', model '{LLM_MODEL_NAME}'")
    final_prompt = prompt
    if system_instruction:
        final_prompt = f"System Instruction:\n{system_instruction}\n\nUser Question:\n{prompt}"
    try:
        if LLM_PROVIDER == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{LLM_MODEL_NAME}:generateContent?key={LLM_API_KEY}"
            headers = {"Content-Type": "application/json"}
            payload = {"contents": [{"parts": [{"text": final_prompt}]}]}
            if system_instruction:
                payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
                payload["contents"][0]["parts"][0]["text"] = prompt
            req_body = json.dumps(payload).encode("utf-8")
        elif LLM_PROVIDER == "ollama":
            if "v1" in LLM_API_ENDPOINT:
                url = f"{LLM_API_ENDPOINT.rstrip('/')}/chat/completions"
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})
                payload = {"model": LLM_MODEL_NAME, "messages": messages, "temperature": 0.2}
            else:
                url = f"{LLM_API_ENDPOINT.rstrip('/')}/api/chat"
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                messages.append({"role": "user", "content": prompt})
                payload = {"model": LLM_MODEL_NAME, "messages": messages, "stream": False, "options": {"temperature": 0.2}}
            headers = {"Content-Type": "application/json"}
            req_body = json.dumps(payload).encode("utf-8")
        else:
            url = f"{LLM_API_ENDPOINT.rstrip('/')}/chat/completions"
            headers = {"Content-Type": "application/json"}
            if LLM_API_KEY:
                headers["Authorization"] = f"Bearer {LLM_API_KEY}"
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})
            payload = {"model": LLM_MODEL_NAME, "messages": messages, "temperature": 0.2}
            req_body = json.dumps(payload).encode("utf-8")
 
        req = urllib.request.Request(url, data=req_body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=300.0) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            if LLM_PROVIDER == "gemini":
                candidates = res_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
                return ""
            else:
                choices = res_json.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
                if "message" in res_json and "content" in res_json["message"]:
                    return res_json["message"]["content"].strip()
                return ""
    except urllib.error.HTTPError as he:
        err_msg = he.read().decode("utf-8") if he.fp else str(he)
        logger.error(f"LLM API HTTP Error ({he.code}): {err_msg}")
        return f"Error connecting to LLM server: {he.reason}"
    except Exception as e:
        logger.error(f"Failed to generate LLM response: {str(e)}")
        return f"Error communicating with LLM client: {str(e)}"
 
def classify_case_type_by_ocr_text(ocr_text: str) -> str:
    text_lower = ocr_text.lower()
    injury_keywords = ["injury", "disability", "permanent disability", "partial disability", "bodily injury", "enhancement", "claimant injury"]
    death_keywords = ["death", "deceased", "fatal", "died", "legal heirs", "widow", "death claim"]
    injury_count = sum(text_lower.count(kw) for kw in injury_keywords)
    death_count = sum(text_lower.count(kw) for kw in death_keywords)
    logger.info(f"OCR case type keyword count: Injury = {injury_count}, Death = {death_count}")
    if injury_count > death_count and injury_count >= 1:
        return "injury"
    elif death_count > injury_count and death_count >= 1:
        return "death"
    elif injury_count == death_count and injury_count >= 1:
        injury_weight = sum(text_lower.count(kw) * 2 for kw in ["permanent disability", "partial disability", "bodily injury", "claimant injury"])
        death_weight = sum(text_lower.count(kw) * 2 for kw in ["deceased", "legal heirs", "death claim", "widow"])
        if injury_weight > death_weight:
            return "injury"
        elif death_weight > injury_weight:
            return "death"
    return None
 
def _strip_devanagari_lines(text: str, threshold: float = 0.5) -> str:
    """Remove lines that are predominantly Devanagari so LLM only sees English content."""
    kept = []
    for line in text.splitlines():
        alpha = [ch for ch in line if ch.isalpha()]
        if not alpha:
            kept.append(line)
            continue
        deva = sum(1 for ch in alpha if '\u0900' <= ch <= '\u097F')
        if (deva / len(alpha)) < threshold:
            kept.append(line)
    return "\n".join(kept)
 
 
def extract_smart_context_for_llm(raw_ocr_text: str, track: str = "high_court") -> str:
    # Strip predominantly Hindi/Devanagari lines so the LLM only processes English text —
    # but ONLY for the high_court track. For lower_court bundles the fields we need
    # (award amount, accident date, party names) live IN the Hindi lines, so stripping
    # them here would throw away the exact content this call exists to recover.
    if track != "lower_court":
        raw_ocr_text = _strip_devanagari_lines(raw_ocr_text)
    if len(raw_ocr_text) <= 30000:
        return raw_ocr_text
    front_context = raw_ocr_text[:12000]
    remainder_text = raw_ocr_text[12000:]
    lines = remainder_text.split("\n")
    high_value_keywords = [
        "compensation", "multiplier", "dependency", "consortium",
        "funeral", "monthly income", "disability", "earning", "quantum",
        "award", "rs.", "rupees", "attender", "medical", "pain",
        "future prospect", "interest", "loss of", "notional", "deduction"
    ]
    selected_chunks = []
    i = 0
    n = len(lines)
    while i < n:
        line_lower = lines[i].lower()
        if any(kw in line_lower for kw in high_value_keywords):
            start = max(0, i - 1)
            end = min(n, i + 3)
            chunk = "\n".join(lines[start:end])
            selected_chunks.append(chunk)
            i = end
        else:
            i += 1
    selected_text = "\n\n... [Section Extract] ...\n\n".join(selected_chunks)
    if len(selected_text) > 25000:
        selected_text = selected_text[:25000] + "\n\n... [Truncated] ..."
    end_context = raw_ocr_text[-8000:]
 
    # For all cases, unconditionally extract and merge Cause Title, Prayer, and Grounds
    extra_case_context = ""
    try:
        # Segment text into pages
        pages_list = []
        current_page_num = 1
        current_page_lines = []
        text_lines = raw_ocr_text.split("\n")
        for line in text_lines:
            line_strip = line.strip()
            if line_strip.startswith("--- PAGE"):
                if current_page_lines:
                    pages_list.append({
                        "page_number": current_page_num,
                        "lines": current_page_lines,
                        "text": "\n".join(current_page_lines)
                    })
                m = re.search(r'PAGE\s+(\d+)', line_strip, re.IGNORECASE)
                if m:
                    current_page_num = int(m.group(1))
                current_page_lines = []
            else:
                current_page_lines.append(line)
        if current_page_lines or not pages_list:
            pages_list.append({
                "page_number": current_page_num,
                "lines": current_page_lines,
                "text": "\n".join(current_page_lines)
            })
 
        from backend.parser_heuristics import detect_document_sections
        sections_metadata = detect_document_sections(raw_ocr_text, pages_list)
 
        claimant_sec = sections_metadata.get("claimant_section", {}).get("content", "").strip()
        relief_sec = sections_metadata.get("relief_section", {}).get("content", "").strip()
        grounds_sec = sections_metadata.get("grounds_section", {}).get("content", "").strip()
 
        case_parts = []
        if claimant_sec:
            claimant_sec_trunc = claimant_sec if len(claimant_sec) <= 8000 else claimant_sec[:8000] + "\n... [Truncated Claimant Section] ..."
            case_parts.append(f"=== CAUSE TITLE / CLAIMANT SECTION ===\n{claimant_sec_trunc}")
        if relief_sec:
            relief_sec_trunc = relief_sec if len(relief_sec) <= 8000 else relief_sec[:8000] + "\n... [Truncated Relief Section] ..."
            case_parts.append(f"=== PRAYER / RELIEF CLAIMS SECTION ===\n{relief_sec_trunc}")
        if grounds_sec:
            grounds_sec_trunc = grounds_sec if len(grounds_sec) <= 8000 else grounds_sec[:8000] + "\n... [Truncated Grounds Section] ..."
            case_parts.append(f"=== GROUNDS OF APPEAL SECTION ===\n{grounds_sec_trunc}")
 
        if case_parts:
            extra_case_context = "\n\n".join(case_parts)
    except Exception as ex:
        logger.error(f"Failed to extract case-specific context sections: {str(ex)}")
 
    if extra_case_context:
        return (
            f"=== KEY CASE SECTIONS (CAUSE TITLE, PRAYER/RELIEF, GROUNDS OF APPEAL) ===\n\n"
            f"{extra_case_context}\n\n"
            f"=== FRONT PAGE METADATA ===\n\n"
            f"{front_context}\n\n"
            f"=== RELEVANT QUANTUM & COMPENSATION EXTRACTS ===\n\n"
            f"{selected_text}\n\n"
            f"=== FINAL JUDGMENT AWARD SECTIONS ===\n\n"
            f"{end_context}"
        )
 
    return (
        f"{front_context}\n\n"
        f"=== RELEVANT QUANTUM & COMPENSATION EXTRACTS ===\n\n"
        f"{selected_text}\n\n"
        f"=== FINAL JUDGMENT AWARD SECTIONS ===\n\n"
        f"{end_context}"
    )
 
def ai_data_recovery(raw_ocr_text: str, track: str = "high_court") -> dict:
    """
    Invokes the LLM to parse raw OCR text and extract ALL legal claims fields
    for both injury and death cases.
    """
    system_instruction = (
        "You are an expert legal data extraction engine specializing in Indian Motor Accident Claims Tribunal (MACT) judgments.\n"
        "Analyze the provided raw OCR text and extract ALL compensation parameters for both injury and death cases.\n"
        "Return ONLY a clean valid JSON object. Every key maps to {\"value\": ..., \"confidence\": 0.0-1.0}.\n"
        "Use null for value and 0.0 for confidence if a field is not found.\n"
        "Do NOT write preamble, explanation, markdown fences, or comments. Return only the JSON.\n\n"
 
        "Extract ALL of these fields:\n\n"
 
        "IDENTITY FIELDS:\n"
        "- case_type: 'injury' or 'death'\n"
        "- claimant_name: full name of claimant/petitioner\n"
        "- deceased_name: full name of the deceased (only for death cases)\n"
        "- claimant_relationship_type: relationship of claimant to deceased e.g. 'Wife', 'Son', 'Mother' (only for death cases)\n"
        "- father_name: father or husband name\n"
        "- spouse_name: spouse name if mentioned\n"
        "- dob: date of birth as DD-MM-YYYY\n"
        "- age: integer age at time of accident\n"
        "- occupation: job/profession of claimant or deceased\n"
        "- monthly_income: monthly income as float (convert annual to monthly if needed; use notional if stated)\n"
        "- dependents: number of dependents as integer\n"
        "- marital_status: 'married', 'unmarried', or 'widowed'\n"
        "- accident_date: DD-MM-YYYY\n"
        "- accident_place: full location string\n"
        "- vehicle_number: vehicle registration number\n"
        "- insurance_company: name of insurance company\n"
        "- fir_number: FIR/complaint number\n"
        "- case_number: court case/petition number\n"
        "- court_name: name of the tribunal/court\n"
        "- judge_name: name of the judge\n"
        "- decision_date: date of judgment as DD-MM-YYYY\n\n"
 
        "IMPORTANT: In death cases, the claimant and deceased are different people. Do not mix them up.\n"
        "- claimant_name is the legal heir/representative filing the case (e.g. wife/son/daughter/mother).\n"
        "- deceased_name is the person who died in the accident.\n"
        "- Ensure that age, father_name, and occupation are attributed to the correct person (deceased in death cases, claimant/injured in injury cases).\n\n"
 
        "INJURY CASE HEADS (fill for injury cases):\n"
        "- disability_percentage: float e.g. 35.0 (look for '35% disability', 'permanent disability 40%')\n"
        "- medical_expenses: float (bills paid for treatment)\n"
        "- future_medical_expenses: float\n"
        "- pain_and_suffering: float (also called 'pain and agony')\n"
        "- transportation: float (conveyance/transport charges)\n"
        "- special_diet: float\n"
        "- attender_charges: float (attendant/nursing charges)\n"
        "- loss_of_income: float (loss of earnings during treatment)\n"
        "- loss_of_amenities: float (loss of amenities of life)\n\n"
 
        "DEATH CASE HEADS (fill for death cases):\n"
        "- loss_of_dependency: float (main head — monthly income x multiplier x dependency ratio)\n"
        "- loss_of_consortium: float (per-person standard rate per Pranay Sethi = Rs.40000. Do NOT use tribunal total award. If document shows 2,20,000 for 5 claimants, extract 40000 not 2,20,000)\n"
        "- loss_of_estate: float (loss of estate of deceased)\n"
        "- funeral_expenses: float (funeral/obsequies expenses)\n"
        "- loss_of_love_affection: float (parental/filial consortium)\n\n"
 
        "CALCULATION PARAMETERS:\n"
        "- future_prospect: float percentage e.g. 25.0 or 40.0 (future prospects addition)\n"
        "- multiplier: integer from Sarla Verma table (based on age)\n"
        "- dependency_ratio: float e.g. 0.5 or 0.667 (deduction for personal expenses)\n"
        "- interest_rate: float e.g. 7.5 (rate of interest awarded)\n"
        "- total_compensation: float (total award amount)\n"
        "- award_amount: float (final amount awarded by court)\n\n"
 
        "RULES:\n"
        "1. monetary values as plain floats with no Rs/commas/symbols\n"
        "2. For monthly_income: if annual given divide by 12; if notional stated use that value.\n"
        "   If the claimant's income appears in Hindi as a pleaded figure in the original\n"
        "   petition (words like 'अभिवचनित' or 'मूल याचिका में...आय' near a 'रुपये प्रतिमाह'\n"
        "   amount), prefer THAT pleaded figure over any oral-testimony figure ('मुख्य परीक्षण\n"
        "   में बताया') or the tribunal's own notionally-assessed/minimum-wage figure\n"
        "   ('निर्धारित', 'मानते हुए'). Never invent or estimate an income figure that is not\n"
        "   explicitly stated in the text — if no income figure is present, return null.\n"
        "3. disability_percentage: extract number from phrases like '40% permanent disability'\n"
        "4. multiplier: look for 'multiplier of 17' or Sarla Verma table references\n"
        "5. future_prospect: look for '25% future prospects' or '40% addition'\n"
        "6. For death cases always try to fill loss_of_dependency, funeral_expenses, loss_of_consortium\n"
        "7. confidence 0.95+ only when exact number found in text; 0.7-0.94 for inferred values\n"
        "8. In death cases, NEVER default deceased_name to claimant_name. They are distinct individuals.\n"
        "9. NEVER guess, round, or fabricate a numeric value merely to fill a field. If a field is not\n"
        "   clearly and explicitly stated anywhere in the text, return null for its value and 0.0 for\n"
        "   confidence rather than estimating. A missing field is far better than a wrong one.\n"
        "10. For every date field (accident_date, decision_date, dob), return strictly DD-MM-YYYY.\n"
        "    Convert whatever date format appears in the text (DD/MM/YYYY, 'DD Month YYYY', etc.)\n"
        "    into DD-MM-YYYY. If a date is only partially legible or ambiguous, return null rather\n"
        "    than guessing the missing part.\n"
    )
 
    smart_text = extract_smart_context_for_llm(raw_ocr_text, track=track)
    prompt = f"Analyze this MACT court judgment and extract all fields:\n\n{smart_text}"
    logger.info(f"Exact text being sent to LLM prompt (length={len(prompt)}):\n{prompt}")
    logger.info(f"Exact system instruction being sent to LLM:\n{system_instruction}")
 
    response = generate_response(prompt, system_instruction)
 
    try:
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            raw_data = json.loads(json_match.group(0))
        else:
            raw_data = json.loads(response)
 
        data = {}
        confidence_scores = {}
 
        for key, field_obj in raw_data.items():
            if isinstance(field_obj, dict) and "value" in field_obj:
                val = field_obj.get("value")
                conf = field_obj.get("confidence", 1.0)
            else:
                val = field_obj
                conf = 1.0 if val is not None else 0.0
            data[key] = val
            confidence_scores[key] = {"confidence": conf}
 
        # ── Canonicalise every date field to strict DD-MM-YYYY ─────────────
        # (see normalize_date_to_ddmmyyyy docstring for why this matters —
        # without it, LLM dates that aren't already exactly DD-MM-YYYY get
        # silently rejected by the frontend's <input type="date"> and the
        # field appears to "not fill" at all.)
        for _date_key in ("dob", "date_of_birth", "accident_date", "date_of_accident", "decision_date"):
            if data.get(_date_key):
                data[_date_key] = normalize_date_to_ddmmyyyy(data[_date_key])
 
        # ── Case type deterministic override ──────────────────────────────
        ocr_evidence_case = classify_case_type_by_ocr_text(raw_ocr_text)
        if ocr_evidence_case:
            case_type_val = ocr_evidence_case
            case_type_conf = 1.0
            ocr_evidence_str = ocr_evidence_case.upper()
            logger.info(f"Deterministic OCR Case Type overrides LLM: {case_type_val.upper()}")
        else:
            llm_case_obj = raw_data.get("case_type", {})
            if isinstance(llm_case_obj, dict):
                case_type_val = llm_case_obj.get("value")
                case_type_conf = llm_case_obj.get("confidence", 0.0)
            else:
                case_type_val = llm_case_obj
                case_type_conf = 1.0 if case_type_val else 0.0
            if not case_type_val or case_type_val not in ["injury", "death"]:
                case_type_val = "death"
                case_type_conf = 0.5
            ocr_evidence_str = "UNCLEAR"
 
        data["case_type"] = case_type_val
        confidence_scores["case_type"] = {"confidence": case_type_conf}
 
        # ── Aliases for calculator field name compatibility ────────────────
        aliases = [
            # (source_key, alias_key)
            ("accident_date",        "date_of_accident"),
            ("dob",                  "date_of_birth"),
            ("accident_place",       "place_of_accident"),
            ("disability_percentage","disability"),
            ("loss_of_consortium",   "consortium"),
            ("loss_of_dependency",   "dependency"),
            ("funeral_expenses",     "funeral"),
            ("loss_of_estate",       "estate"),
            ("loss_of_love_affection","love_affection"),
            ("loss_of_amenities",    "amenities"),
            ("future_prospect",      "future_prospects"),
            ("total_compensation",   "total_award"),
            ("award_amount",         "award"),
        ]
        if case_type_val == "injury":
            aliases.extend([
                ("claimant_name", "name"),
                ("claimant_name", "injured_name")
            ])
        elif case_type_val == "death":
            aliases.extend([
                ("deceased_name", "name"),
                ("deceased_name", "injured_name")
            ])
 
        for src, alias in aliases:
            if src in data and data[src] is not None:
                if data.get(alias) is None or data.get(alias) == "":   # don't clobber an existing real value
                    data[alias] = data[src]
                    confidence_scores[alias] = confidence_scores.get(src, {"confidence": 0.8})
 
        data["confidence_scores"] = confidence_scores
        data["ocr_evidence_case"] = ocr_evidence_str
 
        # ── Hindi "pleaded income" override ──────────────────────────────
        try:
            from backend.parser_heuristics import extract_hindi_narrative_income
            hindi_income, hindi_ctx = extract_hindi_narrative_income(raw_ocr_text)
            if hindi_income is not None:
                llm_val = data.get("monthly_income")
                llm_conf = confidence_scores.get("monthly_income", {}).get("confidence", 0.0)
                should_override = False
                reason = ""
                if llm_conf < 0.85:
                    should_override = True
                    reason = f"LLM monthly_income confidence ({llm_conf}) is below 0.85"
                elif llm_val is None or llm_val == 0 or llm_val == "":
                    should_override = True
                    reason = "LLM monthly_income is missing or zero"
                else:
                    try:
                        llm_float = float(llm_val)
                        diff_ratio = abs(llm_float - hindi_income) / hindi_income
                        if diff_ratio > 0.20:
                            should_override = True
                            reason = f"LLM monthly_income ({llm_float}) differs from Hindi pleaded income ({hindi_income}) by {diff_ratio:.1%}"
                    except (ValueError, TypeError):
                        should_override = True
                        reason = f"LLM monthly_income ({llm_val}) is not a valid number"
                if should_override:
                    logger.info(f"[HINDI OVERRIDE] Overwriting monthly_income from {llm_val} to {hindi_income}. Reason: {reason}. Context: {hindi_ctx}")
                    data["monthly_income"] = hindi_income
                    confidence_scores["monthly_income"] = {"confidence": 0.9}
        except Exception as override_err:
            logger.error(f"Failed to run Hindi narrative income override: {str(override_err)}")
 
        logger.info(f"AI Data Recovery successful with structured confidences: {list(data.keys())}")
        return data
 
    except Exception as e:
        logger.error(f"Failed to parse AI Data Recovery JSON: {str(e)}. Raw response: {response}")
        return {"ai_recovery_error": str(e), "raw_response_preview": response[:300]}