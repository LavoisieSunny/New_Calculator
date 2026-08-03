import os
import logging
import hashlib
import uuid
import time
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VectorDB")

# Centralized collection name for all legal precedents
COLLECTION_NAME = "legal_documents"

# Qdrant server connection URL (configured to run on server port 7204)
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:7204")

# Global lazy-initialized clients to prevent loading models during module imports
_qdrant_client = None
VECTOR_DB_INITIALIZED = False

def get_qdrant_client():
    global _qdrant_client, VECTOR_DB_INITIALIZED
    if _qdrant_client is None:
        try:
            logger.info(f"Initializing Qdrant client at URL: {QDRANT_URL}")
            
            # Connect to external Qdrant server (running on port 7204)
            _qdrant_client = QdrantClient(url=QDRANT_URL)
            
            # Create centralized legal_documents collection if it doesn't exist yet
            try:
                collection_info = _qdrant_client.get_collection(COLLECTION_NAME)
                
                # Retrieve vector dimension and distance metrics
                existing_size = collection_info.config.params.vectors.size
                existing_distance = collection_info.config.params.vectors.distance
                
                # Check distance compatibility
                distance_str = str(existing_distance).lower()
                is_cosine = "cosine" in distance_str
                
                # Dynamically fetch test embedding size
                test_emb = get_ollama_embedding("dimension_test_query")
                detected_dim = len(test_emb) if test_emb is not None else 768
                
                if existing_size == detected_dim and is_cosine:
                    logger.info(f"Existing Qdrant collection '{COLLECTION_NAME}' verified successfully (size={existing_size}, distance={existing_distance}). Reusing safely.")
                else:
                    logger.warning(
                        f"Existing collection '{COLLECTION_NAME}' layout mismatch. "
                        f"Expected size={detected_dim}, cosine distance. "
                        f"Found size={existing_size}, distance={existing_distance}. "
                        "Recreation bypassed to protect existing records. Please manually resolve."
                    )
            except Exception:
                logger.info(f"Collection '{COLLECTION_NAME}' not found. Creating a new one...")
                
                # Measure embedding dimension dynamically before creating
                test_emb = get_ollama_embedding("dimension_test_query")
                if test_emb is not None and len(test_emb) > 0:
                    detected_dim = len(test_emb)
                    logger.info(f"Ollama nomic-embed-text active. Dynamically detected embedding dimension: {detected_dim}")
                else:
                    detected_dim = 768
                    logger.warning(f"Ollama connection offline or embedding failed during startup. Defaulting collection dimension to: {detected_dim}")
                
                _qdrant_client.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=VectorParams(size=detected_dim, distance=Distance.COSINE)
                )
                logger.info(f"Collection '{COLLECTION_NAME}' created successfully with size={detected_dim}!")
            
            VECTOR_DB_INITIALIZED = True
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant client at {QDRANT_URL}: {str(e)}")
            _qdrant_client = None
            VECTOR_DB_INITIALIZED = False
    return _qdrant_client

def get_ollama_embedding(text: str) -> list:
    """
    Fetches a 768-dimension vector embedding from local Ollama server
    using the 'nomic-embed-text' model.
    Returns None if embedding fails. Never returns a zero vector.
    """
    import urllib.request
    import json
    
    # Clean text to remove control/non-printable characters and limit length to prevent Ollama HTTP 500 errors
    clean_text = "".join(c for c in text if c.isprintable() or c in "\n\r\t").strip()
    if not clean_text:
        return None
    if len(clean_text) > 4000:
        clean_text = clean_text[:4000]

    # Use config endpoint or default to local Ollama port
    from config.llm import LLM_API_ENDPOINT
    base_url = LLM_API_ENDPOINT if LLM_API_ENDPOINT else "http://localhost:11434"
    url = f"{base_url.rstrip('/')}/api/embeddings"
    payload = {
        "model": "nomic-embed-text",
        "prompt": clean_text
    }
    
    from backend.ollama_gate import embed_slot, record_embed_result, OllamaPausedError
    try:
        req_body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=req_body, headers={"Content-Type": "application/json"}, method="POST")
        with embed_slot():
            with urllib.request.urlopen(req, timeout=20.0) as response:
                res_json = json.loads(response.read().decode("utf-8"))
        vector = res_json.get("embedding")
        if not vector or not isinstance(vector, list):
            raise ValueError("Embedding response is empty or invalid.")
        record_embed_result(True)
        return vector
    except OllamaPausedError as pe:
        logger.warning(f"Embedding gate paused: {pe}")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch Ollama embedding: {str(e)}")
        record_embed_result(False)
        return None

