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
from typing import Dict, List, Optional

import pandas as pd

from .config import AppConfig

log = logging.getLogger("taller.warehouse")

# Esquemas del almacen DuckDB que se publican y como se nombran en destino.
#  - main:      datasets crudos tal como entran al ETL  ->  giro_<dataset>
#  - core:      capa canonica (facturas, clientes, detalle)  ->  giro_core_<tabla>
#  - analitica: vistas listas para BI (ingresos, churn, RFM, ...) -> giro_vista_<vista>
ESQUEMAS_DISPONIBLES = ("datasets", "core", "analitica")


def _engine(dsn: str):
    from sqlalchemy import create_engine
    return create_engine(dsn)


def _nombre_tabla(prefijo: str, objeto: str) -> str:
    """Sanitiza un nombre de objeto DuckDB a un identificador SQL lowercase."""
    import re
    limpio = re.sub(r"\W+", "_", str(objeto)).strip("_").lower()
    return f"{prefijo or ''}{limpio}"


def _tabla_publica(prefijo: str, esquema: str, objeto: str) -> str:
    mapa = {"datasets": "", "core": "core_", "analitica": "vista_"}
    return _nombre_tabla(prefijo, f"{mapa.get(esquema, '')}{objeto}")


def sincronizar(cfg: AppConfig, dsn: str,
                esquemas: tuple = ESQUEMAS_DISPONIBLES,
                prefijo: str = "giro_") -> List[Dict]:
    """Publica el almacen DuckDB hacia un warehouse SQL (via SQLAlchemy).

    Si el almacen local no existe (o esta desactualizado frente a los archivos
    fuente) ejecuta el ETL antes de publicar, para que el warehouse refleje el
    mismo estado que ve la analitica.
    """
    from pathlib import Path
    from ..storage.store import DataStore

    ruta_bd = Path(cfg.db_path)
    if not ruta_bd.exists():
        from .pipeline import procesar_etl
        log.info("El almacen local no existe: ejecutando ETL antes de publicar")
        res = procesar_etl(cfg)
        if res.errores:
            for nombre, err in res.errores.items():
                log.warning("ETL sin %s: %s", nombre, err)

    store = DataStore(cfg.db_path, cfg.cache_dir, usar_cache=cfg.usar_cache)
    engine = _engine(dsn)
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
                    df = store.consulta(f'SELECT * FROM "{esquema}"."{objeto}"')  # noqa: store.consulta ya usa columnas explicitas
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
    if df is None or df.empty:
        with engine.begin() as conn:
            conn.execute(text(f'DROP TABLE IF EXISTS "{tabla}"'))
        return
    df.to_sql(tabla, engine, if_exists="replace", index=False)


def ver(cfg: AppConfig, dsn: str, prefijo: str = "giro_") -> pd.DataFrame:
    """Lista los objetos GIRO ya publicados en el warehouse destino."""
    from sqlalchemy import inspect, text
    engine = _engine(dsn)
    insp = inspect(engine)
    filas = []
    for tabla in insp.get_table_names():
        if prefijo and not tabla.startswith(prefijo):
            continue
        nb = insp.get_table_options(tabla)
        if isinstance(nb, dict) and nb.get("mysql_table_type") == "VIEW":
            filas.append({"tabla": tabla, "tipo": "vista", "filas": None})
            continue
        try:
            with engine.connect() as conn:
                n = conn.execute(text(f'SELECT COUNT(*) FROM "{tabla}"')).scalar()
            filas.append({"tabla": tabla, "tipo": "tabla", "filas": n})
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo contar %s: %s", tabla, e)
            filas.append({"tabla": tabla, "tipo": "tabla", "filas": None})
    return pd.DataFrame(filas).reindex(columns=["tabla", "tipo", "filas"])