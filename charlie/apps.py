import os
import httpx
import logging
import threading
from dotenv import load_dotenv
from django.apps import AppConfig

load_dotenv()
logger = logging.getLogger(__name__)

OLLAMA_HOST  = os.getenv('OLLAMA_HOST',  'localhost')
OLLAMA_PORT  = os.getenv('OLLAMA_PORT',  '11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3.1:8b-instruct-q5_K_M')


def preload_ollama_model():
    try:
        logger.info(f"Loading {OLLAMA_MODEL}...")
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f'http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/chat',
                json={
                    'model':      OLLAMA_MODEL,
                    'messages':   [{'role': 'user', 'content': '.'}],
                    'stream':     False,
                    'keep_alive': -1,
                    'options':    {'num_predict': 1},
                },
            )
        if response.status_code == 200:
            logger.info("Model loaded successfully")
    except Exception as e:
        logger.debug(f"Model preload skipped: {e}")


class CharlieConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'charlie'

    def ready(self):
        if not os.environ.get('DJANGO_SKIP_READY'):
            logger.info("Charlie starting up...")

            thread = threading.Thread(target=preload_ollama_model, daemon=True)
            thread.start()

            from .rag_utils import initialize_rag_system
            initialize_rag_system()

            logger.info("Charlie is ready!")