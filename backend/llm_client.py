# backend/llm_client.py
import json
import logging
import urllib.request
import urllib.error
import socket
import re
import time
from datetime import datetime
from rapidfuzz import fuzz
 
from config.llm import LLM_PROVIDER, LLM_MODEL_NAME, LLM_API_KEY, LLM_API_ENDPOINT
 
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LLMClient")

import os as _os
LOG_VERBOSE_GROUNDING_FAILURES = _os.getenv("LOG_VERBOSE_GROUNDING_FAILURES", "false").strip().lower() == "true"

def _redact(text: str, n: int = 24) -> str:
    if LOG_VERBOSE_GROUNDING_FAILURES:
        return text
    text = text or ""
    if len(text) <= n * 2:
        return text
    return f"{text[:n]}...[REDACTED]...{text[-n:]}"
 
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
 
def generate_response(prompt: str, system_instruction: str = None, response_format: str = None, history: list[dict] | None = None, model: str = None, temperature: float = None) -> str:
    effective_model = model or LLM_MODEL_NAME
    effective_temperature = 0.2 if temperature is None else temperature
    logger.info(f"Generating LLM response using provider '{LLM_PROVIDER}', model '{effective_model}', temperature {effective_temperature}")
    
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
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{effective_model}:generateContent?key={LLM_API_KEY}"
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
            
            generation_config = {}
            if response_format == "json":
                generation_config["responseMimeType"] = "application/json"
            if effective_temperature is not None:
                generation_config["temperature"] = effective_temperature
            if generation_config:
                payload["generationConfig"] = generation_config
                
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
                    "model": effective_model, 
                    "messages": messages, 
                    "temperature": effective_temperature,
                    "options": {"temperature": effective_temperature, "keep_alive": "10m", "num_ctx": 16384}
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
                    "model": effective_model, 
                    "messages": messages, 
                    "stream": False, 
                    "options": {"temperature": effective_temperature, "keep_alive": "10m", "num_ctx": 16384}
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
            payload = {"model": effective_model, "messages": messages, "temperature": effective_temperature}
            if response_format == "json":
                payload["response_format"] = {"type": "json_object"}
            req_body = json.dumps(payload).encode("utf-8")
 
        req = urllib.request.Request(url, data=req_body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=240.0) as response:
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
            logger.error("LLM Request timed out after 240 seconds.")
            return "Error connecting to LLM server: Request timed out after 240 seconds"
        
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
            with urllib.request.urlopen(req, timeout=240.0) as response:
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
            logger.error("LLM Stream Request timed out after 240 seconds.")
            yield "Error communicating with LLM stream: Request timed out after 240 seconds"
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

            is_blocked = False
            matched_phrase = None
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

 
        # ── Canonicalise every date field to strict DD-MM-YYYY & verify against raw OCR text ─────────────
        for _date_key in ("dob", "date_of_birth", "accident_date", "date_of_accident", "decision_date"):
            if data.get(_date_key):
                norm_date = normalize_date_to_ddmmyyyy(data[_date_key])
                orig_date = str(data[_date_key]).strip()
                # Strict verification: date of birth must appear in source text to prevent guessing
                if _date_key in ("dob", "date_of_birth") and raw_ocr_text:
                    if norm_date not in raw_ocr_text and orig_date not in raw_ocr_text:
                        logger.info(f"[DOB-HALLUCINATION-GUARD] Discarding unverified DOB '{orig_date}' (norm: '{norm_date}') not present in OCR text.")
                        data[_date_key] = None
                        confidence_scores[_date_key] = {"confidence": 0.0}
                    else:
                        data[_date_key] = norm_date
                else:
                    data[_date_key] = norm_date

        # ── Disability anti-hallucination & case-type guard ──────────────
        dis_val = data.get("disability_percentage") or data.get("disability")
        if case_type == "death":
            data["disability_percentage"] = None
            data["disability"] = None
            confidence_scores["disability_percentage"] = {"confidence": 0.0}
            confidence_scores["disability"] = {"confidence": 0.0}
        elif dis_val is not None and raw_ocr_text:
            dis_str = str(dis_val).strip()
            # Normalize "35.0" / "35" so both forms are checked
            try:
                dis_str_int = str(int(float(dis_str)))
            except (ValueError, TypeError):
                dis_str_int = dis_str
            # STRICT CHECK: the exact percentage figure itself must appear literally in
            # the OCR text. Previously this also allowed the value through if the mere
            # word "disability" appeared anywhere in the document -- but that word is
            # almost always present somewhere (statute references, boilerplate, headers)
            # even when no percentage was ever stated, which let hallucinated numbers
            # (e.g. a stray "35") slip through untouched. Require the actual figure.
            number_present = (
                dis_str in raw_ocr_text
                or dis_str_int in raw_ocr_text
                or f"{dis_str}%" in raw_ocr_text
                or f"{dis_str_int}%" in raw_ocr_text
            )
            if not number_present:
                logger.info(f"[DISABILITY-HALLUCINATION-GUARD] Discarding unverified disability '{dis_str}' -- this exact figure was not found anywhere in the OCR text.")
                data["disability_percentage"] = None
                data["disability"] = None
                confidence_scores["disability_percentage"] = {"confidence": 0.0}
                confidence_scores["disability"] = {"confidence": 0.0}

 
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


# ======================================================
# FEATURE 1: APPEAL GROUNDS & RELIEF SUMMARY
# ======================================================

