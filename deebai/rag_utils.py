import os
import random
from pathlib import Path
import logging
import re
from rank_bm25 import BM25Okapi
import numpy as np

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_DIR = BASE_DIR / "chromadb"

_client = None
_collection = None
_embedder = None
_bm25_index = None
_bm25_documents = []
_bm25_metadatas = []


def initialize_rag_system():
    global _client, _collection, _embedder

    if _collection is None or _embedder is None:
        import chromadb
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = _client.get_or_create_collection(
            name="surigao_documents",
            metadata={"description": "Surigao City knowledge base"}
        )

        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer('all-MiniLM-L6-v2')

        _build_bm25_index()


def get_collection():
    global _collection
    if _collection is None:
        initialize_rag_system()
    return _collection


def get_embedder():
    global _embedder
    if _embedder is None:
        initialize_rag_system()
    return _embedder


def _tokenize(text):
    return re.findall(r'\w+', text.lower())


def _build_bm25_index():
    global _bm25_index, _bm25_documents, _bm25_metadatas

    try:
        all_data = get_collection().get(
            where={"status": "published"},
            include=["documents", "metadatas"]
        )
        if not all_data['documents']:
            return
        _bm25_documents = all_data['documents']
        _bm25_metadatas = all_data['metadatas']
        tokenized_docs = [_tokenize(doc) for doc in _bm25_documents]
        _bm25_index = BM25Okapi(tokenized_docs)
    except Exception as e:
        logger.error(f"BM25 index error: {e}")


def _bm25_search(query, n_results=25):
    global _bm25_index, _bm25_documents, _bm25_metadatas

    if _bm25_index is None or not _bm25_documents:
        return []

    tokenized_query = _tokenize(query)
    scores = _bm25_index.get_scores(tokenized_query)
    top_indices = np.argsort(scores)[::-1][:n_results]

    results = []
    for idx in top_indices:
        if scores[idx] > 0:
            results.append({
                'content': _bm25_documents[idx],
                'metadata': _bm25_metadatas[idx],
                'bm25_score': float(scores[idx])
            })
    return results


def _reciprocal_rank_fusion(semantic_results, bm25_results, k=60):
    doc_scores = {}
    doc_data = {}

    for rank, result in enumerate(semantic_results, start=1):
        doc_id = result['content'][:100]
        rrf_score = 1.0 / (k + rank)
        if doc_id not in doc_scores:
            doc_scores[doc_id] = 0
            doc_data[doc_id] = result
            doc_data[doc_id]['source'] = 'semantic'
        doc_scores[doc_id] += rrf_score

    for rank, result in enumerate(bm25_results, start=1):
        doc_id = result['content'][:100]
        rrf_score = 1.0 / (k + rank)
        if doc_id not in doc_scores:
            doc_scores[doc_id] = 0
            doc_data[doc_id] = result
            doc_data[doc_id]['source'] = 'bm25'
        else:
            doc_data[doc_id]['source'] = 'hybrid'
        doc_scores[doc_id] += rrf_score

    sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
    combined_results = []
    for doc_id, rrf_score in sorted_docs:
        result = doc_data[doc_id].copy()
        result['rrf_score'] = rrf_score
        combined_results.append(result)
    return combined_results


def get_knowledge_base_sample(sample_size=3):
    try:
        results = get_collection().get(
            where={"status": "published"},
            include=["metadatas"]
        )
        if not results['metadatas']:
            return []
        seen_ids = set()
        unique_docs = []
        for metadata in results['metadatas']:
            doc_id = metadata.get('document_id')
            if doc_id and doc_id not in seen_ids:
                seen_ids.add(doc_id)
                unique_docs.append({
                    'title': metadata.get('title', 'Unknown Document'),
                    'category': metadata.get('category', 'general')
                })
        if not unique_docs:
            return []
        return random.sample(unique_docs, min(sample_size, len(unique_docs)))
    except Exception as e:
        logger.error(f"Error getting knowledge base sample: {e}")
        return []


