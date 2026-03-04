# Charlie RAG-based Chatbot

A Django-based RAG (Retrieval-Augmented Generation) chatbot that uses ChromaDB, BM25 search, and Ollama for local LLM inference.

## Prerequisites

- **Python 3.10+**
- **Ollama** — [Install from ollama.ai](https://ollama.ai)

## Quick Start

### 1. Create and activate a virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

On Linux/macOS:

```bash
python -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and set the required variables:

```bash
cp .env.example .env
```

Edit `.env` and set at least:

| Variable       | Required | Description                                                                                                                                    |
| -------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `DJANGO_KEY`   | Yes      | Django secret key. Generate with: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `OLLAMA_HOST`  | No       | Ollama host (default: `localhost`)                                                                                                             |
| `OLLAMA_PORT`  | No       | Ollama port (default: `11434`)                                                                                                                 |
| `OLLAMA_MODEL` | No       | Model name (default: `llama3.1:8b-instruct-q6_K`)                                                                                              |

### 4. Set up Ollama

Install Ollama and pull the model:

```bash
ollama pull llama3.1:8b-instruct-q6_K
```

### 5. Run migrations and collect static files

```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

### 6. Start the server

```bash
python manage.py runserver
```

Open **http://127.0.0.1:8000** in your browser.

## Optional: Add documents for RAG

To use the RAG features, add documents via the Django admin:

1. Create a superuser: `python manage.py createsuperuser`
2. Go to http://127.0.0.1:8000/admin
3. Upload documents in the Charlie app
