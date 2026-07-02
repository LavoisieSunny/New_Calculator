import os
import re
import sys
import gc
import time
import base64
import shutil
import tempfile
import logging
import uuid
import threading
import queue as _queue
import psutil
import numpy as np
from PIL import Image
import asyncio
import json
import urllib.request
import urllib.error
import concurrent.futures as _cf
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pypdf import PdfReader
import pypdfium2 as pdfium

from backend.parser_heuristics import parse_extracted_text, HINDI_HEADING_KEYWORDS, parse_hindi_extracted_text
from backend.vector_db import index_document, COLLECTION_NAME
from backend.track_detection import detect_case_track

# ======================================================
# LOGGING
# ======================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OCRModule")
logger.setLevel(logging.INFO)
logger.propagate = True

def _tlog(msg: str):
    line = f"[OCR] {msg}"
    print(line, flush=True)
    print(line, flush=True, file=sys.stderr)
    logger.info(msg)

router = APIRouter()

# ======================================================
# CONFIGURATION — all tunable via environment variables
# ======================================================

OCR_RENDER_DPI      = int(os.getenv("OCR_RENDER_DPI", "150"))       # 150 DPI is sweet spot for qwen2.5vl
OCR_RETRY_DPI       = int(os.getenv("OCR_RETRY_DPI", "200"))        # Retry DPI for poor quality pages
OCR_MAX_PARALLEL_WORKERS = int(os.getenv("OCR_MAX_PARALLEL_WORKERS", "4"))  # Parallel image prep workers
# Phase 2 (the page-processing loop) uses a SEPARATE, larger worker pool than
# rendering. Vision calls are already serialized by _VISION_SEMAPHORE (only
# one qwen2.5vl request in flight at a time) and PaddleOCR calls are already
# serialized by _PADDLE_INFER_LOCK — so the worker pool itself isn't adding
# real parallel model throughput, it's just allowing more pages to be
# IN FLIGHT (queued behind those locks) at once. With only 4 workers, a burst
# of vision escalations (common on a run of hard/handwritten pages) ties up
# every worker waiting on the vision semaphore simultaneously, which then
# blocks completely unrelated Paddle-only pages from even starting — this is
# exactly what produced the 90s+ "PaddleOCR" page times in production logs
# (those pages weren't slow to OCR; their worker thread was stuck queued
# behind vision). A larger pool here costs only thread overhead (cheap) and
# lets non-vision pages keep flowing past a vision backlog instead of
# stalling behind it.
OCR_PAGE_WORKER_POOL_SIZE = int(os.getenv("OCR_PAGE_WORKER_POOL_SIZE", str(min(16, max(4, (os.cpu_count() or 2) * 2)))))
OCR_PAGE_TIMEOUT    = float(os.getenv("OCR_PAGE_TIMEOUT", "60.0"))  # Per-page timeout (vision is slower)
OCR_VISION_MODEL    = os.getenv("OCR_VISION_MODEL", "qwen2.5vl:7b") # Ollama vision model
OCR_OLLAMA_ENDPOINT = os.getenv("LLM_API_ENDPOINT", "http://localhost:11434")
DEBUG_OCR           = os.getenv("DEBUG_OCR", "false").lower() == "true"
OCR_QUALITY_GATE_THRESHOLD = 0.05

# PaddleOCR — middle layer between vision and Tesseract.
# Fast, CPU-only, excellent at printed Hindi+English and structural layouts
# (tables/columns). Used as the FIRST OCR pass on every non-blank page;
# qwen2.5vl is only invoked when Paddle's result is low quality (handwriting,
# stamps, badly skewed/garbled mixed-script text). This ordering is what keeps
# the pipeline fast and keeps the heavy, serialized vision model off the hot
# path for the common case (clean printed scans).
OCR_PADDLE_LANG              = os.getenv("OCR_PADDLE_LANG", "hi")  # "hi" -> PP-OCRv5 devanagari rec model (also covers Latin/English chars)
OCR_PADDLE_CONF_THRESHOLD    = float(os.getenv("OCR_PADDLE_CONF_THRESHOLD", "0.70"))   # avg per-line rec confidence
OCR_PADDLE_QUALITY_THRESHOLD = float(os.getenv("OCR_PADDLE_QUALITY_THRESHOLD", "0.40")) # heuristic legal-text quality score
OCR_ENABLE_VISION_ESCALATION = os.getenv("OCR_ENABLE_VISION_ESCALATION", "true").lower() == "true"
OCR_HYBRID_LABEL = f"PaddleOCR+{OCR_VISION_MODEL}"
OCR_MEMORY_WARN_MB = int(os.getenv("OCR_MEMORY_WARN_MB", "3000"))  # soft RSS warning threshold
# NOTE: OCR_MEMORY_WARN_MB previously existed but was never actually enforced
# anywhere — it was logged per-page and nothing else. With OCR_PAGE_WORKER_POOL_SIZE
# threads all able to start concurrently, each holding a full-res PIL image (and,
# on vision/Tesseract pages, a second CLAHE-processed copy + a base64 buffer) in
# RAM at once, a burst of "hard" pages is exactly what was producing OOM kills in
# production. OCR_MEMORY_GATE_MAX_WAIT bounds how long a worker will pause for
# memory to free up before proceeding anyway (never deadlock the batch).
OCR_MEMORY_GATE_MAX_WAIT = float(os.getenv("OCR_MEMORY_GATE_MAX_WAIT", "20.0"))

# Vision model Ollama concurrency semaphore —
# qwen2.5vl:7b runs one inference at a time on a single GPU/CPU.
# All other work (render, preprocess, encode) runs fully parallel.
_VISION_SEMAPHORE = threading.Semaphore(1)

# Tracks consecutive vision-model failures/timeouts (mirrors the PaddleOCR
# circuit breaker below). A single extremely dense page — large embossed
# stamps, a multi-column form, dozens of handwritten table cells — can hang
# or crash a local Ollama instance. Without this, every remaining page in
# the batch pays a full OCR_PAGE_TIMEOUT (default 90s) waiting on a vision
# model that is no longer responding, which for ~85 remaining pages is over
# two hours of dead time AND zero text recovered for any of them. After a
# few consecutive failures, vision escalation is paused for a cooldown
# window so the pipeline falls back to Paddle/Tesseract-only for the rest
# of the batch instead of hanging on every page.
_VISION_CONSECUTIVE_FAILURES = 0
_VISION_FAILURE_PAUSE_THRESHOLD = 4
_VISION_COOLDOWN_SECONDS = 120.0
_VISION_PAUSED_UNTIL = 0.0
_VISION_STATE_LOCK = threading.Lock()


def _vision_is_paused() -> bool:
    with _VISION_STATE_LOCK:
        return time.time() < _VISION_PAUSED_UNTIL


def _record_vision_result(success: bool, page_num: int = 0):
    """Updates the vision circuit breaker state after each call."""
    global _VISION_CONSECUTIVE_FAILURES, _VISION_PAUSED_UNTIL
    with _VISION_STATE_LOCK:
        if success:
            _VISION_CONSECUTIVE_FAILURES = 0
            return
        _VISION_CONSECUTIVE_FAILURES += 1
        if _VISION_CONSECUTIVE_FAILURES >= _VISION_FAILURE_PAUSE_THRESHOLD:
            _VISION_PAUSED_UNTIL = time.time() + _VISION_COOLDOWN_SECONDS
            logger.error(
                f"Vision model paused for {_VISION_COOLDOWN_SECONDS:.0f}s after "
                f"{_VISION_CONSECUTIVE_FAILURES} consecutive failures (last at page {page_num}). "
                f"Falling back to PaddleOCR/Tesseract only until cooldown expires — "
                f"this prevents every remaining page in the batch from paying the "
                f"full {OCR_PAGE_TIMEOUT:.0f}s timeout against an unresponsive Ollama."
            )

# PaddleOCR predictor concurrency lock —
# the singleton's predict() call is serialized too. PaddleOCR's CPU inference
# is not guaranteed thread-safe for concurrent predict() calls on one instance,
# and letting N worker threads all hammer the CPU predictor at once is exactly
# the kind of contention that starves the host and can get the whole container
# OOM/CPU-killed. Image render/preprocess/encode stays fully parallel; only the
# actual model call is serialized — same pattern as the vision semaphore above.
_PADDLE_INIT_LOCK  = threading.Lock()
_PADDLE_INFER_LOCK = threading.Lock()

# ------------------------------------------------------------------
# REAL memory release (glibc malloc doesn't return freed arenas to the OS
# on its own). gc.collect() only frees *Python* objects back to the
# allocator's free lists — it does NOT shrink the process's RSS. That is
# exactly why production logs show RSS frozen at an identical value
# (8725MB) across dozens of consecutive pages even while pages are being
# processed and discarded: nothing was leaking, the memory just was never
# handed back to the kernel. malloc_trim(0) forces glibc to release fully-
# free arenas back to the OS, which is what actually moves the RSS number.
# ------------------------------------------------------------------
try:
    import ctypes
    _LIBC = ctypes.CDLL("libc.so.6")
except Exception:
    _LIBC = None

def _release_memory_to_os():
    gc.collect()
    if _LIBC is not None:
        try:
            _LIBC.malloc_trim(0)
        except Exception:
            pass

# Hard admission-control semaphore — actually bounds how many pages may
# simultaneously hold decoded image data (raw PIL image + CLAHE copy +
# base64 buffer) in RAM, independent of OCR_PAGE_WORKER_POOL_SIZE.
# The previous "memory gate" only POLLED RSS and then proceeded regardless
# after a timeout — it could delay a worker but could never actually stop
# more workers from piling on, so under a sustained run it just added a
# flat 20s tax per page without capping anything. A semaphore is real
# backpressure: with N slots, AT MOST N pages can be holding image memory
# at once, full stop, no matter how many threads are submitted.
OCR_MAX_PAGES_IN_FLIGHT = int(os.getenv("OCR_MAX_PAGES_IN_FLIGHT", "3"))
_PAGE_MEMORY_SLOTS = threading.BoundedSemaphore(OCR_MAX_PAGES_IN_FLIGHT)


def _wait_for_memory_headroom(page_num: int = 0):
    """
    Soft secondary check kept for visibility/logging: if RSS is still high
    even with admission control bounding concurrency (e.g. a genuinely large
    single page, or external memory pressure), give the OS a brief chance to
    reclaim trimmed memory before proceeding. The hard cap is now the
    semaphore above — this no longer needs to (and won't) block forever.
    """
    if OCR_MEMORY_WARN_MB <= 0:
        return
    try:
        proc = psutil.Process(os.getpid())
        rss_mb = proc.memory_info().rss / (1024 * 1024)
    except Exception:
        return
    if rss_mb < OCR_MEMORY_WARN_MB:
        return
    logger.warning(
        f"Page {page_num}: RSS={rss_mb:.0f}MB >= warn threshold {OCR_MEMORY_WARN_MB}MB "
        f"— forcing OS memory release before continuing."
    )
    _release_memory_to_os()
    try:
        rss_mb2 = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
        logger.info(f"Page {page_num}: RSS after malloc_trim: {rss_mb2:.0f}MB (was {rss_mb:.0f}MB)")
    except Exception:
        pass

# Global Batch Upload Queue
BATCH_QUEUE = {}

# Legal keywords for quality scoring
_LEGAL_QUALITY_KEYWORDS = [
    "tribunal", "claimant", "petitioner", "mact", "mcop", "accident",
    "rs.", "compensation", "disability", "income", "award", "court",
    "deceased", "injured", "monthly", "insurance", "motor", "claim"
]

# Devanagari unicode range
_DEVANAGARI_RE = re.compile(r'[\u0900-\u097F]')


# ======================================================
# VISION OCR — qwen2.5vl:7b via Ollama
# ======================================================

_VISION_PROMPT = (
    "You are an expert OCR engine for Indian legal court documents. "
    "Extract ALL text from this scanned page exactly as it appears. "
    "Rules:\n"
    "- Output ONLY the extracted text, line by line. No commentary, no preamble.\n"
    "- Preserve Hindi (Devanagari) and English text. Output both scripts faithfully.\n"
    "- For tables, output each row on a new line with cells separated by ' | '.\n"
    "- For handwritten text that is legible, include it. For completely illegible text, skip it.\n"
    "- Preserve numbers, dates, case numbers, amounts (Rs., /-) exactly as written.\n"
    "- Do NOT add headings, markdown, or formatting. Plain text only.\n"
    "- If the page is blank or contains only stamps/seals with no readable text, output: [BLANK PAGE]"
)