def get_embedding_model():
    """Backwards compatibility helper."""
    return True

# ======================================================
# CHUNKING & INDEXING PIPELINE
# ======================================================

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list:
    """
    Intelligently chunks legal document text for optimal semantic retrieval.
    Guarantees that chunks:
    1. Do not slice raw characters or cut words in half.
    2. Prefer splitting on paragraph (\n\n) or sentence (. ! ?) boundaries.
    3. Keep complete legal facts and context intact.
    """
    import re
    # Normalize newlines
    text = text.replace("\r\n", "\n")
    
    # Split into paragraphs
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    
    # If there are no double newlines, fallback to single newlines
    if len(paragraphs) <= 1:
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        
    chunks = []
    current_chunk = []
    current_length = 0
    
    for p in paragraphs:
        # If a single paragraph is larger than chunk_size, split it into sentences
        if len(p) > chunk_size:
            # Simple sentence splitting regex
            sentences = re.split(r'(?<=[.!?])\s+', p)
            for s in sentences:
                s = s.strip()
                if not s:
                    continue
                if current_length + len(s) <= chunk_size:
                    current_chunk.append(s)
                    current_length += len(s) + 1 # +1 for space
                else:
                    if current_chunk:
                        chunks.append(" ".join(current_chunk))
                    current_chunk = [s]
                    current_length = len(s)
        else:
            if current_length + len(p) <= chunk_size:
                current_chunk.append(p)
                current_length += len(p) + 2 # +2 for \n\n
            else:
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk) if "\n\n" in text else "\n".join(current_chunk))
                current_chunk = [p]
                current_length = len(p)
                
    if current_chunk:
        chunks.append("\n\n".join(current_chunk) if "\n\n" in text else "\n".join(current_chunk))
        
    # If chunks are still empty or somehow sparse, fallback to a safe word-boundary window
    if not chunks:
        words = text.split()
        current_words = []
        current_len = 0
        for w in words:
            if current_len + len(w) <= chunk_size:
                current_words.append(w)
                current_len += len(w) + 1
            else:
                if current_words:
                    chunks.append(" ".join(current_words))
                # Add overlap of ~20 words if possible
                overlap_words = current_words[-20:] if len(current_words) > 20 else []
                current_words = overlap_words + [w]
                current_len = sum(len(x) + 1 for x in current_words)
        if current_words:
            chunks.append(" ".join(current_words))
            
    return chunks

