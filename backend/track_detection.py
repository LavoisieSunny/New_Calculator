"""
backend/track_detection.py

Detects whether an uploaded bundle is a High Court appeal (English, small
bundle, memo-of-appeal structure) or a Lower Court / MACT record (Hindi,
often very large, scanned with registry/admin pages mixed in).

Deliberately cheap: only the first `sample_pages` pages are rendered at low
DPI and OCR'd (PaddleOCR first; vision only if Paddle returns nothing at
all), so this adds at most a couple of seconds to any upload — it must run
unconditionally before every autofill so downstream OCR/parsing can pick
the right pipeline.
"""

import os
import re
import tempfile
import uuid
import logging

import pypdfium2 as pdfium

logger = logging.getLogger("TrackDetection")

# High Court appeal markers (English memo-of-appeal / cause-title language).
_HC_MARKERS = [
    "high court", "principal seat at jabalpur", "jabalpur", "misc. appeal",
    "m.a. no", "miscellaneous appeal", "173 of the motor vehicle",
    "memo of appeal", "grounds of appeal",
] 

# Lower Court / MACT tribunal markers (Hindi + common English tribunal terms).
_LC_MARKERS = [
    "अधिकरण", "मोटर दुर्घटना दावा अधिकरण", "न्यायालय", "मैक्ट", "macc",
    "केन्द्रीय भरण काउन्टर", "केंद्रीय भरण काउंटर", "अधिनिर्णय", "claims tribunal",
]

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

# How many leading (front-matter) pages decide the bundle-level track.
# A High Court appeal bundle always attaches a certified copy of the
# impugned lower-court award as an annexure -- in Hindi, and frequently
# more pages than the appeal memo itself -- so the overall track must be
# decided from the cause-title / computer-sheet / memo-of-appeal pages at
# the front, not from a majority vote across every page in the bundle.
TRACK_DECISION_SAMPLE_PAGES = 3


def _devanagari_ratio(text: str) -> float:
    """Fraction of alphabetic characters that are Devanagari script."""
    alpha = [c for c in text if c.isalpha()]
    if not alpha:
        return 0.0
    deva = sum(1 for c in alpha if _DEVANAGARI_RE.match(c))
    return deva / len(alpha)


_OCR_PROBE_CACHE = {}


def _extract_digital_text_per_page(pdf_path: str) -> dict:
    from backend.ocr import extract_digital_pdf_text, extract_alternate_pdf_text
    lines = extract_digital_pdf_text(pdf_path)
    if not lines or len(" ".join(lines).strip()) < 100:
        lines = extract_alternate_pdf_text(pdf_path)
    
    page_texts = {}
    current_page = None
    current_lines = []
    
    for line in lines:
        m = re.match(r'^---\s*PAGE\s+(\d+)\s*---', line, re.IGNORECASE)
        if m:
            if current_page is not None:
                page_texts[current_page] = "\n".join(current_lines)
            current_page = int(m.group(1))
            current_lines = []
        else:
            current_lines.append(line)
    if current_page is not None:
        page_texts[current_page] = "\n".join(current_lines)
    return page_texts


