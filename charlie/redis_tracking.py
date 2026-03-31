"""
redis_tracking.py
-----------------
All document tracking read/write operations via Redis.
Redis runs on the Ubuntu server at 192.168.160.118:6379.

Key structure:
  doc:pdid:{pdid}          → JSON of full document record
  idx:title:{word}         → SET of pdids matching this word in title
  idx:subject:{word}       → SET of pdids matching this word in subject
  idx:office:{word}        → SET of pdids matching this word in office
  idx:agency:{word}        → SET of pdids matching this word in agency
  idx:doctype:{word}       → SET of pdids matching this word in document_type
  idx:createdby:{word}     → SET of pdids matching this word in created_by
  idx:slug:{word}          → SET of pdids matching this word in slug
  tracking:all_pdids       → SET of all pdids (for full scans)
"""

import re
import json
import logging
import os

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv('REDIS_HOST', '192.168.160.118')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB   = int(os.getenv('REDIS_DB', 0))

_redis_client = None


def get_redis():
    global _redis_client
    if _redis_client is None:
        import redis
        _redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
    return _redis_client


def redis_available():
    try:
        get_redis().ping()
        return True
    except Exception:
        return False


def _tokenize(text):
    if not text:
        return []
    return list(set(re.findall(r'\w+', text.lower())))


def store_document(doc: dict):
    """
    Store a single document record in Redis with all its search indexes.
    doc must have at minimum: pdid, title, subject, office, agency,
    document_type, created_by, slug
    """
    r = get_redis()
    pdid = str(doc['pdid'])
    pipe = r.pipeline()

    # Store the full document record as JSON
    pipe.set(f"doc:pdid:{pdid}", json.dumps(doc))

    # Add to master set
    pipe.sadd("tracking:all_pdids", pdid)

    # Build search indexes
    field_map = {
        'title':         f"idx:title:",
        'subject':       f"idx:subject:",
        'office':        f"idx:office:",
        'agency':        f"idx:agency:",
        'document_type': f"idx:doctype:",
        'created_by':    f"idx:createdby:",
        'slug':          f"idx:slug:",
    }

    for field, prefix in field_map.items():
        value = doc.get(field, '') or ''
        for token in _tokenize(value):
            if len(token) >= 2:
                pipe.sadd(f"{prefix}{token}", pdid)

    pipe.execute()
    logger.debug(f"Stored PDID {pdid} in Redis")


def search_documents(message: str):
    """
    Search Redis for documents matching the message tokens.
    Returns list of document dicts ordered by match score and timestamp.
    """
    r = get_redis()
    
    # Extract distinct identifiers instead of every single dictionary word
    # This prevents loading the entire database into memory if the user says "track document"
    tokens = re.findall(r'\w+', message.lower())
    alobs_matches = re.findall(r'\b\d{4}-\d{2}-\d{2}-\d{3}\b', message.lower())
    
    pdid_scores = {}

    for token in tokens:
        token_matches = set()
        
        # Pure numeric token - match pdid directly
        if token.isdigit():
            key = f"doc:pdid:{token}"
            if r.exists(key):
                token_matches.add(token)
            token_matches.update(r.smembers(f"idx:slug:{token}"))
        else:
            # Extract embedded numbers like pdid1012
            embedded_nums = re.findall(r'\d+', token)
            for num in embedded_nums:
                key = f"doc:pdid:{num}"
                if r.exists(key):
                    token_matches.add(num)
                token_matches.update(r.smembers(f"idx:slug:{num}"))

        # Scored hits: documents that match multiple words get a higher score
        for pdid in token_matches:
            pdid_scores[pdid] = pdid_scores.get(pdid, 0) + 1

    # Also search parts of ALOBS ids to ensure they get matched
    for alobs in alobs_matches:
        parts = alobs.split('-')
        for part in parts:
            token_matches = r.smembers(f"idx:slug:{part}")
            token_matches.update(r.smembers(f"idx:subject:{part}"))
            for pdid in token_matches:
                pdid_scores[pdid] = pdid_scores.get(pdid, 0) + 1

    if not pdid_scores:
        return []

    # Fetch all matched documents
    pipe = r.pipeline()
    pdids_list = list(pdid_scores.keys())
    for pdid in pdids_list:
        pipe.get(f"doc:pdid:{pdid}")
    results = pipe.execute()

    docs = []
    for i, raw in enumerate(results):
        if raw:
            try:
                doc = json.loads(raw)
                doc['_match_score'] = pdid_scores[pdids_list[i]]
                docs.append(doc)
            except Exception:
                pass

    # Sort by match score (highest first), then by timestamp
    docs.sort(key=lambda d: (d.get('_match_score', 0), d.get('updated_timestamp', '')), reverse=True)
    return docs


def get_document_by_pdid(pdid: int):
    """Fetch a single document by PDID."""
    r = get_redis()
    raw = r.get(f"doc:pdid:{pdid}")
    if raw:
        return json.loads(raw)
    return None


def get_total_document_count():
    """Return total number of tracked documents in Redis."""
    r = get_redis()
    return r.scard("tracking:all_pdids")


def clear_all_tracking_data():
    """Wipe all tracking data from Redis. Used before a full resync."""
    r = get_redis()
    keys = r.keys("doc:pdid:*") + r.keys("idx:*") + ["tracking:all_pdids"]
    if keys:
        r.delete(*keys)
    logger.info("Cleared all tracking data from Redis")