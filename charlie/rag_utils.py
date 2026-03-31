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

CONTEXT_BUDGET            = int(os.getenv('CONTEXT_BUDGET',             100000))
SMALL_DOC_THRESHOLD       = int(os.getenv('SMALL_DOC_THRESHOLD',        15))
SMALL_DOC_GUARANTEE       = int(os.getenv('SMALL_DOC_GUARANTEE',        4000))
LARGE_DOC_RELEVANCE_FLOOR = float(os.getenv('LARGE_DOC_RELEVANCE_FLOOR', 0.05))
RELEVANCE_FLOOR_RATIO     = float(os.getenv('RELEVANCE_FLOOR_RATIO',    0.10))

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


def _bm25_search(query, n_results=50):
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
        elif qt.endswith('s') and len(qt) > 3 and qt[:-1] in chunk_tokens:
            hits += 0.8
        elif qt + 's' in chunk_tokens:
            hits += 0.8
        elif len(qt) >= 5 and any(ct.startswith(qt[:5]) for ct in chunk_tokens):
            hits += 0.5

    return hits / len(meaningful)


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


def get_knowledge_base_sample(sample_size=3):
    docs = get_all_document_titles()
    return random.sample(docs, min(sample_size, len(docs)))


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

    if re.search(r'═{20,}', text):
        sections = re.split(r'═{20,}', text)
    elif re.search(r'={50,}', text):
        sections = re.split(r'={50,}', text)
    else:
        sections = [text]

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

    query_tokens = set(_tokenize(query)) if query else set()
    for chunk in rag_results:
        overlap = _score_text_against_query(chunk.get('content', ''), query_tokens)
        chunk['final_score'] = chunk.get('rrf_score', 0.0) + (overlap * 0.4)

    max_score = max(c['final_score'] for c in rag_results)
    floor = max_score * RELEVANCE_FLOOR_RATIO
    rag_results = [c for c in rag_results if c['final_score'] >= floor]

    doc_chunks = {}
    for chunk in rag_results:
        doc_id = chunk['metadata'].get('document_id')
        if doc_id not in doc_chunks:
            doc_chunks[doc_id] = []
        doc_chunks[doc_id].append(chunk)

    for doc_id in doc_chunks:
        doc_chunks[doc_id].sort(key=lambda r: r['final_score'], reverse=True)

    seen_indices = set()
    selected = []
    chars_so_far = 0

    for doc_id, chunks in doc_chunks.items():
        total_chunks = chunks[0]['metadata'].get('total_chunks', 99)
        if total_chunks >= SMALL_DOC_THRESHOLD:
            continue
        ordered = sorted(chunks, key=lambda c: c['metadata'].get('chunk_index', 0))
        doc_chars = 0
        for chunk in ordered:
            key = (chunk['metadata'].get('document_id'), chunk['metadata'].get('chunk_index'))
            content = chunk['content']
            if key in seen_indices:
                continue
            if doc_chars + len(content) + 2 > SMALL_DOC_GUARANTEE:
                continue
            if chars_so_far + len(content) + 2 > CONTEXT_BUDGET:
                break
            seen_indices.add(key)
            selected.append(chunk)
            chars_so_far += len(content) + 2
            doc_chars += len(content) + 2

    remaining = sorted(rag_results, key=lambda r: r['final_score'], reverse=True)
    for chunk in remaining:
        key = (chunk['metadata'].get('document_id'), chunk['metadata'].get('chunk_index'))
        content = chunk['content']
        if key in seen_indices:
            continue
        if chars_so_far + len(content) + 2 > CONTEXT_BUDGET:
            continue
        seen_indices.add(key)
        selected.append(chunk)
        chars_so_far += len(content) + 2

    doc_groups = {}
    for chunk in selected:
        doc_id = chunk['metadata'].get('document_id')
        if doc_id not in doc_groups:
            doc_groups[doc_id] = []
        doc_groups[doc_id].append(chunk)

    context_parts = []
    for doc_id, chunks in doc_groups.items():
        chunks.sort(key=lambda c: c['metadata'].get('chunk_index', 0))
        for chunk in chunks:
            section = chunk['metadata'].get('section_title', '')
            prefix = f"[SECTION: {section}]\n" if section else ""
            context_parts.append(prefix + chunk['content'])

    context = "\n\n".join(context_parts).strip()
    heading_block = extract_headings_from_context(context)
    item_count = _count_list_items_in_text(context)
    return (heading_block + context) if heading_block else context, item_count


def search_documents(query, n_results=50, category_filter=None, query_info=None):
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

        def _get_expansion_threshold(doc_id, collection):
            try:
                result = collection.get(
                    where={"document_id": doc_id},
                    include=["metadatas"],
                    limit=1
                )
                if result['metadatas']:
                    total = result['metadatas'][0].get('total_chunks', 99)
                    return 1 if total < SMALL_DOC_THRESHOLD else 3
            except Exception:
                pass
            return 3

        expanded_doc_ids = {
            doc_id for doc_id, count in doc_chunk_counts.items()
            if count >= _get_expansion_threshold(doc_id, get_collection())
        }
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
                query_tokens = set(_tokenize(query))
                total_doc_chunks = len(all_doc_data['documents'])
                is_small_doc = total_doc_chunks < SMALL_DOC_THRESHOLD

                for i, doc in enumerate(all_doc_data['documents']):
                    meta = all_doc_data['metadatas'][i]
                    key = (doc_id, meta.get('chunk_index', -1))
                    if key not in existing_chunk_keys:
                        relevance = _score_text_against_query(doc, query_tokens)
                        relevance_threshold = 0.0 if is_small_doc else LARGE_DOC_RELEVANCE_FLOOR

                        if relevance > relevance_threshold:
                            combined_results.append({
                                'content': doc,
                                'title': meta.get('title', 'Unknown'),
                                'category': meta.get('category', 'Unknown'),
                                'chunk_size': meta.get('chunk_size', len(doc)),
                                'rrf_score': 0.001 + (relevance * 0.3),
                                'relevance_score': relevance,
                                'metadata': meta,
                                'source': 'auto_expanded',
                            })
                            existing_chunk_keys.add(key)

                logger.info(
                    f"Auto-expanded '{doc_id}': "
                    f"{len(all_doc_data['documents'])} total chunks fetched "
                    f"({'small' if is_small_doc else 'large'} doc)"
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