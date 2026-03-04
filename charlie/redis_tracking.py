"""
redis_tracking.py
-----------------
All document tracking read/write operations via Redis.
Redis runs on the Ubuntu server at 192.168.168.108:6379.

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

REDIS_HOST = os.getenv('REDIS_HOST', '192.168.168.108')
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
    Returns list of document dicts ordered by updated_timestamp desc.
    """
    r = get_redis()
    tokens = re.findall(r'\w+', message.lower())

    matched_pdids = set()

    for token in tokens:
        # Pure numeric token - match pdid directly
        if token.isdigit():
            key = f"doc:pdid:{token}"
            if r.exists(key):
                matched_pdids.add(token)
            # Also check slug index
            slug_matches = r.smembers(f"idx:slug:{token}")
            matched_pdids.update(slug_matches)
        else:
            # Extract embedded numbers like pdid1012
            embedded_nums = re.findall(r'\d+', token)
            for num in embedded_nums:
                key = f"doc:pdid:{num}"
                if r.exists(key):
                    matched_pdids.add(num)
                slug_matches = r.smembers(f"idx:slug:{num}")
                matched_pdids.update(slug_matches)

        # Text token - search all text indexes
        if len(token) >= 4:
            for prefix in ['idx:title:', 'idx:subject:', 'idx:office:',
                           'idx:agency:', 'idx:doctype:', 'idx:createdby:']:
                matches = r.smembers(f"{prefix}{token}")
                matched_pdids.update(matches)

    if not matched_pdids:
        return []

    # Fetch all matched documents
    pipe = r.pipeline()
    for pdid in matched_pdids:
        pipe.get(f"doc:pdid:{pdid}")
    results = pipe.execute()

    docs = []
    for raw in results:
        if raw:
            try:
                docs.append(json.loads(raw))
            except Exception:
                pass

    # Sort by updated_timestamp descending
    docs.sort(key=lambda d: d.get('updated_timestamp', ''), reverse=True)
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