# backend/llm_client.py
import json
import logging
import urllib.request
import urllib.error
import socket
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
 
def generate_response(prompt: str, system_instruction: str = None, response_format: str = None, history: list[dict] | None = None) -> str:
    logger.info(f"Generating LLM response using provider '{LLM_PROVIDER}', model '{LLM_MODEL_NAME}'")
    
    char_count = len(prompt)
    token_est = int(char_count / 4)
    logger.info(f"LLM Prompt size: {char_count} chars, approx {token_est} tokens")
    if system_instruction:
        sys_char_count = len(system_instruction)
        sys_token_est = int(sys_char_count / 4)
        logger.info(f"LLM System Instruction size: {sys_char_count} chars, approx {sys_token_est} tokens")

    final_prompt = prompt
    if system_instruction:
        final_prompt = f"System Instruction:\n{system_instruction}\n\nUser Question:\n{prompt}"
    
    # Cap history defensively
    history_sliced = history[-12:] if history else None

    try:
        if LLM_PROVIDER == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{LLM_MODEL_NAME}:generateContent?key={LLM_API_KEY}"
            headers = {"Content-Type": "application/json"}
            if history_sliced:
                contents = []
                for turn in history_sliced:
                    role = "user" if turn.get("role") == "user" else "model"
                    contents.append({"role": role, "parts": [{"text": turn.get("content", "")}]})
                contents.append({"role": "user", "parts": [{"text": prompt}]})
                payload = {"contents": contents}
                if system_instruction:
                    payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
            else:
                payload = {"contents": [{"parts": [{"text": final_prompt}]}]}
                if system_instruction:
                    payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
                    payload["contents"][0]["parts"][0]["text"] = prompt
            if response_format == "json":
                payload["generationConfig"] = {"responseMimeType": "application/json"}
            req_body = json.dumps(payload).encode("utf-8")
        elif LLM_PROVIDER == "ollama":
            if "v1" in LLM_API_ENDPOINT:
                url = f"{LLM_API_ENDPOINT.rstrip('/')}/chat/completions"
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                if history_sliced:
                    messages.extend(history_sliced)
                messages.append({"role": "user", "content": prompt})
                payload = {
                    "model": LLM_MODEL_NAME, 
                    "messages": messages, 
                    "temperature": 0.2,
                    "options": {"temperature": 0.2, "keep_alive": "10m", "num_ctx": 16384}
                }
                if response_format == "json":
                    payload["response_format"] = {"type": "json_object"}
            else:
                url = f"{LLM_API_ENDPOINT.rstrip('/')}/api/chat"
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                if history_sliced:
                    messages.extend(history_sliced)
                messages.append({"role": "user", "content": prompt})
                payload = {
                    "model": LLM_MODEL_NAME, 
                    "messages": messages, 
                    "stream": False, 
                    "options": {"temperature": 0.2, "keep_alive": "10m", "num_ctx": 16384}
                }
                if response_format == "json":
                    payload["format"] = "json"
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
            if history_sliced:
                messages.extend(history_sliced)
            messages.append({"role": "user", "content": prompt})
            payload = {"model": LLM_MODEL_NAME, "messages": messages, "temperature": 0.2}
            if response_format == "json":
                payload["response_format"] = {"type": "json_object"}
            req_body = json.dumps(payload).encode("utf-8")
 
        req = urllib.request.Request(url, data=req_body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=90.0) as response:
            res_body = response.read().decode("utf-8")
            logger.debug(f"Raw LLM Response: {res_body}")
            res_json = json.loads(res_body)
            content = ""
            if LLM_PROVIDER == "gemini":
                candidates = res_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        content = parts[0].get("text", "")
            else:
                choices = res_json.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                elif "message" in res_json and "content" in res_json["message"]:
                    content = res_json["message"]["content"]
            
            content_stripped = content.strip()
            if not content_stripped:
                logger.error(f"LLM returned an empty response. Raw response: {res_body}")
                return "LLM returned an empty response — the prompt may have exceeded the model's context window"
            return content_stripped
    except urllib.error.HTTPError as he:
        err_msg = he.read().decode("utf-8") if he.fp else str(he)
        logger.error(f"LLM API HTTP Error ({he.code}): {err_msg}")
        return f"Error connecting to LLM server: {he.reason}"
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        is_timeout = False
        if isinstance(e, urllib.error.URLError) and isinstance(e.reason, (socket.timeout, TimeoutError)):
            is_timeout = True
        elif isinstance(e, (socket.timeout, TimeoutError)):
            is_timeout = True
        
        if is_timeout or "timed out" in str(e).lower():
            logger.error("LLM Request timed out after 90 seconds.")
            return "Error connecting to LLM server: Request timed out after 90 seconds"
        
        err_msg = str(e)
        logger.error(f"LLM API URL Error: {err_msg}")
        return f"Error communicating with LLM client: {err_msg}"
    except Exception as e:
        logger.error(f"Failed to generate LLM response: {str(e)}")
        return f"Error communicating with LLM client: {str(e)}"
 
