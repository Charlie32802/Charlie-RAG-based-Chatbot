"""
rag_utils.py — Django laptop side (thin HTTP client)
All heavy lifting (embeddings, ChromaDB, BM25) now runs on the Ubuntu RAG server.
"""

import os
import logging
import requests
from pathlib import Path

logger = logging.getLogger(__name__)

# ── RAG server URL (set RAG_SERVER_URL in your .env) ─────────────────────────
RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://192.168.160.118:8001").rstrip("/")

# ── Request timeout config ────────────────────────────────────────────────────
TIMEOUT_SEARCH = int(os.getenv("RAG_TIMEOUT_SEARCH", 60))   # seconds
TIMEOUT_INDEX  = int(os.getenv("RAG_TIMEOUT_INDEX",  120))  # indexing can be slower


def _get(path, **kwargs):
    """GET helper — returns parsed JSON or raises."""
    resp = requests.get(f"{RAG_SERVER_URL}{path}", timeout=TIMEOUT_SEARCH, **kwargs)
    resp.raise_for_status()
    return resp.json()


def _post(path, payload, timeout=None):
    """POST helper — returns parsed JSON or raises."""
    resp = requests.post(
        f"{RAG_SERVER_URL}{path}",
        json=payload,
        timeout=timeout or TIMEOUT_SEARCH,
    )
    resp.raise_for_status()
    return resp.json()


def _delete(path):
    """DELETE helper — returns parsed JSON or raises."""
    resp = requests.delete(f"{RAG_SERVER_URL}{path}", timeout=TIMEOUT_SEARCH)
    resp.raise_for_status()
    return resp.json()


# ── These kept for compatibility — no-ops now (server handles init) ───────────
def initialize_rag_system():
    """No-op: initialisation happens on the RAG server at startup."""
    pass


def get_collection():
    """Not used directly anymore; kept so existing imports don't break."""
    raise NotImplementedError("ChromaDB now lives on the RAG server.")


def get_embedder():
    """Not used directly anymore; kept so existing imports don't break."""
    raise NotImplementedError("Embedder now lives on the RAG server.")


# ── Text extraction (still runs on laptop — no model needed) ──────────────────
def extract_text_from_docx(file_path):
    from docx import Document as DocxDocument
    doc = DocxDocument(file_path)
    return "\n\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())


def extract_text_from_pdf(file_path):
    from pypdf import PdfReader
    text = []
    with open(file_path, "rb") as f:
        for page in PdfReader(f).pages:
            page_text = page.extract_text()
            if page_text.strip():
                text.append(page_text.strip())
    return "\n\n".join(text)


def extract_text_from_txt(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def extract_text(file_path):
    extension = os.path.splitext(file_path)[1].lower()
    if extension == ".docx":
        return extract_text_from_docx(file_path)
    elif extension == ".pdf":
        return extract_text_from_pdf(file_path)
    elif extension == ".txt":
        return extract_text_from_txt(file_path)
    else:
        raise ValueError(f"Unsupported file type: {extension}")


# ── Document indexing ─────────────────────────────────────────────────────────
def add_document_to_chromadb(document):
    """
    Extract text on the laptop, then ship it to the RAG server for
    chunking, embedding, and indexing into ChromaDB + BM25.
    """
    try:
        text = extract_text(document.file.path)
        if not text.strip():
            logger.error(f"No text extracted from '{document.title}'")
            return False

        payload = {
            "document_id": str(document.id),
            "title":       document.title,
            "category":    document.category,
            "status":      document.status,
            "text":        text,
        }
        result = _post("/index-document", payload, timeout=TIMEOUT_INDEX)
        chunks_added = result.get("chunks_added", 0)
        logger.info(f"[OK] Indexed {chunks_added} chunks from '{document.title}'")
        return chunks_added

    except requests.RequestException as e:
        logger.error(f"RAG server error while indexing '{document.title}': {e}")
        return False
    except Exception as e:
        logger.error(f"Error processing '{document.title}': {e}", exc_info=True)
        return False


# ── Search ────────────────────────────────────────────────────────────────────
def search_documents(query, n_results=50, category_filter=None, query_info=None):
    """
    Run hybrid search on the RAG server.
    Returns the formatted context string and item count,
    matching the original return shape expected by your views.
    """
    try:
        payload = {
            "query":           query,
            "n_results":       n_results,
            "category_filter": category_filter,
        }
        result = _post("/search", payload)
        # Result shape: {"context": str, "item_count": int}
        return result.get("context", ""), result.get("item_count", 0)

    except requests.RequestException as e:
        logger.error(f"RAG server search error: {e}")
        return "", 0
    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        return "", 0


# ── format_rag_results kept as pass-through ───────────────────────────────────
# The server now returns the final formatted context directly from /search.
# If any view calls format_rag_results separately, it's a no-op here.
def format_rag_results(rag_results, query_info=None, query=""):
    """
    No-op pass-through: formatting now happens server-side.
    If rag_results is already a (context_str, item_count) tuple
    (returned by search_documents above), just return it.
    """
    if isinstance(rag_results, tuple):
        return rag_results
    # Fallback — shouldn't happen in normal flow
    logger.warning("format_rag_results called with raw results — server should handle this.")
    return str(rag_results), 0


# ── Document management ───────────────────────────────────────────────────────
def delete_document_from_chromadb(document_id):
    try:
        result = _delete(f"/document/{document_id}")
        return result.get("deleted", False)
    except requests.RequestException as e:
        logger.error(f"RAG server error deleting document {document_id}: {e}")
        return False


# ── Metadata helpers ──────────────────────────────────────────────────────────
def get_all_document_titles():
    try:
        return _get("/documents")
    except requests.RequestException as e:
        logger.error(f"RAG server error getting document titles: {e}")
        return []


def get_knowledge_base_sample(sample_size=3):
    try:
        return _get("/documents/sample", params={"sample_size": sample_size})
    except requests.RequestException as e:
        logger.error(f"RAG server error getting sample: {e}")
        return []


def get_collection_stats():
    try:
        return _get("/stats")
    except requests.RequestException as e:
        logger.error(f"RAG server error getting stats: {e}")
        return None


def get_available_categories():
    try:
        return _get("/categories")
    except requests.RequestException as e:
        logger.error(f"RAG server error getting categories: {e}")
        return []


# ── Health check ──────────────────────────────────────────────────────────────
def check_rag_server_health():
    """Call this from your Django startup or admin view to verify the connection."""
    try:
        result = _get("/health")
        logger.info(f"RAG server healthy: {result}")
        return True
    except Exception as e:
        logger.error(f"RAG server unreachable: {e}")
        return False