def extract_paragraphs_with_page_info(text_lines: list) -> list:
    """
    Groups OCR lines into paragraph blocks and tracks their starting page numbers.
    Returns list of dict: [{"page": int, "text": str}]
    """
    import re
    from backend.parser_heuristics import clean_noisy_text
    
    current_page = 1
    page_paragraphs = []
    
    cleaned_items = []
    
    boilerplate_patterns = [
        r'^\s*presented\s+on\s*[:\-]',
        r'^\s*presented\s+by\s*[:\-]',
        r'^\s*registry\s+notice',
        r'^\s*in\s+the\s+court\s+of\b',
        r'^\s*adjudication\s+sheet\b',
        r'^\s*advocates?\s+for\b',
        r'^\s*date\s+of\s+stamping\b',
        r'^\s*stamps?\b',
        r'^\s*office\s+use\s+only\b',
        r'^\s*certified\s+copy\b',
        r'^\s*read\s+by\s*:',
        r'^\s*compared\s+by\s*:',
        r'^\s*typed\s+by\s*:'
    ]
    
    for line in text_lines:
        # Detect page separator
        page_match = re.match(r'^---\s*PAGE\s+(\d+)\s*---', line, re.IGNORECASE)
        if page_match:
            current_page = int(page_match.group(1))
            continue
            
        cleaned = clean_noisy_text(line)
        if not cleaned:
            continue
            
        # Ignore obvious procedural boilerplate lines
        if any(re.search(pat, cleaned.lower()) for pat in boilerplate_patterns):
            continue
            
        cleaned_items.append({"page": current_page, "text": cleaned})
        
    # Paragraph reconstruction while retaining page info
    merged_blocks = []
    current_block = []
    block_start_page = 1
    
    for item in cleaned_items:
        line = item["text"]
        p_num = item["page"]
        
        if not current_block:
            current_block = [line]
            block_start_page = p_num
            continue
            
        # Continuation heuristic
        last_line = current_block[-1]
        ends_with_terminal = last_line[-1] in ['.', '?', '!', ':']
        starts_with_heading = line.isupper() and len(line) > 5
        starts_with_bullet = bool(re.match(r'^\s*(?:\d+|[a-zA-Z])[\.\)\-\]]', line))
        
        if not ends_with_terminal and not starts_with_heading and not starts_with_bullet:
            if last_line.endswith('-'):
                current_block[-1] = last_line[:-1] + line
            else:
                current_block.append(line)
        else:
            merged_blocks.append({
                "page": block_start_page,
                "text": "\n".join(current_block) if "\n" in "\n".join(current_block) else " ".join(current_block)
            })
            current_block = [line]
            block_start_page = p_num
            
    if current_block:
        merged_blocks.append({
            "page": block_start_page,
            "text": "\n".join(current_block) if "\n" in "\n".join(current_block) else " ".join(current_block)
        })
        
    return merged_blocks

def chunk_paragraphs_with_page_info(page_paragraphs: list, chunk_size: int = 1000, overlap: int = 200) -> list:
    """
    Intelligently chunks paragraphs into 1000-char blocks while retaining starting page numbers.
    When a chunk exceeds chunk_size, seeds the next chunk with trailing overlap characters 
    from the previous chunk, trimmed to a word boundary.
    Returns list of dict: [{"page": int, "text": str}]
    """
    chunks_with_page = []
    
    current_chunk_text = []
    current_chunk_len = 0
    current_chunk_page = None
    
    for item in page_paragraphs:
        para_text = item["text"]
        para_page = item["page"]
        
        if current_chunk_page is None:
            current_chunk_page = para_page
            
        if current_chunk_len + len(para_text) <= chunk_size:
            current_chunk_text.append(para_text)
            current_chunk_len += len(para_text) + 2 # +2 for newline
        else:
            # Current chunk is full, save it
            if current_chunk_text:
                prev_text = "\n\n".join(current_chunk_text)
                chunks_with_page.append({
                    "page": current_chunk_page,
                    "text": prev_text
                })
                
                # Get trailing overlap characters
                if overlap > 0 and len(prev_text) > 0:
                    raw_overlap = prev_text[-overlap:] if len(prev_text) > overlap else prev_text
                    # Trim to first whitespace to align with word boundary
                    first_ws = -1
                    for idx, ch in enumerate(raw_overlap):
                        if ch.isspace():
                            first_ws = idx
                            break
                    if first_ws != -1:
                        overlap_seed = raw_overlap[first_ws:].strip()
                    else:
                        overlap_seed = raw_overlap.strip()
                else:
                    overlap_seed = ""
            else:
                overlap_seed = ""
            
            # Start new chunk with overlap seed (if any) and current paragraph
            if overlap_seed:
                current_chunk_text = [overlap_seed, para_text]
                current_chunk_len = len(overlap_seed) + len(para_text) + 2
            else:
                current_chunk_text = [para_text]
                current_chunk_len = len(para_text)
            
            current_chunk_page = para_page
            
    if current_chunk_text:
        chunks_with_page.append({
            "page": current_chunk_page,
            "text": "\n\n".join(current_chunk_text)
        })
        
    return chunks_with_page

