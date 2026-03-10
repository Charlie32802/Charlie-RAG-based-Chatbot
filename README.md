# 1. Create and activate venv
python -m venv venv
venv/Scripts/activate        # Windows
source venv/bin/activate     # Mac/Linux

# 2. Install packages
pip install -r requirements.txt

# 3. Set up environment
cp .env.example .env

# Generate a secret key and paste it into your .env as DJANGO_KEY
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# 4. Run
python manage.py migrate
uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --reload