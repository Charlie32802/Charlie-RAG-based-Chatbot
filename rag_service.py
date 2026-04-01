"""
rag_service.py — RAG Microservice for Ubuntu Server

This runs automatically as a systemd service (charlie-rag.service).
To check status: sudo systemctl status charlie-rag
To restart:      sudo systemctl restart charlie-rag
"""

import os
import pickle
import hashlib
import random
import logging
import re
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from rank_bm25 import BM25Okapi

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR        = Path(__file__).resolve().parent
CHROMA_DIR      = BASE_DIR / "chromadb"
BM25_CACHE_PATH = BASE_DIR / "bm25_index.pkl"

CONTEXT_BUDGET            = int(os.getenv("CONTEXT_BUDGET",             100000))
MAX_CONTEXT_DOCS          = int(os.getenv("MAX_CONTEXT_DOCS",            40))
SMALL_DOC_THRESHOLD       = int(os.getenv("SMALL_DOC_THRESHOLD",        15))   
SMALL_DOC_GUARANTEE       = int(os.getenv("SMALL_DOC_GUARANTEE",        20000)) 
LARGE_DOC_RELEVANCE_FLOOR = float(os.getenv("LARGE_DOC_RELEVANCE_FLOOR", 0.0))
RELEVANCE_FLOOR_RATIO     = float(os.getenv("RELEVANCE_FLOOR_RATIO",    0.0)) 
EMBEDDING_MODEL           = os.getenv("EMBEDDING_MODEL",                "BAAI/bge-m3")