def get_all_document_titles():
    try:
        results = get_collection().get(
            where={"status": "published"},
            include=["metadatas"]
        )
        if not results['metadatas']:
            return []
        seen_ids = set()
        unique_docs = []
        for metadata in results['metadatas']:
            doc_id = metadata.get('document_id')
            if doc_id and doc_id not in seen_ids:
                seen_ids.add(doc_id)
                unique_docs.append({
                    'title': metadata.get('title', 'Unknown Document'),
                    'category': metadata.get('category', 'general')
                })
        return unique_docs
    except Exception as e:
        logger.error(f"Error getting all document titles: {e}")
        return []


def _detect_heading_level(text):
    stripped = text.strip()
    if re.match(r'^[═=]{10,}$', stripped) or re.match(r'^[A-Z\s]{10,}$', stripped):
        return 1
    if re.match(r'^\d+\.0\s+[A-Z]', stripped):
        return 2
    if re.match(r'^\d+\.\d+\s+', stripped):
        return 3
    if re.match(r'^[•\-\*]\s+', stripped):
        return 4
    if re.match(r'^[a-z]\.\s+|^\d+\)\s+', stripped):
        return 5
    return 0


def _extract_section_title(text):
    text = re.sub(r'[═=]{3,}', '', text)
    text = re.sub(r'^\d+\.\d*\s*', '', text)
    text = re.sub(r'^[•\-\*]\s+', '', text)
    return text.strip()[:200]


def chunk_text_smart(text, chunk_size=3000, overlap=200):
    chunks = []
    sections = re.split(r'═{51,}', text)

    for section in sections:
        section = section.strip()
        if not section or len(section) < 100:
            continue

        lines = section.split('\n')
        section_title = _extract_section_title(lines[0]) if lines else "Unknown Section"
        section_level = _detect_heading_level(lines[0]) if lines else 0

        list_patterns = [
            r'^\d+\.\s+', r'^\d+\)\s+', r'^\(\d+\)\s+',
            r'^[a-zA-Z]\.\s+', r'^[ivxIVX]+\.\s+',
            r'^•\s+', r'^-\s+', r'^\*\s+',
        ]

        is_list_section = any(
            re.search(pattern, section, re.MULTILINE)
            for pattern in list_patterns
        )

        if is_list_section and len(section) <= chunk_size * 1.5:
            chunks.append({
                'text': section,
                'metadata': {
                    'contains_list': True,
                    'list_complete': True,
                    'section_title': section_title,
                    'section_level': section_level
                }
            })
            continue

        if is_list_section:
            combined_pattern = '|'.join(f'(?={p})' for p in list_patterns)
            list_items = re.split(combined_pattern, section, flags=re.MULTILINE)
            current_chunk = []
            current_size = 0
            chunk_index = 0

            for item in list_items:
                item = item.strip()
                if not item:
                    continue
                item_size = len(item)
                if current_size + item_size > chunk_size and current_chunk:
                    chunks.append({
                        'text': '\n\n'.join(current_chunk),
                        'metadata': {
                            'contains_list': True,
                            'list_complete': False,
                            'list_part': chunk_index,
                            'section_title': section_title,
                            'section_level': section_level
                        }
                    })
                    chunk_index += 1
                    continuation_header = f"[SECTION CONTINUED: {section_title}]"
                    if overlap > 0 and current_chunk:
                        overlap_text = current_chunk[-1]
                        if len(overlap_text) > overlap:
                            overlap_text = overlap_text[-overlap:]
                        current_chunk = [continuation_header, overlap_text, item]
                        current_size = len(continuation_header) + len(overlap_text) + item_size
                    else:
                        current_chunk = [continuation_header, item]
                        current_size = len(continuation_header) + item_size
                else:
                    current_chunk.append(item)
                    current_size += item_size

            if current_chunk:
                chunks.append({
                    'text': '\n\n'.join(current_chunk),
                    'metadata': {
                        'contains_list': True,
                        'list_complete': False,
                        'list_part': chunk_index,
                        'section_title': section_title,
                        'section_level': section_level
                    }
                })
            continue

        if len(section) <= chunk_size:
            chunks.append({
                'text': section,
                'metadata': {
                    'contains_list': False,
                    'section_title': section_title,
                    'section_level': section_level
                }
            })
            continue

        paragraphs = section.split('\n\n')
        current_chunk = []
        current_size = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            para_size = len(para)
            if current_size + para_size > chunk_size and current_chunk:
                chunks.append({
                    'text': '\n\n'.join(current_chunk),
                    'metadata': {
                        'contains_list': False,
                        'section_title': section_title,
                        'section_level': section_level
                    }
                })
                if overlap > 0 and current_chunk:
                    overlap_text = current_chunk[-1]
                    if len(overlap_text) > overlap:
                        overlap_text = overlap_text[-overlap:]
                    current_chunk = [overlap_text, para]
                    current_size = len(overlap_text) + para_size
                else:
                    current_chunk = [para]
                    current_size = para_size
            else:
                current_chunk.append(para)
                current_size += para_size

        if current_chunk:
            chunks.append({
                'text': '\n\n'.join(current_chunk),
                'metadata': {
                    'contains_list': False,
                    'section_title': section_title,
                    'section_level': section_level
                }
            })

    return [c for c in chunks if len(c['text']) >= 80]