class BoundedCache(dict):
    """Size-bounded in-memory LRU cache to prevent memory growth and retain PII ephemerally, with TTL."""
    def __init__(self, maxsize=200, ttl=3600):
        super().__init__()
        self.maxsize = maxsize
        self.ttl = ttl
        self._keys = []

    def __setitem__(self, key, value):
        if key in self:
            self._keys.remove(key)
        self._keys.append(key)
        if len(self._keys) > self.maxsize:
            oldest = self._keys.pop(0)
            super().pop(oldest, None)
        super().__setitem__(key, (time.time(), value))

    def __getitem__(self, key):
        self._prune_key_if_expired(key)
        _, value = super().__getitem__(key)
        # Move to end to maintain LRU
        self._keys.remove(key)
        self._keys.append(key)
        return value

    def __contains__(self, key):
        self._prune_key_if_expired(key)
        return super().__contains__(key)

    def get(self, key, default=None):
        if key in self:
            return self[key]
        return default

    def pop(self, key, default=None):
        self._prune_key_if_expired(key)
        if key in self:
            self._keys.remove(key)
            _, val = super().pop(key)
            return val
        return default

    def _prune_key_if_expired(self, key):
        if super().__contains__(key):
            timestamp, _ = super().__getitem__(key)
            if time.time() - timestamp > self.ttl:
                if key in self._keys:
                    self._keys.remove(key)
                super().pop(key, None)


_SUMMARY_CACHE = BoundedCache(maxsize=200)
_TRANSLATION_CACHE = BoundedCache(maxsize=200)
_FINAL_SUMMARY_CACHE = BoundedCache(maxsize=200)


def validate_final_summary_shape(raw_data: dict) -> bool:
    if not isinstance(raw_data, dict):
        return False
    if not all(k in raw_data for k in ("issue_wise_view", "final_summary_points", "probable_outcome")):
        return False
    if not isinstance(raw_data["issue_wise_view"], list):
        return False
    if not isinstance(raw_data["final_summary_points"], list):
        return False
        
    valid_outcomes = {"enhancement", "reduction", "exoneration", "upheld", "not_determinable"}
    outcome = str(raw_data.get("probable_outcome", "")).lower().strip()
    if outcome not in valid_outcomes:
        if "enhance" in outcome or "increase" in outcome:
            raw_data["probable_outcome"] = "enhancement"
        elif "reduc" in outcome or "lower" in outcome:
            raw_data["probable_outcome"] = "reduction"
        elif "exonerat" in outcome or "set aside" in outcome:
            raw_data["probable_outcome"] = "exoneration"
        elif "upheld" in outcome or "dismiss" in outcome:
            raw_data["probable_outcome"] = "upheld"
        else:
            raw_data["probable_outcome"] = "not_determinable"
            
    for entry in raw_data["issue_wise_view"]:
        if not isinstance(entry, dict):
            return False
        for k in ("issue", "trial_court_finding", "hc_ground_challenge", "likely_judicial_view"):
            entry.setdefault(k, "")
            
    if "factual_discrepancies" not in raw_data or not isinstance(raw_data.get("factual_discrepancies"), list):
        raw_data["factual_discrepancies"] = []
    if not isinstance(raw_data.get("rejected_candidate_claims"), list):
        raw_data["rejected_candidate_claims"] = []
        
    return True


def _verify_final_summary_grounding(summary: dict, source_text: str) -> dict:
    """Same numeric-grounding check as _verify_summary_grounding(), applied to
    likely_judicial_view / trial_court_finding / final_summary_points."""
    if not summary or not isinstance(summary, dict):
        return summary
        
    source_normalized = (source_text or "").lower().replace(",", "")
    source_digits = re.sub(r"\D", "", source_text or "")
    
    def _numbers(s: str) -> list:
        return re.findall(r"\b[a-zA-Z]*\d+[\w\d\.,\-%/]*\b", s or "")
        
    def _clean_list(items: list) -> list:
        out = []
        for item in items:
            bad = None
            for raw in _numbers(item):
                digits = re.sub(r"\D", "", raw)
                raw_normalized = raw.lower().replace(",", "")
                if digits and len(digits) >= 2 and digits not in source_digits and raw_normalized not in source_normalized:
                    bad = raw
                    logger.warning(f"[FINAL-SUMMARY GROUNDING CHECK] Unverified number '{raw}' in text snippet: {_redact(item)}")
                    break
            out.append(item.replace(bad, "[figure unverified]") if bad else item)
        return out

    if "final_summary_points" in summary and isinstance(summary["final_summary_points"], list):
        summary["final_summary_points"] = _clean_list(summary["final_summary_points"])
        
    if "issue_wise_view" in summary and isinstance(summary["issue_wise_view"], list):
        for entry in summary["issue_wise_view"]:
            if isinstance(entry, dict):
                for fld in ("trial_court_finding", "hc_ground_challenge", "likely_judicial_view"):
                    if entry.get(fld):
                        entry[fld] = _clean_list([entry[fld]])[0]
                        
    if "factual_discrepancies" in summary and isinstance(summary["factual_discrepancies"], list):
        for entry in summary["factual_discrepancies"]:
            if isinstance(entry, dict) and entry.get("note"):
                entry["note"] = _clean_list([entry["note"]])[0]
    return summary


def validate_summary_shape(raw_data: dict) -> bool:
    if not isinstance(raw_data, dict):
        return False
    expected_keys = {
        "case_overview", "appeal_direction", "grounds_of_appeal", "relief_sought", "key_figures_cited"
    }
    if not all(k in raw_data for k in expected_keys):
        return False

    direction_str = str(raw_data.get("appeal_direction", "")).lower().strip()
    if "enhance" in direction_str or "increase" in direction_str:
        raw_data["appeal_direction"] = "enhancement"
    elif "reduc" in direction_str or "decrease" in direction_str or "lower" in direction_str:
        raw_data["appeal_direction"] = "reduction"
    elif "exonerat" in direction_str or "set aside" in direction_str or "no liability" in direction_str:
        raw_data["appeal_direction"] = "exoneration"
    elif "not" in direction_str or "unclear" in direction_str or "unknown" in direction_str:
        raw_data["appeal_direction"] = "not_determinable"
    
    valid_directions = {"enhancement", "reduction", "exoneration", "not_determinable"}
    if raw_data.get("appeal_direction") not in valid_directions:
        return False

    if not isinstance(raw_data.get("grounds_of_appeal"), list):
        return False
    if not isinstance(raw_data.get("relief_sought"), list):
        return False
    if not isinstance(raw_data.get("key_figures_cited"), list):
        return False
    return True


