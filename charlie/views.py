import os
import re
import json
import logging
import asyncio
import httpx
import time
import random
import threading
from asyncio import Lock as AsyncLock

from dotenv import load_dotenv
load_dotenv()

from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from asgiref.sync import sync_to_async

from .models import ConversationSession, ConversationMessage
from .timezone_utils import get_philippine_time, get_time_greeting
from .rag_utils import search_documents, get_collection_stats, format_rag_results
from .prompts import get_system_prompt

logger = logging.getLogger(__name__)

OLLAMA_HOST  = os.getenv('OLLAMA_HOST',  '192.168.160.118')
OLLAMA_PORT  = os.getenv('OLLAMA_PORT',  '11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3.1:8b-instruct-q5_K_M')

MAX_MESSAGE_LENGTH      = int(os.getenv('MAX_MESSAGE_LENGTH',      2000))
MAX_HISTORY_MESSAGES    = int(os.getenv('MAX_HISTORY_MESSAGES',    7))
MAX_HISTORY_CHARS       = int(os.getenv('MAX_HISTORY_CHARS',       4000))
MAX_RESPONSE_TOKENS     = int(os.getenv('MAX_RESPONSE_TOKENS',     4096))
SAFE_TOTAL_PROMPT_CHARS = int(os.getenv('SAFE_TOTAL_PROMPT_CHARS', 120000))
OLLAMA_NUM_CTX          = int(os.getenv('OLLAMA_NUM_CTX',          32768))
OLLAMA_TIMEOUT          = int(os.getenv('OLLAMA_TIMEOUT',          60))
MIN_REQUEST_INTERVAL    = float(os.getenv('MIN_REQUEST_INTERVAL',  1.0))
MAX_STORED_MESSAGES     = int(os.getenv('MAX_STORED_MESSAGES',     40))
OLLAMA_TEMPERATURE      = float(os.getenv('OLLAMA_TEMPERATURE',    0.3))

RAG_SEARCH_RESULTS      = int(os.getenv('RAG_SEARCH_RESULTS',     150))

ERR_TIMEOUT    = "This is taking longer than expected. Please try again."
ERR_CONNECTION = "I'm having trouble connecting. Please try again in a moment."
ERR_GENERIC    = "Something went wrong. Please try again."
ERR_RATE_LIMIT = "Please wait a moment before sending another message."
ERR_EMPTY      = "I tried to respond but nothing came out. Could you ask again?"

_processing_sessions = set()
_last_request_time   = {}
_request_lock        = AsyncLock()


_tracking_openers = [
    "I've located the record you requested. Here are the complete tracking details:",
    "Sure thing. Here is the current processing status and information for that document:",
    "Got it! I pulled the most recent tracking data from the system for you:",
    "No problem. Here are the routing details and history tied to that record:",
    "Alright, I found the document in the database. Here is what you need to know:",
    "I'd be happy to help. Here is the latest timeline and status update for that file:",
    "Of course. I have retrieved the necessary tracking information for you right here:",
    "Here you go! These are the complete details currently associated with that document:"
]

_shuffle_state = {
    'list': [],
    'index': 0,
    'lock': threading.Lock()
}

def _get_next_shuffled_opener(count: int) -> str:
    with _shuffle_state['lock']:
        shuffled = _shuffle_state['list']
        idx = _shuffle_state['index']
        
        if not shuffled or idx >= len(shuffled):
            shuffled = _tracking_openers.copy()
            random.shuffle(shuffled)
            _shuffle_state['list'] = shuffled
            idx = 0
            
        selected = shuffled[idx]
        _shuffle_state['index'] = idx + 1
        
    if count > 1:
        return f"I found {count} tracking records related to your search. {selected}\n"
        
    return selected + "\n"