def extract_text_from_docx(file_path):
    from docx import Document as DocxDocument
    doc = DocxDocument(file_path)
    return "\n\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())


def extract_text_from_pdf(file_path):
    from pypdf import PdfReader
    text = []
    with open(file_path, 'rb') as file:
        for page in PdfReader(file).pages:
            page_text = page.extract_text()
            if page_text.strip():
                text.append(page_text.strip())
    return "\n\n".join(text)


def extract_text_from_txt(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()


def extract_text(file_path):
    extension = os.path.splitext(file_path)[1].lower()
    if extension == '.docx':
        return extract_text_from_docx(file_path)
    elif extension == '.pdf':
        return extract_text_from_pdf(file_path)
    elif extension == '.txt':
        return extract_text_from_txt(file_path)
    else:
        raise ValueError(f"Unsupported file type: {extension}")


def add_document_to_chromadb(document):
    try:
        text = extract_text(document.file.path)
        if not text.strip():
            logger.error(f"No text extracted from '{document.title}'")
            return False

        chunks_with_metadata = chunk_text_smart(text, chunk_size=3000, overlap=200)
        if not chunks_with_metadata:
            logger.error(f"No chunks created from '{document.title}'")
            return False

        chunk_texts = [c['text'] for c in chunks_with_metadata]
        embeddings = get_embedder().encode(chunk_texts).tolist()

        ids, metadatas, documents = [], [], []
        for i, chunk_data in enumerate(chunks_with_metadata):
            ids.append(f"doc_{document.id}_chunk_{i}")
            metadatas.append({
                "document_id": str(document.id),
                "title": document.title,
                "category": document.category,
                "chunk_index": i,
                "total_chunks": len(chunks_with_metadata),
                "chunk_size": len(chunk_data['text']),
                "status": document.status,
                "contains_list": chunk_data['metadata'].get('contains_list', False),
                "list_complete": chunk_data['metadata'].get('list_complete', True),
                "list_part": chunk_data['metadata'].get('list_part', 0),
                "section_title": chunk_data['metadata'].get('section_title', ''),
                "section_level": chunk_data['metadata'].get('section_level', 0)
            })
            documents.append(chunk_data['text'])

        get_collection().add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
        _build_bm25_index()
        logger.info(f"[OK] Added {len(documents)} chunks from '{document.title}'")
        return len(documents)
    except Exception as e:
        logger.error(f"Error processing '{document.title}': {e}", exc_info=True)
        return False


def _count_list_items_in_text(text):
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r'^[•\-\*]\s+', stripped) or re.match(r'^\d+[\.\)]\s+', stripped):
            count += 1
    return count


_HEADING_PATTERNS = [
    re.compile(r'^\s*[A-Z][A-Z\s]+\d+\s+OF\s+\d+\s*:\s*(.+)$', re.IGNORECASE),
    re.compile(r'^\s*[A-Z][A-Z\s]*\d+\s*[—\-–]\s*(.+)$', re.IGNORECASE),
    re.compile(r'^\s*\w*\s*sub[\-\s]?\w+\s+\d+\s*:\s*(.+)$', re.IGNORECASE),
    re.compile(r'^\s*([A-Z][A-Z\s\(\)\/\-]{4,78}[A-Z\)])\s*$'),
]