def generate_response_stream(prompt: str, system_instruction: str = None, history: list[dict] | None = None):
    logger.info(f"Streaming LLM response using provider '{LLM_PROVIDER}', model '{LLM_MODEL_NAME}'")
    
    char_count = len(prompt)
    token_est = int(char_count / 4)
    logger.info(f"LLM Stream Prompt size: {char_count} chars, approx {token_est} tokens")
    if system_instruction:
        sys_char_count = len(system_instruction)
        sys_token_est = int(sys_char_count / 4)
        logger.info(f"LLM Stream System Instruction size: {sys_char_count} chars, approx {sys_token_est} tokens")

    # Cap history defensively
    history_sliced = history[-12:] if history else None

    try:
        if LLM_PROVIDER == "ollama":
            if "v1" in LLM_API_ENDPOINT:
                url = f"{LLM_API_ENDPOINT.rstrip('/')}/chat/completions"
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                if history_sliced:
                    messages.extend(history_sliced)
                messages.append({"role": "user", "content": prompt})
                payload = {
                    "model": LLM_MODEL_NAME, 
                    "messages": messages, 
                    "temperature": 0.2, 
                    "stream": True,
                    "options": {"temperature": 0.2, "keep_alive": "10m", "num_ctx": 16384}
                }
            else:
                url = f"{LLM_API_ENDPOINT.rstrip('/')}/api/chat"
                messages = []
                if system_instruction:
                    messages.append({"role": "system", "content": system_instruction})
                if history_sliced:
                    messages.extend(history_sliced)
                messages.append({"role": "user", "content": prompt})
                payload = {
                    "model": LLM_MODEL_NAME,
                    "messages": messages,
                    "stream": True,
                    "options": {"temperature": 0.2, "keep_alive": "10m", "num_ctx": 16384}
                }
            headers = {"Content-Type": "application/json"}
            req_body = json.dumps(payload).encode("utf-8")
            
            req = urllib.request.Request(url, data=req_body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=90.0) as response:
                for line in response:
                    if not line:
                        continue
                    line_str = line.decode("utf-8").strip()
                    if not line_str:
                        continue
                    try:
                        if "v1" in LLM_API_ENDPOINT:
                            if line_str.startswith("data:"):
                                line_str = line_str[5:].strip()
                            if line_str == "[DONE]":
                                break
                            res_json = json.loads(line_str)
                            choices = res_json.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                if "content" in delta:
                                    yield delta["content"]
                        else:
                            res_json = json.loads(line_str)
                            if "message" in res_json and "content" in res_json["message"]:
                                yield res_json["message"]["content"]
                    except Exception as e:
                        logger.warning(f"Error parsing stream line: {str(e)}")
        else:
            full_resp = generate_response(prompt, system_instruction, history=history_sliced)
            yield full_resp
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        is_timeout = False
        if isinstance(e, urllib.error.URLError) and isinstance(e.reason, (socket.timeout, TimeoutError)):
            is_timeout = True
        elif isinstance(e, (socket.timeout, TimeoutError)):
            is_timeout = True
        
        if is_timeout or "timed out" in str(e).lower():
            logger.error("LLM Stream Request timed out after 90 seconds.")
            yield "Error communicating with LLM stream: Request timed out after 90 seconds"
        else:
            yield f"Error communicating with LLM stream: {str(e)}"
    except Exception as e:
        logger.error(f"Failed to stream LLM response: {str(e)}")
        yield f"Error communicating with LLM stream: {str(e)}"
 
