"""Dependencias de la API: sesion, workspace y configuracion.

Aqui se cumple la regla 1 de AGENTS.md para el adaptador HTTP. Toda
peticion autenticada resuelve:

1. **identidad** desde la cookie ``auth.NOMBRE_COOKIE`` o la cabecera
   ``Authorization: Bearer <token>``, siempre a traves de
   ``auth.inicio_de_sesion`` (misma firma HMAC y mismo registro que la UI);
2. **workspace** a traves de ``auth.workspace_permitido``, que corrige la
   peticion contra los permisos de la sesion aunque el cliente pida otra
   empresa;
3. **configuracion** a traves de ``config_del_workspace``, que NUNCA pasa
   por ``workspaces.config_actual``: esa mira ``GIRO_WORKSPACE`` primero y
   en el contenedor esta fijada a ``principal``, de modo que todos los
   clientes habrian leido la configuracion de la empresa de
   demostracion.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import Depends, HTTPException, Query, Request

from .. import workspaces
from ..core import auth
from ..core.config_manager import cargar_config

log = logging.getLogger("taller.api")

#: Direcciones que cuentan como "no expuesta a la red".
_LOOBACK = ("127.0.0.1", "localhost", "::1")


def token_de_peticion(request: Request) -> str:
    """Token de sesion de la peticion: cabecera Authorization o cookie.

    La cabecera gana sobre la cookie porque es la que usa un cliente que no
    es navegador y porque un cookie jar mal configurado no deberia poder
    silenciar las credenciales que el llamador acaba de mandar explicitamente.
    """
    cabecera = request.headers.get("authorization", "")
    if cabecera[:7].lower() == "bearer ":
        token = cabecera[7:].strip()
        if token:
            return token
    return request.cookies.get(auth.NOMBRE_COOKIE) or ""


def _host_de_argv(argv) -> str:
    """Host declarado en la linea de comandos (``--host`` / ``--host=``)."""
    for i, arg in enumerate(argv):
        if arg == "--host" and i + 1 < len(argv):
            return argv[i + 1].strip()
        if arg.startswith("--host="):
            return arg.split("=", 1)[1].strip()
    return ""


def api_expuesta() -> bool:
    """True si la API escucha fuera de loopback.

    ``GIRO_AUTH=0`` desactiva la autenticacion pensando en Streamlit, y
    ``auth._escucha_solo_loopback`` decide eso leyendo la direccion de
    Streamlit. Este proceso no la tiene, asi que sin esta comprobacion el
    modo desarrollo dejaria la API abierta en ``0.0.0.0``. Mismo criterio
    que ``auth``: ante la duda (sin host declarado) se responde False,
    porque uvicorn por defecto escucha en ``127.0.0.1``.
    """
    host = os.environ.get("GIRO_API_HOST", "").strip() or _host_de_argv(sys.argv[1:])
    if not host:
        return False
    return host not in _LOOBACK


def sesion_actual(request: Request) -> auth.Sesion:
    """Sesion de la peticion, ya validada, o 401."""
    sesion = auth.inicio_de_sesion(token_de_peticion(request) or None)
    if sesion.modo_abierto:
        # Autenticacion desactivada: solo es admisible si nadie de fuera
        # puede llegar al puerto.
        if api_expuesta():
            raise HTTPException(
                status_code=401,
                detail="GIRO_AUTH=0 solo se admite cuando la API escucha en "
                       "loopback; define una sesion o cierra el puerto.",
            )
        return sesion
    if not sesion.hay_sesion:
        raise HTTPException(
            status_code=401,
            detail="Sesion ausente o invalida: envia la cookie "
                   f"'{auth.NOMBRE_COOKIE}' o 'Authorization: Bearer <token>'.",
        )
    return sesion


def workspace_solicitado(sesion: auth.Sesion, workspace: Optional[str]) -> str:
    """Workspace efectivo de la peticion, corregido contra la sesion.

    ``workspace`` es solo una peticion: primero se valida la clave (400 si
    trae rutas o separadores) y despues manda
    ``auth.workspace_permitido``, que la sustituye por una de las empresas
    asignadas si la sesion no llega a ella.
    """
    clave = (workspace or "").strip()
    if clave:
        try:
            clave = workspaces.validar_clave(clave)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    return auth.workspace_permitido(sesion, clave)


def config_del_workspace(clave: str) -> Any:
    """Configuracion del workspace ``clave`` (``principal`` lee la raiz).

    Explicitamente NO usa ``workspaces.config_actual``: esa prefiere la
    variable ``GIRO_WORKSPACE`` al selector, y en docker-compose esta
    fijada a ``principal``. Aqui la clave viene ya corregida por
    ``auth.workspace_permitido``, que es la unica fuente de verdad del
    alcance.
    """
    if not clave or clave == workspaces.CLAVE_PRINCIPAL:
        return cargar_config()
    try:
        return workspaces.config_workspace(clave)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=f"No existe la empresa '{clave}'.",
        ) from e


@dataclass(frozen=True)
class Contexto:
    """Identidad, alcance y configuracion ya resueltos para una peticion."""

    sesion: auth.Sesion
    workspace: str
    cfg: Any


def contexto(
    request: Request,
    workspace: Optional[str] = Query(
        default=None,
        description="Empresa solicitada. Se corrige contra los permisos de la sesion.",
    ),
) -> Contexto:
    """Dependencia base de los endpoints autenticados."""
    sesion = sesion_actual(request)
    clave = workspace_solicitado(sesion, workspace)
    return Contexto(sesion=sesion, workspace=clave, cfg=config_del_workspace(clave))


def permiso_consola_sql(ctx: Contexto = Depends(contexto)) -> Contexto:
    """Autorizacion de ``POST /api/consulta``: se decide aqui, no en el cuerpo.

    Un ``cliente`` sin la concesion recibe 403 antes de mirar la consulta,
    de modo que ni siquiera llega a cargarse los datos del workspace.
    """
    if not ctx.sesion.puede(auth.PERMISO_CONSOLA_SQL):
        raise HTTPException(
            status_code=403,
            detail="La consola SQL es una funcion de administracion.",
        )
    return ctx


__all__ = [
    "Contexto", "api_expuesta", "config_del_workspace", "contexto",
    "permiso_consola_sql", "sesion_actual", "token_de_peticion",
    "workspace_solicitado",
]
