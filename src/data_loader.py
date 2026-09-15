"""Compatibilidad con la interfaz anterior + acceso a datos desde la nueva arquitectura.

Este modulo sigue exponiendo `load_all`, `load_clientes`, etc. con la misma firma,
pero por debajo usa el catalogo, los cargadores plugin (CSV/Excel/PSPP) y DuckDB.
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path
from typing import Optional

from .core.config_manager import cargar_config
from .core.pipeline import load_all as pipeline_load_all, get_data_summary as pipeline_resumen
from .loaders import get_loader

APP_CONFIG = cargar_config()


def load_all(data_dir: Optional[Path] = None, cfg=None) -> dict:
    """Carga todos los datasets: CSV, Excel o .sav/.por de PSPP (deteccion automatica).

    Acepta tanto `load_all(directorio)` (interfaz clasica) como
    `load_all(cfg)` / `load_all(cfg=cfg)` (nueva arquitectura).
    """
    from copy import deepcopy
    from .core.config import AppConfig

    if isinstance(data_dir, AppConfig):
        cfg, data_dir = data_dir, None
    if cfg is None:
        cfg = APP_CONFIG
    if data_dir is not None:
        cfg = deepcopy(cfg)
        cfg.directorio_datos = Path(data_dir)
    return pipeline_load_all(cfg)


def _cargar_tabla(nombre: str, path: Optional[Path] = None):
    """Carga un dataset individual; si `path` apunta a un archivo, lo usa directamente."""
    if path is not None:
        loader = get_loader(Path(path))
        result = loader.cargar(Path(path))
        return result.datos
    cfg = APP_CONFIG
    datos = pipeline_load_all(cfg)
    # pipeline_load_all devuelve todos; extraemos el que toca
    if nombre in datos:
        return datos[nombre]
    # fallback: intentar carga directa del archivo configurado
    dcfg = cfg.datasets.get(nombre)
    if dcfg is None or not dcfg.archivo:
        return pd.DataFrame()
    ruta = cfg.directorio_datos / dcfg.archivo
    if not ruta.exists():
        return pd.DataFrame()
    return get_loader(ruta, dcfg.formato).cargar(ruta).datos


def load_clientes(path: Optional[Path] = None):
    return _cargar_tabla("clientes", path)


def load_vehiculos(path: Optional[Path] = None):
    return _cargar_tabla("vehiculos", path)


def load_servicios(path: Optional[Path] = None):
    return _cargar_tabla("servicios", path)


def load_facturas(path: Optional[Path] = None):
    return _cargar_tabla("facturas", path)


def load_inventario(path: Optional[Path] = None):
    return _cargar_tabla("inventario", path)


def merge_datasets(data):
    """Une facturas + clientes + vehiculos en un DataFrame analitico."""
    facturas = data["facturas"].copy() if "facturas" in data else pd.DataFrame()
    if facturas.empty:
        return pd.DataFrame()

    clientes = data.get("clientes", pd.DataFrame())
    vehiculos = data.get("vehiculos", pd.DataFrame())

    if not clientes.empty and "cliente_id" in facturas.columns and "id" in clientes.columns:
        cols_cli = [c for c in ["id", "nombre", "telefono", "email", "fecha_registro"] if c in clientes.columns]
        facturas = facturas.merge(clientes[cols_cli], left_on="cliente_id", right_on="id", suffixes=("", "_cliente"))

    if not vehiculos.empty and "vehiculo_id" in facturas.columns and "id" in vehiculos.columns:
        cols_veh = [c for c in ["id", "marca", "modelo", "anio", "placa", "color", "kilometraje"] if c in vehiculos.columns]
        facturas = facturas.merge(vehiculos[cols_veh], left_on="vehiculo_id", right_on="id", suffixes=("", "_vehiculo"))

    facturas["fecha"] = pd.to_datetime(facturas["fecha"], errors="coerce")
    facturas = facturas.dropna(subset=["fecha"])

    if "fecha_registro" in facturas.columns:
        facturas["antiguedad_cliente_dias"] = (facturas["fecha"] - facturas["fecha_registro"]).dt.days
    facturas["mes"] = facturas["fecha"].dt.month
    facturas["anio"] = facturas["fecha"].dt.year
    facturas["trimestre"] = facturas["fecha"].dt.quarter
    facturas["dia_semana"] = facturas["fecha"].dt.day_name()
    facturas["anio_mes"] = facturas["fecha"].dt.to_period("M").astype(str)
    return facturas


def get_data_summary(data: dict) -> dict:
    return pipeline_resumen(data)


def get_store():
    """Devuelve la capa de almacenamiento (DuckDB + cache) ya configurada."""
    from .storage import DataStore
    return DataStore(APP_CONFIG.db_path, APP_CONFIG.cache_dir, usar_cache=APP_CONFIG.usar_cache)