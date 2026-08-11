# backend/general_chatbot.py
# ==========================================================================
# GENERAL CHATBOT (TEST FEATURE)
# --------------------------------------------------------------------------
# Standalone, self-contained module. Upload a document, then ask questions
# about it. Powered by DeepSeek — by default via a LOCAL Ollama server
# (http://localhost:11434/v1), or the hosted DeepSeek cloud API if configured.
#
# This file is intentionally isolated from the rest of the codebase so it
# can be removed later with just 3 steps:
#   1. Delete this file (backend/general_chatbot.py)
#   2. Remove the 2 lines that were added to backend/main.py
#      (the import line + the app.include_router(...) line)
#   3. Remove the matching frontend block (see frontend/general_chatbot.js
#      and the HTML/CSS snippets that were added)
# ==========================================================================

import os
import io
import json
import uuid
import asyncio
import logging
import tempfile

import requests
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("GeneralChatbot")

router = APIRouter()

# ======================================================
# DEEPSEEK CONFIGURATION
# ======================================================
# By default this points at a LOCAL Ollama server serving DeepSeek
# (Ollama exposes an OpenAI-compatible endpoint at /v1/chat/completions).
# No API key is required for a local Ollama server.
#
# If you instead want to use the hosted DeepSeek cloud API, set:
#   DEEPSEEK_API_BASE=https://api.deepseek.com
#   DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "http://localhost:11434/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-r1:14b")

# Roughly cap how much document text we forward to the model per request.
# deepseek-chat has a large context window, but we keep this conservative
# so requests stay fast and cheap during testing.
MAX_DOC_CHARS = 60000

# ======================================================
# IN-MEMORY SESSION STORE (test feature -- no DB needed)
# session_id -> {"filename": str, "text": str}
# ======================================================
_SESSIONS: dict[str, dict] = {}


# ======================================================
# TEXT EXTRACTION HELPERS
# ======================================================
def _extract_pdf_text_sync(temp_path: str) -> str:
    """
    Digital-text-first, OCR-fallback extraction — reuses the SAME pipeline
    the rest of this app already uses for scanned MACT judgments
    (backend/ocr.py), so scanned/image-only PDFs work here too.
    """
    # Import lazily so this module doesn't force-load PaddleOCR/vision models
    # unless a PDF is actually being processed.
    from backend.ocr import (
        extract_digital_pdf_text,
        is_extracted_text_sparse,
        perform_ocr_on_scanned_pdf,
    )

    text_lines = extract_digital_pdf_text(temp_path)

    if is_extracted_text_sparse(text_lines):
        logger.info("[GeneralChatbot] Digital text layer looks sparse/scanned — running OCR pipeline (this can take a while)...")
        try:
            ocr_lines, _debug = perform_ocr_on_scanned_pdf(temp_path)
            if ocr_lines:
                text_lines = ocr_lines
        except Exception as e:
            logger.error(f"[GeneralChatbot] OCR fallback failed: {e}")

    cleaned = [l for l in text_lines if not l.strip().startswith("--- PAGE")]
    return "\n".join(cleaned).strip()


async def _extract_pdf_text(raw: bytes) -> str:
    """Writes the upload to a temp file (required by the OCR pipeline,
    which reads PDFs from disk) and runs extraction in a worker thread
    so the OCR work doesn't block the event loop."""
    fd, temp_path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        return await asyncio.to_thread(_extract_pdf_text_sync, temp_path)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def _extract_docx_text(raw: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(raw))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(parts).strip()


def _extract_txt_text(raw: bytes) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


async def extract_document_text(filename: str, raw: bytes) -> str:
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext == "pdf":
        text = await _extract_pdf_text(raw)
    elif ext in ("docx",):
        text = _extract_docx_text(raw)
    elif ext in ("txt", "md", "csv"):
        text = _extract_txt_text(raw)
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Please upload a PDF, DOCX, or TXT file."
        )

    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="No readable text could be extracted from this file, "
                   "even after running OCR. It may be blank or badly damaged."
        )

    return text