def call_vision_model(image_b64: str, page_num: int = 0) -> str:
    """
    Calls qwen2.5vl:7b via Ollama /api/chat with a base64-encoded image.
    Serialized through _VISION_SEMAPHORE — only one inference at a time.
    Returns raw text string from the model.

    Guarded by a circuit breaker: if Ollama is unresponsive/crashed, this
    returns immediately ("") instead of attempting (and potentially hanging
    on) a request, once enough consecutive failures have been observed.
    """
    if _vision_is_paused():
        logger.warning(f"Page {page_num}: vision model in cooldown, skipping call.")
        return ""

    url = f"{OCR_OLLAMA_ENDPOINT.rstrip('/')}/api/chat"
    payload = {
        "model": OCR_VISION_MODEL,
        "stream": False,
        "options": {
            "temperature": 0.0,       # deterministic for OCR
            "num_predict": 4096,      # max output tokens per page
            "num_ctx": 8192,          # context window
        },
        "messages": [
            {
                "role": "user",
                "content": _VISION_PROMPT,
                "images": [image_b64]
            }
        ]
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with _VISION_SEMAPHORE:
        try:
            with urllib.request.urlopen(req, timeout=OCR_PAGE_TIMEOUT) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                content = result.get("message", {}).get("content", "").strip()
                _record_vision_result(success=bool(content), page_num=page_num)
                return content
        except urllib.error.URLError as e:
            logger.error(f"Page {page_num}: Ollama vision request failed: {e}")
            _record_vision_result(success=False, page_num=page_num)
            return ""
        except Exception as e:
            logger.error(f"Page {page_num}: Vision model call error: {e}")
            _record_vision_result(success=False, page_num=page_num)
            return ""


def is_vision_model_available() -> bool:
    """Checks that qwen2.5vl:7b is available in Ollama."""
    try:
        url = f"{OCR_OLLAMA_ENDPOINT.rstrip('/')}/api/tags"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            available = any(OCR_VISION_MODEL.split(":")[0] in m for m in models)
            if available:
                _tlog(f"Vision model '{OCR_VISION_MODEL}' confirmed available in Ollama.")
            else:
                _tlog(f"WARNING: '{OCR_VISION_MODEL}' not found. Available: {models}")
            return available
    except Exception as e:
        logger.error(f"Ollama availability check failed: {e}")
        return False


# ======================================================
# PADDLEOCR — middle layer (printed Hindi+English, tables/columns, no GPU)
# ======================================================

_PADDLE_INSTANCE = None
_PADDLE_AVAILABLE = None


def get_ocr_instance():
    """
    Lazily creates and returns the singleton PaddleOCR engine.

    Loaded ONCE per process and reused for every page/request. Re-instantiating
    PaddleOCR per call is one of the easiest ways to slowly choke a server
    (repeated model loads = repeated big memory allocations); the singleton
    pattern here, combined with main.py's startup warm-up, avoids that.
    """
    global _PADDLE_INSTANCE
    if _PADDLE_INSTANCE is not None:
        return _PADDLE_INSTANCE
    with _PADDLE_INIT_LOCK:
        if _PADDLE_INSTANCE is None:
            from paddleocr import PaddleOCR
            _tlog(f"Loading PaddleOCR singleton (PP-OCRv5, lang={OCR_PADDLE_LANG})...")
            t0 = time.time()
            _PADDLE_INSTANCE = PaddleOCR(
                lang=OCR_PADDLE_LANG,
                use_doc_orientation_classify=False,  # scans are upright; skip for speed
                use_doc_unwarping=False,              # not photographed/curved pages
                use_textline_orientation=False,       # skip per-line angle model for speed
            )
            _tlog(f"PaddleOCR singleton ready in {time.time() - t0:.1f}s.")
    return _PADDLE_INSTANCE


def is_paddle_available() -> bool:
    """Checks (and caches) whether PaddleOCR initialised successfully."""
    global _PADDLE_AVAILABLE
    if _PADDLE_AVAILABLE is not None:
        return _PADDLE_AVAILABLE
    try:
        get_ocr_instance()
        _PADDLE_AVAILABLE = True
        _tlog("PaddleOCR confirmed available.")
    except Exception as e:
        logger.error(f"PaddleOCR unavailable: {e}")
        _PADDLE_AVAILABLE = False
    return _PADDLE_AVAILABLE


# ======================================================
# PP-STRUCTUREV3 — real table-structure extraction (layout + table model)
# ======================================================
# Plain PaddleOCR (above) only does detect+recognize text boxes; the
# " | "-joined "table" output from _sort_paddle_reading_order is a gap-based
# GUESS at structure, not real table understanding (breaks on merged cells,
# multi-line cells, hand-filled rows with no clean gutter). PPStructureV3 is
# a separate, heavier PaddleOCR pipeline that does proper layout detection +
# table recognition, returning actual table structure. It's deliberately
# NOT run on every page (it's slower and more memory-hungry than plain
# PaddleOCR) — only invoked for pages the cheap heuristic already flagged as
# tabular (>=2 multi-cell rows), as a targeted second pass.
OCR_ENABLE_TABLE_STRUCTURE = os.getenv("OCR_ENABLE_TABLE_STRUCTURE", "true").lower() == "true"
_TABLE_MIN_ROWS_TO_TRIGGER = 2

_STRUCTURE_INSTANCE = None
_STRUCTURE_AVAILABLE = None
_STRUCTURE_INIT_LOCK = threading.Lock()
_STRUCTURE_INFER_LOCK = threading.Lock()


def get_structure_instance():
    """Lazily creates and returns the singleton PPStructureV3 engine.
    Same singleton pattern as get_ocr_instance() — loaded once, reused."""
    global _STRUCTURE_INSTANCE
    if _STRUCTURE_INSTANCE is not None:
        return _STRUCTURE_INSTANCE
    with _STRUCTURE_INIT_LOCK:
        if _STRUCTURE_INSTANCE is None:
            from paddleocr import PPStructureV3
            _tlog(f"Loading PP-StructureV3 singleton (table/layout, lang={OCR_PADDLE_LANG})...")
            t0 = time.time()
            _STRUCTURE_INSTANCE = PPStructureV3(
                lang=OCR_PADDLE_LANG,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
            _tlog(f"PP-StructureV3 singleton ready in {time.time() - t0:.1f}s.")
    return _STRUCTURE_INSTANCE


def is_table_structure_available() -> bool:
    global _STRUCTURE_AVAILABLE
    if not OCR_ENABLE_TABLE_STRUCTURE:
        return False
    if _STRUCTURE_AVAILABLE is not None:
        return _STRUCTURE_AVAILABLE
    try:
        get_structure_instance()
        _STRUCTURE_AVAILABLE = True
        _tlog("PP-StructureV3 confirmed available.")
    except Exception as e:
        logger.warning(f"PP-StructureV3 unavailable (table-structure pass disabled): {e}")
        _STRUCTURE_AVAILABLE = False
    return _STRUCTURE_AVAILABLE


def extract_tables_via_structure(image_path: str, page_num: int = 0) -> list:
    """
    Runs PP-StructureV3 on a page image and returns a list of markdown table
    strings (one per detected table region), in top-to-bottom order.

    Defensive about output shape: PPStructureV3's result schema has changed
    across paddleocr releases, so every field access below falls back to []
    / "" rather than raising — a parsing miss here should degrade to "no
    table found" (the heuristic-joined PaddleOCR text is still used), never
    crash the page.
    """
    if not is_table_structure_available():
        return []
    try:
        with _STRUCTURE_INFER_LOCK:
            engine = get_structure_instance()
            results = engine.predict(image_path)
    except Exception as e:
        logger.warning(f"Page {page_num}: PP-StructureV3 predict failed: {e}")
        return []

    tables = []
    try:
        for res in (results or []):
            res_dict = res.get("res", res) if hasattr(res, "get") else getattr(res, "res", res)
            blocks = None
            for key in ("parsing_res_list", "layout_parsing_result", "table_res_list"):
                blocks = res_dict.get(key) if hasattr(res_dict, "get") else getattr(res_dict, key, None)
                if blocks:
                    break
            if not blocks:
                continue
            for block in blocks:
                block_type = block.get("block_label") if hasattr(block, "get") else getattr(block, "block_label", None)
                if block_type and "table" not in str(block_type).lower():
                    continue
                md = None
                for key in ("table_md", "html", "markdown"):
                    md = block.get(key) if hasattr(block, "get") else getattr(block, key, None)
                    if md:
                        break
                if md and isinstance(md, str) and md.strip():
                    tables.append(md.strip())
    except Exception as e:
        logger.warning(f"Page {page_num}: PP-StructureV3 result parsing failed: {e}")
        return []

    if tables:
        _tlog(f"Page {page_num}: PP-StructureV3 extracted {len(tables)} table(s)")
    return tables


def _sort_paddle_reading_order(rec_texts: list, rec_scores: list, rec_boxes) -> tuple:
    """
    PaddleOCR returns text boxes in detection order, which is NOT reliably
    top-to-bottom/left-to-right for multi-column legal documents or tables.
    Clusters boxes into rows by vertical center, then sorts each row
    left-to-right — this is what gives Paddle's "structural extraction"
    (columns, tables) a coherent reading order instead of scrambled output.

    Rows with multiple cells (a real horizontal gap between consecutive boxes,
    not just normal word-spacing) are joined into ONE line with " | " between
    cells — the same delimiter the vision prompt already uses for tables —
    instead of being emitted as separate single-cell lines. Without this,
    every table on a page collapses into N flat unrelated lines downstream
    and the row/column relationship between e.g. "वाद क्रमांक" and its value
    is lost before parser_heuristics ever sees it.

    This gap-based join is only a heuristic approximation of a real table
    (it can't handle merged cells, multi-line cells, or hand-filled rows
    without clean gutters). Returns (ordered, table_row_count) so callers
    can detect "this page has >=2 multi-cell rows → probably a real table"
    and trigger proper PP-StructureV3 table extraction instead of trusting
    the heuristic join alone.

    Returns (list of (text, score) tuples in reading order, table_row_count).
    """
    if rec_boxes is None or len(rec_boxes) == 0 or len(rec_texts) == 0:
        return list(zip(rec_texts, rec_scores if rec_scores else [0.0] * len(rec_texts))), 0

    items = []
    for i, box in enumerate(rec_boxes):
        x0, y0, x1, y1 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
        items.append({
            "text": rec_texts[i],
            "score": float(rec_scores[i]) if rec_scores is not None and i < len(rec_scores) else 0.0,
            "x0": x0, "x1": x1, "cy": (y0 + y1) / 2.0, "h": max(y1 - y0, 1.0)
        })
    items.sort(key=lambda it: it["cy"])
    # Estimate page width from the boxes themselves (no need to pass the
    # actual image dims through). Used below to cap how wide a "column
    # gutter" is allowed to be before two boxes are deemed UNRELATED text
    # blocks (e.g. a left-margin case stamp and a right-margin "Most Urgent"
    # annotation sharing a vertical band by coincidence) rather than two
    # cells of the same table row.
    page_width = max((it["x1"] for it in items), default=1.0)
    MAX_JOIN_GAP_FRAC = 0.40  # gaps wider than 40% of page width → not a table gutter

    rows, current_row, row_cy = [], [], None
    for it in items:
        if row_cy is None or abs(it["cy"] - row_cy) <= it["h"] * 0.6:
            current_row.append(it)
            row_cy = sum(r["cy"] for r in current_row) / len(current_row)
        else:
            rows.append(current_row)
            current_row, row_cy = [it], it["cy"]
    if current_row:
        rows.append(current_row)

    ordered = []
    table_row_count = 0
    for row in rows:
        row.sort(key=lambda it: it["x0"])
        if len(row) == 1:
            ordered.append((row[0]["text"], row[0]["score"]))
            continue
        # Detect real cell boundaries: gap between this box's right edge and
        # the next box's left edge that's wide relative to this row's text
        # height. Normal inter-word spacing is well under 1x line-height;
        # table/column gutters are typically 1.5x+ . Consecutive boxes
        # WITHOUT a wide gap are still part of the same visual cell/phrase
        # and get joined with a space, not " | ". A gap can ALSO be too wide
        # to be a gutter at all (> MAX_JOIN_GAP_FRAC of the page) — that's
        # two unrelated blocks (margin annotation vs. main text, two
        # separate stamps) that happen to land in the same vertical band;
        # those get emitted as separate lines, never joined with " | ".
        cells, cell_buf, hard_break_before = [], [row[0]], [False]
        for prev, cur in zip(row, row[1:]):
            gap = cur["x0"] - prev["x1"]
            avg_h = (prev["h"] + cur["h"]) / 2.0
            if gap > page_width * MAX_JOIN_GAP_FRAC:
                cells.append(cell_buf)
                cell_buf = [cur]
                hard_break_before.append(True)
            elif gap > avg_h * 1.5:
                cells.append(cell_buf)
                cell_buf = [cur]
                hard_break_before.append(False)
            else:
                cell_buf.append(cur)
        cells.append(cell_buf)

        # Group cells into runs separated by hard breaks; only cells WITHIN
        # a run (i.e. plausible real table gutters) get " | " joined into
        # one row. A run by itself becomes one or more separate output lines.
        runs, run_buf = [], [cells[0]]
        for is_hard, cell in zip(hard_break_before[1:], cells[1:]):
            if is_hard:
                runs.append(run_buf)
                run_buf = [cell]
            else:
                run_buf.append(cell)
        runs.append(run_buf)

        for run in runs:
            if len(run) > 1:
                table_row_count += 1
                cell_texts = [" ".join(b["text"] for b in cell).strip() for cell in run]
                row_score = sum(b["score"] for cell in run for b in cell) / max(sum(len(c) for c in run), 1)
                ordered.append((" | ".join(t for t in cell_texts if t), row_score))
            else:
                # Single cell in this run → not a table gutter, just one
                # continuous phrase. Join its boxes with spaces.
                cell = run[0]
                joined_text = " ".join(b["text"] for b in cell).strip()
                row_score = sum(b["score"] for b in cell) / max(len(cell), 1)
                ordered.append((joined_text, row_score))
    return ordered, table_row_count


# Tracks consecutive PaddleOCR failures across calls. A handful of genuinely
# blank/unreadable pages failing in a row is normal; dozens in a row almost
# always means the native predict() backend has crashed or gotten into a
# corrupted state (segfault recovered by the C++ layer, OOM-truncated
# allocation, etc) rather than that 30+ pages in a row are all unreadable.
# Python's try/except around engine.predict() cannot catch a native crash —
# it can only catch the case where Paddle returns cleanly but empty — so
# this counter is what actually detects "the engine is dead" and forces a
# fresh singleton instead of silently returning [] for every remaining page.
_PADDLE_CONSECUTIVE_FAILURES = 0
_PADDLE_FAILURE_RESET_THRESHOLD = 8


def _reset_paddle_singleton(reason: str = ""):
    """Tears down the PaddleOCR singleton so the next call re-initializes it
    from scratch. Used when repeated failures suggest the engine has crashed
    or entered a bad state, rather than that pages are individually unreadable."""
    global _PADDLE_INSTANCE, _PADDLE_AVAILABLE, _PADDLE_CONSECUTIVE_FAILURES
    logger.error(f"PaddleOCR singleton reset triggered: {reason}")
    with _PADDLE_INIT_LOCK:
        _PADDLE_INSTANCE = None
        _PADDLE_AVAILABLE = None
    _PADDLE_CONSECUTIVE_FAILURES = 0


def call_paddle_ocr(image_path: str, page_num: int = 0) -> tuple:
    """
    Runs the PaddleOCR singleton on a rendered page image.
    The actual predict() call is serialized through _PADDLE_INFER_LOCK.
    Returns (lines: list[str], avg_confidence: float, is_tabular: bool).
    is_tabular is True when >=2 rows on the page looked like real table rows
    (multi-cell, gap-detected) — callers can use this to trigger a real
    PP-StructureV3 table-structure pass instead of trusting the heuristic
    " | " join alone.

    Tracks consecutive failures: if PaddleOCR returns nothing/errors many
    times in a row, the singleton is assumed dead/corrupted and is torn down
    so the NEXT call rebuilds it fresh — this is what stops one bad page from
    silently killing OCR quality for every remaining page in a large batch.
    """
    global _PADDLE_CONSECUTIVE_FAILURES

    try:
        engine = get_ocr_instance()
    except Exception as e:
        logger.error(f"Page {page_num}: PaddleOCR init failed: {e}")
        return [], 0.0, False

    with _PADDLE_INFER_LOCK:
        try:
            results = engine.predict(image_path)
        except Exception as e:
            logger.error(f"Page {page_num}: PaddleOCR predict failed: {e}")
            _PADDLE_CONSECUTIVE_FAILURES += 1
            if _PADDLE_CONSECUTIVE_FAILURES >= _PADDLE_FAILURE_RESET_THRESHOLD:
                _reset_paddle_singleton(
                    f"{_PADDLE_CONSECUTIVE_FAILURES} consecutive predict() exceptions "
                    f"(last at page {page_num})"
                )
            return [], 0.0, False

    if not results:
        _PADDLE_CONSECUTIVE_FAILURES += 1
        if _PADDLE_CONSECUTIVE_FAILURES >= _PADDLE_FAILURE_RESET_THRESHOLD:
            _reset_paddle_singleton(
                f"{_PADDLE_CONSECUTIVE_FAILURES} consecutive empty predict() results "
                f"(last at page {page_num}) — engine likely crashed/corrupted"
            )
        return [], 0.0, False

    res = results[0]
    rec_texts = res.get("rec_texts", []) if hasattr(res, "get") else getattr(res, "rec_texts", [])
    rec_scores = res.get("rec_scores", []) if hasattr(res, "get") else getattr(res, "rec_scores", [])
    rec_boxes = res.get("rec_boxes", None) if hasattr(res, "get") else getattr(res, "rec_boxes", None)

    if rec_texts is None or len(rec_texts) == 0:
        # A clean-but-empty result on a non-blank page (classify_scanned_page
        # already filtered out actually-blank pages before this is called) is
        # also suspicious — count it the same way as a hard failure.
        _PADDLE_CONSECUTIVE_FAILURES += 1
        if _PADDLE_CONSECUTIVE_FAILURES >= _PADDLE_FAILURE_RESET_THRESHOLD:
            _reset_paddle_singleton(
                f"{_PADDLE_CONSECUTIVE_FAILURES} consecutive zero-text results "
                f"(last at page {page_num}) — engine likely crashed/corrupted"
            )
        return [], 0.0, False

    # Real, non-empty result — engine is healthy again, reset the counter.
    _PADDLE_CONSECUTIVE_FAILURES = 0

    ordered, table_row_count = _sort_paddle_reading_order(rec_texts, rec_scores, rec_boxes)
    lines = [t.strip() for t, s in ordered if t and t.strip()]
    scores = [s for _, s in ordered if s is not None]
    avg_conf = (sum(scores) / len(scores)) if scores else 0.0
    is_tabular = table_row_count >= _TABLE_MIN_ROWS_TO_TRIGGER
    return lines, round(float(avg_conf), 3), is_tabular


# ======================================================
# TESSERACT FALLBACK (offline safety net)
# ======================================================

_TESSERACT_AVAILABLE = None
_TESSERACT_LANG_CACHE = None

def _init_tesseract():
    global _TESSERACT_AVAILABLE
    if _TESSERACT_AVAILABLE is not None:
        return _TESSERACT_AVAILABLE
    try:
        import pytesseract
        tess_path = shutil.which("tesseract")
        if tess_path:
            pytesseract.pytesseract.tesseract_cmd = tess_path
        pytesseract.get_tesseract_version()
        _TESSERACT_AVAILABLE = True
        _tlog("Tesseract fallback: available.")
    except Exception:
        _TESSERACT_AVAILABLE = False
        _tlog("Tesseract fallback: NOT available.")
    return _TESSERACT_AVAILABLE


def _get_tesseract_lang() -> str:
    global _TESSERACT_LANG_CACHE
    if _TESSERACT_LANG_CACHE:
        return _TESSERACT_LANG_CACHE
    try:
        import subprocess
        r = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=5)
        _TESSERACT_LANG_CACHE = "eng+hin" if "hin" in (r.stdout + r.stderr) else "eng"
    except Exception:
        _TESSERACT_LANG_CACHE = "eng"
    _tlog(f"Tesseract lang: {_TESSERACT_LANG_CACHE}")
    return _TESSERACT_LANG_CACHE


def run_tesseract_fallback(pil_img) -> list:
    """Last-resort Tesseract OCR. Returns list of text lines."""
    if not _init_tesseract():
        return []
    temp_path = None
    try:
        import pytesseract
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            temp_path = tmp.name
            pil_img.save(temp_path)
        lang = _get_tesseract_lang()
        text = pytesseract.image_to_string(temp_path, lang=lang, config="--oem 1 --psm 6")
        return [l.strip() for l in text.split("\n") if l.strip()]
    except Exception as e:
        logger.warning(f"Tesseract fallback error: {e}")
        return []
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass


# ======================================================
# IMAGE UTILITIES
# ======================================================

def guard_and_downscale_image(pil_img):
    """Downscale images that would exceed ~80MB in memory."""
    w, h = pil_img.size
    est = w * h * 3
    if est > 80 * 1024 * 1024:
        ratio = min(1800.0 / w, (80.0 * 1024 * 1024 / est) ** 0.5)
        nw, nh = int(w * ratio), int(h * ratio)
        logger.info(f"Downscaling {w}x{h} → {nw}x{nh} (memory guard)")
        return pil_img.resize((nw, nh), Image.Resampling.LANCZOS)
    return pil_img


def preprocess_for_vision(pil_img) -> Image.Image:
    """
    Lightweight preprocessing optimised for vision model input:
    - Convert to RGB (model expects colour)
    - Mild CLAHE contrast boost (helps faded scans)
    - NO binarization — vision models read grayscale gradients better than hard thresholds
    """
    try:
        import cv2
        img_np = np.array(pil_img.convert("RGB"))
        # Convert to LAB, apply CLAHE to L channel only
        lab = cv2.cvtColor(img_np, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        enhanced = cv2.merge([l, a, b])
        rgb = cv2.cvtColor(enhanced, cv2.COLOR_LAB2RGB)
        del img_np, lab, l, a, b, enhanced
        gc.collect()
        return Image.fromarray(rgb)
    except Exception as e:
        logger.warning(f"Preprocessing failed, using original: {e}")
        return pil_img.convert("RGB")


def image_to_base64(pil_img, quality: int = 85) -> str:
    """Encodes PIL image to base64 JPEG string for Ollama API."""
    buf = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)
    pil_img.save(buf, format="JPEG", quality=quality, optimize=True)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    buf.close()
    return encoded


def classify_scanned_page(pil_img) -> str:
    """
    Fast visual page classifier.
    Returns: 'blank', 'low-content', 'text-heavy', 'image-heavy'
    """
    try:
        import cv2
        img_np = np.array(pil_img)
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY) if len(img_np.shape) == 3 else img_np.copy()
        variance = np.var(gray)
        stddev = np.std(gray)
        if variance < 50.0 or stddev < 7.0:
            return "blank"
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ratio = np.sum(thresh == 255) / thresh.size
        del img_np, gray, thresh
        gc.collect()
        if ratio < 0.0015:
            return "blank"
        if ratio < 0.03:
            return "low-content"
        if ratio <= 0.25:
            return "text-heavy"
        return "image-heavy"
    except Exception:
        return "text-heavy"


