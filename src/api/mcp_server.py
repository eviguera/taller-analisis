"""Servidor MCP de GIRO sobre FastMCP (Streamable-HTTP).

Montado en la app FastAPI principal en ``/mcp``. Expone recursos y
herramientas para consultar los datos analíticos de un workspace desde
cualquier cliente MCP (Claude Code, Cursor, etc.).

Inspirado en OpenExecutive (mcp_server/server.py): recursos tipo
``giro://workspace/*`` y herramientas ``giro.consultar_sql``,
``giro.ejecutar_alertas``, ``giro.generar_briefing``.

Autenticación: reusa la sesión de GIRO (cookie o Bearer token). El workspace
se resuelve contra los permisos de la sesión (regla 1 de AGENTS.md).

Nota sobre FastMCP 4.x: los recursos URI template requieren al menos un
parámetro en el path. Por tanto los recursos estáticos se exponen como
``giro://workspace/{seccion}`` donde ``seccion`` es uno de:
perfil, kpis, alertas, clientes, recomendaciones, briefing.
Y ``giro://scheduler/{seccion}`` para la salud del scheduler.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastmcp import Context, FastMCP

from .. import aplicacion
from ..alertas_avanzadas import (
    evaluar_alertas_avanzadas,
    resumen_alertas_avanzadas,
)
from ..analyzer import Analyzer
from ..briefing import generar_briefing
from ..core import auth
from ..memoria import (
    inicializar_db,
    obtener_historial_scheduler,
    ruta_db_por_workspace,
)
from ..negocio import salud_cartera
from ..predictions import Predictor
from ..recomendaciones import next_best_action
from . import deps
from .deps import Contexto

log = logging.getLogger("taller.api.mcp")

mcp = FastMCP(
    name="giro-mcp",
    instructions=(
        "GIRO MCP server: contexto analitico de un workspace y herramientas "
        "para consultar KPIs, alertas, recomendaciones, briefing ejecutivo y "
        "ejecutar SQL de solo lectura. Autenticado con la sesion de GIRO; "
        "aislamiento por workspace."
    ),
)


# ---------------------------------------------------------------------------
#  Auxiliar de autenticacion e isolamiento por workspace
# ---------------------------------------------------------------------------

def _contexto_de_request(request) -> Contexto:
    """Resuelve el Contexto de GIRO (workspace + config) desde una request
    HTTP de Starlette. Reusa la misma logica de autenticacion y aislamiento
    que el resto de la API."""
    sesion = deps.sesion_actual(request)
    clave = deps.workspace_solicitado(sesion, "")
    cfg = deps.config_del_workspace(clave)
    return Contexto(sesion=sesion, workspace=clave, cfg=cfg)


def _cargar_datos(cfg) -> dict[str, Any]:
    from ..data_loader import load_all  # noqa: PLC0415
    return load_all(cfg)


# ---------------------------------------------------------------------------
#  Recursos (read-only, estilo OpenExecutive oe://*)
#  FastMCP 4.x requiere URI template con al menos un parametro.
# ---------------------------------------------------------------------------

@mcp.resource("giro://workspace/{seccion}")
def recurso_workspace(ctx: Context, seccion: str) -> str:
    """Recursos del workspace: perfil, kpis, alertas, clientes,
    recomendaciones, briefing."""
    request = ctx.request_context.request
    ctx_giro = _contexto_de_request(request)
    clave = ctx_giro.workspace
    cfg = ctx_giro.cfg

    # El cliente MCP puede pedir otro workspace mediante ?workspace= en la
    # URI del recurso; se valida contra los permisos de la sesion.
    ws_param = request.query_params.get("workspace")
    if ws_param and ws_param != clave:
        clave = deps.workspace_solicitado(ctx_giro.sesion, ws_param)
        cfg = deps.config_del_workspace(clave)

    if seccion == "perfil":
        perfil = {
            "nombre": cfg.negocio_nombre,
            "sector": cfg.sector,
            "moneda": cfg.moneda,
            "clave": clave,
            "slogan": getattr(cfg, "slogan", ""),
            "tema": getattr(cfg, "tema", {}),
        }
        return json.dumps(perfil, ensure_ascii=False, indent=2)

    if seccion == "kpis":
        datos = _cargar_datos(cfg)
        analyzer = Analyzer(datos)
        return json.dumps(
            analyzer.kpis_globales(), ensure_ascii=False, indent=2, default=str
        )

    if seccion == "alertas":
        datos = _cargar_datos(cfg)
        alertas = evaluar_alertas_avanzadas(cfg, datos)
        return json.dumps(
            {
                "alertas": alertas,
                "resumen": resumen_alertas_avanzadas(alertas),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    if seccion == "clientes":
        datos = _cargar_datos(cfg)
        analyzer = Analyzer(datos)
        salud = salud_cartera(analyzer)
        return json.dumps(
            {"salud_cartera": salud},
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    if seccion == "recomendaciones":
        datos = _cargar_datos(cfg)
        predictor = Predictor(datos, cfg=cfg)
        nba = next_best_action(datos, cfg, predictor=predictor)
        return json.dumps(
            {
                "recomendaciones": (
                    nba.to_dict(orient="records") if not nba.empty else []
                ),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    if seccion == "briefing":
        datos = _cargar_datos(cfg)
        analyzer = Analyzer(datos)
        kpis = analyzer.kpis_globales()
        salud = salud_cartera(analyzer)
        alertas = evaluar_alertas_avanzadas(cfg, datos)
        texto = generar_briefing(datos, kpis, alertas, salud, cfg)
        return json.dumps({"texto": texto}, ensure_ascii=False, indent=2)

    return json.dumps(
        {"error": f"Seccion desconocida: {seccion}"}, ensure_ascii=False
    )


@mcp.resource("giro://scheduler/{seccion}")
def recurso_scheduler(ctx: Context, seccion: str) -> str:
    """Salud del scheduler del workspace."""
    import json

    request = ctx.request_context.request
    ctx_giro = _contexto_de_request(request)
    clave = ctx_giro.workspace
    cfg = ctx_giro.cfg

    ws_param = request.query_params.get("workspace")
    if ws_param and ws_param != clave:
        clave = deps.workspace_solicitado(ctx_giro.sesion, ws_param)
        cfg = deps.config_del_workspace(clave)

    if seccion != "salud":
        return json.dumps(
            {"error": f"Seccion desconocida: {seccion}"}, ensure_ascii=False
        )

    db_path = ruta_db_por_workspace(cfg.directorio_datos)
    try:
        inicializar_db(db_path)
    except Exception as exc:  # noqa: BLE001
        log.exception("No se pudo inicializar el ledger del scheduler")
        return json.dumps({"error": str(exc)}, ensure_ascii=False)

    try:
        historial = obtener_historial_scheduler(db_path=db_path, limite=20)
    except Exception as exc:  # noqa: BLE001
        log.exception("No se pudo leer el historial del scheduler")
        return json.dumps({"error": str(exc)}, ensure_ascii=False)

    from src.scheduler import listar_jobs

    payload = {
        "workspace": clave,
        "jobs_registrados": listar_jobs(),
        "ultimas_ejecuciones": [
            {
                "ejecutada_en": h.ejecutada_en,
                "job": h.job,
                "estado": h.estado,
                "error": h.error,
                "filas_afectadas": h.filas_afectadas,
            }
            for h in historial
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


# ---------------------------------------------------------------------------
#  Herramientas (acciones estructuradas)
# ---------------------------------------------------------------------------

@mcp.tool()
def giro_consultar_sql(
    ctx: Context,
    sql: str,
    limite: int = 100,
) -> str:
    """Ejecuta una consulta SQL de solo lectura sobre el workspace.

    Valida que la consulta sea de solo lectura antes de ejecutarla.
    Requiere el permiso ``consola_sql`` (regla 4 de AGENTS.md).
    """
    request = ctx.request_context.request
    ctx_giro = _contexto_de_request(request)
    cfg = ctx_giro.cfg

    # Verificar permiso de consola SQL (mismo requisito que la API REST)
    if not ctx_giro.sesion.puede(auth.PERMISO_CONSOLA_SQL):
        return json.dumps(
            {"error": "Permiso denegado: se requiere rol de administrador "
                      "para ejecutar consultas SQL."},
            ensure_ascii=False,
        )

    from ..aplicacion.almacen import consulta_sql, validar_sql_solo_lectura

    try:
        validar_sql_solo_lectura(sql)
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)

    datos = _cargar_datos(cfg)
    try:
        df = consulta_sql(cfg, datos, sql)
    except Exception as exc:  # noqa: BLE001
        log.exception("Consulta MCP fallo")
        return json.dumps({"error": "Error ejecutando la consulta."}, ensure_ascii=False)

    if len(df) > limite:
        df = df.head(limite)
    return json.dumps(
        {
            "filas": df.to_dict(orient="records"),
            "columnas": list(df.columns),
            "total": len(df),
        },
        ensure_ascii=False,
        default=str,
    )


@mcp.tool()
def giro_ejecutar_alertas(
    ctx: Context,
    workspace: str = "principal",
) -> str:
    """Reevaluar las reglas de alerta del workspace y devolver alertas activas."""
    request = ctx.request_context.request
    ctx_giro = _contexto_de_request(request)
    clave = ctx_giro.workspace
    cfg = ctx_giro.cfg
    if workspace and workspace != clave:
        clave = deps.workspace_solicitado(ctx_giro.sesion, workspace)
        cfg = deps.config_del_workspace(clave)

    datos = _cargar_datos(cfg)
    alertas = evaluar_alertas_avanzadas(cfg, datos)
    return json.dumps(
        {
            "alertas": alertas,
            "resumen": resumen_alertas_avanzadas(alertas),
        },
        ensure_ascii=False,
        default=str,
    )


@mcp.tool()
def giro_generar_briefing(
    ctx: Context,
    workspace: str = "principal",
) -> str:
    """Generar el briefing ejecutivo narrativo del workspace."""
    request = ctx.request_context.request
    ctx_giro = _contexto_de_request(request)
    clave = ctx_giro.workspace
    cfg = ctx_giro.cfg
    if workspace and workspace != clave:
        clave = deps.workspace_solicitado(ctx_giro.sesion, workspace)
        cfg = deps.config_del_workspace(clave)

    datos = _cargar_datos(cfg)
    analyzer = Analyzer(datos)
    kpis = analyzer.kpis_globales()
    salud = salud_cartera(analyzer)
    alertas = evaluar_alertas_avanzadas(cfg, datos)
    texto = generar_briefing(datos, kpis, alertas, salud, cfg)
    return json.dumps({"texto": texto}, ensure_ascii=False)