def index_document(filename: str, text_lines: list, suggestions: dict = None, case_session_id: str = None, doc_type: str = None) -> bool:
    """
    Chunks document text, generates vector embeddings using Ollama nomic-embed-text, 
    and inserts them into Qdrant collection with rich metadata.
    Prevents duplicate uploads by matching file hashes.
    """
    if suggestions is None:
        suggestions = {}
    if doc_type is None:
        doc_type = suggestions.get("document_type") or "hc_judgment"

    client = get_qdrant_client()
    
    if client is None:
        logger.warning("Vector DB is offline. Skipping indexing.")
        return False
        
    # Calculate file MD5 hash of raw OCR text for duplicate protection
    full_raw_text = "\n".join(text_lines)
    file_hash = hashlib.md5(full_raw_text.encode("utf-8")).hexdigest()
    
    # Check for duplicate indexing
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        scroll_res, _ = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=Filter(must=[
                FieldCondition(key="file_hash", match=MatchValue(value=file_hash))
            ]),
            limit=1
        )
        if scroll_res:
            logger.info(f"Duplicate Upload Protection: Document '{filename}' with hash '{file_hash}' is already indexed. Skipping indexing.")
            return True
    except Exception as e:
        logger.warning(f"Error checking duplicate indexing in Qdrant: {str(e)}")

    # Pre-merge OCR text lines into clean coherent paragraphs while tracking page numbers
    page_paragraphs = extract_paragraphs_with_page_info(text_lines)
    chunks_with_page = chunk_paragraphs_with_page_info(page_paragraphs, chunk_size=1000, overlap=200)
    
    if not chunks_with_page:
        logger.warning(f"No text extracted to index for {filename}")
        return False

    try:
        logger.info(f"Generating Ollama nomic-embed-text embeddings for {len(chunks_with_page)} chunks of: {filename}")
        
        from concurrent.futures import ThreadPoolExecutor

        def embed_chunk(item_with_idx):
            idx, chunk_item = item_with_idx
            chunk = chunk_item["text"]
            p_num = chunk_item["page"]
            try:
                vector = get_ollama_embedding(chunk)
                return idx, p_num, chunk, vector
            except Exception as e:
                logger.error(f"Error calling get_ollama_embedding for chunk {idx} of '{filename}': {str(e)}")
                return idx, p_num, chunk, None

        indexed_chunks = list(enumerate(chunks_with_page))
        with ThreadPoolExecutor(max_workers=6) as executor:
            embeddings_results = list(executor.map(embed_chunk, indexed_chunks))

        points = []
        for idx, p_num, chunk, vector in embeddings_results:
            if vector is None:
                logger.warning(f"Embedding generation failed for chunk {idx} of '{filename}'. Skipping this chunk.")
                continue
                
            # MD5 hex of filename + chunk_index, converted to UUID string for stable point ID across restarts
            unique_str = f"{filename}_{idx}"
            point_id = str(uuid.UUID(hex=hashlib.md5(unique_str.encode("utf-8")).hexdigest()))
            
            # Rich metadata payload
            payload = {
                "filename": filename,
                "chunk_id": idx,
                "chunk_index": idx,
                "page_number": p_num,
                "file_hash": file_hash,
                "text": chunk,
                "case_type": suggestions.get("case_type", "injury"),
                "claimant": suggestions.get("name") or suggestions.get("claimant") or "",
                "respondent": suggestions.get("respondent", "Insurance Company / Respondent"),
                "document_type": suggestions.get("document_type", "Judgment"),
                "upload_date": suggestions.get("upload_date") or time.strftime("%d-%m-%Y"),
                # For backwards compatibility with evaluation models
                "name": suggestions.get("name", ""),
                "father_name": suggestions.get("father_name", ""),
                "age": suggestions.get("age", ""),
                "monthly_income": suggestions.get("monthly_income", ""),
                "disability": suggestions.get("disability", ""),
                "dependents": suggestions.get("dependents", ""),
                "marital_status": suggestions.get("marital_status", "married"),
                "award_amount": suggestions.get("award_amount", ""),
                "case_session_id": case_session_id,
                "doc_type": doc_type
            }
            
            points.append(PointStruct(
                id=point_id,
                vector=vector,
                payload=payload
            ))
            
        if not points:
            logger.warning(f"No points successfully embedded for document '{filename}'. Indexing aborted.")
            return False

        # Upsert batch into Qdrant
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )
        logger.info(f"Indexed {len(points)} points for document '{filename}' in Qdrant successfully!")
        if case_session_id and doc_type:
            _FULL_TEXT_CACHE[(case_session_id, doc_type)] = full_raw_text
        return True
    except Exception as e:
        logger.error(f"Error during Qdrant indexing: {str(e)}")
        return False