def save_ocr_debug_image(filename: str, img):
    if not DEBUG_OCR:
        return
    try:
        import cv2
        img_np = np.array(img) if isinstance(img, Image.Image) else img
        if len(img_np.shape) == 3:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        cv2.imwrite(filename, img_np)
    except Exception as e:
        logger.warning(f"Debug image save failed: {e}")


# ======================================================
# DIGITAL PDF TEXT EXTRACTION (fast path)
# ======================================================

def extract_digital_pdf_text(file_path: str) -> list:
    """Extract text from native digital PDF — fast, no OCR needed."""
    try:
        reader = PdfReader(file_path)
        lines = []
        for i, page in enumerate(reader.pages):
            lines.append(f"--- PAGE {i+1} ---")
            text = page.extract_text()
            if text:
                for l in text.split("\n"):
                    l = l.strip()
                    if l:
                        lines.append(l)
        return lines
    except Exception as e:
        logger.warning(f"Digital PDF extraction failed: {e}")
        return []


def extract_alternate_pdf_text(file_path: str) -> list:
    """PyMuPDF + pdfplumber fallback for digital PDFs."""
    lines = []
    try:
        import fitz
        with fitz.open(file_path) as doc:
            mupdf_lines = []
            for i, page in enumerate(doc):
                mupdf_lines.append(f"--- PAGE {i+1} ---")
                text = page.get_text()
                if text:
                    for l in text.split("\n"):
                        l = l.strip()
                        if l:
                            mupdf_lines.append(l)
            if len(mupdf_lines) > 20:
                lines = mupdf_lines
    except Exception as e:
        logger.warning(f"PyMuPDF alternate extraction failed: {e}")
    if len(lines) < 25:
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                plumber_lines = []
                for i, page in enumerate(pdf.pages):
                    plumber_lines.append(f"--- PAGE {i+1} ---")
                    text = page.extract_text()
                    if text:
                        for l in text.split("\n"):
                            l = l.strip()
                            if l:
                                plumber_lines.append(l)
                if len(plumber_lines) > len(lines):
                    lines = plumber_lines
        except Exception as e:
            logger.warning(f"pdfplumber alternate extraction failed: {e}")
    return lines


def is_extracted_text_sparse(text_lines: list) -> bool:
    """Returns True if digital text extraction failed or produced garbage."""
    actual = [l for l in text_lines if not l.strip().startswith("--- PAGE")]
    if len(actual) < 15:
        return True
    full_text = " ".join(actual).lower()
    legal_kws = ["tribunal", "claimant", "petitioner", "accident", "compensation",
                 "deceased", "injured", "insurance", "award", "judgment"]
    kw_hits = sum(1 for kw in legal_kws if kw in full_text)
    words = [w for w in full_text.split() if w]
    if not words:
        return True
    avg_word_len = sum(len(w) for w in words) / len(words)
    gibberish = sum(1 for w in words if len(w) > 15 or any(c in w for c in "@#$[]{}|"))
    gibberish_ratio = gibberish / len(words)
    is_poor = (
        (kw_hits < 3 and len(actual) > 50) or
        (gibberish_ratio > 0.05) or
        (avg_word_len > 12.0) or
        (avg_word_len < 2.5 and len(actual) > 50)
    )
    if is_poor:
        logger.info(f"Digital text layer: poor quality (hits={kw_hits}, gibberish={gibberish_ratio:.2f}). Triggering OCR.")
    return is_poor


# ======================================================
# OCR QUALITY SCORING
# ======================================================