def extract_headings_from_context(context_text):
    found_labels = []
    seen = set()
    for line in context_text.splitlines():
        line = line.strip()
        if not line:
            continue
        for pattern in _HEADING_PATTERNS:
            match = pattern.match(line)
            if match:
                label = match.group(1).strip() if pattern.groups else line.strip()
                label = re.sub(r'\s+', ' ', label).strip(' .:—-')
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
        "⚠️ You MUST use these names WORD-FOR-WORD in your answer.\n"
        "Do NOT rename, paraphrase, or reorder them:\n"
        f"{label_lines}\n"
        "══════════════════════════════════════════════════\n\n"
    )


def format_rag_results(rag_results, query_info=None, query=""):
    if not rag_results:
        return "", 0

    CONTEXT_BUDGET = 14000

    doc_chunks = {}
    doc_best_score = {}
    for r in rag_results:
        doc_id = r['metadata'].get('document_id', 'unknown')
        if doc_id not in doc_chunks:
            doc_chunks[doc_id] = []
            doc_best_score[doc_id] = 0
        doc_chunks[doc_id].append(r)
        score = r.get('rrf_score', 0)
        if score > doc_best_score[doc_id]:
            doc_best_score[doc_id] = score

    # Sort all documents by their best score, best first
    docs_by_score = sorted(doc_best_score, key=doc_best_score.get, reverse=True)

    # Expand the top 2 highest-scoring documents fully.
    # This handles any multi-topic question (comparisons, contrasts, or any
    # question that spans two subjects) without needing keyword detection.
    # For normal single-topic questions, the second doc simply adds more
    # supporting context — it never hurts.
    TOP_DOCS_TO_EXPAND = 2

    context = ""
    chars_so_far = 0

    for doc_id in docs_by_score[:TOP_DOCS_TO_EXPAND]:
        doc_by_relevance = sorted(
            doc_chunks[doc_id],
            key=lambda r: r.get('rrf_score', 0),
            reverse=True
        )

        selected_indices = set()
        for chunk in doc_by_relevance:
            idx = chunk['metadata'].get('chunk_index', 0)
            if idx in selected_indices:
                continue
            content = chunk['content']
            if chars_so_far + len(content) + 2 <= CONTEXT_BUDGET:
                selected_indices.add(idx)
                chars_so_far += len(content) + 2
            if chars_so_far >= CONTEXT_BUDGET:
                break

        # Re-sort selected chunks into reading order before adding to context
        ordered = sorted(
            [c for c in doc_by_relevance
             if c['metadata'].get('chunk_index', 0) in selected_indices],
            key=lambda r: r['metadata'].get('chunk_index', 0)
        )
        for chunk in ordered:
            context += chunk['content'] + "\n\n"

    # Fill any remaining budget with the best chunk from other documents
    remaining_budget = CONTEXT_BUDGET - len(context)
    for doc_id in docs_by_score[TOP_DOCS_TO_EXPAND:]:
        best_chunk = max(doc_chunks[doc_id], key=lambda r: r.get('rrf_score', 0))
        content = best_chunk['content']
        if len(content) + 2 <= remaining_budget:
            context += content + "\n\n"
            remaining_budget -= len(content) + 2

    context = context.strip()

    heading_block = extract_headings_from_context(context)
    item_count = _count_list_items_in_text(context)

    return (heading_block + context) if heading_block else context, item_count


