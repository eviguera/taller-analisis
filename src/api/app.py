"""Fabrica de la aplicacion FastAPI del adaptador de entrada HTTP.

El modulo no hace nada al importarse: no arranca uvicorn, no conecta al
almacen, no lee configuracion. Toda la construccion vive en
``crear_app()``, que es lo que invoca ``uvicorn --factory`` desde
``entrypoint.sh`` y lo que usan los tests. Correr este archivo como
``python -m src.api.app`` levanta un servidor en loopback (o en
``GIRO_API_HOST``/``GIRO_API_PORT``), pero solo bajo ``__main__``.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .. import __version__
from . import rutas

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
    app = FastAPI(
        title="API GIRO",
        description=_DESCRIPCION,
        version=__version__,
        docs_url="/docs",
        redoc_url=None,
    )
    app.include_router(rutas.router)
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