def score_ocr_page_quality(text_lines: list) -> float:
    real = [l for l in text_lines if l and not l.startswith("--- PAGE")]
    if not real:
        return 0.0
    line_score = min(len(real) / 10.0, 1.0)
    full = " ".join(real).lower()
    kw_hits = sum(1 for kw in _LEGAL_QUALITY_KEYWORDS if kw in full)
    kw_score = min(kw_hits / 5.0, 1.0)
    words = full.split()
    if words:
        avg_len = sum(len(w) for w in words) / len(words)
        word_score = 1.0 if 3.0 <= avg_len <= 10.0 else max(0.0, 1.0 - abs(avg_len - 6.5) / 6.5)
    else:
        word_score = 0.0
    avg_line_len = sum(len(l) for l in real) / len(real)
    density_score = min(avg_line_len / 40.0, 1.0)
    return round(
        (line_score * 0.30) + (kw_score * 0.35) + (word_score * 0.20) + (density_score * 0.15),
        3
    )


def _build_ocr_debug(
    engine_used, retry_count, quality_score, failed_pages, successful_pages,
    preprocessing_applied, fallback_ocr_engine, text_density_score,
    average_page_confidence=0.0, raw_ocr_preview="", pages=None, total_ocr_time=0.0
) -> dict:
    return {
        "ocr_engine_used": engine_used,
        "ocr_retry_count": retry_count,
        "ocr_quality_score": round(quality_score, 3),
        "successful_pages": successful_pages,
        "failed_pages": failed_pages,
        "fallback_ocr_engine": fallback_ocr_engine,
        "preprocessing_applied": preprocessing_applied,
        "text_density_score": round(text_density_score, 3),
        "average_page_confidence": round(average_page_confidence, 3),
        "raw_ocr_preview": raw_ocr_preview,
        "pages": pages or [],
        "total_ocr_time": round(total_ocr_time, 2)
    }


def _paddle_result_is_trustworthy(lines, confidence, quality_score):
    return (
        bool(lines)
        and confidence >= OCR_PADDLE_CONF_THRESHOLD
        and quality_score >= OCR_PADDLE_QUALITY_THRESHOLD
    )


# ======================================================
# CORE VISION OCR — SINGLE PAGE
# ======================================================

def ocr_page_with_vision(
    page_idx: int,
    total_pages: int,
    rendered_img_path: str,      # pre-rendered PNG path (or None = use fitz cache)
    fitz_text: str = "",         # cached digital text from fitz (may be empty)
    pdf_path: str = None,        # original PDF path (for retry renders)
    vision_available: bool = True,
    paddle_available: bool = True
) -> tuple:
    """
    Processes a single page through the hybrid OCR pipeline.

    Decision tree:
    1. If fitz has good digital text → return it directly (fastest path)
    2. Classify the rendered image:
       a. blank → skip
       b. low-content → PaddleOCR (fast, sufficient for sparse printed text)
       c. text-heavy / image-heavy → PaddleOCR FIRST (fast, CPU-only, strong on
          printed Hindi+English, tables/columns). Only escalate to qwen2.5vl:7b
          if Paddle's confidence/quality is low — i.e. handwriting, stamps,
          seals, or badly garbled mixed-script text, which Paddle struggles with.
    3. If both PaddleOCR and vision return nothing → Tesseract (last resort)
    4. If quality is still poor → retry at higher DPI (once), same order

    Returns (lines: list[str], page_meta: dict)
    """
    page_num = page_idx + 1
    start = time.time()

    # ── 1. Fast path: trust fitz digital text ───────────────────────
    if fitz_text and len(fitz_text.strip()) > 200:
        keywords = ["court", "claimant", "petitioner", "respondent", "accident",
                    "compensation", "tribunal", "judgment", "deceased", "injured"]
        hits = sum(1 for kw in keywords if kw in fitz_text.lower())
        native_lines = [l.strip() for l in fitz_text.split("\n") if l.strip()]
        # Check for Devanagari mojibake (garbled Hindi in digital layer)
        is_mojibake = _looks_like_devanagari_mojibake(native_lines)
        if hits >= 2 and not is_mojibake:
            lines = native_lines
            elapsed = time.time() - start
            meta = {
                "page": page_num, "engine": "PyMuPDF", "dpi": 72,
                "confidence": 1.0, "text_length": len(fitz_text),
                "quality_score": 1.0, "preprocessing_applied": [],
                "lines": len(lines), "ocr_boxes": [],
                "render_time": 0.0, "ocr_time": elapsed, "total_page_time": elapsed,
                "confidence_untrusted": False
            }
            logger.info(f"Page {page_num}: PyMuPDF fast path ({len(lines)} lines, {elapsed:.2f}s)")
            return lines, meta

    # ── 2. Load rendered image ────────────────────────────────────────
    if rendered_img_path is None or rendered_img_path == "error":
        meta = {
            "page": page_num, "engine": "Error", "dpi": OCR_RENDER_DPI,
            "confidence": 0.0, "text_length": 0, "quality_score": 0.0,
            "preprocessing_applied": [], "lines": 0, "ocr_boxes": [],
            "render_time": 0.0, "ocr_time": 0.0, "total_page_time": time.time() - start,
            "confidence_untrusted": False
        }
        return [], meta

    try:
        pil_img = Image.open(rendered_img_path).convert("RGB")
    except Exception as e:
        logger.error(f"Page {page_num}: Cannot open rendered image: {e}")
        return [], {
            "page": page_num, "engine": "Error", "dpi": OCR_RENDER_DPI,
            "confidence": 0.0, "text_length": 0, "quality_score": 0.0,
            "preprocessing_applied": [], "lines": 0, "ocr_boxes": [],
            "render_time": 0.0, "ocr_time": 0.0, "total_page_time": time.time() - start,
            "confidence_untrusted": False
        }

    # ── 3. Blank page check ───────────────────────────────────────────
    classification = classify_scanned_page(pil_img)
    if classification == "blank":
        del pil_img
        gc.collect()
        elapsed = time.time() - start
        logger.info(f"Page {page_num}: blank — skipped.")
        return [], {
            "page": page_num, "engine": "Skipped-blank", "dpi": OCR_RENDER_DPI,
            "confidence": 1.0, "text_length": 0, "quality_score": 0.0,
            "preprocessing_applied": [], "lines": 0, "ocr_boxes": [],
            "render_time": 0.0, "ocr_time": 0.0, "total_page_time": elapsed,
            "confidence_untrusted": False
        }

    # ── 4. Downscale only — defer the (CPU/RAM-costly) CLAHE/colour-space
    # preprocessing until we actually know we need it. PaddleOCR (the engine
    # that handles the large majority of pages) reads `rendered_img_path`
    # directly off disk and never touches `processed` — running CLAHE on
    # every single page unconditionally was pure wasted CPU + an extra
    # full-resolution image copy held in RAM for every page in the batch,
    # even ones that finish on the PaddleOCR-only fast path. `_get_processed()`
    # computes it once, lazily, only on the paths that truly need it
    # (vision escalation / Tesseract fallback / debug dump).
    pil_img = guard_and_downscale_image(pil_img)
    _processed_cache = {}

    def _get_processed():
        if "img" not in _processed_cache:
            _processed_cache["img"] = preprocess_for_vision(pil_img)
            save_ocr_debug_image(f"debug_page_{page_num}.png", _processed_cache["img"])
        return _processed_cache["img"]

    lines = []
    engine_used = ""
    ocr_start = time.time()
    confidence = 0.0

    # ── 5a. Low-content → PaddleOCR (fast, no GPU needed) ────────────
    if classification == "low-content":
        paddle_lines, paddle_conf, paddle_q = [], 0.0, 0.0
        if paddle_available:
            logger.info(f"Page {page_num}: low-content → PaddleOCR")
            paddle_lines, paddle_conf, _ = call_paddle_ocr(rendered_img_path, page_num=page_num)
            paddle_q = score_ocr_page_quality(paddle_lines)

        if _paddle_result_is_trustworthy(paddle_lines, paddle_conf, paddle_q):
            lines, engine_used, confidence = paddle_lines, "PaddleOCR", paddle_conf
        elif vision_available and OCR_ENABLE_VISION_ESCALATION and not _vision_is_paused():
            _tlog(f"[OCR] Page {page_num}: low-content Paddle result untrusted "
                  f"(conf={paddle_conf:.2f}, q={paddle_q:.2f}, lines={len(paddle_lines)}) "
                  f"-> escalating to vision")
            img_b64 = image_to_base64(_get_processed(), quality=85)
            raw_text = call_vision_model(img_b64, page_num=page_num)
            del img_b64
            vis_lines = [l.strip() for l in raw_text.split("\n") if l.strip()] if raw_text and raw_text.strip() != "[BLANK PAGE]" else []
            if vis_lines:
                lines, engine_used, confidence = vis_lines, "qwen2.5vl:7b", 0.85
            elif paddle_lines and paddle_conf > 0.0:
                # vision found nothing either — Paddle's untrusted output is
                # still strictly better than nothing; keep it but flag it
                lines, engine_used, confidence = paddle_lines, "PaddleOCR", paddle_conf
        elif paddle_lines and paddle_conf > 0.0:
            # vision unavailable/paused/disabled — same "best we have" fallback
            lines, engine_used, confidence = paddle_lines, "PaddleOCR", paddle_conf

        if not lines:
            lines = run_tesseract_fallback(_get_processed())
            engine_used = "Tesseract"
            confidence = 0.70 if lines else 0.0

    # ── 5b. Text/image-heavy → PaddleOCR first, escalate to vision ──
    else:
        paddle_is_tabular = False
        if paddle_available:
            logger.info(f"Page {page_num}: {classification} → PaddleOCR")
            paddle_lines, paddle_conf, paddle_is_tabular = call_paddle_ocr(rendered_img_path, page_num=page_num)
            paddle_q = score_ocr_page_quality(paddle_lines)
            paddle_good = _paddle_result_is_trustworthy(paddle_lines, paddle_conf, paddle_q)
            if paddle_good:
                lines, engine_used, confidence = paddle_lines, "PaddleOCR", paddle_conf
            elif vision_available and OCR_ENABLE_VISION_ESCALATION and not _vision_is_paused():
                logger.info(f"Page {page_num}: PaddleOCR quality low (conf={paddle_conf:.2f}, q={paddle_q:.2f}) → escalating to qwen2.5vl:7b")
                img_b64 = image_to_base64(_get_processed(), quality=85)
                raw_text = call_vision_model(img_b64, page_num=page_num)
                del img_b64
                vis_lines = [l.strip() for l in raw_text.split("\n") if l.strip()] if raw_text and raw_text.strip() != "[BLANK PAGE]" else []
                vis_q = score_ocr_page_quality(vis_lines)
                # Vision must clearly beat Paddle on the quality score, not just be
                # longer — "more lines" alone is a weak/gameable signal (vision models
                # can hallucinate repeated boilerplate or split single lines, which
                # would otherwise let a worse transcription win purely on line count).
                # Require a real quality margin; only fall back to the line-count
                # signal when Paddle produced essentially nothing to compare against.
                vision_wins = (
                    (vis_lines and not paddle_lines) or
                    (vis_lines and vis_q >= paddle_q + 0.05)
                )
                if vision_wins:
                    lines, engine_used, confidence = vis_lines, "qwen2.5vl:7b", 0.90
                elif _paddle_result_is_trustworthy(paddle_lines, paddle_conf, paddle_q):
                    lines, engine_used, confidence = paddle_lines, "PaddleOCR", paddle_conf
                elif vis_lines:
                    lines, engine_used, confidence = vis_lines, "qwen2.5vl:7b", 0.75
                elif paddle_lines and paddle_conf > 0.0:
                    # last resort: vision tried and found nothing usable either,
                    # Paddle's untrusted output is still the best we have (if > 0.0)
                    lines, engine_used, confidence = paddle_lines, "PaddleOCR", paddle_conf
                    _tlog(f"[OCR] Page {page_num}: accepting untrusted PaddleOCR output "
                          f"(conf={paddle_conf:.2f}) — vision escalation found nothing better")
            elif _paddle_result_is_trustworthy(paddle_lines, paddle_conf, paddle_q):
                # Paddle's result is the best we have (vision unavailable/disabled)
                lines, engine_used, confidence = paddle_lines, "PaddleOCR", paddle_conf
        elif vision_available:
            logger.info(f"Page {page_num}: PaddleOCR unavailable → qwen2.5vl:7b")
            img_b64 = image_to_base64(_get_processed(), quality=85)
            raw_text = call_vision_model(img_b64, page_num=page_num)
            del img_b64
            if raw_text and raw_text.strip() != "[BLANK PAGE]":
                lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
                engine_used, confidence = "qwen2.5vl:7b", 0.90

        # ── 5b-bis. Real table-structure pass ─────────────────────────
        # If the page settled on PaddleOCR's output AND the cheap heuristic
        # already flagged it as tabular (>=2 multi-cell rows), run the
        # heavier PP-StructureV3 layout/table model on this one page to get
        # actual table structure (proper cells, not a gap-guessed " | "
        # join), and append it. This only fires for pages that need it —
        # not a blanket cost on every page in the batch.
        if engine_used == "PaddleOCR" and paddle_is_tabular and OCR_ENABLE_TABLE_STRUCTURE:
            table_mds = extract_tables_via_structure(rendered_img_path, page_num=page_num)
            if table_mds:
                lines = list(lines) + ["", "[STRUCTURED TABLE — PP-StructureV3]"]
                for tmd in table_mds:
                    lines.extend(tmd.split("\n"))

        # ── 5c. Nothing worked → Tesseract (last resort) ─────────────
        if not lines:
            lines = run_tesseract_fallback(_get_processed())
            engine_used = "Tesseract"
            confidence = 0.70 if lines else 0.0

        # If every engine genuinely produced nothing on a page we already
        # know is NOT blank (classify_scanned_page said so above), don't let
        # it disappear silently and look identical to a skipped blank page.
        # This is exactly the case you flagged: a visually dense page (logo,
        # stamps, large multi-column handwritten table) can legitimately
        # defeat all three engines — surface that instead of hiding it.
        if not lines:
            lines = [f"[OCR FAILED — page has visible content but no text engine "
                     f"could extract it. Engines attempted: PaddleOCR, "
                     f"{'qwen2.5vl (paused/cooldown)' if _vision_is_paused() else 'qwen2.5vl'}, "
                     f"Tesseract. Manual review recommended — see rendered page image.]"]
            engine_used = "Failed-AllEngines"
            confidence = 0.0

    ocr_time = time.time() - ocr_start
    q_score = score_ocr_page_quality(lines)

    # ── 6. Poor quality retry at higher DPI ─────────────────────────
    is_poor = (len(lines) == 0 or q_score < 0.15 or confidence < 0.30)
    if is_poor and classification != "blank" and OCR_RETRY_DPI > OCR_RENDER_DPI and pdf_path:
        logger.info(f"Page {page_num}: poor quality (q={q_score:.2f}) → retrying at {OCR_RETRY_DPI} DPI")
        _processed_cache.clear()
        del pil_img
        gc.collect()
        try:
            retry_img_path = rendered_img_path.replace(".png", "_retry.png")
            import fitz
            with fitz.open(pdf_path) as doc:
                retry_mat = fitz.Matrix(OCR_RETRY_DPI / 72.0, OCR_RETRY_DPI / 72.0)
                pix = doc[page_idx].get_pixmap(matrix=retry_mat, alpha=False)
                retry_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                retry_img = guard_and_downscale_image(retry_img)
                retry_img.save(retry_img_path)
                del pix
            retry_proc = preprocess_for_vision(Image.open(retry_img_path).convert("RGB"))
            retry_lines_best = []
            if paddle_available:
                retry_lines_best, retry_paddle_conf, _ = call_paddle_ocr(retry_img_path, page_num=page_num)
                if retry_lines_best and len(retry_lines_best) > len(lines):
                    lines = retry_lines_best
                    engine_used = "PaddleOCR-retry"
                    confidence = retry_paddle_conf
                    q_score = score_ocr_page_quality(lines)
            if (not retry_lines_best or q_score < OCR_PADDLE_QUALITY_THRESHOLD) and vision_available and OCR_ENABLE_VISION_ESCALATION:
                retry_b64 = image_to_base64(retry_proc, quality=85)
                retry_text = call_vision_model(retry_b64, page_num=page_num)
                del retry_b64
                if retry_text and retry_text.strip() != "[BLANK PAGE]":
                    retry_vis_lines = [l.strip() for l in retry_text.split("\n") if l.strip()]
                    if len(retry_vis_lines) > len(lines):
                        lines = retry_vis_lines
                        engine_used = "qwen2.5vl:7b-retry"
                        confidence = 0.90
                        q_score = score_ocr_page_quality(lines)
            if not lines:
                retry_lines = run_tesseract_fallback(retry_proc)
                if len(retry_lines) > len(lines):
                    lines = retry_lines
                    engine_used = "Tesseract-retry"
                    confidence = 0.70
                    q_score = score_ocr_page_quality(lines)
            del retry_proc
            if os.path.exists(retry_img_path):
                os.unlink(retry_img_path)
        except Exception as retry_err:
            logger.warning(f"Page {page_num}: retry failed: {retry_err}")
    else:
        _processed_cache.clear()
        del pil_img
        gc.collect()

    elapsed = time.time() - start
    try:
        ram_mb = int(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024))
    except Exception:
        ram_mb = 0

    _tlog(f"Page {page_num:>3}/{total_pages} | {engine_used:<20} | {len(lines):>4} lines | q={q_score:.2f} | {elapsed:.1f}s | RAM={ram_mb}MB")

    meta = {
        "page": page_num, "engine": engine_used, "dpi": OCR_RENDER_DPI,
        "confidence": round(confidence, 3),
        "text_length": sum(len(l) for l in lines),
        "quality_score": q_score,
        "preprocessing_applied": ["rgb_convert", "clahe_contrast"],
        "lines": len(lines), "ocr_boxes": [],
        "render_time": 0.0, "ocr_time": ocr_time, "total_page_time": elapsed,
        "confidence_untrusted": confidence == 0.0 and bool(lines)
    }
    return lines, meta