async def _get_tracking_context_redis(message: str):
    try:
        from .redis_tracking import search_documents as redis_search, redis_available
        if not redis_available():
            logger.warning("Redis unavailable — falling back to SQLite tracking")
            return await _db_get_tracking_context_sqlite(message)

        docs = await asyncio.to_thread(redis_search, message)
        if not docs:
            return '', 0

        tokens = set(re.findall(r'\w+', message.lower()))
        
        exact_matches = [d for d in docs if str(d.get('pdid', '')) in tokens or str(d.get('slug', '')) in tokens]
        
        if not exact_matches:
            return '', 0
            
        docs = exact_matches[:3]

        if not docs:
            return '', 0

        doc_title = docs[0].get('title', 'Document') if docs else ''
        lines = [_get_next_shuffled_opener(len(docs))]
        for doc in docs:
            status = 'Completed' if doc.get('document_completed_status') else 'In progress'
            lines.append(f"**{doc.get('title', 'Document')}**")
            lines.append(f"• **PDID:** {doc.get('pdid', '')}")
            lines.append(f"• **Type:** {doc.get('document_type', '')}")
            lines.append(f"• **Office:** {doc.get('office', '')}")
            lines.append(f"• **Agency:** {doc.get('agency', '')}")
            
            subject_raw = doc.get('subject', '') or ''
            subject_cleaned = re.sub(r'\[.*?\]', '', subject_raw).strip()
            bracket_matches = re.findall(r'\[(.*?)\]', subject_raw)
            
            sub_lines = [line.strip() for line in subject_cleaned.split('\n') if line.strip()]
            if sub_lines:
                lines.append(f"• **Subject:** {sub_lines[0]}")
                for extra_line in sub_lines[1:]:
                    if ':' in extra_line:
                        k, v = extra_line.split(':', 1)
                        lines.append(f"• **{k.strip()}:** {v.strip()}")
                    else:
                        lines.append(f"• {extra_line}")
            else:
                lines.append(f"• **Subject:** None")
                
            for bracket in bracket_matches:
                k_v = bracket.split(':', 1)
                lines.append(f"• **{k_v[0].strip()}:** {k_v[1].strip() if len(k_v) > 1 else ''}")
            
            lines.append(f"• **Status:** {status}")
            if doc.get('current_location') and doc['current_location'] != 'Unknown':
                lines.append(f"• **Current location:** {doc['current_location']}")
            if doc.get('last_action'):
                lines.append(f"• **Last action:** {doc['last_action']}")
            if doc.get('overall_days_onprocess'):
                lines.append(f"• **Days on process:** {doc.get('overall_days_onprocess')}")
            if doc.get('created_at'):
                lines.append(f"• **Filed:** {doc['created_at']}")
            if doc.get('created_by'):
                lines.append(f"• **Filed by:** {doc['created_by']}")
            if doc.get('route_count'):
                lines.append(f"• **Routing stops:** {doc['route_count']}")
            lines.append("")

        logger.info(f"Tracking: Redis hit — {len(docs)} record(s) matched")
        return '\n'.join(lines).strip(), len(docs)

    except Exception as e:
        logger.error(f"Redis tracking error: {e} — falling back to SQLite")
        return await _db_get_tracking_context_sqlite(message)


@sync_to_async
def _db_get_tracking_context_sqlite(message: str):
    from .models import TrackedDocument
    from django.db.models import Q

    numbers_in_message = set(re.findall(r'\d+', message))
    if not numbers_in_message:
        return '', 0

    q = Q()
    for num in numbers_in_message:
        q |= Q(pdid=int(num)) | Q(slug__icontains=num)

    if not q.children:
        return '', 0

    docs = list(
        TrackedDocument.objects
        .filter(q)
        .distinct()
        .order_by('-updated_timestamp')
    )

    if not docs:
        return '', 0

    lines = [_get_next_shuffled_opener(len(docs))]
    for doc in docs:
        status = 'Completed' if doc.document_completed_status else 'In progress'
        location = doc.get_current_location()
        last_action = doc.get_last_action()
        try:
            route_count = len(doc.details.get('routes', []))
        except Exception:
            route_count = 0

        lines.append(f"**{doc.title}**")
        lines.append(f"• **PDID:** {doc.pdid}")
        lines.append(f"• **Type:** {doc.document_type}")
        lines.append(f"• **Office:** {doc.office}")
        lines.append(f"• **Agency:** {doc.agency}")
        
        subject_raw = doc.subject or ''
        subject_cleaned = re.sub(r'\[.*?\]', '', subject_raw).strip()
        bracket_matches = re.findall(r'\[(.*?)\]', subject_raw)
        
        sub_lines = [line.strip() for line in subject_cleaned.split('\n') if line.strip()]
        if sub_lines:
            lines.append(f"• **Subject:** {sub_lines[0]}")
            for extra_line in sub_lines[1:]:
                if ':' in extra_line:
                    k, v = extra_line.split(':', 1)
                    lines.append(f"• **{k.strip()}:** {v.strip()}")
                else:
                    lines.append(f"• {extra_line}")
        else:
            lines.append(f"• **Subject:** None")
            
        for bracket in bracket_matches:
            k_v = bracket.split(':', 1)
            lines.append(f"• **{k_v[0].strip()}:** {k_v[1].strip() if len(k_v) > 1 else ''}")
            
        lines.append(f"• **Status:** {status}")
        lines.append(f"• **Current location:** {location}")
        if last_action:
            lines.append(f"• **Last action:** {last_action}")
        if doc.overall_days_onprocess:
            lines.append(f"• **Days on process:** {doc.overall_days_onprocess}")
        if doc.created_at:
            lines.append(f"• **Filed:** {doc.created_at}")
        if doc.created_by:
            lines.append(f"• **Filed by:** {doc.created_by}")
        if route_count:
            lines.append(f"• **Routing stops:** {route_count}")
        lines.append("")

    logger.warning(f"Tracking: SQLite fallback — {len(docs)} record(s) matched")
    return '\n'.join(lines).strip(), len(docs)