def _verify_summary_grounding(summary: dict, source_text: str) -> dict:
    if not summary or not isinstance(summary, dict):
        return summary
    source_normalized = source_text.lower().replace(",", "")
    
    def extract_numbers(s: str) -> list:
        tokens = re.findall(r'\b[a-zA-Z]*\d+[\w\d\.,\-%/]*\b|\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b', s)
        numeric_tokens = []
        for t in tokens:
            cleaned = re.sub(r'[^\d\.\-]', '', t)
            if cleaned:
                numeric_tokens.append((t, cleaned))
        return numeric_tokens

    # Verify key_figures_cited
    if "key_figures_cited" in summary and isinstance(summary["key_figures_cited"], list):
        verified_figures = []
        for fig in summary["key_figures_cited"]:
            nums = extract_numbers(fig)
            fig_valid = True
            for raw, norm in nums:
                digits = re.sub(r'\D', '', norm)
                if not digits:
                    continue
                if norm not in source_normalized and digits not in source_normalized:
                    fig_valid = False
                    logger.warning(f"[GROUNDING CHECK FAILED] Figure '{raw}' (normalized: '{norm}') from: {_redact(fig)}")
                    break
            if fig_valid:
                verified_figures.append(fig)
        summary["key_figures_cited"] = verified_figures

    # Verify grounds_of_appeal
    if "grounds_of_appeal" in summary and isinstance(summary["grounds_of_appeal"], list):
        verified_grounds = []
        for ground in summary["grounds_of_appeal"]:
            nums = extract_numbers(ground)
            ground_valid = True
            offending_raw = None
            for raw, norm in nums:
                digits = re.sub(r'\D', '', norm)
                if not digits:
                    continue
                if norm not in source_normalized and digits not in source_normalized:
                    ground_valid = False
                    offending_raw = raw
                    logger.warning(f"[GROUNDING CHECK FAILED] Numeric figure '{raw}' (normalized: '{norm}') in ground: {_redact(ground)}")
                    break
            if ground_valid:
                verified_grounds.append(ground)
            else:
                rewritten = ground.replace(offending_raw, "[figure unverified]")
                logger.warning(f"[GROUNDING REWRITE] Ground bullet rewritten from: {_redact(ground)} to: {_redact(rewritten)} due to unverified figure '{offending_raw}'")
                verified_grounds.append(rewritten)
        summary["grounds_of_appeal"] = verified_grounds

    # Verify relief_sought
    if "relief_sought" in summary and isinstance(summary["relief_sought"], list):
        verified_relief = []
        for relief in summary["relief_sought"]:
            nums = extract_numbers(relief)
            relief_valid = True
            offending_raw = None
            for raw, norm in nums:
                digits = re.sub(r'\D', '', norm)
                if not digits:
                    continue
                if norm not in source_normalized and digits not in source_normalized:
                    relief_valid = False
                    offending_raw = raw
                    logger.warning(f"[GROUNDING CHECK FAILED] Numeric figure '{raw}' (normalized: '{norm}') in relief: {_redact(relief)}")
                    break
            if relief_valid:
                verified_relief.append(relief)
            else:
                rewritten = relief.replace(offending_raw, "[figure unverified]")
                logger.warning(f"[GROUNDING REWRITE] Relief bullet rewritten from: {_redact(relief)} to: {_redact(rewritten)} due to unverified figure '{offending_raw}'")
                verified_relief.append(rewritten)
        summary["relief_sought"] = verified_relief

    return summary

def _synthesize_human_summary_points(raw_lines: list, is_relief: bool = False, verdict: str = "not_determinable") -> list:
    synthesized = []
    prefix_cleaner = re.compile(
        r'^(That,?\s*|That the\s+|Because the\s+|1\.\s*|2\.\s*|3\.\s*|4\.\s*|5\.\s*|[A-Z]\.\s*|\([a-z0-9]+\)\s*)+',
        re.IGNORECASE
    )
    noise_re = re.compile(r'limitation period|copying|total days|compliance period|order\)\s*\d|verbatim', re.IGNORECASE)

    for line in (raw_lines or []):
        if not line or not str(line).strip():
            continue
        cleaned = prefix_cleaner.sub('', str(line).strip()).strip()
        cleaned = noise_re.sub('', cleaned).strip()
        if len(cleaned) < 10:
            continue
        # Capitalize first letter cleanly
        cleaned = cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()
        # Truncate overly long single run-on lines to 1-2 clear sentences
        if len(cleaned) > 220:
            end_match = re.search(r'[\.\;]\s+', cleaned[100:])
            if end_match:
                cleaned = cleaned[:100 + end_match.start() + 1]
        if cleaned not in synthesized:
            synthesized.append(cleaned)

    # Ensure targeted count and human fallback if input points are sparse
    if not is_relief:
        # Grounds: target 3-4 points
        if len(synthesized) == 0:
            if verdict == "enhancement":
                synthesized = [
                    "Challenged the Tribunal's assessment of monthly income and future prospects as inadequate.",
                    "Disputed the calculation of multiplier and non-pecuniary compensation heads.",
                    "Claimed Tribunal failed to award just and reasonable compensation under standard precedents."
                ]
            elif verdict == "reduction":
                synthesized = [
                    "Challenged Tribunal award on grounds of excessive quantum and incorrect income assessment.",
                    "Disputed liability and coverage under the terms of the insurance policy.",
                    "Contended contributory negligence was improperly disregarded by the Tribunal."
                ]
            else:
                synthesized = [
                    "Appealed against Tribunal judgment on grounds of flawed quantum assessment.",
                    "Disputed evidence evaluation regarding income, age, and multiplier applied.",
                    "Challenged liability allocation and statutory interest rate awarded."
                ]
        elif len(synthesized) < 3:
            if verdict == "enhancement":
                synthesized.append("Sought enhancement of award based on miscalculation of income and future prospects.")
                synthesized.append("Disputed adequacy of non-pecuniary damages awarded under established legal principles.")
            else:
                synthesized.append("Challenged legal and factual findings of the Tribunal regarding overall compensation.")
        return synthesized[:4]
    else:
        # Relief: target 2-3 points
        if len(synthesized) == 0:
            if verdict == "enhancement":
                synthesized = [
                    "Prayer for enhancement of overall compensation award.",
                    "Grant of standard statutory interest rate from the date of filing petition."
                ]
            elif verdict == "reduction":
                synthesized = [
                    "Prayer to set aside or reduce the impugned compensation award.",
                    "Exoneration or restriction of insurance company liability."
                ]
            else:
                synthesized = [
                    "Prayer for modification/setting aside of the impugned Tribunal judgment.",
                    "Grant of appropriate relief and costs of the appeal."
                ]
        elif len(synthesized) < 2:
            synthesized.append("Grant of just compensation with interest and costs of proceedings.")
        return synthesized[:3]