def _looks_like_devanagari_mojibake(lines: list) -> bool:
    """Heuristic: detects garbled English output from a Devanagari page."""
    if not lines:
        return False
    suspect = 0
    total = 0
    for line in lines:
        s = line.strip()
        if len(s) < 4:
            continue
        alpha = sum(1 for c in s if c.isalpha())
        if alpha == 0:
            continue
        total += 1
        if (alpha / len(s)) < 0.55:
            suspect += 1
    if total == 0:
        return False
    return suspect >= 2 or (suspect / total) > 0.40


# ======================================================
# SCANNED PDF OCR PIPELINE
# ======================================================

# ======================================================
# HEADING-TARGETED PAGE FINDER (lower-court / Hindi bundles)
# ======================================================
#
# Large trial-court bundles (200-300+ scanned pages, mostly Hindi, mixed
# with administrative/registry images) make it prohibitively slow to run
# the full Paddle→vision pipeline on every page just to autofill a handful
# of numeric/date fields. The fields we actually need for autofill live on
# 1-4 short, structured pages (the "केन्द्रीय भरण काउन्टर" cover sheet, the
# award's operative/compensation-table pages) that can be located by
# heading text, not by page number (position varies bundle to bundle).
#
# Strategy: a cheap, low-DPI, Paddle-only first pass (no vision, no retry)
# scans pages in order and stops as soon as every target heading has been
# found (or a hard page cap is hit, so a 271-page bundle can never make
# this pass unbounded). Only the matched pages are then promoted to the
# full-quality Paddle→vision pipeline.

OCR_HEADING_SCAN_DPI = int(os.getenv("OCR_HEADING_SCAN_DPI", "110"))
OCR_HEADING_SCAN_MAX_PAGES = int(os.getenv("OCR_HEADING_SCAN_MAX_PAGES", "80"))
OCR_HEADING_SCAN_WIDEN_MAX_PAGES = int(os.getenv("OCR_HEADING_SCAN_WIDEN_MAX_PAGES", "150"))


def find_relevant_pages_by_heading(
    pdf_path: str,
    heading_keywords: dict,
    max_scan_pages: int = None,
    quick_dpi: int = None,
    stop_after_all_found: bool = True,
) -> dict:
    """
    Fast first pass: low-DPI Paddle-only OCR per page (no vision escalation,
    no retry-at-higher-DPI), matched against `heading_keywords`
    (dict[str, list[str]]). Returns {heading_key: page_idx (0-based)}.

    Bails out early once every non-skip heading key has been matched, so a
    'central filing counter' page near the front of a 271-page bundle costs
    a handful of page OCRs, not 271. `skip_admin_hi` (or any key literally
    named that) is excluded from the "stop once found" set — it exists only
    as a recognized-but-ignored keyword list for callers that want to
    explicitly exclude admin pages elsewhere; it is not a target to search for.
    """
    max_scan_pages = max_scan_pages or OCR_HEADING_SCAN_MAX_PAGES
    quick_dpi = quick_dpi or OCR_HEADING_SCAN_DPI

    found = {}
    target_keys = {k for k in heading_keywords.keys() if not k.startswith("skip_")}
    scanned = 0

    try:
        with pdfium.PdfDocument(pdf_path) as doc:
            total_pages = len(doc)
            scan_limit = min(total_pages, max_scan_pages)
            scale = quick_dpi / 72.0

            for idx in range(scan_limit):
                scanned = idx + 1
                try:
                    page_obj = doc[idx]
                    bitmap = page_obj.render(scale=scale)
                    pil_img = bitmap.to_pil()
                    del bitmap, page_obj
                except Exception as e:
                    logger.warning(f"[HEADING-SCAN] page {idx+1}: render failed: {e}")
                    continue

                pil_img = guard_and_downscale_image(pil_img)
                classification = classify_scanned_page(pil_img)
                if classification in ("blank", "image-heavy"):
                    del pil_img
                    continue

                tmp_path = os.path.join(tempfile.gettempdir(), f"_headscan_{uuid.uuid4().hex}.png")
                try:
                    pil_img.save(tmp_path, format="PNG")
                    lines, conf, _ = call_paddle_ocr(tmp_path, page_num=idx + 1)
                finally:
                    del pil_img
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)

                text = " ".join(lines).lower()
                for key, kws in heading_keywords.items():
                    if key.startswith("skip_") or key in found:
                        continue
                    if any(kw.lower() in text for kw in kws):
                        found[key] = idx
                        _tlog(f"[HEADING-SCAN] '{key}' matched on page {idx+1} (of {total_pages})")

                if stop_after_all_found and target_keys <= found.keys():
                    break

            _tlog(f"[HEADING-SCAN] scanned {scanned}/{total_pages} pages, "
                  f"found {len(found)}/{len(target_keys)} target headings: {list(found.keys())}")
    except Exception as e:
        logger.error(f"[HEADING-SCAN] failed: {e}")

    return found


def perform_targeted_ocr_lower_court(
    file_path: str,
    page_callback=None,
    heading_keywords: dict = None,
) -> tuple:
    """
    Lower-court / Hindi bundle entrypoint. Instead of OCRing every page
    (`perform_ocr_on_scanned_pdf` with scan_all_pages), locates the small
    set of pages that actually carry autofill-relevant fields via
    `find_relevant_pages_by_heading`, then runs the full Paddle→vision
    pipeline (`ocr_page_with_vision`, same quality/escalation logic used
    for every other page in this module) on ONLY those pages.

    Returns (text_lines, ocr_debug) in the same shape as
    perform_ocr_on_scanned_pdf, so callers/downstream parsing don't need to
    special-case the return type — only which parser they feed it to.
    """
    start_time = time.time()
    heading_keywords = heading_keywords or HINDI_HEADING_KEYWORDS
    vision_available = is_vision_model_available()
    paddle_available = is_paddle_available()

    target_pages = find_relevant_pages_by_heading(file_path, heading_keywords)
    page_idxs = sorted(set(target_pages.values()))

    if not page_idxs:
        # Nothing matched within the default cap — widen the scan once,
        # still bounded (never fall back to OCRing the whole bundle).
        _tlog(f"[TARGETED-OCR] no headings matched in first pass — widening scan to "
              f"{OCR_HEADING_SCAN_WIDEN_MAX_PAGES} pages")
        target_pages = find_relevant_pages_by_heading(
            file_path, heading_keywords, max_scan_pages=OCR_HEADING_SCAN_WIDEN_MAX_PAGES
        )
        page_idxs = sorted(set(target_pages.values()))

    with pdfium.PdfDocument(file_path) as doc:
        total_pages = len(doc)

    if not page_idxs:
        _tlog(f"[TARGETED-OCR] no target-heading pages found in {total_pages}-page bundle "
              f"— returning empty result (manual review recommended)")
        return [], _build_ocr_debug(
            "none", 0, 0.0, [], [], [], "none", 0.0,
            total_ocr_time=time.time() - start_time
        )

    text_lines = []
    pages_meta = []
    scale = OCR_RENDER_DPI / 72.0
    for i, idx in enumerate(page_idxs):
        with pdfium.PdfDocument(file_path) as doc:
            page_obj = doc[idx]
            bitmap = page_obj.render(scale=scale)
            pil_img = bitmap.to_pil()
            del bitmap, page_obj
        pil_img = guard_and_downscale_image(pil_img)
        classification = classify_scanned_page(pil_img)
        if classification in ("blank", "image-heavy"):
            del pil_img
            _tlog(f"[TARGETED-OCR] Page {idx+1} is {classification} — skipping expensive OCR")
            if page_callback:
                page_callback({
                    "page": idx + 1, "total_pages": total_pages,
                    "pages_done": i + 1, "engine": f"Skipped ({classification})",
                    "confidence": 0.0,
                    "quality_score": 0.0,
                    "lines": 0
                })
            continue

        img_path = os.path.join(tempfile.gettempdir(), f"_targeted_{uuid.uuid4().hex}.png")
        pil_img.save(img_path, format="PNG")
        del pil_img

        lines, meta = ocr_page_with_vision(
            page_idx=idx, total_pages=total_pages, rendered_img_path=img_path,
            pdf_path=file_path, vision_available=vision_available, paddle_available=paddle_available,
        )
        if os.path.exists(img_path):
            os.unlink(img_path)

        matched_headings = [k for k, v in target_pages.items() if v == idx]
        meta["matched_headings"] = matched_headings
        pages_meta.append(meta)
        text_lines.append(f"--- PAGE {idx + 1} ---")
        text_lines.extend(lines)

        if page_callback:
            page_callback({
                "page": idx + 1, "total_pages": total_pages,
                "pages_done": i + 1, "engine": meta.get("engine", ""),
                "confidence": meta.get("confidence", 0.0),
                "quality_score": meta.get("quality_score", 0.0),
                "lines": meta.get("lines", 0),
                "ocr_time": meta.get("ocr_time", 0.0),
                "total_page_time": meta.get("total_page_time", 0.0),
            })

    avg_conf = (sum(m.get("confidence", 0.0) for m in pages_meta) / len(pages_meta)) if pages_meta else 0.0
    avg_q = (sum(m.get("quality_score", 0.0) for m in pages_meta) / len(pages_meta)) if pages_meta else 0.0
    total_time = time.time() - start_time
    _tlog(f"[TARGETED-OCR] done: {len(page_idxs)}/{total_pages} pages OCR'd "
          f"(skipped {total_pages - len(page_idxs)}) in {total_time:.1f}s")

    ocr_debug = _build_ocr_debug(
        OCR_HYBRID_LABEL, 0, avg_q, [], [p + 1 for p in page_idxs], ["rgb_convert", "clahe_contrast"],
        "none", avg_q, average_page_confidence=avg_conf, pages=pages_meta, total_ocr_time=total_time
    )
    ocr_debug["targeted_pages"] = {k: v + 1 for k, v in target_pages.items()}
    ocr_debug["total_pages_in_bundle"] = total_pages
    ocr_debug["pages_skipped"] = total_pages - len(page_idxs)
    return text_lines, ocr_debug