def detect_case_track_per_page(pdf_path: str) -> list[dict]:
    """Returns [{'page': 1, 'track': 'high_court', 'deva_ratio': 0.02}, ...] for every page."""
    from backend.ocr import (
        call_paddle_ocr, guard_and_downscale_image, is_vision_model_available,
        call_vision_model, image_to_base64, preprocess_for_vision, classify_scanned_page,
        detect_page_language_from_probe
    )

    page_texts = _extract_digital_text_per_page(pdf_path)
    
    try:
        with pdfium.PdfDocument(pdf_path) as doc:
            total_pages = len(doc)
    except Exception as e:
        logger.error(f"detect_case_track_per_page failed to open PDF: {e}")
        return []

    results = []
    has_digital = any(len(text.strip()) >= 100 for text in page_texts.values())
    vision_available = is_vision_model_available()

    if has_digital:
        for page_num in range(1, total_pages + 1):
            text = page_texts.get(page_num, "")
            text_lower = text.lower()
            deva_ratio = _devanagari_ratio(text)
            hc_hits = sum(1 for m in _HC_MARKERS if m in text_lower)
            lc_hits = sum(1 for m in _LC_MARKERS if m.lower() in text_lower)

            if hc_hits >= 1 and deva_ratio < 0.15:
                track = "high_court"
            elif lc_hits >= 1 or deva_ratio >= 0.30:
                track = "lower_court"
            else:
                track = "high_court" if hc_hits >= lc_hits else "lower_court"

            results.append({
                "page": page_num,
                "track": track,
                "deva_ratio": round(deva_ratio, 3),
                "hc_hits": hc_hits,
                "lc_hits": lc_hits,
                "method": "digital"
            })
        logger.info(f"[TRACK-PER-PAGE] Digital classification completed for {total_pages} pages.")
        return results

    # Scanned PDF fallback
    for page_idx in range(total_pages):
        page_num = page_idx + 1
        lines = []
        try:
            with pdfium.PdfDocument(pdf_path) as doc:
                page_obj = doc[page_idx]
                bitmap = page_obj.render(scale=100 / 72.0)
                pil_img = bitmap.to_pil()
                del bitmap, page_obj
            
            pil_img = guard_and_downscale_image(pil_img)
            if classify_scanned_page(pil_img) != "blank":
                lang = detect_page_language_from_probe(pil_img, page_num=page_num)
                tmp_path = os.path.join(tempfile.gettempdir(), f"_track_probe_{uuid.uuid4().hex}.png")
                try:
                    pil_img.save(tmp_path, format="PNG")
                    lines, conf, _ = call_paddle_ocr(tmp_path, page_num=page_num, lang=lang)
                    if not lines and vision_available:
                        b64 = image_to_base64(preprocess_for_vision(pil_img))
                        raw = call_vision_model(b64, page_num=page_num)
                        if raw and raw.strip() != "[BLANK PAGE]":
                            lines = [l.strip() for l in raw.split("\n") if l.strip()]
                    
                    if lines:
                        _OCR_PROBE_CACHE[(pdf_path, page_num)] = (lines, lang)
                finally:
                    if os.path.exists(tmp_path):
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass
            del pil_img
        except Exception as e:
            logger.warning(f"Track probe failed on page {page_num}: {e}")

        combined = " ".join(lines)
        combined_lower = combined.lower()
        deva_ratio = _devanagari_ratio(combined)
        hc_hits = sum(1 for m in _HC_MARKERS if m in combined_lower)
        lc_hits = sum(1 for m in _LC_MARKERS if m.lower() in combined_lower)

        if hc_hits >= 1 and deva_ratio < 0.15:
            track = "high_court"
        elif lc_hits >= 1 or deva_ratio >= 0.30:
            track = "lower_court"
        else:
            track = "high_court" if hc_hits >= lc_hits else "lower_court"

        results.append({
            "page": page_num,
            "track": track,
            "deva_ratio": round(deva_ratio, 3),
            "hc_hits": hc_hits,
            "lc_hits": lc_hits,
            "method": "ocr"
        })
    logger.info(f"[TRACK-PER-PAGE] OCR classification completed for scanned PDF ({total_pages} pages).")
    return results


def detect_case_track(pdf_path: str, sample_pages: int = 3) -> dict:
    """Legacy wrapper for compatibility. Detects track based on majority page tracks."""
    per_page = detect_case_track_per_page(pdf_path)
    if not per_page:
        return {
            "track": "high_court",
            "hc_hits": 0, "lc_hits": 0,
            "devanagari_ratio": 0.0, "sampled_pages": 0
        }
    
    hc_count = sum(1 for p in per_page if p["track"] == "high_court")
    lc_count = len(per_page) - hc_count
    majority_track = "high_court" if hc_count >= lc_count else "lower_court"
    
    hc_hits = sum(p["hc_hits"] for p in per_page)
    lc_hits = sum(p["lc_hits"] for p in per_page)
    avg_deva_ratio = sum(p["deva_ratio"] for p in per_page) / len(per_page)
    
    return {
        "track": majority_track,
        "hc_hits": hc_hits,
        "lc_hits": lc_hits,
        "devanagari_ratio": round(avg_deva_ratio, 3),
        "sampled_pages": len(per_page)
    }
