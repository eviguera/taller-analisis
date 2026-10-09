"""Compatibilidad con la interfaz anterior + acceso a datos desde la nueva arquitectura.

Este modulo sigue exponiendo `load_all`, `load_clientes`, etc. con la misma firma,
pero por debajo usa el catalogo, los cargadores plugin (CSV/Excel/PSPP) y DuckDB.
"""

from __future__ import annotations

import os
import re

import pandas as pd
from pathlib import Path
from typing import Optional

from .core.config_manager import cargar_config
from .core.pipeline import load_all as pipeline_load_all, get_data_summary as pipeline_resumen
from .loaders import get_loader
from .workspaces import config_actual

#: Motores aceptados para el almacen analitico (`PuertoAlmacen`).
MOTOR_DUCKDB = "duckdb"
MOTOR_POSTGRES = "postgres"

def get_app_config():
    """Configuracion global del workspace activo.

    Permite multiempresa via ``GIRO_WORKSPACE`` o el selector del dashboard:
    cada workspace tiene su propio config, datos y almacen. La resolucion es
    barata y siempre fresca; no lleva cache propia (el cacheo vivo lo hace
    ``st.cache_data`` en ``ui/context.py``, que si sabe del workspace).
    """
    return config_actual()


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
        cfg = get_app_config()
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
    cfg = get_app_config()
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


# Esquema que devuelve ``enriquecer_facturas``: hechos de origen, las
# dimensiones de cliente y vehiculo del join, y las columnas derivadas de
# tiempo. Analyzer, Predictor y las paginas seleccionan columnas por nombre,
# asi que este listado es el contrato.
COLUMNAS_HECHOS = [
    "id", "cliente_id", "vehiculo_id", "fecha", "total", "descuento",
    "estado", "detalles",
    "id_cliente", "nombre", "telefono", "email", "fecha_registro",
    "id_vehiculo", "marca", "modelo", "anio", "placa", "color", "kilometraje",
    "antiguedad_cliente_dias", "mes", "trimestre", "dia_semana", "anio_mes",
]
_HECHOS_FECHAS = ("fecha", "fecha_registro")
_HECHOS_DECIMALES = ("total", "descuento")
_HECHOS_NUMEROS = (
    "id", "cliente_id", "vehiculo_id", "id_cliente", "id_vehiculo", "anio",
    "kilometraje", "antiguedad_cliente_dias", "mes", "trimestre",
)


def hechos_vacios() -> pd.DataFrame:
    """El esquema de ``enriquecer_facturas`` con cero filas.

    Un workspace recien creado no tiene facturas todavia. Devolver un
    ``DataFrame()`` sin columnas hacia que ``Analyzer`` y ``Predictor``
    fallaran con un ``KeyError: 'estado'``, y ``obtener_estado`` presentaba
    ese error al usuario como "No se pudieron cargar los datos" en lugar de
    los estados vacios que las paginas ya saben pintar.

    Los tipos se declaran uno a uno: un ``[]`` a secas se guarda como
    ``float64`` y el acceso ``.str`` de pandas (``detalles``) lo rechaza.
    """
    vacio = pd.DataFrame()
    for columna in COLUMNAS_HECHOS:
        if columna in _HECHOS_FECHAS:
            vacio[columna] = pd.Series(dtype="datetime64[ns]")
        elif columna in _HECHOS_DECIMALES:
            vacio[columna] = pd.Series(dtype="float64")
        elif columna in _HECHOS_NUMEROS:
            vacio[columna] = pd.Series(dtype="int64")
        else:
            vacio[columna] = pd.Series(dtype="string")
    return vacio


def enriquecer_facturas(data):
    """Enriquece facturas con dimensiones de clientes y vehiculos (left join)."""
    facturas = data["facturas"].copy() if "facturas" in data else pd.DataFrame()
    if facturas.empty:
        # Sin filas no hay nada que unir: se devuelve el esquema completo,
        # no un frame vacio sin columnas (ver hechos_vacios).
        return hechos_vacios()

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


