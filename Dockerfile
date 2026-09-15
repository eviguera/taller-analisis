# Imagen base ligera con Python 3.11 (totalmente libre, MIT/BSD/Apache).
# Adecuada para Hugging Face Spaces (plan CPU gratuito) y cualquier host Docker.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# Dependencias primero (mejor cache de capas Docker).
COPY requirements.txt requirements.lock ./
RUN pip install -r requirements.txt

# Codigo, configuracion y datos fuente.
COPY . .

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "dashboard.py"]