# ======================================================
# PYDANTIC SCHEMAS
# ======================================================
class GeneralChatUploadResponse(BaseModel):
    session_id: str
    filename: str
    char_count: int
    preview: str


class GeneralChatAskRequest(BaseModel):
    session_id: str
    question: str
    history: list[dict] = []  # [{"role": "user"|"assistant", "content": "..."}]


class GeneralChatClearRequest(BaseModel):
    session_id: str


# ======================================================
# ENDPOINTS
# ======================================================
@router.post("/upload", response_model=GeneralChatUploadResponse)
async def upload_document(file: UploadFile = File(...), session_id: str | None = Form(None)):
    """Upload a document for the General Chatbot to answer questions about."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    text = await extract_document_text(file.filename, raw)

    sid = session_id or str(uuid.uuid4())
    _SESSIONS[sid] = {"filename": file.filename, "text": text}

    logger.info(f"[GeneralChatbot] Indexed '{file.filename}' ({len(text)} chars) under session {sid}")

    return GeneralChatUploadResponse(
        session_id=sid,
        filename=file.filename,
        char_count=len(text),
        preview=text[:400]
    )


@router.post("/clear")
async def clear_document(payload: GeneralChatClearRequest):
    """Remove the uploaded document + its text from memory."""
    _SESSIONS.pop(payload.session_id, None)
    return {"status": "cleared"}


@router.post("/ask")
async def ask_question(payload: GeneralChatAskRequest):
    """Stream a DeepSeek-generated answer grounded in the uploaded document."""
    session = _SESSIONS.get(payload.session_id)
    if not session:
        raise HTTPException(
            status_code=400,
            detail="No document found for this session. Please upload a document first."
        )

    doc_text = session["text"][:MAX_DOC_CHARS]
    truncated_note = (
        "\n\n[Note: document truncated for length; only the first "
        f"{MAX_DOC_CHARS} characters were provided.]"
        if len(session["text"]) > MAX_DOC_CHARS else ""
    )

    system_instruction = (
        "You are a helpful general-purpose document assistant. "
        f"You have been given the full text of a document named '{session['filename']}'. "
        "Answer the user's questions using ONLY the information in the document. "
        "If the answer isn't in the document, say so clearly instead of guessing. "
        "Be concise and directly answer the question first, then add supporting detail if useful.\n\n"
        f"DOCUMENT TEXT:\n{doc_text}{truncated_note}"
    )

    messages = [{"role": "system", "content": system_instruction}]
    for turn in payload.history[-12:]:
        role = turn.get("role")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": payload.question})

    def stream_deepseek():
        headers = {"Content-Type": "application/json"}
        if DEEPSEEK_API_KEY:
            headers["Authorization"] = f"Bearer {DEEPSEEK_API_KEY}"

        try:
            with requests.post(
                f"{DEEPSEEK_API_BASE}/chat/completions",
                headers=headers,
                json={
                    "model": DEEPSEEK_MODEL,
                    "messages": messages,
                    "temperature": 0.3,
                    "stream": True,
                },
                stream=True,
                timeout=120,
            ) as resp:
                if resp.status_code != 200:
                    err_text = resp.text[:500]
                    logger.error(f"[GeneralChatbot] DeepSeek API error {resp.status_code}: {err_text}")
                    yield json.dumps({"message": {"content": f"[DeepSeek API error {resp.status_code}]"}}) + "\n"
                    return

                for line in resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        token = chunk["choices"][0]["delta"].get("content", "")
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                    if token:
                        yield json.dumps({"message": {"content": token}}) + "\n"
        except requests.exceptions.RequestException as e:
            logger.error(f"[GeneralChatbot] Request to DeepSeek failed: {e}")
            yield json.dumps({"message": {"content": "[Error contacting DeepSeek API. Please try again.]"}}) + "\n"

    return StreamingResponse(stream_deepseek(), media_type="application/x-ndjson")