def _is_bullet_line(line):
    return bool(re.match(r'^\s*•\s+|^\s*\d+\.\s+', line))


def _clean_response(text):
    lines = text.split('\n')

    pass1 = []
    for line in lines:
        sub = re.match(r'^(\s+)([*+\-•])\s+(.+)$', line)
        if sub:
            pass1.append(f'    • {sub.group(3)}')
        else:
            line = re.sub(r'^\*(?!\*)\s+', '• ', line)
            line = re.sub(r'^\+\s+',       '• ', line)
            line = re.sub(r'^-(?!-)\s+',   '• ', line)
            pass1.append(line)

    pass2 = []
    i = 0
    while i < len(pass1):
        pass2.append(pass1[i])
        if (
            i + 2 < len(pass1)
            and _is_bullet_line(pass1[i])
            and pass1[i + 1].strip() == ''
            and _is_bullet_line(pass1[i + 2])
        ):
            i += 2
        else:
            i += 1

    return '\n'.join(pass2)


def _build_ollama_payload(messages):
    return {
        'model':    OLLAMA_MODEL,
        'messages': messages,
        'options': {
            'temperature':    OLLAMA_TEMPERATURE,
            'num_predict':    MAX_RESPONSE_TOKENS,
            'num_ctx':        OLLAMA_NUM_CTX,
            'top_p':          0.85,
            'top_k':          20,
            'repeat_penalty': 1.1,
            'num_thread':     16,
            'stop':           ['</s>', 'User:'],
        },
    }


def _validate_message(data):
    user_message = data.get('message', '').strip()
    if not user_message:
        return None, JsonResponse({'error': 'No message provided'}, status=400)
    if len(user_message) > MAX_MESSAGE_LENGTH:
        return None, JsonResponse(
            {'error': f'Message too long. Maximum {MAX_MESSAGE_LENGTH} characters.'}, status=400
        )
    return user_message, None


def build_conversation_history(db_messages):
    history     = []
    total_chars = 0

    for msg in db_messages[:MAX_HISTORY_MESSAGES]:
        content = msg.content
        if total_chars + len(content) <= MAX_HISTORY_CHARS:
            history.append({'role': msg.role, 'content': content})
            total_chars += len(content)
        else:
            space_left = MAX_HISTORY_CHARS - total_chars
            if space_left > 200:
                history.append({'role': msg.role, 'content': content[:space_left] + '...'})
            break

    history.reverse()
    return history


async def _check_rate_limit(session_key):
    async with _request_lock:
        now = time.time()
        if now - _last_request_time.get(session_key, 0) < MIN_REQUEST_INTERVAL:
            return False
        _last_request_time[session_key] = now
        return True


@sync_to_async
def _db_get_or_create_session(session_key):
    session, _ = ConversationSession.objects.get_or_create(session_key=session_key)
    return session


@sync_to_async
def _db_get_messages(session):
    return list(session.messages.all().order_by('-timestamp')[:MAX_HISTORY_MESSAGES])


