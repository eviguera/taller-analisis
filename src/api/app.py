"""Fabrica de la aplicacion FastAPI del adaptador de entrada HTTP.

El modulo no hace nada al importarse: no arranca uvicorn, no conecta al
almacen, no lee configuracion. Toda la construccion vive en
``crear_app()``, que es lo que invoca ``uvicorn --factory`` desde
``entrypoint.sh`` y lo que usan los tests. Correr este archivo como
``python -m src.api.app`` levanta un servidor en loopback (o en
``GIRO_API_HOST``/``GIRO_API_PORT``), pero solo bajo ``__main__``.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import OrderedDict
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .. import __version__
from . import rutas
from .mcp_server import mcp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Cabeceras de seguridad en todas las respuestas (regla 2 de AGENTS.md)."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Añade X-Request-ID a cada respuesta para trazabilidad de peticiones."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id")
        if not request_id:
            import uuid
            request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class JsonLoggingMiddleware(BaseHTTPMiddleware):
    """Logging estructurado JSON de todas las peticiones para auditoría y monitoreo."""

    async def dispatch(self, request: Request, call_next):
        inicio = time.time()
        request_id = request.headers.get("x-request-id") or str(time.time())
        response = await call_next(request)
        duracion = round((time.time() - inicio) * 1000, 2)

        registro = {
            "evento": "request",
            "request_id": request_id,
            "metodo": request.method,
            "ruta": request.url.path,
            "codigo_estado": response.status_code,
            "duracion_ms": duracion,
            "cliente": request.client.host if request.client else "desconocido",
        }
        log.info(json.dumps(registro, ensure_ascii=False))
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting simple basado en IP del cliente.

    Permite ``GIRO_API_RATE_LIMIT`` peticiones por ventana de
    ``GIRO_API_RATE_WINDOW_SEGUNDOS`` segundos (default: 100 por 60s).
    ``GIRO_API_RATE_MAX_CLIENTES`` limita la memoria reservada para IPs
    (default: 4096). IPs nuevas se rechazan con 429 mientras todos los
    registros estén activos y el límite esté lleno.
    Superado cualquier limite, devuelve 429 Too Many Requests.
    """

    def __init__(self, app: Callable, max_requests: int = 100,
                 window_seconds: int = 60, max_clients: int = 4096):
        super().__init__(app)
        if max_requests < 1 or window_seconds < 1 or max_clients < 1:
            raise ValueError("Los limites del rate limiter deben ser positivos")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        # OrderedDict mantiene al inicio la IP usada menos recientemente,
        # permitiendo borrar registros expirados sin crecer sin limite.
        self._client_requests: OrderedDict[str, list[float]] = OrderedDict()

    def _client_ip(self, request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def _clean_old(self, ip: str, now: float) -> None:
        cutoff = now - self.window_seconds
        historial = self._client_requests.get(ip)
        if historial is None:
            return
        vigente = [t for t in historial if t > cutoff]
        if vigente:
            self._client_requests[ip] = vigente
        else:
            del self._client_requests[ip]

    def _clean_expired_clients(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._client_requests:
            _ip, historial = next(iter(self._client_requests.items()))
            if historial and historial[-1] > cutoff:
                break
            self._client_requests.popitem(last=False)

    def _rechazar(self) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"error": "Demasiadas peticiones. Vuelve mas tarde."},
            headers={"Retry-After": str(self.window_seconds)},
        )

    async def dispatch(self, request: Request, call_next):
        ip = self._client_ip(request)
        now = time.time()
        self._clean_old(ip, now)
        self._clean_expired_clients(now)

        historial = self._client_requests.get(ip)
        if historial is None:
            # No expulsar clientes activos: una IP nueva espera al vencimiento
            # en vez de borrar el contador de otra IP y abrir un bypass.
            if len(self._client_requests) >= self.max_clients:
                return self._rechazar()
            historial = []
            self._client_requests[ip] = historial

        if len(historial) >= self.max_requests:
            return self._rechazar()

        historial.append(now)
        self._client_requests.move_to_end(ip)
        return await call_next(request)


