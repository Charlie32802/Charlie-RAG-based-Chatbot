"""
sync_tracking.py
----------------
Loads tracked documents into Redis.

Currently loads from local SQLite (charlie_trackeddocument table).
When production API URL becomes available, swap _fetch_from_sqlite()
with _fetch_from_api() — everything else stays the same.

Usage:
  python sync_tracking.py            # full sync
  python sync_tracking.py --check    # just check Redis connection and count
"""

import os
import sys
import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

# Make sure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _setup_django():
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()


def _get_redis_functions():
    from charlie.redis_tracking import (
        store_document,
        clear_all_tracking_data,
        get_total_document_count,
        redis_available,
    )
    return store_document, clear_all_tracking_data, get_total_document_count, redis_available


def _fetch_from_sqlite():
    """
    Fetch all tracked documents from local SQLite.
    Returns list of dicts ready for Redis storage.
    """
    from charlie.models import TrackedDocument

    docs = []
    for doc in TrackedDocument.objects.all():
        try:
            details = doc.details if isinstance(doc.details, dict) else {}
            routes = details.get('routes', [])
            route_count = len(routes)

            # Determine current location from last route
            current_location = 'Unknown'
            last_action = ''
            if routes:
                last_route = routes[-1]
                current_location = last_route.get('office', 'Unknown')
                employees = last_route.get('staff_operation', {}).get('employee', [])
                if employees:
                    last_employee = employees[-1]
                    processes = last_employee.get('processing', {}).get('process', [])
                    if processes:
                        last_action = processes[-1].get('action', '')

            docs.append({
                'pdid':                     doc.pdid,
                'slug':                     doc.slug,
                'title':                    doc.title,
                'agency':                   doc.agency,
                'office':                   doc.office,
                'subject':                  doc.subject,
                'document_type':            doc.document_type,
                'created_at':               doc.created_at,
                'created_by':               doc.created_by,
                'overall_days_onprocess':   doc.overall_days_onprocess,
                'document_completed_status': doc.document_completed_status,
                'current_location':         current_location,
                'last_action':              last_action,
                'route_count':              route_count,
                'updated_timestamp':        str(doc.updated_timestamp) if doc.updated_timestamp else '',
            })
        except Exception as e:
            logger.warning(f"Skipped PDID {doc.pdid}: {e}")

    return docs