def summarize_grounds_and_relief(sections: dict, heuristic_signal: dict, case_type: str) -> dict:
    """
    Generates an LLM summary of the appeal grounds and prayer.
    Uses generate_response with JSON mode.
    """
    import hashlib

    # 1. Input fallbacks
    memo_text = sections.get("memo_of_appeal_section", "") or ""
    grounds_text = sections.get("grounds_section", "") or sections.get("facts_section", "") or ""
    if not grounds_text.strip():
        grounds_text = memo_text
        
    relief_text = sections.get("relief_section", "") or ""
    if not relief_text.strip():
        relief_text = sections.get("facts_section", "") or memo_text
        
    if not grounds_text.strip() and not relief_text.strip():
        grounds_text = sections.get("raw_ocr", "")
        relief_text = ""

    # 2. Cache check
    concat_text = f"{grounds_text}|||{relief_text}"
    h = hashlib.sha256(concat_text.encode("utf-8")).hexdigest()
    if h in _SUMMARY_CACHE:
        logger.info("[APPEAL-SUMMARY] Returning cached summary.")
        return _SUMMARY_CACHE[h]

    # 3. Import prompts and configurations
    from config.llm import (
        APPEAL_SUMMARY_SYSTEM_INSTRUCTION, APPEAL_SUMMARY_USER_PROMPT, LLM_SUMMARY_TEMPERATURE
    )

    # 4. Construct prompt context
    heuristic_context = ""
    if heuristic_signal:
        verdict = heuristic_signal.get("verdict", "unclear")
        confidence = heuristic_signal.get("confidence", 0.0)
        basis = heuristic_signal.get("basis", "no_signal")
        heuristic_context = (
            f"Pattern Engine Initial Classification (Heuristic Signal):\n"
            f"- Suggested Verdict: {verdict}\n"
            f"- Confidence Score: {confidence}\n"
            f"- Classification Basis: {basis}\n"
            f"- Grounds matched snippet: {heuristic_signal.get('grounds_signal', {}).get('snippet', 'None')}\n"
            f"- Relief matched snippet: {heuristic_signal.get('relief_signal', {}).get('snippet', 'None')}\n"
            f"Please use this pattern engine classification as a supporting sanity check context. Do not blindly trust it."
        )

    prompt_base = APPEAL_SUMMARY_USER_PROMPT.format(
        grounds_text=grounds_text[:4000],
        relief_text=relief_text[:4000]
    )
    if heuristic_context:
        prompt_base += "\n\n" + heuristic_context

    current_prompt = prompt_base
    attempts = 2
    success = False
    result_dict = {}

    for attempt in range(attempts):
        try:
            # We override or pass parameters for the LLM if needed.
            # generate_response uses the global LLM config parameters.
            response = generate_response(
                prompt=current_prompt,
                system_instruction=APPEAL_SUMMARY_SYSTEM_INSTRUCTION,
                response_format="json"
            )

            # Direct parse & shape validation
            start_idx = response.find("{")
            end_idx = response.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                candidate = response[start_idx:end_idx+1]
            else:
                candidate = response

            parsed = json.loads(candidate)
            if validate_summary_shape(parsed):
                source_full_text = grounds_text + "\n" + relief_text
                verified = _verify_summary_grounding(parsed, source_full_text)
                result_dict = verified
                result_dict["summary_source"] = "llm_summary"
                success = True
                break
            else:
                logger.warning(f"[APPEAL-SUMMARY] Attempt {attempt+1} parsed JSON failed shape/enum validation.")
        except Exception as e:
            logger.warning(f"[APPEAL-SUMMARY] Attempt {attempt+1} failed: {e}")

        current_prompt = prompt_base + "\n\nREMINDER: your last response was invalid. Return ONLY a valid JSON matching the schema, with strict enum appeal_direction: 'enhancement' | 'reduction' | 'exoneration' | 'not_determinable'."

    if success:
        _SUMMARY_CACHE[h] = result_dict
        return result_dict
    else:
        # Synthesize clean human summary points for fallback
        g_pts_raw = heuristic_signal.get("grounds_points", []) if heuristic_signal else []
        r_pts_raw = heuristic_signal.get("relief_points", []) if heuristic_signal else []
        verdict = heuristic_signal.get("verdict", "not_determinable") if heuristic_signal else "not_determinable"

        cleaned_grounds = _synthesize_human_summary_points(g_pts_raw, is_relief=False, verdict=verdict)
        cleaned_relief = _synthesize_human_summary_points(r_pts_raw, is_relief=True, verdict=verdict)

        fallback_summary = {
            "case_overview": "Case summary synthesized from extracted document points.",
            "appeal_direction": verdict,
            "grounds_of_appeal": cleaned_grounds,
            "relief_sought": cleaned_relief,
            "key_figures_cited": [],
            "confidence": heuristic_signal.get("confidence", 0.5) if heuristic_signal else 0.5,
            "summary_source": "heuristic_fallback"
        }

        _SUMMARY_CACHE[h] = fallback_summary
        return fallback_summary