log = logging.getLogger("taller.api")

_DESCRIPCION = """\
Segundo adaptador de entrada de GIRO: expone el mismo nucleo que el
dashboard (``src.aplicacion``, ``src.core``) como API JSON, sin logica de
negocio propia.

* Autenticacion: cookie `giro_sesion` o `Authorization: Bearer <token>`.
* Aislamiento: el `?workspace=` es una peticion, no una decision; siempre
  se corrige con `auth.workspace_permitido` (regla 1 de AGENTS.md).
* `GET /api/salud` es el unico endpoint publico y no toca datos.
"""


def _error_no_manejado(request: Request, exc: Exception) -> JSONResponse:
    """Ultima red: cualquier excepcion no prevista vuelve 500 en JSON.

    El detalle se queda en el log con traza; al cliente no se le cuenta
    que fallo ni que fichero ni que conector, porque eso es informacion
    para quien esta escuchando. FastAPI/uvicorn re-lanza la excepcion
    despues de responder, de modo que la traza tambien llega al proceso.

    ``exc_info`` se pasa explicitamente: este manejador se invoca como
    corutina, y al reanudarla ``sys.exc_info()`` vuelve vacio, de modo que
    ``log.exception`` solo registraria "NoneType: None".
    """
    log.error("Error no controlado en %s %s: %s", request.method,
              request.url.path, exc, exc_info=exc)
    return JSONResponse(status_code=500,
                        content={"error": "Error interno del servidor."})


def crear_app() -> FastAPI:
    """Construye la aplicacion. Sin efectos secundarios en el import."""
    # El lifespan que hay que propagar es el de la app HTTP de MCP, no el
    # del objeto FastMCP: Starlette lo invoca con la app como argumento y
    # FastMCP.lifespan no acepta parámetros (FastMCP 4.x + Starlette 1.x).
    # FastMCP crea su endpoint en /mcp por defecto; al montarlo en /mcp
    # eso lo dejaría en /mcp/mcp. Con path="/" el endpoint público es /mcp.
    mcp_app = mcp.http_app(path="/")
    app = FastAPI(
        title="API GIRO",
        description=_DESCRIPCION,
        version=__version__,
        docs_url="/docs",
        redoc_url=None,
        lifespan=mcp_app.lifespan,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(JsonLoggingMiddleware)

    max_requests = int(os.environ.get("GIRO_API_RATE_LIMIT", "100"))
    window_seconds = int(os.environ.get("GIRO_API_RATE_WINDOW_SEGUNDOS", "60"))
    max_clients = int(os.environ.get("GIRO_API_RATE_MAX_CLIENTES", "4096"))
    app.add_middleware(RateLimitMiddleware, max_requests=max_requests,
                       window_seconds=window_seconds, max_clients=max_clients)

    app.include_router(rutas.router)
    app.mount("/mcp", mcp_app)
    # Manejador de `Exception`: Starlette lo monta en ServerErrorMiddleware
    # y devuelve JSON en vez del "Internal Server Error" en texto plano.
    app.add_exception_handler(Exception, _error_no_manejado)
    return app


def _puerto() -> int:
    """``GIRO_API_PORT`` (8503 por defecto), con cuidado de que sea un puerto."""
    crudo = os.environ.get("GIRO_API_PORT", "8503").strip() or "8503"
    try:
        puerto = int(crudo)
    except ValueError:
        raise ValueError(f"GIRO_API_PORT no es un numero: {crudo!r}")
    if not 1 <= puerto <= 65535:
        raise ValueError(f"GIRO_API_PORT fuera de rango: {puerto}")
    return puerto


if __name__ == "__main__":
    # Ejecucion directa (`python -m src.api.app`). No hay `uvicorn.run` a
    # nivel de import: solo cuando este modulo es el script principal.
    import uvicorn

    uvicorn.run(
        "src.api.app:crear_app",
        factory=True,
        host=os.environ.get("GIRO_API_HOST", "").strip() or "127.0.0.1",
        port=_puerto(),
        log_level="info",
    )


__all__ = ["crear_app"]