def _fetch_from_api(api_url: str, api_token: str = None):
    """
    Fetch all tracked documents from production API.
    Swap this in when the API URL is known.

    TODO: implement when API URL is available.
    Expected response format: list of document objects with same fields.
    """
    import httpx
    headers = {}
    if api_token:
        headers['Authorization'] = f"Bearer {api_token}"

    docs = []
    page = 1
    while True:
        response = httpx.get(f"{api_url}?page={page}", headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        items = data.get('results', data) if isinstance(data, dict) else data
        if not items:
            break

        for item in items:
            routes = item.get('details', {}).get('routes', [])
            route_count = len(routes)
            current_location = 'Unknown'
            last_action = ''
            if routes:
                last_route = routes[-1]
                current_location = last_route.get('office', 'Unknown')
                employees = last_route.get('staff_operation', {}).get('employee', [])
                if employees:
                    processes = employees[-1].get('processing', {}).get('process', [])
                    if processes:
                        last_action = processes[-1].get('action', '')

            docs.append({
                'pdid':                     item.get('pdid') or item.get('id'),
                'slug':                     item.get('slug', ''),
                'title':                    item.get('title', ''),
                'agency':                   item.get('agency', ''),
                'office':                   item.get('office', ''),
                'subject':                  item.get('subject', ''),
                'document_type':            item.get('document_type', ''),
                'created_at':               item.get('created_at', ''),
                'created_by':               item.get('created_by', ''),
                'overall_days_onprocess':   item.get('overall_days_onprocess', ''),
                'document_completed_status': item.get('document_completed_status', False),
                'current_location':         current_location,
                'last_action':              last_action,
                'route_count':              route_count,
                'updated_timestamp':        item.get('updated_timestamp', ''),
            })

        # If no pagination, break after first page
        if not data.get('next'):
            break
        page += 1

    return docs


def run_sync(use_api=False, api_url=None, api_token=None):
    _setup_django()
    store_document, clear_all_tracking_data, get_total_document_count, redis_available = _get_redis_functions()
    logger.info("=" * 50)
    logger.info("Charlie Tracking Sync — Starting")
    logger.info("=" * 50)

    # Check Redis connection
    if not redis_available():
        logger.error("Cannot connect to Redis. Is it running on 192.168.160.118:6379?")
        logger.error("Run on Ubuntu: sudo systemctl start redis-server")
        sys.exit(1)

    logger.info("Redis connection OK")

    # Fetch documents
    if use_api and api_url:
        logger.info(f"Fetching from API: {api_url}")
        docs = _fetch_from_api(api_url, api_token)
    else:
        logger.info("Fetching from local SQLite...")
        docs = _fetch_from_sqlite()

    if not docs:
        logger.warning("No documents fetched. Aborting sync.")
        return

    logger.info(f"Fetched {len(docs)} documents")

    # Clear existing data and reload
    logger.info("Clearing existing Redis tracking data...")
    clear_all_tracking_data()

    # Store all documents
    success = 0
    for doc in docs:
        try:
            store_document(doc)
            success += 1
        except Exception as e:
            logger.warning(f"Failed to store PDID {doc.get('pdid')}: {e}")

    total = get_total_document_count()
    logger.info("=" * 50)
    logger.info(f"Sync complete: {success}/{len(docs)} stored — {total} total in Redis")
    logger.info("=" * 50)


def _fetch_from_sql_file(sql_path: str):
    """
    Parse documents directly from a .sql dump file.
    Use this if you want to sync without Django being fully set up.
    """
    import sqlite3, tempfile, os

    # Load SQL into a temporary in-memory SQLite DB
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql = f.read()

    tmp = tempfile.mktemp(suffix='.sqlite3')
    try:
        conn = sqlite3.connect(tmp)
        conn.executescript(sql)
        conn.commit()

        cursor = conn.execute("""
            SELECT pdid, slug, title, agency, office, subject,
                   document_type, created_at, created_by,
                   overall_days_onprocess, document_completed_status,
                   details, updated_timestamp
            FROM charlie_trackeddocument
        """)

        docs = []
        for row in cursor.fetchall():
            details = {}
            try:
                details = json.loads(row[11]) if row[11] else {}
            except Exception:
                pass

            routes = details.get('routes', [])
            current_location = 'Unknown'
            last_action = ''
            if routes:
                last_route = routes[-1]
                current_location = last_route.get('office', 'Unknown')
                employees = last_route.get('staff_operation', {}).get('employee', [])
                if employees:
                    processes = employees[-1].get('processing', {}).get('process', [])
                    if processes:
                        last_action = processes[-1].get('action', '')

            docs.append({
                'pdid':                      row[0],
                'slug':                      row[1],
                'title':                     row[2],
                'agency':                    row[3],
                'office':                    row[4],
                'subject':                   row[5],
                'document_type':             row[6],
                'created_at':                row[7],
                'created_by':                row[8],
                'overall_days_onprocess':    row[9],
                'document_completed_status': bool(row[10]),
                'current_location':          current_location,
                'last_action':               last_action,
                'route_count':               len(routes),
                'updated_timestamp':         row[12] or '',
            })

        conn.close()
        return docs
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


if __name__ == '__main__':
    if '--check' in sys.argv:
        _, _, get_total_document_count, redis_available = _get_redis_functions()
        if redis_available():
            count = get_total_document_count()
            print(f"Redis OK — {count} documents in cache")
        else:
            print("Redis UNAVAILABLE — check 192.168.160.118:6379")

    elif '--sql' in sys.argv:
        # Load directly from SQL dump file
        # Usage: python sync_tracking.py --sql path/to/charlie_trackeddocument.sql
        idx = sys.argv.index('--sql')
        sql_path = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        if not sql_path:
            print("Usage: python sync_tracking.py --sql path/to/charlie_trackeddocument.sql")
            sys.exit(1)
        store_document, clear_all_tracking_data, get_total_document_count, redis_available = _get_redis_functions()
        if not redis_available():
            print("Redis UNAVAILABLE — check 192.168.168.118:6379")
            sys.exit(1)
        logger.info(f"Loading from SQL file: {sql_path}")
        docs = _fetch_from_sql_file(sql_path)
        logger.info(f"Fetched {len(docs)} documents from SQL file")
        clear_all_tracking_data()
        success = 0
        for doc in docs:
            try:
                store_document(doc)
                success += 1
            except Exception as e:
                logger.warning(f"Failed to store PDID {doc.get('pdid')}: {e}")
        print(f"Sync complete: {success}/{len(docs)} stored in Redis")

    else:
        run_sync()