def validate_factual_discrepancies_shape(items) -> list:
    if not isinstance(items, list):
        return []
    cleaned = []
    for it in items:
        if not isinstance(it, dict) or not it.get("claim"):
            continue
        cleaned.append({
            "claim": str(it.get("claim", "")),
            "found_in_grounds": bool(it.get("found_in_grounds", True)),
            "found_in_trial_court": bool(it.get("found_in_trial_court", False)),
            "note": str(it.get("note", "")),
        })
    return cleaned


def translate_trial_court_text(issues_text: str, award_text: str) -> dict:
    """One LLM call: translates Hindi/mixed trial-court text into precise legal
    English. This is what replaces the fixed bilingual keyword dictionary --
    everything downstream (claim extraction, matching) now works on plain
    English, so it isn't limited to a hardcoded synonym list."""
    import hashlib
    from config.llm import (
        TRIAL_COURT_TRANSLATION_SYSTEM_INSTRUCTION, TRIAL_COURT_TRANSLATION_USER_PROMPT,
        LLM_TRANSLATION_MODEL_NAME, LLM_TRANSLATION_TEMPERATURE
    )
    issues_text = (issues_text or "").strip()
    award_text = (award_text or "").strip()
    if not issues_text and not award_text:
        return {"issues_en": "", "award_en": ""}

    h = hashlib.sha256(f"{issues_text}|||{award_text}".encode("utf-8")).hexdigest()
    if h in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[h]

    prompt = TRIAL_COURT_TRANSLATION_USER_PROMPT.format(
        issues_text=issues_text[:4000], award_text=award_text[:3000]
    )
    # Safe fallback: if translation fails twice, downstream code still gets the
    # original text rather than an empty string -- degrades to "no translation"
    # instead of "no data".
    result = {"issues_en": issues_text, "award_en": award_text}
    for attempt in range(2):
        try:
            response = generate_response(
                prompt=prompt,
                system_instruction=TRIAL_COURT_TRANSLATION_SYSTEM_INSTRUCTION,
                response_format="json",
                model=LLM_TRANSLATION_MODEL_NAME,
                temperature=LLM_TRANSLATION_TEMPERATURE
            )
            s = response.find("{"); e = response.rfind("}")
            candidate = response[s:e+1] if s != -1 and e != -1 and e > s else response
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and parsed.get("issues_en") and parsed.get("award_en"):
                result = {"issues_en": parsed["issues_en"], "award_en": parsed["award_en"]}
                break
        except Exception as ex:
            logger.warning(f"[TRIAL-COURT-TRANSLATION] attempt {attempt + 1} failed: {ex}")

    _TRANSLATION_CACHE[h] = result
    return result


def validate_claims_shape(items) -> list:
    if not isinstance(items, list):
        return []
    valid_categories = {"injury", "death", "vehicle_damage", "income", "disability", "dependency", "other"}
    cleaned = []
    for it in items:
        if not isinstance(it, dict) or not it.get("claim"):
            continue
        cat = str(it.get("category", "other")).strip().lower()
        if cat not in valid_categories:
            cat = "other"
        cleaned.append({
            "claim": str(it.get("claim", "")).strip(),
            "category": cat,
            "text_span": str(it.get("text_span", "")).strip(),
        })
    return cleaned


def extract_claims(text: str, case_type: str = "death", source_label: str = "") -> dict:
    """Replaces the fixed injury dictionary's job of 'what facts are we even
    looking for'. Works for injury, death, vehicle-damage, income, dependency
    claims -- whatever's actually in this document -- instead of a fixed list."""
    from config.llm import (
        CLAIM_EXTRACTION_SYSTEM_INSTRUCTION, CLAIM_EXTRACTION_USER_PROMPT,
        LLM_CLAIM_EXTRACTION_MODEL_NAME, LLM_CLAIM_EXTRACTION_TEMPERATURE
    )
    text = (text or "").strip()
    if not text:
        return {"claims": []}

    prompt = CLAIM_EXTRACTION_USER_PROMPT.format(
        case_type=case_type, source_label=source_label, text=text[:6000]
    )
    for attempt in range(2):
        try:
            response = generate_response(
                prompt=prompt,
                system_instruction=CLAIM_EXTRACTION_SYSTEM_INSTRUCTION,
                response_format="json",
                model=LLM_CLAIM_EXTRACTION_MODEL_NAME,
                temperature=LLM_CLAIM_EXTRACTION_TEMPERATURE
            )
            s = response.find("{"); e = response.rfind("}")
            candidate = response[s:e+1] if s != -1 and e != -1 and e > s else response
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and isinstance(parsed.get("claims"), list):
                return parsed
        except Exception as ex:
            logger.warning(f"[CLAIM-EXTRACTION] attempt {attempt + 1} failed ({source_label}): {ex}")
    return {"claims": []}


_ISSUE_ANCHOR_RE = re.compile(r"(वादप्रश्न|वाद\s*प्रश्न)\s*(क्र?\.?|क0|no\.?)?\s*1\b")
_OPERATIVE_ANCHOR_RE = re.compile(r"(अधिनिर्णय|आदेश)\s*(खुले न्यायालय|पारित)")