# ======================================================
# SEMANTIC QUERY SEARCH
# ======================================================

def semantic_search(query: str, limit: int = 5, case_type_filter: str = None, filename_filter: str = None, case_session_id_filter: str = None, doc_type_filter = None) -> list:
    """
    Performs semantic vector search across all indexed PDFs.
    Optionally filters by case type ('injury' or 'death'), filename, case_session_id, and/or doc_type.
    """
    client = get_qdrant_client()
    
    if client is None:
        logger.warning("Vector DB is offline. Returning empty search results.")
        return []
        
    # Embed query text using Ollama
    query_vector = get_ollama_embedding(query)
    if query_vector is None:
        logger.warning(f"Failed to generate embedding for search query: '{query}'. Returning empty results.")
        return []
        
    try:
        # Build filter conditions
        must_conditions = []
        
        if case_type_filter:
            from qdrant_client.models import FieldCondition, MatchValue
            must_conditions.append(
                FieldCondition(
                    key="case_type",
                    match=MatchValue(value=case_type_filter)
                )
            )
            
        if filename_filter:
            from qdrant_client.models import FieldCondition, MatchValue
            must_conditions.append(
                FieldCondition(
                    key="filename",
                    match=MatchValue(value=filename_filter)
                )
            )

        if case_session_id_filter:
            from qdrant_client.models import FieldCondition, MatchValue
            must_conditions.append(
                FieldCondition(
                    key="case_session_id",
                    match=MatchValue(value=case_session_id_filter)
                )
            )

        if doc_type_filter:
            from qdrant_client.models import FieldCondition, MatchValue, MatchAny
            if isinstance(doc_type_filter, list):
                must_conditions.append(
                    FieldCondition(
                        key="doc_type",
                        match=MatchAny(any=doc_type_filter)
                    )
                )
            else:
                must_conditions.append(
                    FieldCondition(
                        key="doc_type",
                        match=MatchValue(value=doc_type_filter)
                    )
                )
            
        search_filter = None
        if must_conditions:
            from qdrant_client.models import Filter
            search_filter = Filter(must=must_conditions)
            
        # Execute vector search
        search_results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=search_filter,
            limit=limit
        ).points
        
        # Format results
        formatted_results = []
        for res in search_results:
            formatted_results.append({
                "id": res.id,
                "score": round(res.score, 4),
                "text": res.payload.get("text", ""),
                "filename": res.payload.get("filename", ""),
                "metadata": {
                    "case_type": res.payload.get("case_type", ""),
                    "claimant": res.payload.get("claimant", ""),
                    "respondent": res.payload.get("respondent", ""),
                    "document_type": res.payload.get("document_type", ""),
                    "upload_date": res.payload.get("upload_date", ""),
                    "name": res.payload.get("name", ""),
                    "age": res.payload.get("age", ""),
                    "monthly_income": res.payload.get("monthly_income", ""),
                    "disability": res.payload.get("disability", ""),
                    "award_amount": res.payload.get("award_amount", ""),
                    "page_number": res.payload.get("page_number", 1),
                    "chunk_index": res.payload.get("chunk_index", 0),
                    "file_hash": res.payload.get("file_hash", ""),
                    "case_session_id": res.payload.get("case_session_id", ""),
                    "doc_type": res.payload.get("doc_type", "")
                }
            })
            
        return formatted_results
    except Exception as e:
        logger.error(f"Error during semantic vector search: {str(e)}")
        return []