def get_store(cfg=None, usar_cache: Optional[bool] = None):
    """Devuelve el almacen del workspace, ya configurado.

    Punto unico de decision del motor: el resto del sistema pide un
    `PuertoAlmacen` y no sabe si hay DuckDB o Postgres detrás.

    ``usar_cache`` solo tiene sentido en DuckDB (la capa de parquet de
    ``DataStore``); en Postgres se ignora, porque ahi el almacen remoto ya
    es la unica fuente. Se pasa como parametro opcional para que el ETL y
    el CLI puedan pedir ``usar_cache=False`` sin saber que motor hay.
    """
    if cfg is None:
        cfg = get_app_config()
    if motor_almacen(cfg) == MOTOR_POSTGRES:
        from .storage.postgres import AlmacenPostgres
        try:
            return AlmacenPostgres(dbname=dbname_postgres(cfg))
        except Exception as e:  # noqa: BLE001 — se reenvia con contexto, no se traga
            raise RuntimeError(
                f"No se pudo conectar con Postgres para el workspace "
                f"'{getattr(cfg, 'clave', '?')}': {e}\n"
                "Si es la primera vez, cada workspace necesita su propia base "
                "de datos: revisa GIRO_PG_* y GIRO_ALMACEN_MOTOR."
            ) from e
    from .storage import DataStore
    cache = cfg.usar_cache if usar_cache is None else usar_cache
    return DataStore(cfg.db_path, cfg.cache_dir, usar_cache=cache)


def motor_almacen(cfg=None) -> str:
    """Motor del almacen: ``GIRO_ALMACEN_MOTOR``, luego la config, luego DuckDB.

    DuckDB embebido sigue siendo el defecto: es lo que hace que el producto
    se levante en un unico contenedor sin servidor de base de datos.
    Postgres es opt-in por entorno.
    """
    valor = os.environ.get("GIRO_ALMACEN_MOTOR", "").strip().lower()
    if not valor and cfg is not None:
        valor = str(getattr(cfg, "motor_almacen", "") or "").strip().lower()
    valor = valor or MOTOR_DUCKDB
    if valor in ("postgresql", "pg"):
        return MOTOR_POSTGRES
    if valor not in (MOTOR_DUCKDB, MOTOR_POSTGRES):
        raise ValueError(
            f"Motor de almacen desconocido: {valor!r}. "
            f"Acepta '{MOTOR_DUCKDB}' o '{MOTOR_POSTGRES}'.")
    return MOTOR_POSTGRES if valor == MOTOR_POSTGRES else MOTOR_DUCKDB


def dbname_postgres(cfg, prefijo: Optional[str] = None) -> str:
    """Base de datos de Postgres propia del workspace.

    **La unidad de aislamiento es la base de datos** (regla 1), equivalente
    al fichero ``.duckdb`` por workspace de DuckDB. Si dos workspaces
    compartieran una, ``registrar_tabla`` (``DROP TABLE`` + ``CREATE``) de
    uno borraria las tablas del otro, y como la firma de carga vive en
    ``giro_meta`` dentro de la misma base, el primero creeria que sus datos
    estan frescos y **leeria los del segundo**. Por eso el nombre se deriva
    aqui, siempre, y no se acepta un ``dbname`` unico para todos.

    El prefijo (``GIRO_PG_DBPREFIX``, por defecto ``giro``) permite que
    varias instalaciones compartan servidor: el workspace ``demo`` vive en
    ``giro_demo``. Es una variable distinta de ``GIRO_PG_DBNAME`` a
    proposito: esa es la base a la que conecta ``AlmacenPostgres`` cuando
    se construye a mano, y darle dos significados dejaria al operador sin
    saber a donde se conecta.
    """
    clave = (getattr(cfg, "clave", "") or "").strip().lower()
    if not clave:
        raise ValueError(
            "El workspace no tiene clave: no se puede derivar su base de "
            "datos de Postgres sin riesgo de mezclar tenants.")

    # La clave ya viene validada (``^[a-z0-9][a-z0-9_-]{0,63}$``) pero puede
    # llevar '-', que no queremos en el nombre de base de datos.
    base = re.sub(r"[^a-z0-9_]", "_", clave)
    if prefijo is None:
        prefijo = os.environ.get("GIRO_PG_DBPREFIX", "").strip().lower()
    limpio = re.sub(r"[^a-z0-9_]", "_", prefijo or "giro").strip("_") or "giro"
    nombre = f"{limpio}_{base}"

    # Postgres trunca identificadores a 63 bytes: un nombre mas largo se
    # silenciaria y dos workspaces largos podrian colisionar.
    if len(nombre) > 63:
        raise ValueError(
            f"Nombre de base de datos demasiado largo ({len(nombre)} > 63): "
            f"{nombre!r}. Acorta GIRO_PG_DBNAME o la clave del workspace.")
    return nombre