def _split_lower_court_text(text: str):
    issue_m = _ISSUE_ANCHOR_RE.search(text)
    op_m = None
    for m in _OPERATIVE_ANCHOR_RE.finditer(text):
        op_m = m  # last match = final operative order, not a heading mention
    if issue_m and op_m and op_m.start() > issue_m.start():
        return text[issue_m.start():op_m.start()], text[op_m.start():]
    return None, None  # no reliable anchors — caller should NOT guess-split


def classify_doc_type_via_llm(text: str) -> str:
    """Uses LLM to classify document contents as either 'lower_court' (tribunal judgment) or 'hospital_record' / other."""
    system_instruction = (
        "You are a legal and medical document classifier. Your job is to analyze the provided document text "
        "and determine if it is a 'lower_court' (MACT tribunal judgment, issues framed, award details) "
        "or a 'hospital_record' (medical bills, discharge summaries, treatment reports, prescriptions, disability certificates) "
        "or 'other' (FIR copy, insurance policy, etc.).\n"
        "Return a JSON object with a single key 'doc_type' whose value is either 'lower_court', 'hospital_record', or 'other'."
    )
    user_prompt = (
        f"Classify the following document content. Return ONLY JSON conforming to the requested schema:\n\n"
        f"{text[:5000]}"
    )
    try:
        from config.llm import LLM_FINAL_SUMMARY_MODEL_NAME
        response = generate_response(
            prompt=user_prompt,
            system_instruction=system_instruction,
            response_format="json",
            model=LLM_FINAL_SUMMARY_MODEL_NAME,
            temperature=0.1
        )
        response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
        s = response.find("{")
        e = response.rfind("}")
        candidate = response[s:e+1] if s != -1 and e != -1 and e > s else response
        parsed = json.loads(candidate)
        return parsed.get("doc_type", "other")
    except Exception as e:
        logger.error(f"classify_doc_type_via_llm failed: {e}")
        return "other"


def _looks_like_tribunal_judgment(text: str) -> bool:
    """Heuristic + LLM fallback to check if the text contents resemble a MACT tribunal judgment."""
    if not text:
        return False
    keywords = [
        "अधिकरण", "न्यायाधिकरण", "मोटर दुर्घटना", "दावा याचिका", "याचिकाकर्ता", "विपक्षी", 
        "mact", "tribunal", "motor accident", "claim petition", "issues", "award", "judgment",
        "वादप्रश्न", "वाद प्रश्न", "अधिनिर्णय", "पंचाट"
    ]
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw in text_lower)
    if hits >= 3:
        return True
    doc_type = classify_doc_type_via_llm(text)
    return doc_type == "lower_court"


def classify_sections_via_llm(full_text: str) -> dict:
    """Uses LLM to identify the main text spans of the core document sections when keyword matching fails."""
    system_instruction = (
        "You are an expert Indian court document parser. Your job is to extract the exact text blocks "
        "belonging to the main structural sections from the provided document text. "
        "Return a JSON object with the following keys:\n"
        "- grounds_section: Text explaining the grounds of appeal/challenge (or empty string)\n"
        "- relief_section: Text of the relief claimed or prayer (or empty string)\n"
        "- issues_findings_section: Text of issues framed, points for determination, or findings (or empty string)\n"
        "- award_operative_section: Text of the final award amount calculation table, order, or operative details (or empty string)\n"
        "Do not summarize or paraphrase the text. Extract the relevant text spans verbatim from the input text."
    )
    user_prompt = (
        f"Extract the sections from the following document text. Return ONLY JSON conforming to the requested schema:\n\n"
        f"{full_text[:12000]}"
    )
    try:
        from config.llm import LLM_FINAL_SUMMARY_MODEL_NAME
        response = generate_response(
            prompt=user_prompt,
            system_instruction=system_instruction,
            response_format="json",
            model=LLM_FINAL_SUMMARY_MODEL_NAME,
            temperature=0.1
        )
        response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
        s = response.find("{")
        e = response.rfind("}")
        candidate = response[s:e+1] if s != -1 and e != -1 and e > s else response
        parsed = json.loads(candidate)
        
        sections = {}
        for sec_name in ["grounds_section", "relief_section", "issues_findings_section", "award_operative_section"]:
            content = (parsed.get(sec_name) or "").strip()
            if content:
                sections[sec_name] = {
                    "section_name": sec_name,
                    "start_page": 1,
                    "end_page": 1,
                    "content": content,
                    "strong_match": True
                }
        return sections
    except Exception as e:
        logger.error(f"classify_sections_via_llm failed: {e}")
        return None


def find_missing_claims(grounds_claims: list, trial_claims: list, match_threshold: float = 72.0) -> list:
    """Deterministic fuzzy matcher: for every claim raised in the HC grounds of
    appeal / relief, check whether a sufficiently similar claim was actually
    addressed in the trial court issues/award text. Anything that doesn't
    clear the threshold against ANY trial claim is surfaced as a candidate
    factual discrepancy for the LLM to confirm or reject -- this is what
    populates `candidate_discrepancies` in generate_final_judicial_summary.

    Returns a list already shaped like validate_factual_discrepancies_shape
    expects: {"claim", "category", "found_in_grounds", "found_in_trial_court", "note"}.
    """
    if not isinstance(grounds_claims, list) or not grounds_claims:
        return []
    if not isinstance(trial_claims, list):
        trial_claims = []

    candidates = []
    for g in grounds_claims:
        if not isinstance(g, dict):
            continue
        g_claim = str(g.get("claim", "")).strip()
        if not g_claim:
            continue
        g_category = str(g.get("category", "other"))

        best_score = 0.0
        for t in trial_claims:
            if not isinstance(t, dict):
                continue
            t_claim = str(t.get("claim", "")).strip()
            if not t_claim:
                continue
            score = max(
                fuzz.partial_ratio(g_claim.lower(), t_claim.lower()),
                fuzz.token_set_ratio(g_claim.lower(), t_claim.lower()),
            )
            if score > best_score:
                best_score = score
            if best_score >= match_threshold:
                break  # good enough match found, no need to keep scanning

        if best_score < match_threshold:
            candidates.append({
                "claim": g_claim,
                "category": g_category,
                "found_in_grounds": True,
                "found_in_trial_court": False,
                "note": (
                    "Raised in HC grounds/relief but no comparable claim found in the "
                    f"trial court issues/award (best fuzzy match score={best_score:.0f})."
                ),
            })

    return candidates