def semantic_search_rag(query: str, limit: int = 5, filename_filter: str = None, case_session_id_filter: str = None, doc_type_filter = None) -> list:
    """
    Retrieves relevant text chunks from the vector database.
    If filename_filter exists: search only that PDF
    Else: search entire library
    """
    logger.info(f"RAG search query='{query}', limit={limit}, filename_filter='{filename_filter}', case_session_id_filter='{case_session_id_filter}', doc_type_filter='{doc_type_filter}'")
    return semantic_search(query, limit=limit, filename_filter=filename_filter, case_session_id_filter=case_session_id_filter, doc_type_filter=doc_type_filter)

def scroll_documents_by_case_type(case_type: str = None, limit: int = 200) -> list:
    """
    Scrolls the Qdrant collection and returns one representative chunk per unique filename.
    Used as a fallback when Ollama embeddings are unavailable — retrieves real indexed
    document metadata (name, age, income, award_amount, etc.) without needing vectors.

    Returns a list of dicts with the same shape as semantic_search results.
    """
    client = get_qdrant_client()
    if client is None:
        logger.warning("Vector DB is offline. Cannot scroll documents.")
        return []

    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        scroll_filter = None
        if case_type and case_type != "all":
            scroll_filter = Filter(must=[
                FieldCondition(key="case_type", match=MatchValue(value=case_type))
            ])

        # Scroll up to `limit` raw points — we deduplicate by filename below
        results, _ = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=scroll_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False
        )

        # Deduplicate: keep one chunk per filename, preferring the chunk that has the
        # richest metadata (award_amount > 0, age present, income present).
        seen_files = {}
        for point in results:
            p = point.payload
            fname = p.get("filename", "")
            if not fname:
                continue

            award = 0.0
            try:
                award = float(p.get("award_amount") or 0)
            except (ValueError, TypeError):
                award = 0.0

            age_val = p.get("age", "")
            income_val = p.get("monthly_income", "")

            # Score richness: award + has_age + has_income
            richness = (1 if award > 0 else 0) + (1 if age_val else 0) + (1 if income_val else 0)

            if fname not in seen_files or richness > seen_files[fname]["_richness"]:
                seen_files[fname] = {
                    "id": str(point.id),
                    "score": 0.75,   # neutral scroll-match score
                    "text": p.get("text", ""),
                    "filename": fname,
                    "_richness": richness,
                    "metadata": {
                        "case_type": p.get("case_type", ""),
                        "claimant": p.get("claimant", ""),
                        "respondent": p.get("respondent", ""),
                        "document_type": p.get("document_type", ""),
                        "upload_date": p.get("upload_date", ""),
                        "name": p.get("name", "") or p.get("claimant", ""),
                        "age": p.get("age", ""),
                        "monthly_income": p.get("monthly_income", ""),
                        "disability": p.get("disability", ""),
                        "award_amount": p.get("award_amount", ""),
                        "page_number": p.get("page_number", 1),
                        "chunk_index": p.get("chunk_index", 0),
                        "file_hash": p.get("file_hash", "")
                    }
                }

        # Remove internal richness key and return as list
        docs = []
        for entry in seen_files.values():
            entry.pop("_richness", None)
            docs.append(entry)

        logger.info(f"scroll_documents_by_case_type: found {len(docs)} unique documents for case_type='{case_type}'")
        return docs

    except Exception as e:
        logger.error(f"Error scrolling documents from Qdrant: {str(e)}")
        return []