app = FastAPI(title="Charlie RAG Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_client         = None
_collection     = None
_embedder       = None
_bm25_index     = None
_bm25_documents = []
_bm25_metadatas = []


@app.on_event("startup")
def startup():
    global _client, _collection, _embedder
    import chromadb
    from sentence_transformers import SentenceTransformer

    _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    _collection = _client.get_or_create_collection(
        name="surigao_documents",
        metadata={"description": "Surigao City knowledge base"},
    )
    _embedder = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    logger.info(f"Embedding model loaded: {EMBEDDING_MODEL}")
    _build_bm25_index()
    logger.info("RAG service ready.")


def get_collection():
    return _collection


def get_embedder():
    return _embedder


def _tokenize(text):
    return re.findall(r"\w+", text.lower())


def _build_bm25_index():
    global _bm25_index, _bm25_documents, _bm25_metadatas
    try:
        all_data = get_collection().get(
            where={"status": "published"},
            include=["documents", "metadatas"],
        )
        if not all_data["documents"]:
            return

        fingerprint = hashlib.md5(
            "".join(all_data["documents"]).encode()
        ).hexdigest()

        if BM25_CACHE_PATH.exists():
            try:
                with open(BM25_CACHE_PATH, "rb") as f:
                    cached = pickle.load(f)
                if cached.get("fingerprint") == fingerprint:
                    _bm25_documents = cached["documents"]
                    _bm25_metadatas = cached["metadatas"]
                    _bm25_index     = cached["index"]
                    logger.info("BM25: loaded from disk cache")
                    return
            except Exception as e:
                logger.warning(f"BM25 cache load failed: {e} — rebuilding")

        _bm25_documents = all_data["documents"]
        _bm25_metadatas = all_data["metadatas"]
        tokenized_docs  = [_tokenize(doc) for doc in _bm25_documents]
        _bm25_index     = BM25Okapi(tokenized_docs)

        with open(BM25_CACHE_PATH, "wb") as f:
            pickle.dump(
                {
                    "fingerprint": fingerprint,
                    "documents":   _bm25_documents,
                    "metadatas":   _bm25_metadatas,
                    "index":       _bm25_index,
                },
                f,
            )
        logger.info(f"BM25: rebuilt and saved ({len(_bm25_documents)} chunks)")
    except Exception as e:
        logger.error(f"BM25 index error: {e}")


def _bm25_search(query, n_results=150):
    if _bm25_index is None or not _bm25_documents:
        return []
    tokenized_query = _tokenize(query)
    scores          = _bm25_index.get_scores(tokenized_query)
    top_indices     = np.argsort(scores)[::-1][:n_results]
    results = []
    for idx in top_indices:
        if scores[idx] > 0:
            results.append(
                {
                    "content":    _bm25_documents[idx],
                    "metadata":   _bm25_metadatas[idx],
                    "bm25_score": float(scores[idx]),
                }
            )
    return results


def _score_text_against_query(text, query_tokens):
    if not query_tokens:
        return 0.0
    meaningful = [qt for qt in query_tokens if len(qt) >= 3]
    if not meaningful:
        return 0.0
    chunk_tokens = set(_tokenize(text))
    hits = 0.0
    for qt in meaningful:
        if qt in chunk_tokens:
            hits += 1.0
        elif qt.endswith("s") and len(qt) > 3 and qt[:-1] in chunk_tokens:
            hits += 0.8
        elif qt + "s" in chunk_tokens:
            hits += 0.8
        elif len(qt) >= 5 and any(ct.startswith(qt[:5]) for ct in chunk_tokens):
            hits += 0.5
    return hits / len(meaningful)


def _reciprocal_rank_fusion(semantic_results, bm25_results, k=60):
    doc_scores = {}
    doc_data   = {}
    for rank, result in enumerate(semantic_results, start=1):
        doc_id    = result["content"][:100]
        rrf_score = 1.0 / (k + rank)
        if doc_id not in doc_scores:
            doc_scores[doc_id] = 0
            doc_data[doc_id]   = result
            doc_data[doc_id]["source"] = "semantic"
        doc_scores[doc_id] += rrf_score
    for rank, result in enumerate(bm25_results, start=1):
        doc_id    = result["content"][:100]
        rrf_score = 1.0 / (k + rank)
        if doc_id not in doc_scores:
            doc_scores[doc_id] = 0
            doc_data[doc_id]   = result
            doc_data[doc_id]["source"] = "bm25"
        else:
            doc_data[doc_id]["source"] = "hybrid"
        doc_scores[doc_id] += rrf_score
    sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
    combined = []
    for doc_id, rrf_score in sorted_docs:
        result              = doc_data[doc_id].copy()
        result["rrf_score"] = rrf_score
        combined.append(result)
    return combined


_HEADING_PATTERNS = [
    re.compile(r"^\s*[A-Z][A-Z\s]+\d+\s+OF\s+\d+\s*:\s*(.+)$", re.IGNORECASE),
    re.compile(r"^\s*[A-Z][A-Z\s]*\d+\s*[—\-–]\s*(.+)$",        re.IGNORECASE),
    re.compile(r"^\s*\w*\s*sub[\-\s]?\w+\s+\d+\s*:\s*(.+)$",    re.IGNORECASE),
    re.compile(r"^\s*([A-Z][A-Z\s\(\)\/\-]{4,78}[A-Z\)])\s*$"),
]


def _extract_headings_from_context(context_text):
    found_labels = []
    seen         = set()
    for line in context_text.splitlines():
        line = line.strip()
        if not line:
            continue
        for pattern in _HEADING_PATTERNS:
            match = pattern.match(line)
            if match:
                label = match.group(1).strip() if pattern.groups else line.strip()
                label = re.sub(r"\s+", " ", label).strip(" .:—-")
                if len(label) < 3 or len(label) > 100:
                    break
                if label.upper() in seen:
                    break
                seen.add(label.upper())
                found_labels.append(label)
                break
    if not found_labels:
        return ""
    label_lines = "\n".join(f"  • {label}" for label in found_labels)
    return (
        "══════════════════════════════════════════════════\n"
        "EXACT LABELS FOUND IN THIS DOCUMENT.\n"
        "You MUST use these names WORD-FOR-WORD in your answer.\n"
        "Do NOT rename, paraphrase, or reorder them:\n"
        f"{label_lines}\n"
        "══════════════════════════════════════════════════\n\n"
    )


def _count_list_items_in_text(text):
    """
    Count list-like lines broadly enough to catch plantilla/HR table rows,
    numbered entries without punctuation, and standard bullet formats.
    """
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if (
            re.match(r"^[•\-\*]\s+", stripped)           # bullet points
            or re.match(r"^\d+[\.\)]\s+", stripped)       # 1. or 1)
            or re.match(r"^\d+\s+[A-Z]", stripped)        # table rows: "1  JUAN"
            or re.match(r"^[A-Z]{2,}\s+\d+", stripped)    # "SG-15 ..." style
        ):
            count += 1
    return count


def _get_relevance_floor(chunk, base_floor):
    """List-containing chunks get a more lenient relevance floor."""
    if chunk.get("metadata", {}).get("contains_list"):
        return base_floor * 0.33
    return base_floor


def _format_rag_results(rag_results, query=""):
    if not rag_results:
        return "", 0

    query_tokens = set(_tokenize(query)) if query else set()
    for chunk in rag_results:
        overlap             = _score_text_against_query(chunk.get("content", ""), query_tokens)
        chunk["final_score"] = chunk.get("rrf_score", 0.0) + (overlap * 0.4)

    max_score = max(c["final_score"] for c in rag_results)
    base_floor = max_score * RELEVANCE_FLOOR_RATIO

    before_floor = len(rag_results)
    rag_results  = [c for c in rag_results if c["final_score"] >= _get_relevance_floor(c, base_floor)]
    dropped      = before_floor - len(rag_results)
    if dropped:
        logger.debug(f"Relevance floor dropped {dropped} chunks (base_floor={base_floor:.4f})")

    doc_chunks = {}
    for chunk in rag_results:
        doc_id = chunk["metadata"].get("document_id")
        doc_chunks.setdefault(doc_id, []).append(chunk)
    for doc_id in doc_chunks:
        doc_chunks[doc_id].sort(key=lambda r: r["final_score"], reverse=True)

    seen_indices = set()
    selected     = []
    chars_so_far = 0

    # ── Pass 1: guarantee slots for small documents ──────────────────────────
    for doc_id, chunks in doc_chunks.items():
        total_chunks = chunks[0]["metadata"].get("total_chunks", 99)
        if total_chunks >= SMALL_DOC_THRESHOLD:
            continue
        ordered   = sorted(chunks, key=lambda c: c["metadata"].get("chunk_index", 0))
        doc_chars = 0
        for chunk in ordered:
            key     = (chunk["metadata"].get("document_id"), chunk["metadata"].get("chunk_index"))
            content = chunk["content"]
            if key in seen_indices:
                continue
            if doc_chars + len(content) + 2 > SMALL_DOC_GUARANTEE:
                continue
            if chars_so_far + len(content) + 2 > CONTEXT_BUDGET:
                break
            seen_indices.add(key)
            selected.append(chunk)
            chars_so_far += len(content) + 2
            doc_chars    += len(content) + 2

    # ── Pass 2: guarantee at least one chunk for every large doc that has
    #           a relevant hit but was skipped in Pass 1 ────────────────────
    seen_doc_ids = {chunk["metadata"].get("document_id") for chunk in selected}
    for chunk in sorted(rag_results, key=lambda r: r["final_score"], reverse=True):
        doc_id = chunk["metadata"].get("document_id")
        if doc_id in seen_doc_ids:
            continue
        key     = (doc_id, chunk["metadata"].get("chunk_index"))
        content = chunk["content"]
        if key in seen_indices:
            continue
        if chars_so_far + len(content) + 2 > CONTEXT_BUDGET:
            continue
        seen_doc_ids.add(doc_id)
        seen_indices.add(key)
        selected.append(chunk)
        chars_so_far += len(content) + 2

    # ── Pass 3: fill remaining budget with highest-scoring remaining chunks ──
    remaining = sorted(rag_results, key=lambda r: r["final_score"], reverse=True)
    for chunk in remaining:
        key     = (chunk["metadata"].get("document_id"), chunk["metadata"].get("chunk_index"))
        content = chunk["content"]
        if key in seen_indices:
            continue
        if chars_so_far + len(content) + 2 > CONTEXT_BUDGET:
            continue
        seen_indices.add(key)
        selected.append(chunk)
        chars_so_far += len(content) + 2

    doc_groups = {}
    for chunk in selected:
        doc_id = chunk["metadata"].get("document_id")
        doc_groups.setdefault(doc_id, []).append(chunk)

    doc_peak = {
        doc_id: max(c["final_score"] for c in chunks)
        for doc_id, chunks in doc_groups.items()
    }
    sorted_doc_ids = sorted(doc_peak, key=doc_peak.get, reverse=True)
    top_doc_id     = sorted_doc_ids[0] if sorted_doc_ids else None

    context_parts = []
    for doc_id in sorted_doc_ids:
        chunks = doc_groups[doc_id]
        chunks.sort(key=lambda c: c["metadata"].get("chunk_index", 0))

        # Tag the most relevant document so the LLM knows where to focus
        if doc_id == top_doc_id and len(sorted_doc_ids) > 1:
            doc_title = chunks[0]["metadata"].get("title", "")
            context_parts.append(
                f"[MOST RELEVANT — {doc_title}]"
            )

        for chunk in chunks:
            section = chunk["metadata"].get("section_title", "")
            prefix  = f"[SECTION: {section}]\n" if section else ""
            context_parts.append(prefix + chunk["content"])

    logger.info(
        f"_format_rag_results: {len(selected)} chunks selected, "
        f"{chars_so_far} chars, {len(doc_groups)} documents"
    )

    context       = "\n\n".join(context_parts).strip()
    heading_block = _extract_headings_from_context(context)
    item_count    = _count_list_items_in_text(context)

    # ── KEY EXCERPTS: pull the most query-relevant paragraphs to the top ──
    # Small LLMs struggle to find answers buried in long contexts.
    # This extracts the best-matching paragraphs and places them first
    # so the model sees them immediately.
    excerpt_block = ""
    if query_tokens and selected:
        scored_paras = []
        for chunk in selected:
            for para in chunk["content"].split("\n\n"):
                para = para.strip()
                if len(para) < 60:
                    continue
                score = _score_text_against_query(para, query_tokens)
                if score > 0.3:
                    scored_paras.append((score, para))
        scored_paras.sort(key=lambda x: x[0], reverse=True)
        top_excerpts = [p for _, p in scored_paras[:3]]
        if top_excerpts:
            excerpt_text = "\n\n".join(top_excerpts)
            excerpt_block = (
                "══════════════════════════════════════════════════\n"
                "KEY EXCERPTS — Most directly relevant to the question:\n"
                "══════════════════════════════════════════════════\n\n"
                f"{excerpt_text}\n\n"
                "══════════════════════════════════════════════════\n"
                "FULL CONTEXT BELOW\n"
                "══════════════════════════════════════════════════\n\n"
            )

    final = excerpt_block + (heading_block + context if heading_block else context)
    return final, item_count


def _extract_last_heading_from_block(text: str) -> str:
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if not line or len(line) < 8 or len(line) > 120:
            continue
        if re.match(r'^[\d•\-\*\(]', line):
            continue
        if line.endswith((',', ';')):
            continue
        words     = line.split()
        if len(words) < 2:
            continue
        cap_ratio = sum(1 for w in words if w and w[0].isupper()) / len(words)
        if cap_ratio >= 0.55:
            return line
    return ""


def _detect_heading_level(text):
    stripped = text.strip()
    if re.match(r"^[═=]{10,}$", stripped) or re.match(r"^[A-Z\s]{10,}$", stripped):
        return 1
    if re.match(r"^\d+\.0\s+[A-Z]", stripped):
        return 2
    if re.match(r"^\d+\.\d+\s+", stripped):
        return 3
    if re.match(r"^[•\-\*]\s+", stripped):
        return 4
    if re.match(r"^[a-z]\.\s+|^\d+\)\s+", stripped):
        return 5
    return 0


def _extract_section_title(text):
    text = re.sub(r"[═=]{3,}", "", text)
    text = re.sub(r"^\d+\.\d*\s*", "", text)
    text = re.sub(r"^[•\-\*]\s+", "", text)
    return text.strip()[:200]


def chunk_text_smart(text, chunk_size=3000, overlap=200):
    chunks = []
    if re.search(r"═{20,}", text):
        sections = re.split(r"═{20,}", text)
    elif re.search(r"={50,}", text):
        sections = re.split(r"={50,}", text)
    else:
        sections = [text]

    for section in sections:
        section = section.strip()
        if not section or len(section) < 100:
            continue
        lines         = section.split("\n")
        section_title = _extract_section_title(lines[0]) if lines else "Unknown Section"
        section_level = _detect_heading_level(lines[0]) if lines else 0

        list_patterns = [
            r"^\d+\.\s+", r"^\d+\)\s+", r"^\(\d+\)\s+",
            r"^[a-zA-Z]\.\s+", r"^[ivxIVX]+\.\s+",
            r"^•\s+", r"^-\s+", r"^\*\s+",
        ]
        is_list_section = any(
            re.search(p, section, re.MULTILINE) for p in list_patterns
        )

        if is_list_section and len(section) <= chunk_size * 1.5:
            chunks.append({
                "text": section,
                "metadata": {
                    "contains_list": True, "list_complete": True,
                    "section_title": section_title, "section_level": section_level,
                },
            })
            continue

        if is_list_section:
            combined_pattern = "|".join(f"(?={p})" for p in list_patterns)
            list_items       = re.split(combined_pattern, section, flags=re.MULTILINE)
            current_chunk, current_size, chunk_index = [], 0, 0
            current_heading = section_title
            for item in list_items:
                item      = item.strip()
                item_size = len(item)
                if not item:
                    continue
                detected = _extract_last_heading_from_block(item)
                if detected:
                    current_heading = detected
                if current_size + item_size > chunk_size and current_chunk:
                    chunks.append({
                        "text": "\n\n".join(current_chunk),
                        "metadata": {
                            "contains_list": True, "list_complete": False,
                            "list_part": chunk_index,
                            "section_title": current_heading, "section_level": section_level,
                        },
                    })
                    chunk_index += 1
                    cont = f"[Section: {current_heading}]"
                    if overlap > 0 and current_chunk:
                        ot = current_chunk[-1]
                        if len(ot) > overlap:
                            ot = ot[-overlap:]
                        current_chunk = [cont, ot, item]
                        current_size  = len(cont) + len(ot) + item_size
                    else:
                        current_chunk = [cont, item]
                        current_size  = len(cont) + item_size
                else:
                    current_chunk.append(item)
                    current_size += item_size
            if current_chunk:
                chunks.append({
                    "text": "\n\n".join(current_chunk),
                    "metadata": {
                        "contains_list": True, "list_complete": False,
                        "list_part": chunk_index,
                        "section_title": current_heading, "section_level": section_level,
                    },
                })
            continue

        if len(section) <= chunk_size:
            chunks.append({
                "text": section,
                "metadata": {
                    "contains_list": False,
                    "section_title": section_title, "section_level": section_level,
                },
            })
            continue

        paragraphs    = section.split("\n\n")
        current_chunk = []
        current_size  = 0
        for para in paragraphs:
            para      = para.strip()
            para_size = len(para)
            if not para:
                continue
            if current_size + para_size > chunk_size and current_chunk:
                chunks.append({
                    "text": "\n\n".join(current_chunk),
                    "metadata": {
                        "contains_list": False,
                        "section_title": section_title, "section_level": section_level,
                    },
                })
                if overlap > 0 and current_chunk:
                    ot = current_chunk[-1]
                    if len(ot) > overlap:
                        ot = ot[-overlap:]
                    current_chunk = [ot, para]
                    current_size  = len(ot) + para_size
                else:
                    current_chunk = [para]
                    current_size  = para_size
            else:
                current_chunk.append(para)
                current_size += para_size
        if current_chunk:
            chunks.append({
                "text": "\n\n".join(current_chunk),
                "metadata": {
                    "contains_list": False,
                    "section_title": section_title, "section_level": section_level,
                },
            })

    return [c for c in chunks if len(c["text"]) >= 80]


# ── Pydantic models ───────────────────────────────────────────────────────────

class IndexRequest(BaseModel):
    document_id: str
    title:       str
    category:    str
    status:      str
    text:        str

class SearchRequest(BaseModel):
    query:           str
    n_results:       int = 150
    category_filter: Optional[str] = None

class EmbedRequest(BaseModel):
    texts: list[str]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "model": EMBEDDING_MODEL}


