"""Pipeline ETL: catalogo -> carga -> normalizacion -> almacen.

Flujo tipico:
    1. `procesar_etl(cfg)` escanea el directorio de datos.
    2. Detecta y clasifica cada archivo (CSV, Excel, .sav de PSPP, ...).
    3. Carga los datos, aplica el mapeo de columnas configurado.
    4. Normaliza tipos y registra las tablas en DuckDB (+ cache parquet).
    5. `load_all(cfg)` entrega los DataFrames en memoria para el resto del sistema.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .catalog import escanear_directorio, vincular_archivos_a_datasets, ArchivoDetectado
from .config import AppConfig, DatasetConfig
from .config_manager import ETIQUETAS_ESPERADAS
from .hechos import construir_factura_detalle
from ..loaders import get_loader, CargaResultado
from ..storage import DataStore
from ..storage.schema import VISTAS_ANALITICA

log = logging.getLogger("taller.pipeline")


class ResultadoETL:
    def __init__(self):
        self.tablas_registradas: Dict[str, int] = {}
        self.estructura: Dict[str, int] = {}
        self.errores: Dict[str, str] = {}
        self.advertencias: Dict[str, str] = {}
        self.archivos: List[ArchivoDetectado] = []
        self.asignaciones: Dict[str, Path] = {}
        self.tiempo_carga: float = 0.0
        self.tiempo_estructura: float = 0.0
        self.n_vistas: int = 0

    @property
    def ok(self) -> bool:
        return len(self.errores) == 0


def _normalizar_columnas(df: pd.DataFrame, mapeo: Dict[str, str]) -> pd.DataFrame:
    """Renombra columnas de origen al esquema canonico usando el mapeo configurado."""
    if not mapeo:
        return df
    df = df.copy()
    df.rename(columns=mapeo, inplace=True)
    return df


def _limpiar(df: pd.DataFrame, tipo: str) -> pd.DataFrame:
    """Limpieza basica general: columnas vacias, duplicados y tipos basicos."""
    df = df.copy()
    df = df.loc[:, ~df.columns.duplicated()]

    if tipo == "facturas" or tipo == "ventas":
        if "fecha" in df.columns:
            df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        for col in ("total", "descuento"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    if tipo == "clientes" and "fecha_registro" in df.columns:
        df["fecha_registro"] = pd.to_datetime(df["fecha_registro"], errors="coerce")

    for col in ("id", "cliente_id", "vehiculo_id"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def _cargar_dataset(cfg: AppConfig, dcfg: DatasetConfig, ruta: Path) -> CargaResultado:
    loader = get_loader(ruta, dcfg.formato)
    kwargs = {}
    if dcfg.hoja is not None and dcfg.formato in ("excel",):
        kwargs["hoja"] = dcfg.hoja
    return loader.cargar(ruta, **kwargs)


def _cargar_archivos_locales(cfg: AppConfig, directorio: Path,
                             asignaciones: Dict[str, Path],
                             resultado: ResultadoETL) -> Dict[str, pd.DataFrame]:
    """Carga y normaliza los archivos locales del directorio de datos."""
    tablas = {}
    for nombre, dcfg in cfg.datasets.items():
        ruta = asignaciones.get(nombre) or (directorio / dcfg.archivo if dcfg.archivo else None)
        if ruta is None or not ruta.exists():
            resultado.errores[nombre] = f"archivo no encontrado: {dcfg.archivo or nombre}"
            continue
        try:
            cr = _cargar_dataset(cfg, dcfg, ruta)
            df = _normalizar_columnas(cr.datos, dcfg.mapeo)
            df = _limpiar(df, nombre)
            esperadas = ETIQUETAS_ESPERADAS.get(nombre, set())
            faltantes = esperadas - set(df.columns)
            if faltantes:
                resultado.advertencias[nombre] = (
                    f"columnas faltantes: {', '.join(sorted(faltantes))}"
                )
            tablas[nombre] = df
            resultado.tablas_registradas[nombre] = len(df)
        except Exception as e:  # noqa: BLE001
            log.exception("Error al cargar %s", nombre)
            resultado.errores[nombre] = f"{type(e).__name__}: {e}"
    return tablas


def _ejecutar_conectores_externos(cfg: AppConfig, tablas: Dict[str, pd.DataFrame],
                                  resultado: ResultadoETL) -> Dict[str, pd.DataFrame]:
    """Ejecuta conectores externos para llenar datasets ausentes o reemplazar."""
    if not getattr(cfg, "conectores", None):
        return tablas
    from .conector_sql import ejecutar_conectores
    conectados, errores_con = ejecutar_conectores(cfg, ya_cargados=set(tablas))
    tablas.update(conectados)
    resultado.tablas_registradas.update({n: len(df) for n, df in conectados.items()})
    for nombre, err in errores_con.items():
        resultado.advertencias[f"conector:{nombre}"] = err
    return tablas


def _construir_almacen(store, tablas: Dict[str, pd.DataFrame],
                       resultado: ResultadoETL) -> None:
    """Registra tablas, construye hechos y vistas en el DataStore."""
    from time import time
    store.registrar_tablas(tablas)

    if "facturas" in tablas and not tablas["facturas"].empty:
        t1 = time()
        hechos = construir_factura_detalle(
            tablas["facturas"], tablas.get("servicios"))
        if not hechos.empty:
            store.registrar_tabla("factura_detalle", hechos, cache=True)
            store.registrar_tabla_core("factura_detalle", hechos)
        resultado.tiempo_estructura = round(time() - t1, 3)

    t1 = time()
    resultado.estructura = store.construir_estructura(tablas)
    resultado.tiempo_estructura = round(resultado.tiempo_estructura + (time() - t1), 3)
    resultado.n_vistas = len(VISTAS_ANALITICA)


def procesar_etl(cfg: AppConfig, directorio: Optional[Path] = None,
                 guardar: bool = True, usar_cache: bool = True) -> ResultadoETL:
    """Ejecuta el pipeline completo y devuelve el resultado."""
    from time import time
    t0 = time()
    resultado = ResultadoETL()
    directorio = Path(directorio) if directorio else cfg.directorio_datos

    archivos = escanear_directorio(directorio)
    resultado.archivos = archivos
    asignaciones = vincular_archivos_a_datasets(archivos, cfg)
    resultado.asignaciones = asignaciones

    store = DataStore(cfg.db_path, cfg.cache_dir, usar_cache=usar_cache) if guardar else None

    tablas = _cargar_archivos_locales(cfg, directorio, asignaciones, resultado)
    tablas = _ejecutar_conectores_externos(cfg, tablas, resultado)

    if store is not None:
        try:
            _construir_almacen(store, tablas, resultado)
        finally:
            store.cerrar()

    resultado.tiempo_carga = round(time() - t0, 2)
    return resultado


def load_all(cfg: AppConfig = None, data_dir: Optional[Path] = None,
             usar_cache: bool = True) -> Dict[str, pd.DataFrame]:
    """Carga todos los datasets en memoria (compatible con la interfaz previa).

    Usa la configuracion pasada o la por defecto. Si se da `data_dir`, los
    archivos se buscan alli.
    """
    if cfg is None:
        from .config_manager import cargar_config
        cfg = cargar_config()
    directorio = Path(data_dir) if data_dir else cfg.directorio_datos

    archivos = escanear_directorio(directorio)
    asignaciones = vincular_archivos_a_datasets(archivos, cfg)

    datos_final = {}

    for nombre, dcfg in cfg.datasets.items():
        ruta = asignaciones.get(nombre) or (directorio / dcfg.archivo if dcfg.archivo else None)
        if ruta is None or not ruta.exists():
            continue
        try:
            df_cache = _leer_cache_fresco(cfg, nombre, ruta) if usar_cache else None
            if df_cache is not None:
                datos_final[nombre] = df_cache
                continue
            cr = _cargar_dataset(cfg, dcfg, ruta)
            df = _normalizar_columnas(cr.datos, dcfg.mapeo)
            df = _limpiar(df, nombre)
            datos_final[nombre] = df
            if usar_cache:
                _escribir_cache(cfg, nombre, df)
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo cargar %s: %s", nombre, e)

    if getattr(cfg, "conectores", None):
        from .conector_sql import ejecutar_conectores
        conectados, _ = ejecutar_conectores(cfg, ya_cargados=set(datos_final))
        datos_final.update(conectados)

    return datos_final


def _leer_cache_fresco(cfg: AppConfig, nombre: str, ruta_origen: Path) -> Optional[pd.DataFrame]:
    """Lee la cache parquet si existe y es mas nueva que el archivo fuente."""
    if not cfg.cache_dir.exists():
        return None
    archivo_cache = cfg.cache_dir / f"{nombre}.parquet"
    if not archivo_cache.exists():
        return None
    if archivo_cache.stat().st_mtime < ruta_origen.stat().st_mtime:
        return None
    try:
        return pd.read_parquet(archivo_cache)
    except Exception as e:
        log.warning("No se pudo leer cache parquet %s: %s", archivo_cache, e)
        return None


def _escribir_cache(cfg: AppConfig, nombre: str, df: Optional[pd.DataFrame]):
    if df is None or df.empty:
        return
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(cfg.cache_dir / f"{nombre}.parquet", index=False)
    except Exception:  # noqa: BLE001
        log.warning("No se pudo escribir cache para %s", nombre)


def _necesita_recarga(directorio: Path, cfg: AppConfig) -> bool:
    """True si algun archivo de datos es mas nuevo que la base DuckDB (fuerza recarga)."""
    if not cfg.db_path.exists():
        return True
    mtime_db = cfg.db_path.stat().st_mtime
    for archivo in escanear_directorio(directorio):
        if archivo.ruta.stat().st_mtime > mtime_db:
            return True
    return False


def get_data_summary(data: Dict[str, pd.DataFrame]) -> Dict:
    """Resumen de calidad de los datasets cargados (nulos, duplicados, tipos)."""
    resumen = {}
    for nombre, df in data.items():
        if df is None or df.empty:
            resumen[nombre] = {
                "registros": 0,
                "columnas": [],
                "nulos": {},
                "duplicados": 0,
                "tipos": {},
            }
            continue
        resumen[nombre] = {
            "registros": len(df),
            "columnas": list(df.columns),
            "nulos": {k: int(v) for k, v in df.isnull().sum().items() if int(v) > 0},
            "duplicados": int(df.duplicated().sum()),
            "tipos": {k: str(v) for k, v in df.dtypes.astype(str).items()},
        }
    return resumen