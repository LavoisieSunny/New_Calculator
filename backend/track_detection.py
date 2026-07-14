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


def _devanagari_ratio(text: str) -> float:
    """Fraction of alphabetic characters that are Devanagari script."""
    alpha = [c for c in text if c.isalpha()]
    if not alpha:
        return 0.0
    deva = sum(1 for c in alpha if _DEVANAGARI_RE.match(c))
    return deva / len(alpha)


def detect_case_track(pdf_path: str, sample_pages: int = 3) -> dict:
    """
    Renders + OCRs only the first `sample_pages` pages (default 3) to decide
    the processing track. Returns:

        {
            "track": "high_court" | "lower_court",
            "hc_hits": int, "lc_hits": int,
            "devanagari_ratio": float, "sampled_pages": int,
        }

    Imports OCR helpers lazily (inside the function) to avoid a circular
    import with backend.ocr, which itself imports detect_case_track.
    """
    from backend.ocr import (
        call_paddle_ocr, guard_and_downscale_image, is_vision_model_available,
        call_vision_model, image_to_base64, preprocess_for_vision, classify_scanned_page,
        extract_digital_pdf_text, extract_alternate_pdf_text, detect_page_language_from_probe
    )

    # 1. Try digital text-layer extraction first (no OCR at all)
    digital_lines = extract_digital_pdf_text(pdf_path)
    if not digital_lines or len(" ".join(digital_lines).strip()) < 100:
        digital_lines = extract_alternate_pdf_text(pdf_path)

    if digital_lines and len(" ".join(digital_lines).strip()) >= 100:
        combined = " ".join(digital_lines)
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

        logger.info(
            f"[TRACK DETECTED via Digital Text] track={track}, deva_ratio={deva_ratio:.2f}, "
            f"hc_hits={hc_hits}, lc_hits={lc_hits}, text_len={len(combined)}"
        )
        return {
            "track": track,
            "hc_hits": hc_hits,
            "lc_hits": lc_hits,
            "devanagari_ratio": round(deva_ratio, 3),
            "sampled_pages": len(digital_lines),
        }

    # 2. Fall back to rendered-image OCR probe if no usable text layer exists
    texts = []
    try:
        with pdfium.PdfDocument(pdf_path) as doc:
            n = min(sample_pages, len(doc))
            for i in range(n):
                try:
                    page_obj = doc[i]
                    bitmap = page_obj.render(scale=100 / 72.0)
                    pil_img = bitmap.to_pil()
                    del bitmap, page_obj
                except Exception as e:
                    logger.warning(f"Track probe render failed on page {i+1}: {e}")
                    continue

                pil_img = guard_and_downscale_image(pil_img)
                if classify_scanned_page(pil_img) == "blank":
                    del pil_img
                    continue

                # Run dynamic lang probe to determine language
                lang = detect_page_language_from_probe(pil_img, page_num=i + 1)

                tmp_path = os.path.join(tempfile.gettempdir(), f"_track_probe_{uuid.uuid4().hex}.png")
                pil_img.save(tmp_path, format="PNG")
                
                # Call Paddle OCR using detected language
                lines, conf, _ = call_paddle_ocr(tmp_path, page_num=i + 1, lang=lang)

                if not lines and is_vision_model_available():
                    try:
                        b64 = image_to_base64(preprocess_for_vision(pil_img))
                        raw = call_vision_model(b64, page_num=i + 1)
                        if raw and raw.strip() != "[BLANK PAGE]":
                            lines = [l.strip() for l in raw.split("\n") if l.strip()]
                    except Exception as e:
                        logger.warning(f"Track probe vision fallback failed on page {i+1}: {e}")

                del pil_img
                if os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

                texts.append(" ".join(lines))
    except Exception as e:
        logger.error(f"detect_case_track failed to open/scan PDF: {e}")

    combined = " ".join(texts)
    combined_lower = combined.lower()
    deva_ratio = _devanagari_ratio(combined)

    hc_hits = sum(1 for m in _HC_MARKERS if m in combined_lower)
    lc_hits = sum(1 for m in _LC_MARKERS if m.lower() in combined_lower)

    # Decision order: an explicit HC marker with low Devanagari content wins
    # outright (this is the common, unambiguous case: a clean English memo
    # of appeal). Otherwise, either an explicit LC marker OR a high
    # Devanagari ratio routes to lower_court. Ties fall back to whichever
    # marker count is higher.
    if hc_hits >= 1 and deva_ratio < 0.15:
        track = "high_court"
    elif lc_hits >= 1 or deva_ratio >= 0.30:
        track = "lower_court"
    else:
        track = "high_court" if hc_hits >= lc_hits else "lower_court"

    logger.info(
        f"[TRACK DETECTED via OCR Probe] track={track}, deva_ratio={deva_ratio:.2f}, "
        f"hc_hits={hc_hits}, lc_hits={lc_hits}"
    )
    return {
        "track": track,
        "hc_hits": hc_hits,
        "lc_hits": lc_hits,
        "devanagari_ratio": round(deva_ratio, 3),
        "sampled_pages": len(texts),
    }