def perform_ocr_on_scanned_pdf(
    file_path: str,
    progress_callback=None,
    page_callback=None,
    scan_all_pages: bool = False,
    original_filename: str = None
) -> tuple:
    """
    Main pipeline for scanned PDF OCR — hybrid PaddleOCR + qwen2.5vl:7b.

    Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │  Phase 1: Pre-render all pages → PNG files  (parallel, N cpus) │
    │  Phase 2: OCR each PNG: PaddleOCR first (serialised), escalate  │
    │           to qwen2.5vl:7b only for low-quality pages (also      │
    │           serialised). Render/preprocess/encode stays parallel.│
    └─────────────────────────────────────────────────────────────────┘

    PaddleOCR runs first on every non-blank page — it's fast, CPU-only, and
    strong on printed Hindi+English and tabular/columnar layouts. qwen2.5vl:7b
    is only invoked for pages where Paddle's confidence/quality is low
    (handwriting, stamps, seals, badly garbled mixed-script text). Tesseract
    remains the last-resort safety net if both are unavailable or both fail.
    """
    start_time = time.time()
    vision_available = is_vision_model_available()
    paddle_available = is_paddle_available()

    if not vision_available and not paddle_available and not _init_tesseract():
        _tlog("CRITICAL: No OCR engine available (PaddleOCR, vision, and Tesseract all unavailable)!")
        return [], _build_ocr_debug(
            "unavailable", 0, 0.0, [], [], [], "none", 0.0,
            total_ocr_time=time.time() - start_time
        )

    try:
        # ── Pre-cache fitz digital text ──────────────────────────────
        fitz_text_cache = []
        try:
            import fitz
            with fitz.open(file_path) as doc:
                fitz_text_cache = [page.get_text() for page in doc]
        except Exception as e:
            logger.warning(f"fitz pre-cache failed: {e}")

        with pdfium.PdfDocument(file_path) as tmp_doc:
            total_pages = len(tmp_doc)
        gc.collect()

        _tlog(f"PDF: {total_pages} pages | Paddle: {paddle_available} | Vision: {vision_available} | DPI: {OCR_RENDER_DPI}")

        # ── Phase 1: Pre-render all pages to PNG ─────────────────────
        # Rendering (pdfium decode + PNG encode) is CPU-bound and was
        # previously a single-threaded for-loop — on a 200+ page scanned
        # PDF that serial decode/encode step dominates wall-clock time
        # before any OCR even starts. pdfium page objects pulled from the
        # SAME PdfDocument are not safe to render concurrently from
        # multiple threads, so each render worker opens its own short-lived
        # PdfDocument handle (cheap: pdfium documents are just a file
        # handle + page index, not a full re-parse of page content).
        render_dir = tempfile.mkdtemp(prefix="ocr_render_")
        rendered_paths = {}   # page_idx → png path | None (fitz ok) | "error"
        scale = OCR_RENDER_DPI / 72.0

        digital_idxs = []
        render_idxs = []
        for idx in range(total_pages):
            ft = fitz_text_cache[idx] if idx < len(fitz_text_cache) else ""
            if ft and len(ft.strip()) > 200:
                kws = ["court", "claimant", "petitioner", "respondent", "accident",
                       "compensation", "tribunal", "judgment", "deceased", "injured"]
                hits = sum(1 for kw in kws if kw in ft.lower())
                native_lines = [l.strip() for l in ft.split("\n") if l.strip()]
                if hits >= 2 and not _looks_like_devanagari_mojibake(native_lines):
                    digital_idxs.append(idx)
                    continue
            render_idxs.append(idx)

        for idx in digital_idxs:
            rendered_paths[idx] = None   # use fitz text
            if page_callback:
                page_callback({
                    "page": idx + 1, "total_pages": total_pages,
                    "pages_done": len(rendered_paths),
                    "engine": "PyMuPDF", "confidence": 1.0,
                    "quality_score": 1.0, "lines": 0,
                    "ocr_time": 0.0, "total_page_time": 0.0
                })
        if digital_idxs:
            _tlog(f"[RENDER] {len(digital_idxs)} pages → PyMuPDF (digital text, no render needed)")

        def render_one_page(idx):
            try:
                with pdfium.PdfDocument(file_path) as doc:
                    page_obj = doc[idx]
                    bitmap = page_obj.render(scale=scale)
                    pil_img = bitmap.to_pil()
                    del bitmap, page_obj
                pil_img = guard_and_downscale_image(pil_img)
                img_path = os.path.join(render_dir, f"page_{idx:04d}.png")
                pil_img.save(img_path, format="PNG")
                del pil_img
                return idx, img_path
            except Exception as e:
                logger.error(f"Render failed page {idx+1}: {e}")
                return idx, "error"

        if render_idxs:
            # Rendering is pure CPU + I/O with no shared mutable model state,
            # so it is safe to run at full worker parallelism (independent of
            # the OCR-stage semaphores below, which guard the actual model calls).
            with _cf.ThreadPoolExecutor(max_workers=OCR_MAX_PARALLEL_WORKERS) as render_pool:
                for idx, result in render_pool.map(render_one_page, render_idxs):
                    rendered_paths[idx] = result
                    if len(rendered_paths) % 25 == 0 or len(rendered_paths) == total_pages:
                        _tlog(f"[RENDER] {len(rendered_paths)}/{total_pages} pages rendered")
            gc.collect()

        _tlog(f"[RENDER] Done. {len(rendered_paths)} pages mapped. Starting vision OCR...")

        # ── Phase 2: OCR all pages ────────────────────────────────────
        # Threads handle render+preprocess+encode in parallel.
        # The vision inference serializes through _VISION_SEMAPHORE inside call_vision_model().
        page_results = {}
        total_ocr_duration = 0.0

        def process_page(idx):
            ft = fitz_text_cache[idx] if idx < len(fitz_text_cache) else ""
            img_path = rendered_paths.get(idx, "error")
            # Hard cap: blocks here (no timeout, no "proceed anyway") until a
            # slot frees up. This is the real concurrency limiter — at most
            # OCR_MAX_PAGES_IN_FLIGHT pages are ever decoding/holding image
            # buffers simultaneously, regardless of how many threads/futures
            # are queued in the pool.
            with _PAGE_MEMORY_SLOTS:
                _wait_for_memory_headroom(page_num=idx + 1)
                try:
                    lines, meta = ocr_page_with_vision(
                        page_idx=idx,
                        total_pages=total_pages,
                        rendered_img_path=img_path,
                        fitz_text=ft,
                        pdf_path=file_path,
                        vision_available=vision_available,
                        paddle_available=paddle_available
                    )
                except Exception as e:
                    # Critical: without this, an exception on ANY single page
                    # propagates out of future.result() below and aborts the
                    # entire batch via perform_ocr_on_scanned_pdf's outer except —
                    # silently discarding results for every page that hadn't
                    # completed yet, even ones that succeeded fine. One bad page
                    # (corrupt render, a stamp/seal layout that crashes a native
                    # OCR call, a malformed Ollama response) must degrade to a
                    # single failed page, not take down the other 270.
                    logger.error(f"Page {idx + 1}: unhandled exception in process_page: {e}")
                    lines, meta = [], {
                        "page": idx + 1, "engine": "Error", "dpi": OCR_RENDER_DPI,
                        "confidence": 0.0, "text_length": 0, "quality_score": 0.0,
                        "preprocessing_applied": [], "lines": 0, "ocr_boxes": [],
                        "render_time": 0.0, "ocr_time": 0.0, "total_page_time": 0.0,
                        "error": str(e)
                    }
                finally:
                    # Release this page's memory back to the OS (malloc_trim,
                    # not just gc.collect) before the slot opens up for the
                    # next page — keeps RSS from ratcheting upward batch-wide.
                    _release_memory_to_os()
            return idx, lines, meta

        with _cf.ThreadPoolExecutor(max_workers=OCR_PAGE_WORKER_POOL_SIZE) as executor:
            futures = [executor.submit(process_page, idx) for idx in range(total_pages)]
            for future in _cf.as_completed(futures):
                try:
                    idx, page_lines, page_meta = future.result()
                except Exception as e:
                    # Should be unreachable now that process_page catches its own
                    # exceptions, but kept as a last-resort guard: even here, one
                    # future's failure must not cancel the rest of the batch.
                    logger.error(f"Unexpected future failure (process_page should have caught this): {e}")
                    continue
                page_results[idx] = (page_lines, page_meta)
                total_ocr_duration += page_meta.get("ocr_time", 0.0)
                pages_done = len(page_results)
                if progress_callback:
                    progress_callback(int((pages_done / total_pages) * 95))
                if page_callback:
                    page_callback({
                        "page": page_meta.get("page", idx + 1),
                        "total_pages": total_pages,
                        "pages_done": pages_done,
                        "engine": page_meta.get("engine", ""),
                        "confidence": page_meta.get("confidence", 0.0),
                        "quality_score": page_meta.get("quality_score", 0.0),
                        "lines": page_meta.get("lines", 0),
                        "ocr_time": round(page_meta.get("ocr_time", 0.0), 2),
                        "total_page_time": round(page_meta.get("total_page_time", 0.0), 2),
                    })

        # Cleanup render temp dir
        try:
            shutil.rmtree(render_dir)
        except Exception as e:
            logger.warning(f"Failed to clean render dir: {e}")

        # ── Compile results ───────────────────────────────────────────
        avg_ocr_time = total_ocr_duration / total_pages if total_pages else 0.0
        pages_with_results = len(page_results)
        never_processed = [i + 1 for i in range(total_pages) if i not in page_results]
        _tlog(f"[DONE] Total={total_ocr_duration:.1f}s  Avg/page={avg_ocr_time:.1f}s  "
              f"Workers={OCR_PAGE_WORKER_POOL_SIZE}  "
              f"Futures completed={pages_with_results}/{total_pages}")
        if never_processed:
            # If this ever fires, it proves a future genuinely never completed —
            # distinct from a page that was attempted and came back empty. This
            # is the single most important diagnostic for tracing where pages
            # silently disappear: it tells us definitively whether the executor
            # actually ran every page or quietly dropped some.
            logger.error(
                f"CRITICAL: {len(never_processed)} pages were never processed at all "
                f"(no future result recorded): {never_processed[:20]}"
                f"{' ...' if len(never_processed) > 20 else ''}"
            )

        text_lines, page_details = [], []
        failed_pages, successful_pages = [], []
        page_qualities, page_confidences = [], []
        fallback_engine = ""
        all_preprocessing = []
        total_retry_count = 0

        for idx in range(total_pages):
            page_num = idx + 1
            p_lines, p_meta = page_results.get(idx, ([], {}))
            q = p_meta.get("quality_score", 0.0)
            conf = p_meta.get("confidence", 0.0)
            engine = p_meta.get("engine", "")

            if "retry" in engine:
                total_retry_count += 1
            if "Tesseract" in engine:
                fallback_engine = "Tesseract"

            page_qualities.append(q)
            page_confidences.append(conf)
            page_details.append(p_meta)

            for step in p_meta.get("preprocessing_applied", []):
                if step not in all_preprocessing:
                    all_preprocessing.append(step)

            if p_lines:
                successful_pages.append(page_num)
            else:
                failed_pages.append(page_num)

            text_lines.append(f"--- PAGE {page_num} ---")
            text_lines.extend(p_lines)

        # Final outcome breakdown — one line that answers "what actually
        # happened to all 271 pages" without manually scrolling logs.
        from collections import Counter
        engine_counts = Counter(
            (page_results.get(i, ([], {}))[1].get("engine") or "NEVER_PROCESSED")
            for i in range(total_pages)
        )
        _tlog(f"[SUMMARY] Engine breakdown: {dict(engine_counts)}")
        _tlog(f"[SUMMARY] {len(successful_pages)}/{total_pages} pages produced text, "
              f"{len(failed_pages)}/{total_pages} pages produced nothing")

        overall_quality = round(sum(page_qualities) / len(page_qualities), 4) if page_qualities else 0.0
        overall_conf = round(sum(page_confidences) / len(page_confidences), 4) if page_confidences else 0.0
        real_lines = [l for l in text_lines if not l.startswith("--- PAGE")]
        text_density = round(
            sum(len(l) for l in real_lines) / max(len(real_lines), 1) / 80.0, 3
        ) if real_lines else 0.0

        elapsed_total = time.time() - start_time
        ocr_debug = _build_ocr_debug(
            engine_used=OCR_HYBRID_LABEL,
            retry_count=total_retry_count,
            quality_score=overall_quality,
            failed_pages=failed_pages,
            successful_pages=successful_pages,
            preprocessing_applied=all_preprocessing,
            fallback_ocr_engine=fallback_engine,
            text_density_score=min(text_density, 1.0),
            average_page_confidence=overall_conf,
            raw_ocr_preview="\n".join(text_lines)[:3000],
            pages=page_details,
            total_ocr_time=elapsed_total
        )

        # Searchable-PDF generation isn't wired up yet. PaddleOCR pages do carry
        # bounding boxes (rec_boxes), but pages that fell back to qwen2.5vl:7b
        # don't, so a hybrid searchable-PDF overlay is a separate piece of work.
        ocr_debug["searchable_pdf_url"] = ""

        return text_lines, ocr_debug

    except Exception as e:
        logger.error(f"Critical OCR pipeline error: {e}")
        return [], _build_ocr_debug(
            OCR_HYBRID_LABEL, 0, 0.0, [], [], [], "none", 0.0,
            total_ocr_time=time.time() - start_time
        )