@sync_to_async
def _db_save_user_message(session, user_message):
    try:
        session.refresh_from_db()
    except ConversationSession.DoesNotExist:
        return None
    user_msg = ConversationMessage.objects.create(
        session=session, role='user', content=user_message[:MAX_MESSAGE_LENGTH]
    )
    session.message_count = session.messages.count()
    session.save()
    return user_msg.id


@sync_to_async
def _db_save_message_exchange(session, user_message, bot_response, categories):
    try:
        session.refresh_from_db()
    except ConversationSession.DoesNotExist:
        return None, None

    user_msg = ConversationMessage.objects.create(
        session=session, role='user', content=user_message[:MAX_MESSAGE_LENGTH]
    )
    bot_msg = ConversationMessage.objects.create(
        session=session,
        role='assistant',
        content=bot_response[:16000],
        categories_searched=','.join(categories) if categories else '',
        chunks_retrieved=len(categories) if categories else 0,
    )
    session.message_count = session.messages.count()
    session.save()

    if session.message_count > MAX_STORED_MESSAGES:
        for msg in session.messages.all().order_by('-timestamp')[MAX_STORED_MESSAGES:]:
            msg.delete()

    return user_msg.id, bot_msg.id


@sync_to_async
def _db_save_bot_message_only(session, bot_response, categories):
    try:
        session.refresh_from_db()
    except ConversationSession.DoesNotExist:
        return None

    bot_msg = ConversationMessage.objects.create(
        session=session,
        role='assistant',
        content=bot_response[:16000],
        categories_searched=','.join(categories) if categories else '',
        chunks_retrieved=len(categories) if categories else 0,
    )
    session.message_count = session.messages.count()
    session.save()

    if session.message_count > MAX_STORED_MESSAGES:
        for msg in session.messages.all().order_by('-timestamp')[MAX_STORED_MESSAGES:]:
            msg.delete()

    return bot_msg.id


@sync_to_async
def _db_get_history_for_load(session):
    msgs = session.messages.all().order_by('-timestamp')[:MAX_STORED_MESSAGES]
    return [
        {
            'id':        msg.id,
            'role':      msg.role,
            'content':   msg.content,
            'timestamp': msg.timestamp.isoformat(),
        }
        for msg in msgs
    ]


@sync_to_async
def _db_delete_session(session):
    session.delete()


@sync_to_async
def _db_edit_message(session_key, message_id, new_content):
    try:
        session = ConversationSession.objects.get(session_key=session_key)
        message = ConversationMessage.objects.get(
            id=message_id, session=session, role='user'
        )
        message.content = new_content
        message.save()

        ConversationMessage.objects.filter(
            session=session,
            timestamp__gt=message.timestamp
        ).delete()

        session.message_count = session.messages.count()
        session.save()
        return True
    except Exception as e:
        logger.error(f"DB edit message error: {e}")
        return False


@sync_to_async
def _db_get_messages_for_regen(session):
    all_msgs = list(
        session.messages.all().order_by('-timestamp')[:MAX_HISTORY_MESSAGES + 2]
    )
    history_msgs   = []
    last_user_text = None

    for msg in all_msgs:
        if msg.role == 'user' and last_user_text is None:
            last_user_text = msg.content
        else:
            history_msgs.append(msg)

    return history_msgs[:MAX_HISTORY_MESSAGES], last_user_text


async def get_or_create_session(request):
    if not request.session.session_key:
        await sync_to_async(request.session.create)()
    return await _db_get_or_create_session(request.session.session_key)


async def get_relevant_context(user_message):
    stats = await asyncio.to_thread(get_collection_stats)
    if not stats or stats['total_chunks'] == 0:
        return '', [], 0

    try:
        results = await asyncio.to_thread(search_documents, user_message, RAG_SEARCH_RESULTS)
        if not results:
            return '', [], 0
        categories  = list(set(r['category'] for r in results[:10]))
        context, item_count = await asyncio.to_thread(
            format_rag_results, results, None, user_message
        )
        return context, categories, item_count
    except Exception as e:
        logger.error(f"RAG error: {e}")
        return '', [], 0


