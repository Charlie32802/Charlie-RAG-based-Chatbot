import os
import json
import logging
import requests
import time
from threading import Lock

from dotenv import load_dotenv
load_dotenv()

from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect

from .models import ConversationSession, ConversationMessage
from .timezone_utils import get_philippine_time, get_time_greeting
from .rag_utils import search_documents, get_collection_stats, format_rag_results
from .prompts import get_system_prompt

logger = logging.getLogger(__name__)

OLLAMA_HOST  = os.getenv('OLLAMA_HOST',  '192.168.168.164')
OLLAMA_PORT  = os.getenv('OLLAMA_PORT',  '11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3.1:8b-instruct-q6_K')

MAX_MESSAGE_LENGTH      = int(os.getenv('MAX_MESSAGE_LENGTH',      2000))
MAX_HISTORY_MESSAGES    = int(os.getenv('MAX_HISTORY_MESSAGES',    10))
MAX_HISTORY_CHARS       = int(os.getenv('MAX_HISTORY_CHARS',       8000))
MAX_RESPONSE_TOKENS     = int(os.getenv('MAX_RESPONSE_TOKENS',     4096))
SAFE_TOTAL_PROMPT_CHARS = int(os.getenv('SAFE_TOTAL_PROMPT_CHARS', 40000))
OLLAMA_NUM_CTX          = int(os.getenv('OLLAMA_NUM_CTX',          8192))
OLLAMA_TIMEOUT          = int(os.getenv('OLLAMA_TIMEOUT',          60))
MIN_REQUEST_INTERVAL    = float(os.getenv('MIN_REQUEST_INTERVAL',  1.0))
MAX_STORED_MESSAGES     = int(os.getenv('MAX_STORED_MESSAGES',     40))
OLLAMA_TEMPERATURE      = float(os.getenv('OLLAMA_TEMPERATURE',    0.7))

ERR_TIMEOUT    = "This is taking longer than expected. Please try again."
ERR_CONNECTION = "I'm having trouble connecting. Please try again in a moment."
ERR_GENERIC    = "Something went wrong. Please try again."
ERR_RATE_LIMIT = "Please wait a moment before sending another message."
ERR_EMPTY      = "I tried to respond but nothing came out. Could you ask again?"

_processing_sessions = set()
_last_request_time   = {}
_request_lock        = Lock()


def _is_bullet_line(line):
    import re
    return bool(re.match(r'^\s*•\s+|^\s*\d+\.\s+', line))


def _clean_response(text):
    import re

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
        'model': OLLAMA_MODEL,
        'messages': messages,
        'options': {
            'temperature':    OLLAMA_TEMPERATURE,
            'num_predict':    MAX_RESPONSE_TOKENS,
            'num_ctx':        OLLAMA_NUM_CTX,
            'top_p':          0.85,
            'top_k':          40,
            'repeat_penalty': 1.1,
            'num_thread':     8,
            'num_gpu':        99,
            'stop':           ['</s>', 'User:'],
        },
    }


def _check_rate_limit(session_key):
    with _request_lock:
        now = time.time()
        if now - _last_request_time.get(session_key, 0) < MIN_REQUEST_INTERVAL:
            return False
        _last_request_time[session_key] = now
        return True


def _validate_message(data):
    user_message = data.get('message', '').strip()
    if not user_message:
        return None, JsonResponse({'error': 'No message provided'}, status=400)
    if len(user_message) > MAX_MESSAGE_LENGTH:
        return None, JsonResponse(
            {'error': f'Message too long. Maximum {MAX_MESSAGE_LENGTH} characters.'}, status=400
        )
    return user_message, None