@app.post("/embed")
def embed(req: EmbedRequest):
    try:
        embeddings = get_embedder().encode(req.texts).tolist()
        return {"embeddings": embeddings}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/index-document")
def index_document(req: IndexRequest):
    try:
        chunks_with_metadata = chunk_text_smart(req.text, chunk_size=3000, overlap=200)
        if not chunks_with_metadata:
            raise HTTPException(status_code=400, detail="No chunks created from text")

        chunk_texts = [c["text"] for c in chunks_with_metadata]
        embeddings  = get_embedder().encode(chunk_texts).tolist()

        ids, metadatas, documents = [], [], []
        for i, chunk_data in enumerate(chunks_with_metadata):
            ids.append(f"doc_{req.document_id}_chunk_{i}")
            metadatas.append({
                "document_id":   req.document_id,
                "title":         req.title,
                "category":      req.category,
                "chunk_index":   i,
                "total_chunks":  len(chunks_with_metadata),
                "chunk_size":    len(chunk_data["text"]),
                "status":        req.status,
                "contains_list": chunk_data["metadata"].get("contains_list", False),
                "list_complete": chunk_data["metadata"].get("list_complete", True),
                "list_part":     chunk_data["metadata"].get("list_part", 0),
                "section_title": chunk_data["metadata"].get("section_title", ""),
                "section_level": chunk_data["metadata"].get("section_level", 0),
            })
            documents.append(chunk_data["text"])

        get_collection().add(
            ids=ids, embeddings=embeddings,
            documents=documents, metadatas=metadatas,
        )
        _build_bm25_index()
        logger.info(f"Indexed {len(documents)} chunks for document {req.document_id}")
        return {"chunks_added": len(documents)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Index error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search")
def search(req: SearchRequest):
    try:
        # ── Key fix: removed min(..., 80) hard cap so fetch_n scales with corpus ──
        fetch_n = req.n_results * 2

        where = {"status": "published"}
        if req.category_filter:
            where = {"$and": [{"status": "published"}, {"category": req.category_filter}]}

        query_embedding  = get_embedder().encode([req.query]).tolist()
        semantic_results = get_collection().query(
            query_embeddings=query_embedding,
            n_results=fetch_n,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        formatted_semantic = []
        if semantic_results["documents"] and semantic_results["documents"][0]:
            for i, doc in enumerate(semantic_results["documents"][0]):
                meta = semantic_results["metadatas"][0][i]
                if req.category_filter and meta.get("category") != req.category_filter:
                    continue
                formatted_semantic.append({
                    "content":        doc,
                    "title":          meta.get("title", "Unknown"),
                    "category":       meta.get("category", "Unknown"),
                    "chunk_size":     meta.get("chunk_size", len(doc)),
                    "semantic_score": 1 - semantic_results["distances"][0][i],
                    "metadata":       meta,
                    "source":         "semantic",
                })

        bm25_results   = _bm25_search(req.query, n_results=req.n_results)
        formatted_bm25 = []
        for result in bm25_results:
            meta = result["metadata"]
            if req.category_filter and meta.get("category") != req.category_filter:
                continue
            formatted_bm25.append({
                "content":    result["content"],
                "title":      meta.get("title", "Unknown"),
                "category":   meta.get("category", "Unknown"),
                "chunk_size": meta.get("chunk_size", len(result["content"])),
                "bm25_score": result["bm25_score"],
                "metadata":   meta,
                "source":     "bm25",
            })

        logger.info(
            f"Search '{req.query[:60]}': "
            f"{len(formatted_semantic)} semantic, {len(formatted_bm25)} bm25"
        )

        combined = _reciprocal_rank_fusion(formatted_semantic, formatted_bm25)
        if combined:
            max_rrf = max(r["rrf_score"] for r in combined)
            for r in combined:
                r["relevance_score"] = r["rrf_score"] / max_rrf if max_rrf > 0 else 0

        if not combined:
            return {"context": "", "item_count": 0}

        top_results      = combined[: req.n_results]
        doc_chunk_counts = {}
        for r in top_results:
            doc_id = r["metadata"].get("document_id")
            doc_chunk_counts[doc_id] = doc_chunk_counts.get(doc_id, 0) + 1

        def _expansion_threshold(doc_id):
            try:
                result = get_collection().get(
                    where={"document_id": doc_id}, include=["metadatas"], limit=1
                )
                if result["metadatas"]:
                    total = result["metadatas"][0].get("total_chunks", 99)
                    return 1 if total < SMALL_DOC_THRESHOLD else 2
            except Exception:
                pass
            return 2

        expanded_ids = {
            doc_id for doc_id, count in doc_chunk_counts.items()
            if count >= _expansion_threshold(doc_id)
        }
        existing_keys = {
            (r["metadata"].get("document_id"), r["metadata"].get("chunk_index"))
            for r in combined
        }

        for doc_id in expanded_ids:
            try:
                all_doc = get_collection().get(
                    where={"$and": [{"document_id": doc_id}, {"status": "published"}]},
                    include=["documents", "metadatas"],
                )
                query_tokens     = set(_tokenize(req.query))
                total_doc_chunks = len(all_doc["documents"])
                is_small         = total_doc_chunks < SMALL_DOC_THRESHOLD

                for i, doc in enumerate(all_doc["documents"]):
                    meta = all_doc["metadatas"][i]
                    key  = (doc_id, meta.get("chunk_index", -1))
                    if key not in existing_keys:
                        relevance = _score_text_against_query(doc, query_tokens)
                        threshold = 0.0 if is_small else LARGE_DOC_RELEVANCE_FLOOR
                        if relevance > threshold:
                            combined.append({
                                "content":         doc,
                                "title":           meta.get("title", "Unknown"),
                                "category":        meta.get("category", "Unknown"),
                                "chunk_size":      meta.get("chunk_size", len(doc)),
                                "rrf_score":       0.001 + (relevance * 0.3),
                                "relevance_score": relevance,
                                "metadata":        meta,
                                "source":          "auto_expanded",
                            })
                            existing_keys.add(key)
            except Exception as exc:
                logger.warning(f"Auto-expansion failed for {doc_id}: {exc}")

        context, item_count = _format_rag_results(combined, query=req.query)
        logger.info(f"Search result: {len(context)} chars, {item_count} list items")
        return {"context": context, "item_count": item_count}

    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/document/{document_id}")
def delete_document(document_id: str):
    try:
        results = get_collection().get(where={"document_id": document_id})
        if results["ids"]:
            get_collection().delete(ids=results["ids"])
            _build_bm25_index()
            return {"deleted": True, "chunks_removed": len(results["ids"])}
        return {"deleted": False, "chunks_removed": 0}
    except Exception as e:
        logger.error(f"Delete error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents")
def get_all_document_titles():
    try:
        results = get_collection().get(
            where={"status": "published"}, include=["metadatas"]
        )
        if not results["metadatas"]:
            return []
        seen_ids, unique_docs = set(), []
        for meta in results["metadatas"]:
            doc_id = meta.get("document_id")
            if doc_id and doc_id not in seen_ids:
                seen_ids.add(doc_id)
                unique_docs.append({
                    "title":    meta.get("title", "Unknown Document"),
                    "category": meta.get("category", "general"),
                })
        return unique_docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents/sample")
def get_knowledge_base_sample(sample_size: int = 3):
    docs = get_all_document_titles()
    return random.sample(docs, min(sample_size, len(docs)))


@app.get("/stats")
def get_stats():
    try:
        coll = get_collection()
        return {"total_chunks": coll.count(), "collection_name": coll.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/categories")
def get_categories():
    try:
        results = get_collection().get(
            where={"status": "published"}, include=["metadatas"]
        )
        if results["metadatas"]:
            return sorted({m["category"] for m in results["metadatas"] if "category" in m})
        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))