async def _prepare_chat_context(request, user_message):
    session = await get_or_create_session(request)
    _processing_sessions.add(session.session_key)

    db_messages = await _db_get_messages(session)
    history     = build_conversation_history(db_messages)

    ph_time      = get_philippine_time()
    time_context = (
        f"{get_time_greeting()}! Today is "
        f"{ph_time.strftime('%A, %B %d, %Y at %I:%M %p')} (Philippine Time)"
    )

    (tracking_context, tracking_hits), (rag_context, categories, item_count) = await asyncio.gather(
        _get_tracking_context_redis(user_message),
        get_relevant_context(user_message),
    )

    if tracking_hits > 0:
        logger.info(f"Tracking: {tracking_hits} record(s) matched — Bypassing LLM")
        return {
            'session': session,
            'tracking_instant_response': tracking_context,
            'categories': ['tracking']
        }

    system_prompt = get_system_prompt(
        relevant_context=rag_context,
        tracking_context='',
        time_context=time_context,
        is_first_message=session.message_count == 0,
        item_count=item_count,
    )

    def _total_chars(msgs):
        return sum(len(str(m.get('content', ''))) for m in msgs)

    messages    = [system_prompt] + history + [{'role': 'user', 'content': user_message}]
    total_chars = _total_chars(messages)

    if total_chars > SAFE_TOTAL_PROMPT_CHARS:
        trimmed = list(history)
        while trimmed and _total_chars(
            [system_prompt] + trimmed + [{'role': 'user', 'content': user_message}]
        ) > SAFE_TOTAL_PROMPT_CHARS:
            trimmed.pop(0)

        messages    = [system_prompt] + trimmed + [{'role': 'user', 'content': user_message}]
        total_chars = _total_chars(messages)

        if trimmed:
            logger.info(
                f"Prompt trimmed: kept {len(trimmed)} of {len(history)} history turns "
                f"({total_chars} chars)"
            )
        else:
            logger.warning(
                f"Prompt large even without history ({total_chars} chars) "
                f"— proceeding without history"
            )

    logger.info(f"Final prompt size: {total_chars} chars (~{total_chars // 4} tokens)")
    return {'session': session, 'messages': messages, 'categories': categories}


async def call_ollama(messages):
    try:
        payload           = _build_ollama_payload(messages)
        payload['stream'] = False
        async with httpx.AsyncClient(timeout=httpx.Timeout(OLLAMA_TIMEOUT)) as client:
            response = await client.post(
                f'http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/chat',
                json=payload,
            )
            response.raise_for_status()
            raw = response.json().get('message', {}).get('content', '').strip()
            return _clean_response(raw) or ERR_EMPTY
    except httpx.TimeoutException:
        return ERR_TIMEOUT
    except httpx.RequestError as e:
        logger.error(f"Ollama request error: {e}")
        return ERR_CONNECTION
    except Exception as e:
        logger.error(f"Ollama error: {e}", exc_info=True)
        return ERR_GENERIC


def index(request):
    if not request.session.session_key:
        request.session.create()
    return render(request, 'conversation.html')


