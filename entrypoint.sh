#!/usr/bin/env bash
# Entrypoint del contenedor GIRO: levanta el dashboard (Streamlit, 8501)
# y la landing de ventas (Streamlit, 8502) en el mismo proceso.
# Si cualquiera de los dos muere, el contenedor se detiene (los llaveros
# de orquestacion podran reiniciarlo).
set -euo pipefail

GIRO_DASH_PORT="${GIRO_DASH_PORT:-8501}"
GIRO_LANDING_PORT="${GIRO_LANDING_PORT:-8502}"

# Fuera del contenedor, prefiere el venv del repo si existe (python local).
if [ -x ./.venv/bin/python ]; then
    export PATH="./.venv/bin:$PATH"
fi

# Limpia los procesos hijos al recibir SIGTERM/SIGINT (docker stop).
limpiar() {
    trap - TERM INT
    kill "${PID_DASH}" "${PID_LANDING}" 2>/dev/null || true
    timeout 10 wait "${PID_DASH}" "${PID_LANDING}" 2>/dev/null || {
        kill -KILL "${PID_DASH}" "${PID_LANDING}" 2>/dev/null || true
        wait "${PID_DASH}" "${PID_LANDING}" 2>/dev/null || true
    }
}
trap limpiar TERM INT

echo "[giro] arrancando dashboard en :${GIRO_DASH_PORT} y landing en :${GIRO_LANDING_PORT}"

STREAMLIT_SERVER_PORT="${GIRO_DASH_PORT}" STREAMLIT_SERVER_HEADLESS=true \
    python -m streamlit run dashboard.py --server.address 0.0.0.0 &
PID_DASH=$!

STREAMLIT_SERVER_PORT="${GIRO_LANDING_PORT}" STREAMLIT_SERVER_HEADLESS=true \
    python -m streamlit run landing.py --server.address 0.0.0.0 --server.port "${GIRO_LANDING_PORT}" &
PID_LANDING=$!

# Espera a que ambos respondan antes de ceder el control a wait.
espera_salud() {
    local puerto="$1" intentos=0
    until [ "${intentos}" -ge 60 ]; do
        if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${puerto}/_stcore/health', timeout=2)" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
        intentos=$((intentos + 1))
    done
    return 1
}
espera_salud "${GIRO_DASH_PORT}" || { echo "[giro] el dashboard no arranco a tiempo"; exit 1; }
espera_salud "${GIRO_LANDING_PORT}" || { echo "[giro] la landing no arranco a tiempo"; exit 1; }

echo "[giro] listo: dashboard :${GIRO_DASH_PORT} · landing :${GIRO_LANDING_PORT}"

# Espera a que uno de los dos procesos muera y detiene el contenedor
# (portable: sin `wait -n`, que requiere bash >= 4.3).
while :; do
    if ! kill -0 "${PID_DASH}" 2>/dev/null; then
        wait "${PID_DASH}"; exito=$?
        kill "${PID_LANDING}" 2>/dev/null || true
        wait "${PID_LANDING}" 2>/dev/null || true
        echo "[giro] el dashboard termino (exit ${exito}); deteniendo el contenedor"
        exit "${exito}"
    fi
    if ! kill -0 "${PID_LANDING}" 2>/dev/null; then
        wait "${PID_LANDING}"; exito=$?
        kill "${PID_DASH}" 2>/dev/null || true
        wait "${PID_DASH}" 2>/dev/null || true
        echo "[giro] la landing termino (exit ${exito}); deteniendo el contenedor"
        exit "${exito}"
    fi
    sleep 1
done