def classify_case_type_by_ocr_text(ocr_text: str) -> str:
    import re
    text_lower = ocr_text.lower()
    
    # 1. Subject Heading Code / Scrutiny Report Category Check
    # Match strings like "15202/03-DEATH CLAIMS" or "15202/07-INJURY CLAIMS"
    subject_match = re.search(r'\b15202/(\d{2})-([a-zA-Z\s\(\)]+)', ocr_text)
    if subject_match:
        category_desc = subject_match.group(2).lower()
        if "death" in category_desc:
            logger.info(f"Classified case type via Scrutiny Category: death (matched: '{subject_match.group(0)}')")
            return "death"
        elif "injury" in category_desc:
            logger.info(f"Classified case type via Scrutiny Category: injury (matched: '{subject_match.group(0)}')")
            return "injury"
            
    # Also search for lines containing both category codes (15200/15202) and "death"/"injury"
    for line in ocr_text.splitlines():
        line_lower = line.lower()
        if "1520" in line_lower or "15202" in line_lower:
            if "death" in line_lower:
                logger.info(f"Classified case type via subject heading line match (death): '{line}'")
                return "death"
            elif "injury" in line_lower:
                logger.info(f"Classified case type via subject heading line match (injury): '{line}'")
                return "injury"

    injury_keywords = [
        "injury", "disability", "permanent disability", "partial disability", "bodily injury", "claimant injury",
        "स्थायी अपंगता", "स्थायी विकलांगता", "स्थायी निःशक्तता", "अंगहानि", "स्थायी निर्योग्यता", "चोट", "उपहति", "विकलांगता", "प्रतिशत निःशक्तता"
    ]
    death_keywords = [
        "death", "deceased", "fatal", "died", "legal heirs", "widow", "death claim",
        "मृत्यु", "मृतक", "स्वर्गीय", "विधवा", "वैध वारिस", "मृत", "देहांत", "दिवंगत", "आश्रित"
    ]
    injury_count = sum(text_lower.count(kw) for kw in injury_keywords)
    death_count = sum(text_lower.count(kw) for kw in death_keywords)
    logger.info(f"OCR case type keyword count: Injury = {injury_count}, Death = {death_count}")
    if injury_count > death_count and injury_count >= 1:
        return "injury"
    elif death_count > injury_count and death_count >= 1:
        return "death"
    elif injury_count == death_count and injury_count >= 1:
        injury_weight = sum(text_lower.count(kw) * 2 for kw in [
            "permanent disability", "partial disability", "bodily injury", "claimant injury",
            "स्थायी अपंगता", "स्थायी विकलांगता", "स्थायी निःशक्तता", "अंगहानि", "स्थायी निर्योग्यता", "प्रतिशत निःशक्तता"
        ])
        death_weight = sum(text_lower.count(kw) * 2 for kw in [
            "deceased", "legal heirs", "death claim", "widow",
            "मृतक", "वैध वारिस", "मृत्यु", "विधवा", "स्वर्गीय", "दिवंगत", "देहांत"
        ])
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
    if len(raw_ocr_text) <= 15000:
        return raw_ocr_text
    front_context = raw_ocr_text[:3000]
    remainder_text = raw_ocr_text[3000:]
    lines = remainder_text.split("\n")
    high_value_keywords = [
        "compensation", "multiplier", "dependency", "consortium",
        "funeral", "monthly income", "disability", "earning", "quantum",
        "award", "rs.", "rupees", "attender", "medical", "pain",
        "future prospect", "interest", "loss of", "notional", "deduction"
    ]
    if track == "lower_court":
        high_value_keywords.extend([
            "व्यय", "चिकित्सा", "वेदना", "पीड़ा", "परिवहन", "खुराक", "आहार",
            "परिचारक", "अटेंडर", "अपंगता", "विकलांगता", "आय", "वेतन", "प्रतिकर",
            "अधिकरण", "क्षतिपूर्ति", "नुकसान", "अटेण्डर", "कष्ट", "शारीरिक", "मानसिक"
        ])
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
    if len(selected_text) > 8000:
        selected_text = selected_text[:8000] + "\n\n... [Truncated] ..."
    end_context = raw_ocr_text[-3000:]
 
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
            claimant_sec_trunc = claimant_sec if len(claimant_sec) <= 3000 else claimant_sec[:3000] + "\n... [Truncated Claimant Section] ..."
            case_parts.append(f"=== CAUSE TITLE / CLAIMANT SECTION ===\n{claimant_sec_trunc}")
        if relief_sec:
            relief_sec_trunc = relief_sec if len(relief_sec) <= 3000 else relief_sec[:3000] + "\n... [Truncated Relief Section] ..."
            case_parts.append(f"=== PRAYER / RELIEF CLAIMS SECTION ===\n{relief_sec_trunc}")
        if grounds_sec:
            grounds_sec_trunc = grounds_sec if len(grounds_sec) <= 3000 else grounds_sec[:3000] + "\n... [Truncated Grounds Section] ..."
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
 