@csrf_exempt
@require_http_methods(["POST"])
async def chat_stream_api(request):
    session = None
    try:
        session_key = request.session.session_key or 'unknown'
        if not await _check_rate_limit(session_key):
            return JsonResponse({'error': ERR_RATE_LIMIT}, status=429)

        data              = json.loads(request.body)
        user_message, err = _validate_message(data)
        if err:
            return err

        ctx        = await _prepare_chat_context(request, user_message)
        session    = ctx['session']
        categories = ctx.get('categories', [])
        messages   = ctx.get('messages', [])

        async def event_stream():
            full_response = []
            try:
                user_msg_id = await _db_save_user_message(session, user_message)
                if user_msg_id:
                    yield f"data: {json.dumps({'user_message_id': user_msg_id})}\n\n"

                if ctx.get('tracking_instant_response'):
                    complete_response = ctx['tracking_instant_response']
                    chunks = complete_response.split('\n')
                    for chunk in chunks:
                        yield f"data: {json.dumps({'token': chunk + '\n'})}\n\n"
                        await asyncio.sleep(0.02)
                    
                    bot_msg_id = await _db_save_bot_message_only(
                        session, complete_response, categories
                    )
                    yield f"data: {json.dumps({'done': True, 'bot_message_id': bot_msg_id})}\n\n"
                    return

                payload           = _build_ollama_payload(messages)
                payload['stream'] = True
                url = f'http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/chat'

                async with httpx.AsyncClient(timeout=httpx.Timeout(OLLAMA_TIMEOUT)) as client:
                    async with client.stream('POST', url, json=payload) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line:
                                continue
                            try:
                                chunk = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            token = chunk.get('message', {}).get('content', '')
                            if token:
                                full_response.append(token)
                                yield f"data: {json.dumps({'token': token})}\n\n"
                            if chunk.get('done'):
                                break

                complete_response = (
                    _clean_response(''.join(full_response).strip()) or ERR_EMPTY
                )
                bot_msg_id = await _db_save_bot_message_only(
                    session, complete_response, categories
                )
                yield f"data: {json.dumps({'done': True, 'bot_message_id': bot_msg_id})}\n\n"

            except httpx.TimeoutException:
                yield f"data: {json.dumps({'error': ERR_TIMEOUT})}\n\n"
            except httpx.RequestError as e:
                logger.error(f"Ollama stream error: {e}")
                yield f"data: {json.dumps({'error': ERR_CONNECTION})}\n\n"
            except Exception as e:
                logger.error(f"Ollama stream error: {e}", exc_info=True)
                yield f"data: {json.dumps({'error': ERR_GENERIC})}\n\n"
            finally:
                if session:
                    _processing_sessions.discard(session.session_key)

        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control']     = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    except Exception as e:
        logger.error(f"Stream chat setup error: {e}", exc_info=True)
        if session:
            _processing_sessions.discard(session.session_key)
        return JsonResponse({'error': ERR_GENERIC}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
async def chat_api(request):

    session = None
    try:
        session_key = request.session.session_key or 'unknown'
        if not await _check_rate_limit(session_key):
            return JsonResponse({'error': ERR_RATE_LIMIT}, status=429)

        data              = json.loads(request.body)
        user_message, err = _validate_message(data)
        if err:
            return err

        ctx        = await _prepare_chat_context(request, user_message)
        session    = ctx['session']
        categories = ctx.get('categories', [])

        if ctx.get('tracking_instant_response'):
            bot_response = ctx['tracking_instant_response']
        else:
            messages     = ctx['messages']
            bot_response = await call_ollama(messages)

        user_msg_id, _ = await _db_save_message_exchange(session, user_message, bot_response, categories)
        return JsonResponse({'response': bot_response, 'status': 'success', 'user_message_id': user_msg_id})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return JsonResponse({'error': ERR_GENERIC}, status=500)
    finally:
        if session:
            _processing_sessions.discard(session.session_key)


@csrf_exempt
@require_http_methods(["POST"])
async def load_history_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        session  = await get_or_create_session(request)
        messages = await _db_get_history_for_load(session)
        messages.reverse()
        return JsonResponse({'messages': messages, 'status': 'success'})
    except Exception as e:
        logger.error(f"Load error: {e}")
        return JsonResponse({'error': 'Failed to load history'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
async def delete_conversation_api(request):
    try:
        session = await get_or_create_session(request)
        if session.session_key in _processing_sessions:
            return JsonResponse(
                {'error': 'Please wait, message is still processing'}, status=400
            )
        await _db_delete_session(session)
        await sync_to_async(request.session.flush)()
        await sync_to_async(request.session.create)()
        return JsonResponse({'status': 'success', 'message': 'Conversation deleted'})
    except Exception as e:
        logger.error(f"Delete error: {e}")
        return JsonResponse({'error': 'Failed to delete'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
async def edit_message_api(request):
    try:
        data        = json.loads(request.body)
        message_id  = data.get('message_id')
        new_content = data.get('new_content', '').strip()

        if not message_id or not new_content:
            return JsonResponse({'error': 'Invalid data'}, status=400)

        if not request.session.session_key:
            return JsonResponse({'error': 'No session'}, status=400)

        if len(new_content) > MAX_MESSAGE_LENGTH:
            return JsonResponse(
                {'error': f'Message too long. Maximum {MAX_MESSAGE_LENGTH} characters.'}, status=400
            )

        success = await _db_edit_message(
            request.session.session_key, message_id, new_content
        )

        if success:
            return JsonResponse({'status': 'success'})
        else:
            return JsonResponse({'error': 'Message not found'}, status=404)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    except Exception as e:
        logger.error(f"Edit message error: {e}", exc_info=True)
        return JsonResponse({'error': ERR_GENERIC}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
async def regenerate_response_api(request):
    session = None
    try:
        session_key = request.session.session_key or 'unknown'
        if not await _check_rate_limit(session_key):
            return JsonResponse({'error': ERR_RATE_LIMIT}, status=429)

        session = await get_or_create_session(request)
        _processing_sessions.add(session.session_key)

        history_msgs, user_message = await _db_get_messages_for_regen(session)

        if not user_message:
            return JsonResponse({'error': 'No message to regenerate'}, status=400)

        history = build_conversation_history(history_msgs)

        ph_time      = get_philippine_time()
        time_context = (
            f"{get_time_greeting()}! Today is "
            f"{ph_time.strftime('%A, %B %d, %Y at %I:%M %p')} (Philippine Time)"
        )

        (tracking_context, tracking_hits), (rag_context, categories, item_count) = await asyncio.gather(
            _get_tracking_context_redis(user_message),
            get_relevant_context(user_message),
        )


        system_prompt = get_system_prompt(
            relevant_context=rag_context,
            tracking_context='',
            time_context=time_context,
            is_first_message=session.message_count <= 1,
            item_count=item_count,
        )

        def _total_chars(msgs):
            return sum(len(str(m.get('content', ''))) for m in msgs)

        messages    = [system_prompt] + history + [{'role': 'user', 'content': user_message}]
        total_chars = _total_chars(messages)

        if total_chars > SAFE_TOTAL_PROMPT_CHARS:
            trimmed = list(history)
            while trimmed and _total_chars(
                [system_prompt] + trimmed + [{'role': 'user', 'content': user_message}]
            ) > SAFE_TOTAL_PROMPT_CHARS:
                trimmed.pop(0)
            messages = [system_prompt] + trimmed + [{'role': 'user', 'content': user_message}]

        async def event_stream():
            full_response = []
            try:
                if tracking_hits > 0:
                    chunks = tracking_context.split('\n')
                    for chunk in chunks:
                        yield f"data: {json.dumps({'token': chunk + '\n'})}\n\n"
                        await asyncio.sleep(0.01)
                    
                    bot_msg_id = await _db_save_bot_message_only(
                        session, tracking_context, ['tracking']
                    )
                    yield f"data: {json.dumps({'done': True, 'bot_message_id': bot_msg_id})}\n\n"
                    return

                payload           = _build_ollama_payload(messages)
                payload['stream'] = True
                url = f'http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/chat'

                async with httpx.AsyncClient(timeout=httpx.Timeout(OLLAMA_TIMEOUT)) as client:
                    async with client.stream('POST', url, json=payload) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line:
                                continue
                            try:
                                chunk = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            token = chunk.get('message', {}).get('content', '')
                            if token:
                                full_response.append(token)
                                yield f"data: {json.dumps({'token': token})}\n\n"
                            if chunk.get('done'):
                                break

                complete_response = (
                    _clean_response(''.join(full_response).strip()) or ERR_EMPTY
                )
                bot_msg_id = await _db_save_bot_message_only(session, complete_response, categories)
                yield f"data: {json.dumps({'done': True, 'bot_message_id': bot_msg_id})}\n\n"

            except httpx.TimeoutException:
                yield f"data: {json.dumps({'error': ERR_TIMEOUT})}\n\n"
            except httpx.RequestError as e:
                logger.error(f"Regen stream error: {e}")
                yield f"data: {json.dumps({'error': ERR_CONNECTION})}\n\n"
            except Exception as e:
                logger.error(f"Regen stream error: {e}", exc_info=True)
                yield f"data: {json.dumps({'error': ERR_GENERIC})}\n\n"
            finally:
                if session:
                    _processing_sessions.discard(session.session_key)

        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control']     = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    except Exception as e:
        logger.error(f"Regenerate error: {e}", exc_info=True)
        if session:
            _processing_sessions.discard(session.session_key)
        return JsonResponse({'error': ERR_GENERIC}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
async def save_partial_bot_message_api(request):
    try:
        data         = json.loads(request.body)
        partial_text = _clean_response(data.get('partial_text', '').strip())

        if not partial_text:
            return JsonResponse({'error': 'No text provided'}, status=400)

        session    = await get_or_create_session(request)
        bot_msg_id = await _db_save_bot_message_only(session, partial_text, [])

        return JsonResponse({'status': 'success', 'message_id': bot_msg_id})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    except Exception as e:
        logger.error(f"Save partial error: {e}", exc_info=True)
        return JsonResponse({'error': ERR_GENERIC}, status=500)