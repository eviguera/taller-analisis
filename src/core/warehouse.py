"""Sincronizacion con un warehouse SQL central (Fase 3: multi-DB).

GIRO usa DuckDB como almacen local (OLAP) para la analitica, pero muchas
organizaciones necesitan los datos en su warehouse central (Postgres/Neon,
MySQL, Azure SQL, ...). Este modulo *publica* el estado del almacen hacia un
motor SQL externo via SQLAlchemy: datasets crudos, capa core normalizada y
vistas analiticas.

Uso (CLI):
    python main.py warehouse sync --dsn "sqlite:///data/warehouse.sqlite"
    python main.py warehouse sync --dsn "postgresql://user:pass@host:5432/warehouse"
    python main.py warehouse ver  --dsn "postgresql://user:pass@host:5432/warehouse"

El prefijo por defecto (``giro_``) agrupa los objetos publicados y evita
colisiones con tablas propias de la organizacion.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

import pandas as pd

from .config import AppConfig
from .conector_sql import mensaje_error

log = logging.getLogger("taller.warehouse")

# Esquemas del almacen DuckDB que se publican y como se nombran en destino.
#  - main:      datasets crudos tal como entran al ETL  ->  giro_<dataset>
#  - core:      capa canonica (facturas, clientes, detalle)  ->  giro_core_<tabla>
#  - analitica: vistas listas para BI (ingresos, churn, RFM, ...) -> giro_vista_<vista>
ESQUEMAS_DISPONIBLES = ("datasets", "core", "analitica")


def _engine(dsn: str):
    from sqlalchemy import create_engine
    return create_engine(dsn)


_IDENTIFICADOR = re.compile(r"[a-z0-9_]+")


def _identificador(objeto: str) -> str:
    """Valida un identificador SQL contra allowlist; lanza si no es valido.

    Los nombres viajan interpolados en DDL/DML (`DROP TABLE IF EXISTS "x"`),
    asi que no basta con sanitizar: si sobra algo raro, se rechaza.
    """
    limpio = re.sub(r"\W+", "_", str(objeto)).strip("_").lower()
    if not limpio or not _IDENTIFICADOR.fullmatch(limpio):
        raise ValueError(f"Identificador SQL no valido: {objeto!r}")
    return limpio


def _prefijo_efectivo(cfg: AppConfig, prefijo: str) -> str:
    """Prefijo con el workspace incluido: aislamiento por tenant.

    Dos workspaces publicando en el mismo warehouse con el mismo prefijo se
    pisarian (``to_sql(if_exists="replace")`` borra lo del otro). El nombre de
    tabla siempre lleva la clave del workspace salvo que el prefijo ya la
    incluya.
    """
    clave = _identificador(cfg.clave)
    base = prefijo or ""
    # Tiene que acabar en la clave + "_": comprobar que la clave aparece
    # como subcadena no basta (clave "a" con prefijo "datos_" devolvia
    # "datos_" sin clave de tenant y los workspaces volvian a pisarse).
    if base.endswith(f"{clave}_"):
        return base
    return f"{base}{clave}_"


def _nombre_tabla(prefijo: str, objeto: str) -> str:
    """Prefijo + nombre de objeto validado como identificador SQL lowercase."""
    return f"{prefijo or ''}{_identificador(objeto)}"


def _tabla_publica(prefijo: str, esquema: str, objeto: str) -> str:
    mapa = {"datasets": "", "core": "core_", "analitica": "vista_"}
    return _nombre_tabla(prefijo, f"{mapa.get(esquema, '')}{objeto}")


def _avisar_huerfanas(engine, base: str, efectivo: str) -> None:
    """Avisa de tablas del esquema antiguo (publicadas sin clave de tenant).

    Versiones previas publicaban ``<prefijo><objeto>`` sin la clave del
    workspace: esas tablas siguen en el destino con datos mezclados de todos
    los tenants, y ``ver()`` no las lista porque filtra por el prefijo
    efectivo. No se borran solas (pueden ser de otra version del producto);
    se avisa para que las revisen a mano.
    """
    if not base:
        return
    from sqlalchemy import inspect
    try:
        tablas = inspect(engine).get_table_names()
    except Exception as e:  # noqa: BLE001
        log.warning("No se pudo inspeccionar el destino para buscar tablas huerfanas: %s",
                    mensaje_error(e))
        return
    huerfanas = [t for t in tablas if t.startswith(base) and not t.startswith(efectivo)]
    if huerfanas:
        orden = sorted(huerfanas)
        muestra = ", ".join(orden[:10]) + ("..." if len(orden) > 10 else "")
        log.warning(
            "%d tabla(s) del esquema antiguo en el destino (sin clave de "
            "workspace, con datos de todos los tenants): %s. Borralas a mano "
            "cuando lo revises.", len(orden), muestra)


def sincronizar(cfg: AppConfig, dsn: str,
                esquemas: tuple = ESQUEMAS_DISPONIBLES,
                prefijo: str = "giro_") -> List[Dict]:
    """Publica el almacen hacia un warehouse SQL (via SQLAlchemy).

    Si el almacen esta vacio ejecuta el ETL antes de publicar, para que el
    warehouse refleje el mismo estado que ve la analitica. El almacen lo
    decide ``get_store`` (DuckDB o Postgres); con Postgres no hay fichero
    que comprobar, por eso la condicion es "sin estructura" y no "sin
    archivo".
    """
    from ..data_loader import get_store

    store = get_store(cfg)
    try:
        pendiente = store.info_estructura().empty
    finally:
        store.cerrar()
    if pendiente:
        from .pipeline import procesar_etl
        log.info("El almacen esta vacio: ejecutando ETL antes de publicar")
        res = procesar_etl(cfg)
        if res.errores:
            for nombre, err in res.errores.items():
                log.warning("ETL sin %s: %s", nombre, err)

    store = get_store(cfg)
    engine = _engine(dsn)
    prefijo_base = prefijo
    prefijo = _prefijo_efectivo(cfg, prefijo)
    _avisar_huerfanas(engine, prefijo_base, prefijo)
    publicados: List[Dict] = []
    try:
        info = store.info_estructura()
        for esquema in esquemas:
            if esquema == "datasets":
                _publicar_datasets(engine, cfg, prefijo, publicados)
                continue
            objetos = info.loc[info["esquema"] == esquema, "objeto"].tolist()
            for objeto in objetos:
                try:
                    # identificador validado contra allowlist y columnas
                    # explicitas desde el catalogo, no SELECT *
                    ident = _identificador(objeto)
                    df = store.consultar_objeto(esquema, ident)
                except Exception as e:  # noqa: BLE001
                    log.warning("No se pudo leer %s.%s: %s", esquema, objeto, e)
                    continue
                tabla = _tabla_publica(prefijo, esquema, objeto)
                _escribir(engine, tabla, df)
                publicados.append({"esquema": esquema, "origen": objeto,
                                   "tabla": tabla, "filas": len(df)})
    finally:
        store.cerrar()
    return publicados


def _publicar_datasets(engine, cfg, prefijo: str, publicados: List[Dict]) -> None:
    """Publica los datasets crudos (capa main) usando lo que ingiere el ETL."""
    from pathlib import Path
    from .catalog import escanear_directorio, vincular_archivos_a_datasets

    directorio = Path(cfg.directorio_datos)
    asignaciones = vincular_archivos_a_datasets(escanear_directorio(directorio), cfg)

    from .pipeline import _cargar_dataset, _limpiar, _normalizar_columnas

    for nombre, dcfg in cfg.datasets.items():
        ruta = asignaciones.get(nombre) or (directorio / dcfg.archivo if dcfg.archivo else None)
        if ruta is None or not ruta.exists():
            continue
        try:
            cr = _cargar_dataset(cfg, dcfg, ruta)
            df = _normalizar_columnas(cr.datos, dcfg.mapeo)
            df = _limpiar(df, nombre)
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo publicar el dataset %s: %s", nombre, e)
            continue
        tabla = _tabla_publica(prefijo, "datasets", nombre)
        _escribir(engine, tabla, df)
        publicados.append({"esquema": "datasets", "origen": nombre,
                           "tabla": tabla, "filas": len(df)})


def _escribir(engine, tabla: str, df: pd.DataFrame) -> None:
    from sqlalchemy import text
    # la tabla llega de _tabla_publica (objeto validado) pero el prefijo
    # puede venir del CLI: se revalida el identificador completo.
    tabla = _identificador(tabla)
    if df is None or df.empty:
        with engine.begin() as conn:
            conn.execute(text(f'DROP TABLE IF EXISTS "{tabla}"'))
        return
    df.to_sql(tabla, engine, if_exists="replace", index=False)


def ver(cfg: AppConfig, dsn: str, prefijo: str = "giro_") -> pd.DataFrame:
    """Lista los objetos GIRO ya publicados en el warehouse destino."""
    from sqlalchemy import inspect, text
    engine = _engine(dsn)
    prefijo = _prefijo_efectivo(cfg, prefijo)
    insp = inspect(engine)
    filas = []
    for tabla in insp.get_table_names():
        if prefijo and not tabla.startswith(prefijo):
            continue
        try:
            tabla_valida = _identificador(tabla)
        except ValueError:
            log.warning("Tabla con nombre fuera de allowlist, se omite: %r", tabla)
            continue
        nb = insp.get_table_options(tabla)
        if isinstance(nb, dict) and nb.get("mysql_table_type") == "VIEW":
            filas.append({"tabla": tabla, "tipo": "vista", "filas": None})
            continue
        try:
            with engine.connect() as conn:
                n = conn.execute(text(f'SELECT COUNT(*) FROM "{tabla_valida}"')).scalar()
            filas.append({"tabla": tabla, "tipo": "tabla", "filas": n})
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo contar %s: %s", tabla, e)
            filas.append({"tabla": tabla, "tipo": "tabla", "filas": None})
    return pd.DataFrame(filas).reindex(columns=["tabla", "tipo", "filas"])