def delete_document(filename: str) -> bool:
    """
    Deletes all points associated with the given filename from the Qdrant collection.
    """
    client = get_qdrant_client()
    if client is None:
        logger.warning("Vector DB is offline. Skipping deletion.")
        return False
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        delete_filter = Filter(
            must=[
                FieldCondition(
                    key="filename",
                    match=MatchValue(value=filename)
                )
            ]
        )

        # First check whether anything actually matches
        existing, _ = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=delete_filter,
            limit=1,
            with_payload=False,
            with_vectors=False
        )
        if not existing:
            logger.warning(f"No points found in Qdrant matching filename='{filename}'. Nothing deleted.")
            return False

        logger.info(f"Deleting points for document '{filename}' from collection '{COLLECTION_NAME}'...")
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=delete_filter
        )
        logger.info(f"Points for document '{filename}' deleted successfully!")
        return True
    except Exception as e:
        logger.error(f"Error deleting document '{filename}' from Qdrant: {str(e)}")
        return False


import collections
import time
import threading

class BoundedCache(collections.OrderedDict):
    def __init__(self, maxsize=200, ttl=3600):
        super().__init__()
        self.maxsize = maxsize
        self.ttl = ttl
        self._lock = threading.Lock()

    def __contains__(self, key):
        with self._lock:
            if not super().__contains__(key):
                return False
            timestamp, _ = super().__getitem__(key)
            if time.time() - timestamp > self.ttl:
                super().pop(key, None)
                return False
            return True

    def __getitem__(self, key):
        with self._lock:
            timestamp, val = super().__getitem__(key)
            if time.time() - timestamp > self.ttl:
                super().pop(key, None)
                raise KeyError(key)
            self.move_to_end(key)
            return val

    def __setitem__(self, key, value):
        with self._lock:
            if super().__contains__(key):
                super().pop(key, None)
            elif len(self) >= self.maxsize:
                super().popitem(last=False)
            super().__setitem__(key, (time.time(), value))

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

_FULL_TEXT_CACHE = BoundedCache(maxsize=200, ttl=3600)  # (case_session_id, doc_type) -> text

def get_supporting_doc_text(case_session_id: str, doc_type: str) -> str:
    """
    Retrieves supporting document text from memory cache or Qdrant points.
    - If doc_type == "lower_court", prefers concatenated full text of the OCR.
    - If doc_type == "hospital_record", retrieves chunks via semantic search or scroll.
    """
    if not case_session_id:
        return ""
    
    cache_key = (case_session_id, doc_type)
    if cache_key in _FULL_TEXT_CACHE:
        logger.info(f"Retrieved full text for {doc_type} from memory cache.")
        return _FULL_TEXT_CACHE[cache_key]

    client = get_qdrant_client()
    if client is None:
        return ""

    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        # For hospital_record, run semantic search on top chunks
        if doc_type == "hospital_record":
            query_text = "medical evidence hospital records injury disability treatment surgery bills admission discharge summary"
            query_vector = get_ollama_embedding(query_text)
            if query_vector is not None:
                query_filter = Filter(must=[
                    FieldCondition(key="case_session_id", match=MatchValue(value=case_session_id)),
                    FieldCondition(key="doc_type", match=MatchValue(value=doc_type))
                ])
                search_res = client.query_points(
                    collection_name=COLLECTION_NAME,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=10
                ).points
                full_text = "\n\n".join(hit.payload.get("text") or "" for hit in search_res)
                _FULL_TEXT_CACHE[cache_key] = full_text
                return full_text

        # For lower_court and default fallback, scroll and concatenate in chunk order
        scroll_filter = Filter(must=[
            FieldCondition(key="case_session_id", match=MatchValue(value=case_session_id)),
            FieldCondition(key="doc_type", match=MatchValue(value=doc_type))
        ])

        scroll_res, _ = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=scroll_filter,
            limit=100,
            with_payload=True
        )

        if not scroll_res:
            return ""

        # Sort chunks by chunk_index to ensure they are in order
        points_sorted = sorted(scroll_res, key=lambda p: p.payload.get("chunk_index") or 0)
        
        text_parts = []
        last_page = None
        for p in points_sorted:
            p_text = p.payload.get("text") or ""
            p_num = p.payload.get("page_number") or 1
            if last_page is not None and p_num != last_page:
                text_parts.append("\f")
            else:
                if last_page is not None:
                    text_parts.append("\n")
            text_parts.append(p_text)
            last_page = p_num
            
        full_text = "".join(text_parts)
        
        _FULL_TEXT_CACHE[cache_key] = full_text
        return full_text

    except Exception as e:
        logger.error(f"Error reassembling supporting doc text for session={case_session_id}, type={doc_type}: {e}")
        return ""