def perform_ocr_on_image(file_path: str) -> tuple:
    """Single image file OCR — hybrid PaddleOCR + qwen2.5vl:7b (same order as the PDF pipeline)."""
    start_time = time.time()
    vision_available = is_vision_model_available()
    paddle_available = is_paddle_available()
    lines = []
    engine_used = ""
    confidence = 0.0
    temp_img_path = None

    try:
        pil_img = Image.open(file_path).convert("RGB")
        pil_img = guard_and_downscale_image(pil_img)
        processed = preprocess_for_vision(pil_img)
        del pil_img
        gc.collect()

        classification = classify_scanned_page(processed)

        if classification == "blank":
            del processed
            gc.collect()
        else:
            # PaddleOCR needs a file path, so persist the preprocessed image once
            # and reuse it for both Paddle and (if needed) the retry/Tesseract path.
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                temp_img_path = tmp.name
            processed.save(temp_img_path, format="PNG")

            if classification == "low-content":
                if paddle_available:
                    lines, confidence, _ = call_paddle_ocr(temp_img_path, page_num=1)
                    if lines:
                        engine_used = "PaddleOCR"
                if not lines:
                    lines = run_tesseract_fallback(processed)
                    engine_used = "Tesseract"
                    confidence = 0.70 if lines else 0.0
            else:
                img_is_tabular = False
                if paddle_available:
                    paddle_lines, paddle_conf, img_is_tabular = call_paddle_ocr(temp_img_path, page_num=1)
                    paddle_q = score_ocr_page_quality(paddle_lines)
                    paddle_good = bool(paddle_lines) and paddle_conf >= OCR_PADDLE_CONF_THRESHOLD and paddle_q >= OCR_PADDLE_QUALITY_THRESHOLD
                    if paddle_good:
                        lines, engine_used, confidence = paddle_lines, "PaddleOCR", paddle_conf
                    elif vision_available and OCR_ENABLE_VISION_ESCALATION:
                        img_b64 = image_to_base64(processed, quality=85)
                        raw_text = call_vision_model(img_b64, page_num=1)
                        del img_b64
                        vis_lines = [l.strip() for l in raw_text.split("\n") if l.strip()] if raw_text and raw_text.strip() != "[BLANK PAGE]" else []
                        vis_q = score_ocr_page_quality(vis_lines)
                        if vis_lines and (len(vis_lines) > len(paddle_lines) * 1.1 or vis_q > paddle_q):
                            lines, engine_used, confidence = vis_lines, "qwen2.5vl:7b", 0.90
                        elif paddle_lines:
                            lines, engine_used, confidence = paddle_lines, "PaddleOCR", paddle_conf
                    elif paddle_lines:
                        lines, engine_used, confidence = paddle_lines, "PaddleOCR", paddle_conf
                elif vision_available:
                    img_b64 = image_to_base64(processed, quality=85)
                    raw_text = call_vision_model(img_b64, page_num=1)
                    del img_b64
                    if raw_text and raw_text.strip() != "[BLANK PAGE]":
                        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
                        engine_used, confidence = "qwen2.5vl:7b", 0.90

                if not lines:
                    lines = run_tesseract_fallback(processed)
                    engine_used = "Tesseract"
                    confidence = 0.70 if lines else 0.0

                if engine_used == "PaddleOCR" and img_is_tabular and OCR_ENABLE_TABLE_STRUCTURE:
                    table_mds = extract_tables_via_structure(temp_img_path, page_num=1)
                    if table_mds:
                        lines = list(lines) + ["", "[STRUCTURED TABLE — PP-StructureV3]"]
                        for tmd in table_mds:
                            lines.extend(tmd.split("\n"))

            del processed
            gc.collect()

    except Exception as e:
        logger.error(f"Image OCR error: {e}")
    finally:
        if temp_img_path and os.path.exists(temp_img_path):
            try:
                os.unlink(temp_img_path)
            except Exception:
                pass

    elapsed = time.time() - start_time
    q_score = score_ocr_page_quality(lines)
    failed = [] if lines else [1]
    successful = [1] if lines else []

    page_details = [{
        "page": 1, "engine": engine_used, "dpi": 216,
        "confidence": round(confidence, 3),
        "text_length": sum(len(l) for l in lines),
        "quality_score": q_score,
        "preprocessing_applied": ["rgb_convert", "clahe_contrast"],
        "lines": len(lines), "ocr_boxes": []
    }]

    return lines, _build_ocr_debug(
        engine_used=engine_used or "none",
        retry_count=0,
        quality_score=q_score,
        failed_pages=failed,
        successful_pages=successful,
        preprocessing_applied=["rgb_convert", "clahe_contrast"],
        fallback_ocr_engine="" if "Tesseract" not in engine_used else "Tesseract",
        text_density_score=min(len(lines) / 30.0, 1.0),
        average_page_confidence=confidence,
        raw_ocr_preview="\n".join(lines)[:3000],
        pages=page_details,
        total_ocr_time=elapsed
    )



# ======================================================
# HEURISTIC UTILITIES
# ======================================================

def extract_award_amount_from_text(text_lines: list) -> float:
    award_patterns = [
        r'(?:total|final|award|awarded|amount|sum\s+of|compensation\s+of)\b[^0-9]{0,50}?(?:rs\.?|inr|rupees)?\s*([\d,]{5,10})\b',
        r'\b(?:rs\.?|inr)\s*([\d,]{5,10})\b[^0-9]{0,50}?(?:with\s*interest|is\s*awarded|as\s*compensation|towards)'
    ]
    full_text_lower = "\n".join(text_lines).lower()
    for pat in award_patterns:
        candidates = []
        for match in re.finditer(pat, full_text_lower):
            val_str = match.group(1)
            val = float(re.sub(r'[^\d]', '', val_str))
            start_pos = max(0, match.start() - 60)
            pre_ctx = full_text_lower[start_pos:match.start()]
            neg_kws = ["claim", "claiming", "sought", "demand", "demanded", "prayed", "prayer", "valuation"]
            pos_kws = ["award", "awarded", "awarded sum", "amount awarded", "total compensation", "final award"]
            if any(kw in pre_ctx for kw in neg_kws):
                neg_pos = max((pre_ctx.rfind(kw) for kw in neg_kws), default=-1)
                pos_pos = max((pre_ctx.rfind(kw) for kw in pos_kws), default=-1)
                if neg_pos > pos_pos:
                    continue
            candidates.append(val)
        if candidates:
            valid = [c for c in candidates if c >= 5000]
            if valid:
                return valid[0]
    return 0.0


def apply_ocr_quality_gate(suggestions: dict, ocr_debug: dict) -> dict:
    quality = ocr_debug.get("ocr_quality_score", 1.0)
    suggestions["ocr_quality_insufficient"] = quality < OCR_QUALITY_GATE_THRESHOLD
    if quality < OCR_QUALITY_GATE_THRESHOLD:
        suggestions["ocr_warning"] = f"OCR quality low (score: {quality:.2f}). Partial recovery mode."
        suggestions["partial_extraction_recovery_mode"] = True
    return suggestions


# ======================================================
# BACKGROUND BATCH INDEXING PIPELINE
# ======================================================

def run_background_pdf_indexing(file_id: str, temp_path: str, filename: str):
    """Background worker: OCR → parse → index into Qdrant."""
    start_time = time.time()
    try:
        BATCH_QUEUE[file_id]["status"] = "scanning"
        BATCH_QUEUE[file_id]["progress"] = 20

        text_lines = extract_digital_pdf_text(temp_path)
        fallback_source = "DigitalPDF"
        ocr_debug = _build_ocr_debug("DigitalPDF", 0, 1.0, [], [], [], "", 0.0,
                                      total_ocr_time=time.time() - start_time)

        if is_extracted_text_sparse(text_lines):
            logger.info(f"Sparse digital text for {filename}. Running hybrid OCR (PaddleOCR + vision).")
            def report_progress(p):
                BATCH_QUEUE[file_id]["progress"] = p
            text_lines, ocr_debug = perform_ocr_on_scanned_pdf(
                temp_path, progress_callback=report_progress,
                scan_all_pages=True, original_filename=filename
            )
            fallback_source = OCR_HYBRID_LABEL

        if is_extracted_text_sparse(text_lines):
            alt_lines = extract_alternate_pdf_text(temp_path)
            if len(alt_lines) > len(text_lines):
                text_lines = alt_lines
                fallback_source = "AlternateOCR"
                ocr_debug["fallback_ocr_engine"] = "PyMuPDF/pdfplumber"
                ocr_debug["ocr_quality_score"] = 1.0
                ocr_debug["total_ocr_time"] = round(time.time() - start_time, 2)

        BATCH_QUEUE[file_id]["progress"] = 90

        suggestions = parse_extracted_text(text_lines)
        suggestions = apply_ocr_quality_gate(suggestions, ocr_debug)

        if suggestions.get("ai_recovery_triggered", False):
            fallback_source = "RealTextRecovery"
        suggestions["fallback_source_used"] = fallback_source

        award_amount = extract_award_amount_from_text(text_lines)
        if award_amount > 0:
            suggestions["award_amount"] = award_amount
            suggestions["total_compensation"] = award_amount
            from backend.parser_heuristics import deduce_notional_income
            suggestions["monthly_income"] = deduce_notional_income(
                award_amount,
                suggestions.get("age") or 30,
                suggestions.get("marital_status") or "married",
                suggestions.get("dependents") or "",
                suggestions.get("future_prospect") or 25.0,
                suggestions.get("multiplier") or 15
            )

        BATCH_QUEUE[file_id]["status"] = "indexing"
        success = index_document(filename, text_lines, suggestions)

        from backend.parser_heuristics import format_suggestions_for_calculator
        formatted = format_suggestions_for_calculator(suggestions)

        if os.path.exists(temp_path):
            os.unlink(temp_path)

        if success:
            BATCH_QUEUE[file_id].update({
                "status": "indexed", "progress": 100,
                "suggestions": formatted, "raw_text": text_lines, "ocr_debug": ocr_debug
            })
        else:
            BATCH_QUEUE[file_id].update({"status": "failed", "error": "Indexing insertion failed."})

    except Exception as e:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        BATCH_QUEUE[file_id].update({"status": "failed", "error": str(e)})
        logger.error(f"Background task failed for {filename}: {e}")


# ======================================================
# API ENDPOINTS
# ======================================================

