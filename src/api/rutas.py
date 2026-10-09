"""Endpoints de la API HTTP.

Registro de rutas del adaptador de entrada. Cada handler resuelve su
``Contexto`` (identidad + workspace + configuracion) y llama a un caso de
uso de ``src.aplicacion`` o a una pieza del nucleo. **No hay logica de
negocio propia aqui**: si un calculo crece, sube a ``src/``, no se queda
en el adaptador.

Orden de defensiva que comparten los endpoints con datos:

* la allowlist de vistas se comprueba ANTES de cargar nada, para que un
  nombre inventado ni siquiera toque el almacen;
* la validacion de solo lectura del ``POST /api/consulta`` ocurre ANTES
  de cargar, para que un ``DROP`` devuelva 400 sin coste;
* los fallos de carga se traducen a un 500 generico: el detalle de una
  excepcion de fichero o de conector puede filtrar rutas y credenciales.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import __version__, aplicacion, workspaces
from ..alerts import evaluar_alertas, resumen_alertas
from ..analyzer import Analyzer
from ..core import auth, conector_sql
from ..negocio import salud_cartera
from ..predictions import Predictor
from . import deps
from .deps import Contexto
from .esquemas import (
    ConsultaResultado,
    ConsultaSQL,
    DatosVista,
    Estado,
    ListadoEmpresas,
    ListadoVistas,
    Salud,
    a_jsonable,
    columnas,
    registros,
)

log = logging.getLogger("taller.api")

router = APIRouter(prefix="/api")


def cargar_datos(cfg) -> Dict[str, Any]:
    """Datasets del workspace, ya con la cache parquet del pipeline.

    Es el seam de test y el unico punto que toca disco en los endpoints:
    no hay ``st.cache_data`` aqui porque el proceso no tiene runtime de
    Streamlit y porque la cache del pipeline ya evita releer los originales.
    """
    from ..data_loader import load_all  # noqa: PLC0415 — dependencia del adaptador

    return load_all(cfg)


def _datos(ctx: Contexto) -> Dict[str, Any]:
    """Carga del workspace con error generico si falla.

    El motivo completo va al log con traza; al cliente solo llega un aviso
    generico. Exponer ``No such file or directory: /data/empresaX/...`` o
    un DSN de conector es una fuga, no una ayuda.
    """
    try:
        return cargar_datos(ctx.cfg)
    except Exception as e:  # noqa: BLE001 — se traduce a 500 con log, nunca se traga
        log.exception("No se pudieron cargar los datos de '%s'", ctx.workspace)
        raise HTTPException(
            status_code=500,
            detail="No se pudieron cargar los datos de la empresa.",
        ) from e


# ------------------------------------------------------------------
#  Salud (publico)
# ------------------------------------------------------------------

@router.get("/salud", response_model=Salud, summary="Salud del servicio")
def salud() -> Dict[str, Any]:
    """Unico endpoint sin sesion (200 siempre): no devuelve datos de ningun workspace."""
    return a_jsonable({"estado": "ok", "servicio": "giro-api", "version": __version__})


# ------------------------------------------------------------------
#  Estado analitico
# ------------------------------------------------------------------

@router.get("/estado", response_model=Estado, summary="Radiografia analitica del workspace")
def estado(ctx: Contexto = Depends(deps.contexto)) -> Dict[str, Any]:
    """KPIs, cartera, calidad y alertas del workspace efectivo de la sesion.

    Codigos: 401 sin sesion, 400 workspace mal formado, 404 empresa
    inexistente, 500 si los datos no se pudieron cargar. Si solo falla el
    calculo de alertas la respuesta sigue siendo 200 y lo dice en ``aviso``.
    """
    data = _datos(ctx)
    analyzer = Analyzer(data)

    # Alertas entrena el churn, y ``predecir_churn`` revienta con un frame
    # vacio: un workspace recien creado tiene que devolver 200 con cero
    # alertas, no un 500.
    aviso = None
    if analyzer.df.empty:
        alertas_resumen = resumen_alertas([])
    else:
        predictor = Predictor(data, cfg=ctx.cfg)
        try:
            alertas_resumen = resumen_alertas(
                evaluar_alertas(ctx.cfg, data, analyzer=analyzer, predictor=predictor)
            )
        except Exception as e:  # noqa: BLE001 — se registra con traza y se avisa, nunca se traga
            # Las alertas son una parte de la radiografia, no toda: si una
            # regla no puede calcularse (p. ej. un modelo persistido con
            # otra lista de features que el codigo actual), los KPIs, la
            # cartera y la calidad siguen siendo validos. El fallo entero
            # queda en el log con traza y el cliente lo ve explicitamente
            # en ``aviso``: un ``total: 0`` sin mas contexto mentiria.
            log.error("No se pudieron evaluar las alertas de '%s': %s",
                      ctx.workspace, e, exc_info=e)
            alertas_resumen = resumen_alertas([])
            aviso = "El resumen de alertas no esta disponible en este momento."

    return a_jsonable({
        "workspace": ctx.workspace,
        "negocio": {
            "nombre": ctx.cfg.negocio_nombre,
            "moneda": ctx.cfg.moneda,
            "sector": ctx.cfg.sector,
        },
        "kpis": analyzer.kpis_globales(),
        "cartera": salud_cartera(analyzer),
        "calidad": aplicacion.resumen_calidad(data),
        "alertas": alertas_resumen,
        "aviso": aviso,
    })


# ------------------------------------------------------------------
#  Vistas analiticas
# ------------------------------------------------------------------

@router.get("/vistas", response_model=ListadoVistas, summary="Vistas analiticas consultables")
def vistas(ctx: Contexto = Depends(deps.contexto)) -> Dict[str, Any]:
    """La allowlist que protege ``GET /api/vistas/{nombre}`` (200/401)."""
    return a_jsonable({"workspace": ctx.workspace,
                       "vistas": list(aplicacion.VISTAS_PARA_EXPORTAR)})


@router.get("/vistas/{nombre}", response_model=DatosVista,
           summary="Consulta una vista analitica")
def vista(
    nombre: str,
    ctx: Contexto = Depends(deps.contexto),
    limite: int = Query(default=1000, ge=1, le=10000,
                        description="Maximo de filas devueltas."),
) -> Dict[str, Any]:
    """Devuelve una vista del esquema ``analitica``.

    El nombre se compara contra ``VISTAS_PARA_EXPORTAR`` antes de cargar
    los datos: fuera de la lista hay 404 y ni se abre el almacen, de modo
    que el catalogo de vistas es la unica puerta (no una validacion que
    pueda desviarse del caso de uso).

    Codigos: 401 sin sesion, 404 vista fuera de la allowlist, 500 si los
    datos no se pudieron cargar.
    """
    if nombre not in aplicacion.VISTAS_PARA_EXPORTAR:
        raise HTTPException(
            status_code=404,
            detail=f"Vista desconocida: '{nombre}'. Consulta GET /api/vistas "
                   "para el listado permitido.",
        )
    data = _datos(ctx)
    df = aplicacion.vista(ctx.cfg, data, nombre)
    return a_jsonable({
        "workspace": ctx.workspace,
        "vista": nombre,
        "total_filas": int(len(df)),
        "columnas": columnas(df),
        "registros": registros(df, limite),
    })


# ------------------------------------------------------------------
#  Consola SQL (solo administracion)
# ------------------------------------------------------------------

@router.post("/consulta", response_model=ConsultaResultado,
            summary="Consulta SQL de solo lectura (administracion)")
def consulta(
    cuerpo: ConsultaSQL,
    ctx: Contexto = Depends(deps.permiso_consola_sql),
) -> Dict[str, Any]:
    """Ejecuta una consulta de lectura contra el almacen del workspace.

    El permiso lo impone ``deps.permiso_consola_sql`` (autorizacion) y la
    regla de solo lectura la impone el caso de uso (propiedad de la
    operacion): son dos responsabilidades distintas y ninguna vive en el
    adaptador.

    Codigos: 401 sin sesion, 403 sin ``consola_sql``, 400 consulta que no
    es de lectura o que el almacen rechaza (se comprueba antes de cargar
    nada), 500 si los datos no se pudieron cargar.
    """
    try:
        aplicacion.validar_sql_solo_lectura(cuerpo.sql)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    data = _datos(ctx)
    try:
        df = aplicacion.consulta_sql(ctx.cfg, data, cuerpo.sql)
    except ValueError as e:
        # El caso de uso vuelve a validar (una sola implementacion) y
        # tambien rechaza lo que el almacen no admite.
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001 — la consola informa; nunca se traga
        # Una tabla inexistente o una sintaxis rara no es un fallo del
        # servidor: decirle "500, error interno" al administrador que acaba
        # de escribir mal un SELECT le impide corregirlo. Es lo mismo que
        # hace la consola de la UI. El texto pasa por el enmascarado de
        # ``conector_sql.mensaje_error`` (nunca un DSN) y la traza entera
        # queda en el log.
        log.warning("Consulta rechazada en '%s': %s", ctx.workspace,
                    conector_sql.mensaje_error(e), exc_info=e)
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo ejecutar la consulta. Verifica la sintaxis SQL: "
                   f"{conector_sql.mensaje_error(e)}",
        ) from e

    return a_jsonable({
        "workspace": ctx.workspace,
        "sql": cuerpo.sql,
        "total_filas": int(len(df)),
        "columnas": columnas(df),
        "registros": registros(df, cuerpo.limite),
    })


# ------------------------------------------------------------------
#  Empresas
# ------------------------------------------------------------------

@router.get("/empresas", response_model=ListadoEmpresas,
           summary="Empresas visibles para la sesion")
def empresas(ctx: Contexto = Depends(deps.contexto)) -> Dict[str, Any]:
    """Catalogo de la sesion: siempre ``principal`` + las asignadas.

    Un ``cliente`` nunca ve las demas: la lista sale de
    ``auth.workspaces_visibles``, que es el mismo filtro que usa el
    selector de la UI, de modo que los dos adaptadores no pueden
    desincronizarse.

    Codigos: 401 sin sesion, 400/404 si el workspace efectivo no es valido,
    500 si la configuracion raiz no se pudo leer.
    """
    claves: List[str] = auth.workspaces_visibles(ctx.sesion)
    salida = []
    for clave in claves:
        try:
            cfg = deps.config_del_workspace(clave)
        except HTTPException:
            raise
        except (OSError, ValueError, TypeError) as e:
            # Una empresa con la config ilegible no puede tumbar el
            # listado entero: se publica su clave para que el operador la
            # vea y el motivo queda en el log.
            log.warning("Config ilegible del workspace '%s': %s", clave, e)
            cfg = None
        salida.append({
            "clave": clave,
            "nombre": cfg.negocio_nombre if cfg is not None else clave,
            "moneda": cfg.moneda if cfg is not None else "",
            "sector": cfg.sector if cfg is not None else "",
            "principal": clave == workspaces.CLAVE_PRINCIPAL,
        })
    return a_jsonable({"actual": ctx.workspace, "empresas": salida})


__all__ = ["router", "cargar_datos"]