def get_all_supporting_docs(case_session_id: str, exclude_doc_types: tuple = ("lower_court",)) -> list:
    """
    Generic retrieval: returns EVERY supporting document indexed for this case
    session, grouped by (filename, doc_type), regardless of what tag the
    uploader picked ("hospital_record", "other", or anything else added later).

    Only doc_types in `exclude_doc_types` are skipped -- by default just
    "lower_court", since that document is handled specially elsewhere (its
    text is parsed into issues/award sections rather than treated as evidence).

    Returns a list of dicts: [{"filename": ..., "doc_type": ..., "text": ...}, ...]
    ordered by chunk_index within each document, so a whole family of files
    (an X-ray report, a discharge summary, an income affidavit, etc.) all
    surface here without any of them needing a specific hardcoded key.
    """
    if not case_session_id:
        return []

    client = get_qdrant_client()
    if client is None:
        return []

    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        scroll_filter = Filter(must=[
            FieldCondition(key="case_session_id", match=MatchValue(value=case_session_id))
        ])

        all_points = []
        next_offset = None
        while True:
            scroll_res, next_offset = client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=scroll_filter,
                limit=200,
                offset=next_offset,
                with_payload=True
            )
            all_points.extend(scroll_res)
            if not next_offset:
                break

        if not all_points:
            return []

        # Group by (filename, doc_type) so multi-chunk documents get
        # reassembled in the right order rather than interleaved.
        groups: dict = {}
        for p in all_points:
            doc_type = p.payload.get("doc_type") or "other"
            if doc_type in exclude_doc_types:
                continue
            filename = p.payload.get("filename") or p.payload.get("file_name") or "unnamed document"
            key = (filename, doc_type)
            groups.setdefault(key, []).append(p)

        documents = []
        for (filename, doc_type), points in groups.items():
            points_sorted = sorted(points, key=lambda p: p.payload.get("chunk_index") or 0)
            text = "\n".join((p.payload.get("text") or "") for p in points_sorted).strip()
            if text:
                documents.append({"filename": filename, "doc_type": doc_type, "text": text})

        return documents

    except Exception as e:
        logger.error(f"Error retrieving all supporting docs for session={case_session_id}: {e}")
        return []


def build_supporting_docs_bundle(case_session_id: str) -> dict:
    """
    Single source of truth for assembling the supporting_docs dict passed into
    generate_final_judicial_summary(). Used by every call site so behaviour
    stays consistent no matter which endpoint triggers the analysis.

    - "lower_court": still fetched specifically, since its structure (issues
      framed / operative award) is parsed out separately.
    - "medical_evidence": every OTHER document attached to the case, whatever
      it was tagged as on upload, concatenated with a clear per-document
      header so the LLM knows which fact came from which file.
    """
    if not case_session_id:
        return {"lower_court": "", "medical_evidence": ""}

    lower_court_text = get_supporting_doc_text(case_session_id, "lower_court")

    other_docs = get_all_supporting_docs(case_session_id, exclude_doc_types=("lower_court",))
    labeled_blocks = []
    for doc in other_docs:
        tag_label = {
            "hospital_record": "Hospital / Medical Record",
            "other": "Supporting Document"
        }.get(doc["doc_type"], doc["doc_type"])
        labeled_blocks.append(
            f"=== {tag_label}: {doc['filename']} ===\n{doc['text']}"
        )
    medical_evidence_text = "\n\n".join(labeled_blocks)

    return {
        "lower_court": lower_court_text,
        "medical_evidence": medical_evidence_text
    }