@router.post("/process-ocr")
async def process_single_file(file: UploadFile = File(...)):
    """Streaming SSE endpoint: upload PDF/image → OCR → autofill suggestions."""
    file_ext = os.path.splitext(file.filename)[1].lower()
    allowed_images = {".png", ".jpg", ".jpeg", ".bmp"}
    allowed_docs = {".pdf"}
    if file_ext not in allowed_images and file_ext not in allowed_docs:
        raise HTTPException(status_code=400, detail="Only PNG, JPG, BMP and PDF formats are supported.")

    async def event_generator():
        temp_path = None
        try:
            yield f"data: {json.dumps({'status': 'saving', 'progress': 5, 'message': 'Saving upload...'})}\n\n"
            await asyncio.sleep(0.01)

            def save_to_temp():
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
                    shutil.copyfileobj(file.file, tmp)
                    return tmp.name
            temp_path = await asyncio.to_thread(save_to_temp)

            start_time = time.time()
            fallback_source = "DigitalPDF"
            ocr_debug = _build_ocr_debug("DigitalPDF", 0, 1.0, [], [], [], "", 0.0, total_ocr_time=0.0)

            if file_ext == ".pdf":
                yield f"data: {json.dumps({'status': 'extracting', 'progress': 15, 'message': 'Extracting digital PDF text...'})}\n\n"
                await asyncio.sleep(0.01)
                text_lines = await asyncio.to_thread(extract_digital_pdf_text, temp_path)

                yield f"data: {json.dumps({'status': 'checking', 'progress': 35, 'message': 'Checking text quality...'})}\n\n"
                await asyncio.sleep(0.01)

                # ── Track detection: cheap, 1-3 low-DPI pages, no vision unless
                # Paddle finds nothing at all. Decides which OCR + parsing path
                # to use — English HC bundles vs Hindi lower-court bundles.
                yield f"data: {json.dumps({'status': 'routing', 'progress': 42, 'message': 'Detecting court level (High Court / Lower Court)...'})}\n\n"
                await asyncio.sleep(0.01)
                track_info = await asyncio.to_thread(detect_case_track, temp_path)
                track = track_info["track"]
                _tlog(f"[TRACK] {file.filename}: {track_info}")

                if is_extracted_text_sparse(text_lines):
                    page_event_queue = _queue.Queue()

                    def _page_cb(page_info):
                        page_event_queue.put(page_info)

                    loop = asyncio.get_event_loop()

                    if track == "lower_court":
                        yield f"data: {json.dumps({'status': 'ocr', 'progress': 50, 'message': 'Lower-court bundle detected — locating relevant Hindi pages...'})}\n\n"
                        await asyncio.sleep(0.01)
                        ocr_future = loop.run_in_executor(
                            None,
                            lambda: perform_targeted_ocr_lower_court(
                                temp_path, page_callback=_page_cb
                            )
                        )
                    else:
                        yield f"data: {json.dumps({'status': 'ocr', 'progress': 50, 'message': 'Scanned PDF detected — running PaddleOCR + vision OCR...'})}\n\n"
                        await asyncio.sleep(0.01)
                        ocr_future = loop.run_in_executor(
                            None,
                            lambda: perform_ocr_on_scanned_pdf(
                                temp_path, page_callback=_page_cb, original_filename=file.filename
                            )
                        )

                    while not ocr_future.done():
                        await asyncio.sleep(0.1)
                        while not page_event_queue.empty():
                            pg = page_event_queue.get_nowait()
                            progress_val = 50 + int((pg["pages_done"] / max(pg["total_pages"], 1)) * 40)
                            msg = f"OCR page {pg['page']}/{pg['total_pages']}"
                            payload = json.dumps({"status": "page_progress", "progress": progress_val, "message": msg, "page_info": pg})
                            yield f"data: {payload}\n\n"

                    while not page_event_queue.empty():
                        pg = page_event_queue.get_nowait()
                        progress_val = 50 + int((pg["pages_done"] / max(pg["total_pages"], 1)) * 40)
                        msg = f"OCR page {pg['page']}/{pg['total_pages']}"
                        payload = json.dumps({"status": "page_progress", "progress": progress_val, "message": msg, "page_info": pg})
                        yield f"data: {payload}\n\n"

                    text_lines, ocr_debug = await ocr_future
                    fallback_source = OCR_HYBRID_LABEL
                    ocr_debug["track"] = track_info

                if track == "high_court" and is_extracted_text_sparse(text_lines):
                    yield f"data: {json.dumps({'status': 'checking_alternate', 'progress': 65, 'message': 'Sparse text — trying alternate extraction...'})}\n\n"
                    await asyncio.sleep(0.01)
                    alt_lines = await asyncio.to_thread(extract_alternate_pdf_text, temp_path)
                    if len(alt_lines) > len(text_lines):
                        text_lines = alt_lines
                        fallback_source = "AlternateOCR"
                        ocr_debug["fallback_ocr_engine"] = "PyMuPDF/pdfplumber"
                        ocr_debug["ocr_quality_score"] = 1.0
                        ocr_debug["total_ocr_time"] = round(time.time() - start_time, 2)
            else:
                yield f"data: {json.dumps({'status': 'ocr', 'progress': 40, 'message': 'Running PaddleOCR + vision OCR on image...'})}\n\n"
                await asyncio.sleep(0.01)
                text_lines, ocr_debug = await asyncio.to_thread(perform_ocr_on_image, temp_path)
                fallback_source = OCR_HYBRID_LABEL

            yield f"data: {json.dumps({'status': 'parsing', 'progress': 75, 'message': 'Parsing legal fields...'})}\n\n"
            await asyncio.sleep(0.01)

            # track is only set on the ".pdf" branch above (image uploads have
            # no lower-court/Hindi routing); default to the existing English
            # parser for anything that skipped track detection.
            active_track = locals().get("track", "high_court")
            if active_track == "lower_court":
                suggestions = await asyncio.to_thread(parse_hindi_extracted_text, text_lines)
            else:
                suggestions = await asyncio.to_thread(parse_extracted_text, text_lines)
            suggestions = apply_ocr_quality_gate(suggestions, ocr_debug)

            if suggestions.get("ai_recovery_triggered", False):
                fallback_source = "RealTextRecovery"
            suggestions["fallback_source_used"] = fallback_source

            award_amount = extract_award_amount_from_text(text_lines)
            if award_amount > 0:
                suggestions["award_amount"] = award_amount
                suggestions["total_compensation"] = award_amount
                from backend.parser_heuristics import deduce_notional_income
                suggestions["monthly_income"] = deduce_notional_income(
                    award_amount,
                    suggestions.get("age") or 30,
                    suggestions.get("marital_status") or "married",
                    suggestions.get("dependents") or "",
                    suggestions.get("future_prospect") or 25.0,
                    suggestions.get("multiplier") or 15
                )

            from backend.parser_heuristics import format_suggestions_for_calculator
            formatted_suggestions = format_suggestions_for_calculator(suggestions)

            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
                temp_path = None

            yield f"data: {json.dumps({'status': 'done', 'progress': 100, 'success': True, 'filename': file.filename, 'ocr_status': 'loaded', 'fallback_source': fallback_source, 'suggestions': formatted_suggestions, 'raw_text': text_lines, 'ocr_debug': ocr_debug})}\n\n"

        except Exception as e:
            logger.error(f"Streaming OCR error: {e}")
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
            yield f"data: {json.dumps({'status': 'failed', 'progress': 100, 'success': False, 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("/upload-batch")
async def upload_batch_pdfs(files: list[UploadFile] = File(...), background_tasks: BackgroundTasks = None):
    """Batch PDF upload for background OCR + Qdrant indexing."""
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    enqueued = []
    for file in files:
        filename = file.filename
        if not filename.lower().endswith(".pdf"):
            continue
        file_id = f"file_{uuid.uuid4().hex[:10]}"
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                shutil.copyfileobj(file.file, tmp)
                temp_path = tmp.name
        except Exception as e:
            logger.error(f"Failed saving batch PDF '{filename}': {e}")
            continue
        BATCH_QUEUE[file_id] = {
            "file_id": file_id, "filename": filename, "status": "queued",
            "progress": 0, "suggestions": None, "raw_text": [], "ocr_debug": None, "error": None
        }
        if background_tasks:
            background_tasks.add_task(run_background_pdf_indexing, file_id, temp_path, filename)
        else:
            run_background_pdf_indexing(file_id, temp_path, filename)
        enqueued.append({"file_id": file_id, "filename": filename, "status": "queued"})
    return {"success": True, "message": f"Queued {len(enqueued)} PDFs.", "queue": enqueued}


@router.get("/batch-status")
async def get_batch_status():
    sanitized = []
    for file_id, item in BATCH_QUEUE.items():
        s_item = {
            "file_id": item.get("file_id"), "filename": item.get("filename"),
            "status": item.get("status"), "progress": item.get("progress"),
            "error": item.get("error"), "suggestions": item.get("suggestions"),
            "raw_text": item.get("raw_text", [])
        }
        ocr_debug = item.get("ocr_debug")
        if ocr_debug:
            s_item["ocr_debug"] = {
                "ocr_engine_used": ocr_debug.get("ocr_engine_used"),
                "ocr_retry_count": ocr_debug.get("ocr_retry_count"),
                "ocr_quality_score": ocr_debug.get("ocr_quality_score"),
                "fallback_ocr_engine": ocr_debug.get("fallback_ocr_engine"),
                "preprocessing_applied": ocr_debug.get("preprocessing_applied"),
                "text_density_score": ocr_debug.get("text_density_score"),
                "average_page_confidence": ocr_debug.get("average_page_confidence"),
                "searchable_pdf_url": ocr_debug.get("searchable_pdf_url"),
                "total_ocr_time": ocr_debug.get("total_ocr_time"),
                "pages": [
                    {"page": p.get("page"), "engine": p.get("engine"), "dpi": p.get("dpi"),
                     "total_page_time": p.get("total_page_time"), "confidence": p.get("confidence"),
                     "quality_score": p.get("quality_score")}
                    for p in ocr_debug.get("pages", [])
                ]
            }
        sanitized.append(s_item)
    return {"success": True, "queue": sanitized}


@router.post("/clear-queue")
async def clear_queue():
    global BATCH_QUEUE
    to_remove = [fid for fid, item in BATCH_QUEUE.items() if item["status"] in ("indexed", "failed")]
    for fid in to_remove:
        del BATCH_QUEUE[fid]
    gc.collect()
    return {"success": True, "message": f"Cleared {len(to_remove)} entries.", "active_items": len(BATCH_QUEUE)}


from pydantic import BaseModel

class AIRecoverRequest(BaseModel):
    raw_text: list[str]
    track: str = None   # optional: "high_court" | "lower_court" — inferred from text if omitted

@router.post("/ai-recover")
async def ai_recover_fields(request: AIRecoverRequest):
    try:
        from backend.llm_client import ai_data_recovery
        full_text = "\n".join(request.raw_text)
        track = request.track
        if track not in ("high_court", "lower_court"):
            from backend.track_detection import _devanagari_ratio
            track = "lower_court" if _devanagari_ratio(full_text) >= 0.30 else "high_court"
        recovered_data = await asyncio.to_thread(ai_data_recovery, full_text, track)
        if recovered_data.get("ai_recovery_error"):
            raise HTTPException(status_code=503, detail=f"LLM unavailable: {recovered_data['ai_recovery_error']}")
        from backend.parser_heuristics import format_suggestions_for_calculator
        formatted = format_suggestions_for_calculator(recovered_data)
        return {"success": True, "suggestions": formatted, "raw_recovered": recovered_data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI recovery error: {e}")
        raise HTTPException(status_code=500, detail=f"AI recovery failed: {e}")


class SuggestCaseTypeRequest(BaseModel):
    raw_text: str
    selected_case_type: str

@router.post("/suggest-case-type")
async def suggest_case_type(request: SuggestCaseTypeRequest):
    raw_text = request.raw_text[:8000]
    selected = request.selected_case_type
    CASE_TYPES = [
        "Death", "Permanent Total Disability", "Permanent Partial Disability",
        "Temporary Total Disability", "Medical Only", "Vocational Rehabilitation"
    ]
    system_prompt = (
        "You are a legal document analyst for workers' compensation claims.\n"
        "Given extracted text from a claim document, return ONLY a JSON array (no markdown, no explanation, no backticks) of case type probabilities.\n"
        "Format: [{\"case_type\": \"Death\", \"confidence\": 0.82}, ...]\n"
        "All confidences must sum to 1.0. Include all possible case types even if confidence is near 0."
    )
    user_prompt = (
        f"Document text:\n{raw_text}\n\nThe user selected: \"{selected}\"\n"
        f"Analyze the document and return confidence scores for each case type:\n{', '.join(CASE_TYPES)}"
    )
    try:
        from backend.llm_client import generate_response
        response_text = await asyncio.to_thread(generate_response, user_prompt, system_prompt)
        json_match = re.search(r"\[\s*\{.*\}\s*\]", response_text, re.DOTALL)
        suggestions = json.loads(json_match.group(0) if json_match else response_text)
        existing_types = {s.get("case_type") for s in suggestions if isinstance(s, dict)}
        for ct in CASE_TYPES:
            if ct not in existing_types:
                suggestions.append({"case_type": ct, "confidence": 0.0})
        suggestions.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)
        return {"suggestions": suggestions, "selected": selected}
    except Exception as e:
        logger.error(f"Case type suggestion error: {e}")
        fallback = [{"case_type": ct, "confidence": 1.0 / len(CASE_TYPES)} for ct in CASE_TYPES]
        for fs in fallback:
            if fs["case_type"].lower() == selected.lower():
                fs["confidence"] = 0.5
            else:
                fs["confidence"] = 0.5 / (len(CASE_TYPES) - 1)
        fallback.sort(key=lambda x: x["confidence"], reverse=True)
        return {"suggestions": fallback, "selected": selected, "error": str(e)}


class DownloadDocxRequest(BaseModel):
    raw_text: list[str]
    filename: str = "extracted_text"

@router.post("/download-docx")
async def download_docx(request: DownloadDocxRequest):
    try:
        import io
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        doc = Document()
        title = doc.add_paragraph()
        title_run = title.add_run("Extracted Document Text (OCR)")
        title_run.font.name = "Arial"
        title_run.font.size = Pt(18)
        title_run.bold = True
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        meta = doc.add_paragraph()
        meta_run = meta.add_run(f"Source file: {request.filename}\nGenerated on: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        meta_run.font.name = "Arial"
        meta_run.font.size = Pt(10)
        meta_run.italic = True
        meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph("=" * 60).alignment = WD_ALIGN_PARAGRAPH.CENTER
        for line in request.raw_text:
            p = doc.add_paragraph()
            p_run = p.add_run(line)
            p_run.font.name = "Arial"
            p_run.font.size = Pt(11)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.space_before = Pt(2)
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        download_name = request.filename if request.filename.endswith(".docx") else f"{request.filename}.docx"
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f'attachment; filename="{download_name}"',
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )
    except Exception as e:
        logger.error(f"DOCX generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Word document generation failed: {e}")