def generate_final_judicial_summary(sections: dict, heuristic_signal: dict = None, case_type: str = "death", supporting_docs: dict = None, force_refresh: bool = False) -> dict:
    import hashlib
    from backend.parser_heuristics import normalize_issues_table
    from config.llm import (
        FINAL_JUDICIAL_SUMMARY_SYSTEM_INSTRUCTION,
        FINAL_JUDICIAL_SUMMARY_USER_PROMPT,
        LLM_FINAL_SUMMARY_TEMPERATURE,
        LLM_FINAL_SUMMARY_MODEL_NAME
    )

    issues_raw = (sections.get("issues_findings_section", "") or "").strip()
    award_text_raw = (sections.get("award_operative_section", "") or sections.get("award_copy_section", "") or "").strip()
    grounds_text = (sections.get("grounds_section", "") or sections.get("memo_of_appeal_section", "") or "").strip()
    relief_text = (sections.get("relief_section", "") or "").strip()

    medical_evidence_text = ""
    if supporting_docs and supporting_docs.get("medical_evidence"):
        medical_evidence_text = supporting_docs["medical_evidence"]
    else:
        medical_evidence_text = "(No supporting documents/medical evidence provided.)"

    summary_src = "llm_summary"

    if supporting_docs and supporting_docs.get("lower_court"):
        lower_court_text = supporting_docs["lower_court"]
        
        # 1. Content validation guard
        if not _looks_like_tribunal_judgment(lower_court_text):
            message = (
                "The uploaded document tagged as 'Lower Court Judgment' does not appear to "
                "be a valid trial court judgment -- it lacks expected tribunal layout/keywords. "
                "Please verify the file and ensure it is uploaded under the correct document type."
            )
            return {
                "issue_wise_view": [],
                "final_summary_points": [message],
                "probable_outcome": heuristic_signal.get("verdict", "not_determinable") if heuristic_signal else "not_determinable",
                "factual_discrepancies": [],
                "summary_source": "mislabeled_input"
            }

        from backend.parser_heuristics import detect_document_sections_with_fallback, classify_page_type, segment_text_lines_into_pages

        lc_pages = segment_text_lines_into_pages(lower_court_text.split("\n"))
        lc_sections_meta = detect_document_sections_with_fallback(lower_court_text, lc_pages)
        lc_sections = {k: v["content"] for k, v in lc_sections_meta.items()}
        lc_issues_raw = (lc_sections.get("issues_findings_section", "") or "").strip()
        lc_award_raw = (lc_sections.get("award_operative_section", "") or lc_sections.get("award_copy_section", "") or "").strip()

        # pull out attached exhibit/annexure
        lc_attachment_text = ""
        pages = [p.strip() for p in lower_court_text.split("\f") if p.strip()]  # or however pages are delimited
        attachment_pages = [p for p in pages if classify_page_type(p, 0) in ("annexure", "evidence")]
        if attachment_pages:
            lc_attachment_text = "\n---\n".join(attachment_pages)

        # Determine issues and award texts
        if not lc_issues_raw and not lc_award_raw:
            anchors_issues, anchors_award = _split_lower_court_text(lower_court_text)
            if anchors_issues and anchors_award:
                lc_issues_raw = anchors_issues
                lc_award_raw = anchors_award
                summary_src = "structural_anchor_split"
            else:
                # fall back to the 70/30 split as a last resort
                split_point = int(len(lower_court_text) * 0.7)
                lc_issues_raw = lower_court_text[:split_point]
                lc_award_raw = lower_court_text[split_point:]
                summary_src = "guess_split_70_30"
        else:
            summary_src = "parsed_sections"

        translation = translate_trial_court_text(lc_issues_raw, lc_award_raw)
        issues_text_en = translation.get("issues_en") or lc_issues_raw
        award_text_en = translation.get("award_en") or lc_award_raw

        # fold attachments into medical_evidence_text instead of overwriting it
        if lc_attachment_text:
            medical_evidence_text = (medical_evidence_text + "\n\n[From lower court record attachments]\n" + lc_attachment_text).strip()
    else:
        logger.info(
            f"[JUDICIAL-ANALYSIS] issues_raw_len={len(issues_raw)}, award_text_raw_len={len(award_text_raw)}, "
            f"has_lower_court_supporting_doc={bool(supporting_docs and supporting_docs.get('lower_court'))}"
        )
        if not issues_raw and not award_text_raw:
            no_supporting_doc_uploaded = not (supporting_docs and supporting_docs.get("lower_court"))
            if no_supporting_doc_uploaded:
                message = (
                    "No trial court / tribunal judgment was found for this case -- this is "
                    "an appeal-side-only view. Upload the original MACT award as a supporting "
                    "document (doc type: Lower Court Judgment) to get a full trial-court-vs-appeal comparison."
                )
            else:
                message = (
                    "A lower court document was uploaded, but its issues/award section could not "
                    "be reliably parsed -- summary limited to appeal-side grounds only."
                )
            return {
                "issue_wise_view": [],
                "final_summary_points": [message],
                "probable_outcome": heuristic_signal.get("verdict", "not_determinable") if heuristic_signal else "not_determinable",
                "factual_discrepancies": [],
                "summary_source": "insufficient_input"
            }
        issues_rows = normalize_issues_table(issues_raw)
        issues_text_hi = "\n".join(f"{r.get('issue', '')}: {r.get('finding', '')}" for r in issues_rows) or issues_raw

        translation = translate_trial_court_text(issues_text_hi, award_text_raw)
        issues_text_en = translation.get("issues_en") or issues_text_hi
        award_text_en = translation.get("award_en") or award_text_raw
        summary_src = "mact_quoted_fallback"

    concat = f"{issues_text_en}|||{award_text_en}|||{grounds_text}|||{relief_text}|||{medical_evidence_text}"
    h = hashlib.sha256(concat.encode("utf-8")).hexdigest()
    if not force_refresh and h in _FINAL_SUMMARY_CACHE:
        logger.info("[FINAL-JUDICIAL-SUMMARY] Returning cached summary.")
        return _FINAL_SUMMARY_CACHE[h]

    # Step 2: extract structured claims from both sides (generalizes to any case_type)
    grounds_claims = validate_claims_shape(
        extract_claims(f"{grounds_text}\n{relief_text}", case_type=case_type,
                       source_label="HC grounds of appeal / relief").get("claims", [])
    )
    trial_claims = validate_claims_shape(
        extract_claims(f"{issues_text_en}\n{award_text_en}", case_type=case_type,
                       source_label="trial court issues/award (translated)").get("claims", [])
    )

    # Step 3: deterministic fuzzy matcher -> candidate list for the LLM to verify
    candidate_discrepancies = find_missing_claims(grounds_claims, trial_claims)

    # Step 3b: same deterministic matcher, but for supporting medical/diagnostic
    # evidence (X-ray, USG, CT, discharge cards, etc.) against the trial court
    # record. A clinical finding on an uploaded report may never appear in the
    # HC grounds text at all, so it needs its own direct check against the
    # trial court text rather than riding on the grounds-vs-trial check above.
    medical_discrepancies = []
    if medical_evidence_text and medical_evidence_text.strip() and not medical_evidence_text.startswith("(No supporting"):
        medical_claims = validate_claims_shape(
            extract_claims(medical_evidence_text, case_type=case_type,
                           source_label="supporting medical/diagnostic evidence").get("claims", [])
        )
        medical_discrepancies = find_missing_claims(medical_claims, trial_claims)
        for d in medical_discrepancies:
            d["note"] = (
                "Documented in an uploaded supporting medical/diagnostic report but not "
                "reflected in the trial court's issues/award text. " + d["note"]
            )

    seen_claims = {c["claim"].strip().lower() for c in candidate_discrepancies}
    for d in medical_discrepancies:
        key = d["claim"].strip().lower()
        if key not in seen_claims:
            candidate_discrepancies.append(d)
            seen_claims.add(key)

    candidate_hint = "\n".join(
        f"- {d['claim']} ({d['category']})" for d in candidate_discrepancies
    ) or "(none flagged by automated matcher)"

    prompt = FINAL_JUDICIAL_SUMMARY_USER_PROMPT.format(
        issues_text=issues_text_en[:4000],
        award_text=award_text_en[:3000],
        grounds_text=grounds_text[:4000],
        relief_text=relief_text[:2000],
        medical_evidence_text=medical_evidence_text[:4000],
        candidate_discrepancies=candidate_hint
    )

    result_dict = {}
    success = False

    for attempt in range(2):
        try:
            response = generate_response(
                prompt=prompt,
                system_instruction=FINAL_JUDICIAL_SUMMARY_SYSTEM_INSTRUCTION,
                response_format="json",
                model=LLM_FINAL_SUMMARY_MODEL_NAME,
                temperature=LLM_FINAL_SUMMARY_TEMPERATURE
            )
            if response.startswith("Error connecting to LLM server") or response.startswith("Error communicating with LLM"):
                logger.warning(f"[FINAL-JUDICIAL-SUMMARY] Attempt {attempt + 1} hit an LLM transport error, not retrying: {response}")
                break  # don't waste another 90-240s retrying the same timeout
            response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
            s = response.find("{")
            e = response.rfind("}")
            candidate = response[s:e+1] if s != -1 and e != -1 and e > s else response
            parsed = json.loads(candidate)

            if validate_final_summary_shape(parsed):
                full_source = f"{issues_text_en}\n{award_text_en}\n{grounds_text}\n{relief_text}"
                result_dict = _verify_final_summary_grounding(parsed, full_source)
                result_dict["summary_source"] = summary_src

                # Union, not override: the LLM's reviewed list is authoritative for
                # anything it actually commented on; any matcher candidate the LLM's
                # JSON silently omitted (rather than explicitly rejecting) still gets
                # included, so a weak model can't silently wipe out a real hit just
                # by forgetting to echo it back.
                llm_discrepancies = validate_factual_discrepancies_shape(parsed.get("factual_discrepancies"))
                rejected = {c.strip().lower() for c in parsed.get("rejected_candidate_claims", []) if isinstance(c, str)}
                seen = {d["claim"].strip().lower() for d in llm_discrepancies}

                merged = list(llm_discrepancies)
                for d in candidate_discrepancies:
                    key = d["claim"].strip().lower()
                    if key not in seen and key not in rejected:
                        merged.append(d)

                result_dict["factual_discrepancies"] = merged
                success = True
                break
        except Exception as e:
            logger.warning(f"[FINAL-JUDICIAL-SUMMARY] Attempt {attempt + 1} failed: {e}")
            prompt += "\n\nREMINDER: return ONLY valid JSON matching the schema exactly."

    if not success:
        result_dict = {
            "issue_wise_view": [],
            "final_summary_points": [
                "Automated issue-wise comparison could not be generated for this document; please review the trial court award and HC grounds manually."
            ],
            "probable_outcome": heuristic_signal.get("verdict", "not_determinable") if heuristic_signal else "not_determinable",
            "factual_discrepancies": candidate_discrepancies,
            "summary_source": "fallback"
        }

    _FINAL_SUMMARY_CACHE[h] = result_dict
    return result_dict