def search_documents(query, n_results=25, category_filter=None, query_info=None):
    try:
        fetch_n = min(n_results * 2, 80)

        where_clause = {"status": "published"}
        if category_filter:
            where_clause = {"$and": [{"status": "published"}, {"category": category_filter}]}

        query_embedding = get_embedder().encode([query]).tolist()
        semantic_results = get_collection().query(
            query_embeddings=query_embedding,
            n_results=fetch_n,
            where=where_clause,
            include=["documents", "metadatas", "distances"]
        )

        formatted_semantic = []
        if semantic_results['documents'] and semantic_results['documents'][0]:
            for i, doc in enumerate(semantic_results['documents'][0]):
                metadata = semantic_results['metadatas'][0][i]
                if category_filter and metadata.get('category') != category_filter:
                    continue
                formatted_semantic.append({
                    'content': doc,
                    'title': metadata.get('title', 'Unknown'),
                    'category': metadata.get('category', 'Unknown'),
                    'chunk_size': metadata.get('chunk_size', len(doc)),
                    'semantic_score': 1 - semantic_results['distances'][0][i],
                    'metadata': metadata,
                    'source': 'semantic',
                })

        bm25_results = _bm25_search(query, n_results=fetch_n)
        formatted_bm25 = []
        for result in bm25_results:
            metadata = result['metadata']
            if category_filter and metadata.get('category') != category_filter:
                continue
            formatted_bm25.append({
                'content': result['content'],
                'title': metadata.get('title', 'Unknown'),
                'category': metadata.get('category', 'Unknown'),
                'chunk_size': metadata.get('chunk_size', len(result['content'])),
                'bm25_score': result['bm25_score'],
                'metadata': metadata,
                'source': 'bm25',
            })

        combined_results = _reciprocal_rank_fusion(formatted_semantic, formatted_bm25)

        if combined_results:
            max_rrf = max(r['rrf_score'] for r in combined_results)
            for result in combined_results:
                result['relevance_score'] = result['rrf_score'] / max_rrf if max_rrf > 0 else 0

        if not combined_results:
            return []

        top_results = combined_results[:n_results]
        doc_chunk_counts = {}
        for r in top_results:
            doc_id = r['metadata'].get('document_id')
            doc_chunk_counts[doc_id] = doc_chunk_counts.get(doc_id, 0) + 1

        # Auto-expand: fetch ALL chunks from every document that appeared
        # in the top results, not just the #1 document.
        # This ensures no section is ever missed regardless of how the
        # question was phrased.
        expanded_doc_ids = set(doc_chunk_counts.keys())
        existing_chunk_keys = {
            (r['metadata'].get('document_id'), r['metadata'].get('chunk_index'))
            for r in combined_results
        }

        for doc_id in expanded_doc_ids:
            try:
                all_doc_data = get_collection().get(
                    where={"$and": [
                        {"document_id": doc_id},
                        {"status": "published"}
                    ]},
                    include=["documents", "metadatas"]
                )
                for i, doc in enumerate(all_doc_data['documents']):
                    meta = all_doc_data['metadatas'][i]
                    key = (doc_id, meta.get('chunk_index', -1))
                    if key not in existing_chunk_keys:
                        combined_results.append({
                            'content': doc,
                            'title': meta.get('title', 'Unknown'),
                            'category': meta.get('category', 'Unknown'),
                            'chunk_size': meta.get('chunk_size', len(doc)),
                            'rrf_score': 0.001,
                            'relevance_score': 0.5,
                            'metadata': meta,
                            'source': 'auto_expanded',
                        })
                        existing_chunk_keys.add(key)
                logger.info(
                    f"Auto-expanded '{doc_id}': "
                    f"{len(all_doc_data['documents'])} total chunks fetched"
                )
            except Exception as exc:
                logger.warning(f"Auto-expansion fetch failed for '{doc_id}': {exc}")

        return combined_results

    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        return []


def delete_document_from_chromadb(document_id):
    try:
        results = get_collection().get(where={"document_id": str(document_id)})
        if results['ids']:
            get_collection().delete(ids=results['ids'])
            _build_bm25_index()
            return True
        return False
    except Exception as e:
        logger.error(f"Error deleting document {document_id}: {e}")
        return False


def get_collection_stats():
    try:
        coll = get_collection()
        return {'total_chunks': coll.count(), 'collection_name': coll.name}
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return None


def get_available_categories():
    try:
        results = get_collection().get(
            where={"status": "published"},
            include=["metadatas"]
        )
        if results['metadatas']:
            categories = set()
            for metadata in results['metadatas']:
                if 'category' in metadata:
                    categories.add(metadata['category'])
            return sorted(list(categories))
        return []
    except Exception as e:
        logger.error(f"Error getting categories: {e}")
        return []