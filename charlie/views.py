import os
import re
import json
import logging
import asyncio
import httpx
import time
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

OLLAMA_HOST  = os.getenv('OLLAMA_HOST',  '192.168.168.108')
OLLAMA_PORT  = os.getenv('OLLAMA_PORT',  '11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3.1:8b-instruct-q6_K')

MAX_MESSAGE_LENGTH      = int(os.getenv('MAX_MESSAGE_LENGTH',      2000))
MAX_HISTORY_MESSAGES    = int(os.getenv('MAX_HISTORY_MESSAGES',    7))
MAX_HISTORY_CHARS       = int(os.getenv('MAX_HISTORY_CHARS',       4000))
MAX_RESPONSE_TOKENS     = int(os.getenv('MAX_RESPONSE_TOKENS',     4096))
SAFE_TOTAL_PROMPT_CHARS = int(os.getenv('SAFE_TOTAL_PROMPT_CHARS', 26000))
OLLAMA_NUM_CTX          = int(os.getenv('OLLAMA_NUM_CTX',          14336))
OLLAMA_TIMEOUT          = int(os.getenv('OLLAMA_TIMEOUT',          60))
MIN_REQUEST_INTERVAL    = float(os.getenv('MIN_REQUEST_INTERVAL',  1.0))
MAX_STORED_MESSAGES     = int(os.getenv('MAX_STORED_MESSAGES',     40))
OLLAMA_TEMPERATURE      = float(os.getenv('OLLAMA_TEMPERATURE',    0.3))

RAG_SEARCH_RESULTS      = int(os.getenv('RAG_SEARCH_RESULTS',     50))

ERR_TIMEOUT    = "This is taking longer than expected. Please try again."
ERR_CONNECTION = "I'm having trouble connecting. Please try again in a moment."
ERR_GENERIC    = "Something went wrong. Please try again."
ERR_RATE_LIMIT = "Please wait a moment before sending another message."
ERR_EMPTY      = "I tried to respond but nothing came out. Could you ask again?"

_processing_sessions = set()
_last_request_time   = {}
_request_lock        = AsyncLock()


@sync_to_async
def _db_get_tracking_context(message: str):
    from .models import TrackedDocument
    from django.db.models import Q

    tokens = re.findall(r'\w+', message.lower())

    q = Q()

    for token in tokens:
        if token.isdigit() and len(token) >= 1:
            q |= Q(pdid=int(token)) | Q(slug__icontains=token)
        else:
            embedded_nums = re.findall(r'\d+', token)
            for num in embedded_nums:
                q |= Q(pdid=int(num)) | Q(slug__icontains=num)

    for token in tokens:
        if len(token) >= 4:
            q |= (
                Q(title__icontains=token)
                | Q(subject__icontains=token)
                | Q(office__icontains=token)
                | Q(agency__icontains=token)
                | Q(document_type__icontains=token)
                | Q(created_by__icontains=token)
            )

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

    lines = []
    for doc in docs:
        status = 'Completed' if doc.document_completed_status else 'In progress'
        location = doc.get_current_location()
        last_action = doc.get_last_action()
        try:
            route_count = len(doc.details.get('routes', []))
        except Exception:
            route_count = 0

        lines.append(f"PDID: {doc.pdid}")
        lines.append(f"Title: {doc.title}")
        lines.append(f"Type: {doc.document_type}")
        lines.append(f"Office: {doc.office}")
        lines.append(f"Agency: {doc.agency}")
        lines.append(f"Subject: {doc.subject}")
        lines.append(f"Status: {status}")
        lines.append(f"Current location: {location}")
        if last_action:
            lines.append(f"Last action: {last_action}")
        if doc.overall_days_onprocess:
            lines.append(f"Days on process: {doc.overall_days_onprocess}")
        if doc.created_at:
            lines.append(f"Filed: {doc.created_at}")
        if doc.created_by:
            lines.append(f"Filed by: {doc.created_by}")
        if route_count:
            lines.append(f"Routing stops: {route_count}")
        lines.append("")

    header = (
        f"TOTAL RECORDS IN THIS RESPONSE: {len(docs)}\n"
        f"You MUST list ALL {len(docs)} records below. "
        f"Do not stop early. Do not say there are fewer than {len(docs)}.\n"
        f"{'─' * 50}\n"
    )
    return header + '\n'.join(lines).strip(), len(docs)


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
def _db_save_message_exchange(session, user_message, bot_response, categories):
    try:
        session.refresh_from_db()
    except ConversationSession.DoesNotExist:
        return

    ConversationMessage.objects.create(
        session=session, role='user', content=user_message[:MAX_MESSAGE_LENGTH]
    )
    ConversationMessage.objects.create(
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


@sync_to_async
def _db_get_history_for_load(session):
    msgs = session.messages.all().order_by('-timestamp')[:MAX_STORED_MESSAGES]
    return [
        {
            'role':      msg.role,
            'content':   msg.content,
            'timestamp': msg.timestamp.isoformat(),
        }
        for msg in msgs
    ]


@sync_to_async
def _db_delete_session(session):
    session.delete()


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
        _db_get_tracking_context(user_message),
        get_relevant_context(user_message),
    )

    if tracking_hits > 0:
        logger.info(f"Tracking: {tracking_hits} record(s) matched — using as primary context")
        categories = ['tracking']
        item_count = tracking_hits
    else:
        tracking_context = ''

    system_prompt = get_system_prompt(
        relevant_context=rag_context,
        tracking_context=tracking_context,
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
        categories = ctx['categories']
        messages   = ctx['messages']

        async def event_stream():
            full_response = []
            try:
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
                await _db_save_message_exchange(
                    session, user_message, complete_response, categories
                )
                yield f"data: {json.dumps({'done': True})}\n\n"

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
        categories = ctx['categories']
        messages   = ctx['messages']

        bot_response = await call_ollama(messages)
        await _db_save_message_exchange(session, user_message, bot_response, categories)
        return JsonResponse({'response': bot_response, 'status': 'success'})

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