#!/usr/bin/env bash
# Entrypoint del contenedor GIRO: levanta el dashboard (Streamlit, 8501),
# la landing de ventas (Streamlit, 8502) y la API HTTP (uvicorn, 8503)
# como tres procesos hermanos. Si cualquiera de los tres muere, el
# contenedor se detiene (los llaveros de orquestacion podran reiniciarlo).
set -euo pipefail

GIRO_DASH_PORT="${GIRO_DASH_PORT:-8501}"
GIRO_LANDING_PORT="${GIRO_LANDING_PORT:-8502}"
GIRO_API_PORT="${GIRO_API_PORT:-8503}"
# PIDs inicializados: si una senal llega antes de arrancar los procesos,
# `set -u` haria fallar limpiar() por variable sin definir.
PID_DASH=""
PID_LANDING=""
PID_API=""
# La API escucha en todas las interfaces del contenedor. Se exporta para
# que el propio proceso pueda detectar que esta expuesta y, por tanto, que
# GIRO_AUTH=0 no le es aplicable (src/api/deps.api_expuesta).
GIRO_API_HOST="${GIRO_API_HOST:-0.0.0.0}"
export GIRO_API_HOST

# Fuera del contenedor, prefiere el venv del repo si existe (python local).
if [ -x ./.venv/bin/python ]; then
    export PATH="./.venv/bin:$PATH"
fi

# Limpia los procesos hijos al recibir SIGTERM/SIGINT (docker stop).
limpiar() {
    trap - TERM INT
    kill "${PID_DASH}" "${PID_LANDING}" "${PID_API}" 2>/dev/null || true
    # `wait` es builtin de bash: `timeout 10 wait` nunca funciono (timeout solo
    # ejecuta comandos externos). Se espera con un loop acotado de kill -0.
    local i=0
    while [ "${i}" -lt 10 ] && { kill -0 "${PID_DASH}" 2>/dev/null \
            || kill -0 "${PID_LANDING}" 2>/dev/null \
            || kill -0 "${PID_API}" 2>/dev/null; }; do
        sleep 1
        i=$((i + 1))
    done
    kill -KILL "${PID_DASH}" "${PID_LANDING}" "${PID_API}" 2>/dev/null || true
    wait "${PID_DASH}" "${PID_LANDING}" "${PID_API}" 2>/dev/null || true
}
trap limpiar TERM INT

# La app exige GIRO_AUTH_SECRET en produccion (0.0.0.0). Sin el, cada
# `docker compose up` genera uno nuevo y cierra todas las sesiones.
if [ -z "${GIRO_AUTH_SECRET:-}" ]; then
    echo "[giro] AVISO: GIRO_AUTH_SECRET no esta definido." >&2
    echo "[giro]        Se generara uno efimero: las sesiones se pierden" >&2
    echo "[giro]        en cada reinicio. Fijalo: openssl rand -hex 32" >&2
fi

echo "[giro] arrancando dashboard en :${GIRO_DASH_PORT}, landing en :${GIRO_LANDING_PORT} y API en :${GIRO_API_PORT}"

STREAMLIT_SERVER_PORT="${GIRO_DASH_PORT}" STREAMLIT_SERVER_HEADLESS=true \
    python -m streamlit run dashboard.py --server.address 0.0.0.0 &
PID_DASH=$!

STREAMLIT_SERVER_PORT="${GIRO_LANDING_PORT}" STREAMLIT_SERVER_HEADLESS=true \
    python -m streamlit run landing.py --server.address 0.0.0.0 --server.port "${GIRO_LANDING_PORT}" &
PID_LANDING=$!

python -m uvicorn src.api.app:crear_app --factory \
    --host "${GIRO_API_HOST}" --port "${GIRO_API_PORT}" &
PID_API=$!

# Espera a que los tres respondan antes de ceder el control a wait.
# Streamlit responde en /_stcore/health y la API en /api/salud, de ahi la
# ruta como parametro en vez de una funcion por proceso.
espera_salud() {
    local puerto="$1" ruta="$2" intentos=0
    until [ "${intentos}" -ge 60 ]; do
        if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${puerto}${ruta}', timeout=2)" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
        intentos=$((intentos + 1))
    done
    return 1
}
espera_salud "${GIRO_DASH_PORT}" "/_stcore/health" || { echo "[giro] el dashboard no arranco a tiempo"; exit 1; }
espera_salud "${GIRO_LANDING_PORT}" "/_stcore/health" || { echo "[giro] la landing no arranco a tiempo"; exit 1; }
espera_salud "${GIRO_API_PORT}" "/api/salud" || { echo "[giro] la API no arranco a tiempo"; exit 1; }

echo "[giro] listo: dashboard :${GIRO_DASH_PORT} · landing :${GIRO_LANDING_PORT} · API :${GIRO_API_PORT}"

# Espera a que uno de los tres procesos muera y detiene el contenedor
# (portable: sin `wait -n`, que requiere bash >= 4.3).
while :; do
    if ! kill -0 "${PID_DASH}" 2>/dev/null; then
        wait "${PID_DASH}"; exito=$?
        kill "${PID_LANDING}" "${PID_API}" 2>/dev/null || true
        wait "${PID_LANDING}" "${PID_API}" 2>/dev/null || true
        echo "[giro] el dashboard termino (exit ${exito}); deteniendo el contenedor"
        exit "${exito}"
    fi
    if ! kill -0 "${PID_LANDING}" 2>/dev/null; then
        wait "${PID_LANDING}"; exito=$?
        kill "${PID_DASH}" "${PID_API}" 2>/dev/null || true
        wait "${PID_DASH}" "${PID_API}" 2>/dev/null || true
        echo "[giro] la landing termino (exit ${exito}); deteniendo el contenedor"
        exit "${exito}"
    fi
    if ! kill -0 "${PID_API}" 2>/dev/null; then
        wait "${PID_API}"; exito=$?
        kill "${PID_DASH}" "${PID_LANDING}" 2>/dev/null || true
        wait "${PID_DASH}" "${PID_LANDING}" 2>/dev/null || true
        echo "[giro] la API termino (exit ${exito}); deteniendo el contenedor"
        exit "${exito}"
    fi
    sleep 1
done