def call_ollama(messages):
    try:
        payload           = _build_ollama_payload(messages)
        payload['stream'] = False
        response = requests.post(
            f'http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/chat',
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        raw = response.json().get('message', {}).get('content', '').strip()
        return _clean_response(raw) or ERR_EMPTY
    except requests.exceptions.Timeout:
        return ERR_TIMEOUT
    except requests.exceptions.RequestException as e:
        logger.error(f"Ollama request error: {e}")
        return ERR_CONNECTION
    except Exception as e:
        logger.error(f"Ollama error: {e}", exc_info=True)
        return ERR_GENERIC


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


def get_or_create_session(request):
    if not request.session.session_key:
        request.session.create()
    session, _ = ConversationSession.objects.get_or_create(
        session_key=request.session.session_key
    )
    return session


def get_relevant_context(user_message):
    stats = get_collection_stats()
    if not stats or stats['total_chunks'] == 0:
        return '', []

    try:
        results    = search_documents(user_message, n_results=25)
        if not results:
            return '', []
        categories = list(set(r['category'] for r in results[:10]))
        context, _ = format_rag_results(results, query_info=None, query=user_message)
        return context, categories
    except Exception as e:
        logger.error(f"RAG error: {e}")
        return '', []


def _save_message_exchange(session, user_message, bot_response, categories):
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


def _prepare_chat_context(request, user_message):
    session = get_or_create_session(request)
    _processing_sessions.add(session.session_key)

    db_messages = session.messages.all().order_by('-timestamp')[:MAX_HISTORY_MESSAGES]
    history     = build_conversation_history(db_messages)

    ph_time      = get_philippine_time()
    time_context = (
        f"{get_time_greeting()}! Today is "
        f"{ph_time.strftime('%A, %B %d, %Y at %I:%M %p')} (Philippine Time)"
    )

    relevant_context, categories = get_relevant_context(user_message)

    system_prompt = get_system_prompt(
        relevant_context=relevant_context,
        time_context=time_context,
        is_first_message=session.message_count == 0,
    )

    def _total_chars(msgs):
        return sum(len(str(m.get('content', ''))) for m in msgs)

    messages    = [system_prompt] + history + [{'role': 'user', 'content': user_message}]
    total_chars = _total_chars(messages)

    if total_chars > SAFE_TOTAL_PROMPT_CHARS:
        trimmed = list(history)
        while trimmed and _total_chars([system_prompt] + trimmed + [{'role': 'user', 'content': user_message}]) > SAFE_TOTAL_PROMPT_CHARS:
            trimmed.pop(0)

        messages    = [system_prompt] + trimmed + [{'role': 'user', 'content': user_message}]
        total_chars = _total_chars(messages)

        if trimmed:
            logger.info(f"Prompt trimmed: kept {len(trimmed)} of {len(history)} history turns ({total_chars} chars)")
        else:
            logger.warning(f"Prompt large even without history ({total_chars} chars) — proceeding without history")

    return {'session': session, 'messages': messages, 'categories': categories}


def index(request):
    if not request.session.session_key:
        request.session.create()
    return render(request, 'conversation.html')


@csrf_protect
@require_http_methods(["POST"])
def chat_stream_api(request):
    session = None
    try:
        session_key = request.session.session_key or 'unknown'
        if not _check_rate_limit(session_key):
            return JsonResponse({'error': ERR_RATE_LIMIT}, status=429)

        data              = json.loads(request.body)
        user_message, err = _validate_message(data)
        if err:
            return err

        ctx        = _prepare_chat_context(request, user_message)
        session    = ctx['session']
        categories = ctx['categories']
        messages   = ctx['messages']

        def event_stream():
            full_response = []
            try:
                payload           = _build_ollama_payload(messages)
                payload['stream'] = True
                with requests.post(
                    f'http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/chat',
                    json=payload, stream=True, timeout=OLLAMA_TIMEOUT,
                ) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
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
                _save_message_exchange(session, user_message, complete_response, categories)
                yield f"data: {json.dumps({'done': True})}\n\n"

            except requests.exceptions.Timeout:
                yield f"data: {json.dumps({'error': ERR_TIMEOUT})}\n\n"
            except requests.exceptions.RequestException as e:
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


@csrf_protect
@require_http_methods(["POST"])
def chat_api(request):
    session = None
    try:
        session_key = request.session.session_key or 'unknown'
        if not _check_rate_limit(session_key):
            return JsonResponse({'error': ERR_RATE_LIMIT}, status=429)

        data              = json.loads(request.body)
        user_message, err = _validate_message(data)
        if err:
            return err

        ctx        = _prepare_chat_context(request, user_message)
        session    = ctx['session']
        categories = ctx['categories']
        messages   = ctx['messages']

        bot_response = call_ollama(messages)
        _save_message_exchange(session, user_message, bot_response, categories)
        return JsonResponse({'response': bot_response, 'status': 'success'})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return JsonResponse({'error': ERR_GENERIC}, status=500)
    finally:
        if session:
            _processing_sessions.discard(session.session_key)


@csrf_protect
@require_http_methods(["POST"])
def load_history_api(request):
    try:
        session  = get_or_create_session(request)
        messages = [
            {
                'role':      msg.role,
                'content':   msg.content,
                'timestamp': msg.timestamp.isoformat(),
            }
            for msg in session.messages.all().order_by('-timestamp')[:MAX_STORED_MESSAGES]
        ]
        messages.reverse()
        return JsonResponse({'messages': messages, 'status': 'success'})
    except Exception as e:
        logger.error(f"Load error: {e}")
        return JsonResponse({'error': 'Failed to load history'}, status=500)


@csrf_protect
@require_http_methods(["POST"])
def delete_conversation_api(request):
    try:
        session = get_or_create_session(request)
        if session.session_key in _processing_sessions:
            return JsonResponse(
                {'error': 'Please wait, message is still processing'}, status=400
            )
        session.delete()
        request.session.flush()
        request.session.create()
        return JsonResponse({'status': 'success', 'message': 'Conversation deleted'})
    except Exception as e:
        logger.error(f"Delete error: {e}")
        return JsonResponse({'error': 'Failed to delete'}, status=500)