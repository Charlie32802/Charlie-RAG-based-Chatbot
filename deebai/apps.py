from django.apps import AppConfig
import logging
import requests
import os
import threading
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'localhost')
OLLAMA_PORT = os.getenv('OLLAMA_PORT', '11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3.1:8b-instruct-q6_K')


def preload_ollama_model():
    try:
        logger.info(f"Loading {OLLAMA_MODEL}...")
        
        # Use same endpoint as your chat API
        response = requests.post(
            f'http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/chat',
            json={
                'model': OLLAMA_MODEL,
                'messages': [{'role': 'user', 'content': '.'}],
                'stream': False,
                'keep_alive': -1,
                'options': {'num_predict': 1}
            },
            timeout=30
        )
        
        if response.status_code == 200:
            logger.info(f"Model loaded successfully")
    except Exception as e:
        logger.debug(f"Model preload skipped: {e}")


class DeebaiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'deebai'

    def ready(self):
        if os.environ.get('RUN_MAIN') == 'true':
            logger.info("Deebai starting up...")
            
            # Load model in background immediately
            thread = threading.Thread(target=preload_ollama_model, daemon=True)
            thread.start()
            
            # Initialize RAG (can happen while model loads)
            from .rag_utils import initialize_rag_system
            initialize_rag_system()
            
            logger.info("Deebai is ready!")