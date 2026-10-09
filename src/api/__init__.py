"""Adaptador de entrada HTTP (FastAPI) del hexagono GIRO.

GIRO habla con su nucleo desde tres sitios: `ui/` (Streamlit), `main.py`
(CLI) y aqui. Este paquete es el tercero, y su regla es la misma que la de
los otros dos: **traducir HTTP, no reimplementar el negocio**. Los casos de
uso viven en `src/aplicacion`, la identidad y el alcance en `src/core/auth`
y la configuracion en `src/workspaces`; lo que hay aqui son rutas,
esquemas y dependencias.

No hay efectos secundarios al importar: la aplicacion se construye con
`crear_app()` y solo se sirve con `python -m src.api.app` o con
`uvicorn src.api.app:crear_app --factory`.
"""

from .app import crear_app

__all__ = ["crear_app"]