def validate_recovery_shape(raw_data: dict) -> bool:
    if not isinstance(raw_data, dict):
        return False
    expected_sample_keys = {
        "case_type", "claimant_name", "deceased_name", "age",
        "monthly_income", "award_amount", "medical_expenses",
        "pain_and_suffering", "disability", "disability_percentage"
    }
    if any(k in raw_data for k in expected_sample_keys):
        return True
    return False

def ai_data_recovery(raw_ocr_text: str, track: str = "high_court", case_type: str = None) -> dict:
    """
    Invokes the LLM to parse raw OCR text and extract ALL legal claims fields
    for both injury and death cases.
    """
    extra_prompt = ""
    if case_type:
        extra_prompt = f"\n\nCRITICAL: The case type has been confirmed as '{case_type}'. Extract ONLY fields relevant to '{case_type}' and completely skip/ignore fields for the opposite type."

    system_instruction = (
        "You are an expert legal data extraction engine specializing in Indian Motor Accident Claims Tribunal (MACT) judgments.\n"
        f"Analyze the provided raw OCR text and extract ALL compensation parameters for both injury and death cases.{extra_prompt}\n"
        "Return ONLY a clean valid JSON object. Every key maps to {\"value\": ..., \"confidence\": 0.0-1.0}.\n"
        "Use null for value and 0.0 for confidence if a field is not found.\n"
        "Do NOT write preamble, explanation, markdown fences, or comments. Return only the JSON.\n\n"

        "For Hindi/Devanagari judgments (lower court MACT cases), translate and map standard claims headings as follows:\n"
        "- 'चिकित्सा व्यय' / 'उपचार' / 'इलाज' / 'दवा' -> medical_expenses\n"
        "- 'शारीरिक एवं मानसिक वेदना' / 'पीड़ा और कष्ट' / 'वेदना' / 'कष्ट' -> pain_and_suffering\n"
        "- 'परिवहन व्यय' / 'आवागमन' / 'यातायात' / 'वाहन व्यय' -> transportation\n"
        "- 'विशेष भोजन' / 'पौष्टिक आहार' / 'विशेष खुराक' -> special_diet\n"
        "- 'परिचारक व्यय' / 'अटेंडर' / 'अटेण्डर' / 'सहायक' -> attender_charges\n"
        "- 'भविष्य का चिकित्सा व्यय' / 'आगामी उपचार' / 'भविष्य उपचार' -> future_medical_expenses\n"
        "- 'आय की हानि' / 'वेतन की क्षति' / 'उपचार अवधि के दौरान आय' -> loss_of_income\n"
        "- 'स्थायी अपंगता' / 'स्थायी अपंगता प्रतिशत' / 'विकलांगता प्रतिशत' / 'निरोग्यता प्रतिशत' -> disability_percentage\n"
        "- 'मासिक आय' / 'मासिक वेतन' -> monthly_income\n"
        "- 'प्रतिकर राशि' / 'कुल क्षतिपूर्ति' / 'कुल प्रतिकर' -> total_compensation / award_amount\n"
        "- 'सहचर्य हानि' / 'पति/पत्नी के प्रति सहचर्य' -> loss_of_consortium\n"
        "- 'सम्पदा की हानि' / 'सम्पदा हानि' -> loss_of_estate\n"
        "- 'दाह संस्कार व्यय' / 'दाह संस्कार' / 'अंतिम संस्कार व्यय' -> funeral_expenses\n\n"
 
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
        "- loss_of_consortium: float (per-person loss of consortium. Do NOT default or guess Rs.40000 if not explicitly mentioned in the text. Return null if not mentioned)\n"
        "- loss_of_estate: float (loss of estate. Do NOT default or guess Rs.15000 if not explicitly mentioned in the text. Return null if not mentioned)\n"
        "- funeral_expenses: float (funeral expenses. Do NOT default or guess Rs.15000 if not explicitly mentioned in the text. Return null if not mentioned)\n"
        "- loss_of_love_affection: float (parental/filial consortium)\n"
        "- consortium_claimants: number of claimants eligible for consortium as integer (e.g. number of family members awarded consortium)\n\n"
 
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
        "11. Never return a sentence, explanation, or phrase like 'not stated' as a field's value — the ONLY valid non-answer is JSON null. Any string value you return will be treated as real extracted data and shown directly to the user.\n"
    )
 
    smart_text = extract_smart_context_for_llm(raw_ocr_text, track=track)
    prompt = f"Analyze this MACT court judgment and extract all fields:\n\n{smart_text}"
    logger.info(f"Exact text being sent to LLM prompt (length={len(prompt)}):\n{prompt}")
    logger.info(f"Exact system instruction being sent to LLM:\n{system_instruction}")
 
    # Try with JSON mode enabled
    attempts = 2
    response = None
    raw_data = None
    
    current_prompt = prompt
    for attempt in range(attempts):
        try:
            response = generate_response(current_prompt, system_instruction, response_format="json")
        except Exception as gen_err:
            logger.warning(f"[AI-RECOVERY] Attempt {attempt+1} failed to generate response: {gen_err}")
            if attempt == attempts - 1:
                raise gen_err
            current_prompt = prompt + "\n\nREMINDER: your last response must be corrected — output ONLY the JSON object, nothing else, no summary, no explanation"
            continue

        try:
            # 1. Direct parse
            parsed = json.loads(response)
            if validate_recovery_shape(parsed):
                raw_data = parsed
                logger.info(f"[AI-RECOVERY] Attempt {attempt+1} direct parse and shape validation succeeded")
                break
            else:
                logger.warning(f"[AI-RECOVERY] Attempt {attempt+1} direct parse succeeded but failed shape validation")
        except Exception:
            # 2. Repair extraction
            start_idx = response.find("{")
            end_idx = response.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                candidate = response[start_idx:end_idx+1]
                try:
                    parsed = json.loads(candidate)
                    if validate_recovery_shape(parsed):
                        raw_data = parsed
                        logger.info(f"[AI-RECOVERY] Attempt {attempt+1} direct parse failed, repair-extraction and shape validation succeeded")
                        break
                    else:
                        logger.warning(f"[AI-RECOVERY] Attempt {attempt+1} repair-extraction succeeded but failed shape validation")
                except Exception as e2:
                    logger.warning(f"[AI-RECOVERY] Attempt {attempt+1} direct parse failed, repair-extraction also failed: {e2}")
            else:
                logger.warning(f"[AI-RECOVERY] Attempt {attempt+1} direct parse failed, no valid matching braces found for repair-extraction")
        
        if attempt < attempts - 1:
            logger.info("[AI-RECOVERY] Retrying with forceful format instruction...")
            current_prompt = prompt + "\n\nREMINDER: your last response must be corrected — output ONLY the JSON object, nothing else, no summary, no explanation"

    if raw_data is None:
        err_msg = "AI-assisted recovery unavailable for this document — please fill remaining fields manually."
        logger.error(f"Failed to parse AI Data Recovery JSON after all retries. Raw response: {response}")
        return {"ai_recovery_error": err_msg, "raw_response_preview": response[:300] if response else ""}
 
    try:
        data = {}
        confidence_scores = {}
 
        for key, field_obj in raw_data.items():
            if isinstance(field_obj, dict) and "value" in field_obj:
                val = field_obj.get("value")
                conf = field_obj.get("confidence", 1.0)
            else:
                val = field_obj
                conf = 1.0 if val is not None else 0.0
            
            if isinstance(val, str):
                if key in ("claimant_name", "deceased_name", "father_name", "spouse_name"):
                    from backend.parser_heuristics import clean_person_name
                    cleaned_val = clean_person_name(val)
                    if cleaned_val != val:
                        logger.info(f"[AI-RECOVERY-CLEANER] Cleaned name field '{key}': '{val}' -> '{cleaned_val}'")
                        val = cleaned_val if cleaned_val else None
                        if val is None:
                            conf = 0.0

            if isinstance(val, str):
                val_stripped = val.strip()
                val_lower = val_stripped.lower()
                blocklist = [
                    "not explicitly stated",
                    "not stated",
                    "not mentioned",
                    "not specified",
                    "not available",
                    "n/a",
                    "unknown",
                    "unclear",
                    "not found in text",
                ]
                is_blocked = False
                matched_phrase = None
                for phrase in blocklist:
                    if phrase == "n/a":
                        import re
                        if val_lower == "n/a" or re.search(r'\bn/a\b', val_lower):
                            is_blocked = True
                            matched_phrase = phrase
                            break
                    elif phrase in val_lower:
                        is_blocked = True
                        matched_phrase = phrase
                        break
                
                if is_blocked:
                    logger.info(f"[AI-RECOVERY-SANITIZER] Field '{key}' had non-answer value '{val}' matching blocklist phrase '{matched_phrase}'. Converting to None.")
                    val = None
                    conf = 0.0

            data[key] = val
            confidence_scores[key] = {"confidence": conf}
            if is_blocked:
                confidence_scores[key]["reason"] = f"Document stated non-answer: '{matched_phrase}'"
 
        # ── Canonicalise every date field to strict DD-MM-YYYY ─────────────
        # (see normalize_date_to_ddmmyyyy docstring for why this matters —
        # without it, LLM dates that aren't already exactly DD-MM-YYYY get
        # silently rejected by the frontend's <input type="date"> and the
        # field appears to "not fill" at all.)
        for _date_key in ("dob", "date_of_birth", "accident_date", "date_of_accident", "decision_date"):
            if data.get(_date_key):
                data[_date_key] = normalize_date_to_ddmmyyyy(data[_date_key])
 
        # ── Case type deterministic override ──────────────────────────────
        ocr_evidence_case = case_type or classify_case_type_by_ocr_text(raw_ocr_text)
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
            ("funeral_expenses",     "funeral_expenses"),
            ("loss_of_estate",       "estate"),
            ("loss_of_estate",       "loss_estate"),
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
 
        # ── English Age regex fallback override ──────────────────────────
        try:
            llm_age = data.get("age")
            llm_age_conf = confidence_scores.get("age", {}).get("confidence", 0.0)
            
            if llm_age is None or llm_age == "" or llm_age_conf < 0.7:
                from backend.parser_heuristics import extract_age_from_text
                fallback_age, age_ctx = extract_age_from_text(
                    raw_ocr_text,
                    claimant_name=data.get("claimant_name"),
                    deceased_name=data.get("deceased_name"),
                    case_type=case_type_val
                )
                if fallback_age is not None:
                    logger.info(f"[AGE OVERRIDE] Overwriting age from {llm_age} (conf: {llm_age_conf}) to {fallback_age}. Context: {age_ctx}")
                    data["age"] = fallback_age
                    confidence_scores["age"] = {
                        "confidence": 0.85,
                        "reason": "Extracted via proximity regex override"
                    }
                else:
                    if llm_age is None or llm_age == "":
                        reason_msg = confidence_scores.get("age", {}).get("reason")
                        if not reason_msg:
                            reason_msg = "Not explicitly stated or found near claimant/deceased name in document"
                        confidence_scores["age"] = {
                            "confidence": 0.0,
                            "reason": reason_msg
                        }
                    else:
                        reason_msg = f"Low confidence LLM value ({llm_age}), fallback failed"
                        confidence_scores["age"] = {
                            "confidence": llm_age_conf,
                            "reason": reason_msg
                        }
        except Exception as age_err:
            logger.error(f"Failed to run English age regex override: {str(age_err)}")

        # ── Claimant Relationship & Marital Status post-processing guard ──
        try:
            if case_type_val == "death":
                cname = data.get("claimant_name")
                dname = data.get("deceased_name")
                rel_type = data.get("claimant_relationship_type") or data.get("claimant_relationship_to_deceased") or ""
                
                # Check for "W/o" or "Wife of" relation to claimant name in the text
                if cname and dname:
                    clean_cname = cname.lower().strip()
                    escaped_cname = re.escape(clean_cname)
                    wo_patterns = [
                        (rf'\bw/o\b[\s,:\(\)-]*(?:smt\.?|mrs\.?)?\s*{escaped_cname}', "prefix"),
                        (rf'\bwife\s+of\s+[\s,:\(\)-]*(?:smt\.?|mrs\.?)?\s*{escaped_cname}', "prefix"),
                        (rf'{escaped_cname}[\s,:\(\)-]*(?:is\s+)?\bw/o\b', "suffix"),
                        (rf'{escaped_cname}[\s,:\(\)-]*(?:is\s+)?\bwife\s+of\b', "suffix")
                    ]
                    
                    is_husband_deceased = False
                    found_wo = False
                    raw_ocr_lower = raw_ocr_text.lower()
                    
                    for pat, pat_type in wo_patterns:
                        for line in raw_ocr_lower.split('\n'):
                            m = re.search(pat, line)
                            if m:
                                found_wo = True
                                husband_candidate = ""
                                if pat_type == "suffix":
                                    suffix_match = re.search(rf'\b(?:w/o|wife\s+of)\b[\s\.]*(?:shri|late)?\s*(.*?)(?:\b(?:age|aged|resident|r/o|address|occupation)\b|$)', line)
                                    if suffix_match:
                                        husband_candidate = suffix_match.group(1).strip()
                                else:
                                    prefix_match = re.search(rf'(.*?)\b(?:w/o|wife\s+of)\b', line)
                                    if prefix_match:
                                        husband_candidate = prefix_match.group(1).strip()
                                
                                husband_candidate = re.sub(r'[\s,\.\-\(\)\/\|]+$', '', husband_candidate).strip()
                                husband_candidate = re.sub(r'^[\s,\.\-\(\)\/\|]+', '', husband_candidate).strip()
                                
                                if husband_candidate and dname:
                                    def clean_name(n):
                                        n = n.lower()
                                        n = re.sub(r'\b(?:late|shri|smt|mr|mrs|sh\.?|deceased)\b', '', n)
                                        n = re.sub(r'[^a-z0-9\s]', '', n)
                                        return [t.strip() for t in n.split() if t.strip()]
                                    t1 = clean_name(husband_candidate)
                                    t2 = clean_name(dname)
                                    if t1 and t2:
                                        overlap = set(t1).intersection(set(t2))
                                        if len(overlap) >= min(len(t1), len(t2), 2):
                                            is_husband_deceased = True
                                            break
                        if is_husband_deceased:
                            break
                    
                    # If the claimant has a W/o descriptor in the document, but the husband is NOT the deceased:
                    # Then the claimant is NOT the wife of the deceased!
                    if found_wo and not is_husband_deceased:
                        logger.info(f"[AI-RECOVERY-GUARD] Claimant has W/o relation in text but husband is NOT the deceased. Overriding relation and marital status.")
                        
                        # Infer the real relationship (e.g. Mother)
                        inferred_rel = None
                        search_text = raw_ocr_lower
                        
                        # Look for "mother of deceased" or similar near claimant first name
                        claimant_fn = ""
                        tokens = [t for t in cname.split() if len(t) > 2]
                        if tokens:
                            claimant_fn = tokens[0].lower()
                            
                        if claimant_fn:
                            pos = 0
                            while True:
                                idx = search_text.find(claimant_fn, pos)
                                if idx == -1:
                                    break
                                w_start = max(0, idx - 100)
                                w_end = min(len(search_text), idx + len(claimant_fn) + 100)
                                window = search_text[w_start:w_end]
                                
                                if re.search(r'\b(?:mother\s+of\s+deceased|mother\s+of\s+the\s+deceased|mother)\b', window):
                                    inferred_rel = "Mother"
                                    break
                                elif re.search(r'\b(?:father\s+of\s+deceased|father\s+of\s+the\s+deceased|father)\b', window):
                                    inferred_rel = "Father"
                                    break
                                pos = idx + len(claimant_fn)
                                
                        if not inferred_rel:
                            if re.search(r'\b(?:claimant\s+is\s+the\s+mother|petitioner\s+is\s+the\s+mother|mother\s+of\s+the\s+deceased|mother\s+of\s+deceased)\b', search_text):
                                inferred_rel = "Mother"
                            elif re.search(r'\b(?:claimant\s+is\s+the\s+father|petitioner\s+is\s+the\s+father|father\s+of\s+the\s+deceased|father\s+of\s+deceased)\b', search_text):
                                inferred_rel = "Father"
                        
                        if inferred_rel:
                            data["claimant_relationship_type"] = inferred_rel
                            data["claimant_relationship_to_deceased"] = inferred_rel
                            confidence_scores["claimant_relationship_type"] = {"confidence": 0.85, "reason": "Inferred from text context after mismatch guard"}
                            confidence_scores["claimant_relationship_to_deceased"] = {"confidence": 0.85, "reason": "Inferred from text context after mismatch guard"}
                        else:
                            data["claimant_relationship_type"] = ""
                            data["claimant_relationship_to_deceased"] = ""
                            confidence_scores["claimant_relationship_type"] = {"confidence": 0.0, "reason": "No relationship to deceased found after mismatch guard"}
                            confidence_scores["claimant_relationship_to_deceased"] = {"confidence": 0.0, "reason": "No relationship to deceased found after mismatch guard"}
                        
                        # Also override marital status if the deceased is young and no spouse is listed
                        age_val = data.get("age")
                        try:
                            age_int = int(age_val) if age_val is not None and age_val != "" else 0
                        except Exception:
                            age_int = 0
                            
                        is_young = (0 < age_int <= 25)
                        has_single_kws = any(kw in raw_ocr_lower for kw in ["unmarried", "bachelor", "single"])
                        
                        if is_young or has_single_kws:
                            data["marital_status"] = "single"
                            confidence_scores["marital_status"] = {"confidence": 0.90, "reason": "Inferred single (young/unmarried deceased with parental claimant)"}
                        else:
                            data["marital_status"] = "unmarried"
                            confidence_scores["marital_status"] = {"confidence": 0.80, "reason": "Inferred unmarried after mismatch guard"}
        except Exception as rel_guard_err:
            logger.error(f"Failed to run relationship post-processing guard: {str(rel_guard_err)}")

        # ── Monthly Income Division post-processing guard ──
        try:
            val = data.get("monthly_income")
            if val is not None and val != "":
                cleaned_val = str(val).replace(",", "").replace(" ", "").strip()
                val_float = float(cleaned_val)
                if val_float > 20000.0:
                    is_annual = False
                    val_str = str(int(val_float))
                    raw_lower = raw_ocr_text.lower()
                    
                    pos = 0
                    while True:
                        idx = raw_lower.find(val_str, pos)
                        if idx == -1:
                            break
                        w_start = max(0, idx - 50)
                        w_end = min(len(raw_lower), idx + len(val_str) + 50)
                        window = raw_lower[w_start:w_end]
                        if any(kw in window for kw in ["annual", "annum", "p.a.", "year", "yearly"]):
                            is_annual = True
                            break
                        pos = idx + len(val_str)
                        
                    if is_annual or val_float > 30000.0:
                        logger.info(f"[AI-RECOVERY-INCOME-GUARD] High monthly_income value ({val_float}) confirmed as annual, dividing by 12.0 -> {val_float / 12.0}")
                        data["monthly_income"] = val_float / 12.0
                        confidence_scores["monthly_income"] = {"confidence": 0.85, "reason": "Converted from annual income to monthly"}
        except Exception as income_err:
            logger.error(f"Failed to run monthly income guard: {str(income_err)}")

        # Actively filter out opposite case type fields to enforce strict gating
        if case_type_val == "injury":
            death_fields = [
                "deceased_name", "claimant_relationship_to_deceased", "claimant_relationship_type",
                "marital_status", "future_prospect", "dependents", "consortium", "funeral_expenses",
                "loss_estate", "conlum", "conspo", "conpar", "conchil", "conwif", "conmo", "confath",
                "conhus", "conbro", "consis", "loss_of_consortium", "loss_of_dependency", "loss_of_love_affection",
                "future_prospects", "dependency", "funeral", "estate", "love_affection"
            ]
            for f in death_fields:
                if f in data:
                    data[f] = None
                if f in confidence_scores:
                    confidence_scores[f] = {"confidence": 0.0}
        elif case_type_val == "death":
            injury_fields = [
                "disability", "disability_percentage", "medical_expenses", "pain_and_suffering",
                "transportation", "special_diet", "attender_charges", "future_medical_expenses",
                "loss_of_income", "coliti", "misex", "loamiti", "lopmarri", "loexlife", "loveaff",
                "lossofenjoy", "loss_of_amenities", "amenities", "medical_expense", "pain_suffering",
                "attendant_charges", "loss_income", "loss_of_earnings"
            ]
            for f in injury_fields:
                if f in data:
                    data[f] = None
                if f in confidence_scores:
                    confidence_scores[f] = {"confidence": 0.0}

        logger.info(f"AI Data Recovery successful with structured confidences: {list(data.keys())}")
        return data
 
    except Exception as e:
        err_msg = "AI-assisted recovery unavailable for this document — please fill remaining fields manually."
        logger.error(f"Failed to parse AI Data Recovery JSON: {str(e)}. Raw response: {response}")
        return {"ai_recovery_error": err_msg, "raw_response_preview": (response[:300] if response else str(e))}