# Imagen base ligera con Python 3.11 (totalmente libre, MIT/BSD/Apache).
# Sirve el PAQUETE GIRO completo para venta/consultoria en un solo contenedor:
#  - dashboard analitico  (Streamlit) en el puerto 8501
#  - landing de ventas    (Streamlit) en el puerto 8502
# Adecuada para HF Spaces (plan CPU gratuito), Docker Compose y cualquier VPS.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    GIRO_DASH_PORT=8501 \
    GIRO_LANDING_PORT=8502 \
    GIRO_DEMO_URL="/?kiosco=1"

WORKDIR /app

# Dependencias primero (mejor cache de capas Docker).
COPY requirements.txt requirements.lock ./
RUN pip install -r requirements.txt

# Codigo, configuracion y datos fuente.
COPY . .

# Entrypoint: gobierno de los dos procesos (dashboard + landing).
RUN chmod +x entrypoint.sh

EXPOSE 8501 8502

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; [urllib.request.urlopen(f'http://127.0.0.1:{p}/_stcore/health', timeout=3) for p in (8501, 8502)]" || exit 1

CMD ["./entrypoint.sh"]