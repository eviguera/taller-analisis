# Imagen base ligera con Python 3.11 (totalmente libre, MIT/BSD/Apache).
# Sirve el PAQUETE GIRO completo para venta/consultoria en un solo contenedor:
#  - dashboard analitico  (Streamlit) en el puerto 8501
#  - landing de ventas    (Streamlit) en el puerto 8502
#  - API HTTP             (FastAPI/uvicorn) en el puerto 8503
# Adecuada para HF Spaces (plan CPU gratuito), Docker Compose y cualquier VPS.
#
# El proceso corre como usuario no privilegiado (uid 1001). La imagen NO
# lleva datos de tenants, ni secretos, ni modelos entrenados: se montan en
# volumen o se reponen con la CLI de usuarios.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    GIRO_DASH_PORT=8501 \
    GIRO_LANDING_PORT=8502 \
    GIRO_API_PORT=8503 \
    GIRO_API_HOST=0.0.0.0 \
    GIRO_DEMO_URL="/?kiosco=1"

WORKDIR /app

# Usuario sin privilegios. La app escribe en workspaces/, reports/ y config/,
# asi que se crean vacios y se entregan al usuario antes de perder root.
RUN groupadd --system --gid 1001 giro \
 && useradd  --system --uid 1001 --gid giro --home-dir /app --shell /usr/sbin/nologin giro \
 && mkdir -p /app/data /app/workspaces /app/reports /app/config \
 && chown -R giro:giro /app

# Dependencias primero (mejor cache de capas Docker).
# Usa requirements.lock para builds reproducibles.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

# Codigo, configuracion y datos fuente (.dockerignore deja fuera secretos,
# datos de tenants y modelos entrenados).
COPY --chown=giro:giro . .

# Entrypoint: gobierno de los tres procesos (dashboard + landing + API).
RUN chmod +x entrypoint.sh

USER giro

EXPOSE 8501 8502 8503

# El contenedor escucha en 0.0.0.0, asi que la app exige autenticacion
# (ver auth_activada). Define GIRO_AUTH_SECRET y monta el registro de usuarios
# en /app/config/usuarios.yaml antes de exponerlo. Los tres puertos se
# comprueban: el dashboard y la landing por su health de Streamlit, la API
# por /api/salud, que es su unico endpoint publico.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; [urllib.request.urlopen(f'http://127.0.0.1:{p}/_stcore/health', timeout=3) for p in (os.environ.get('GIRO_DASH_PORT','8501'), os.environ.get('GIRO_LANDING_PORT','8502'))]; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('GIRO_API_PORT','8503') + '/api/salud', timeout=3)" || exit 1

CMD ["./entrypoint.sh"]