"""Conectores a orígenes externos (Fase 2): ERP/SQL, BDD y archivos remotos.

Permite que un workspace se alimente no solo de archivos locales (CSV/Excel/
PSPP) sino también de consultas a otros motores, simulando la lectura de un ERP
o una réplica de datos:

    conectores:
      - nombre: "erp_facturas"
        motor: "sqlite"          # sqlite | duckdb | csv | excel | url | sql(DSN)
        fuente: "erp.sqlite"      # ruta relativa a `directorio_datos` (o URL / DSN)
        consulta: "SELECT * FROM facturas"
        dataset: "facturas"       # dataset canónico al que puebla
        forzar: false             # true = reemplaza la fuente archivo local

Flujo de demo:
    1. ``python main.py conector seed-erp``   -> escribe data/erp.sqlite
       (snapshot de los datasets cargados, como si fuera la exportación del ERP).
    2. ``python main.py conector seed-erp --usar`` -> registra los conectores
       en el config del workspace activo.
    3. ``python main.py conector sincronizar`` o ejecutar el ETL puebla el
       almacén DuckDB desde la "BD" del ERP. El ETL también consulta los
       conectores automáticamente.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yaml

from .config import AppConfig

log = logging.getLogger("taller.conectores")

MOTORES_LOCALES = ("sqlite", "duckdb", "csv", "excel")
MOTORES_SQL_EXTERNOS = ("postgres", "mysql", "sql")

# Lista restrictiva de sentencias de lectura. No es un parser: ante la duda
# se rechaza. Sin esto, un conector podria ejecutar DROP/ATTACH/COPY contra
# la replica del ERP.
_SOLO_LECTURA = re.compile(
    r"^\s*(?:--[^\n]*\n|/\*.*?\*/\s*)*(select|with|explain|describe|show)\b",
    re.IGNORECASE | re.DOTALL,
)
_PELIGROSO = re.compile(
    r"\b(?:copy|attach|detach|install|load|export|import|pragma|delete|"
    r"insert|update|drop|create|alter|truncate|vacuum|checkpoint|set|"
    r"attach|pragma)\b"
    r"|;|read_csv|read_parquet|read_json|glob\(",
    re.IGNORECASE,
)


def validar_solo_lectura(consulta: str) -> None:
    """Deja pasar una unica sentencia de lectura; si no, lanza ValueError."""
    texto = (consulta or "").strip()
    if not texto:
        raise ValueError("Un conector requiere una consulta SQL")
    if not _SOLO_LECTURA.match(texto):
        raise ValueError("Los conectores solo permiten consultas de lectura "
                         "(SELECT, WITH, EXPLAIN, DESCRIBE, SHOW)")
    if ";" in texto.rstrip(";"):
        raise ValueError("Los conectores admiten una sola sentencia por vez.")
    if _PELIGROSO.search(texto.rstrip(";").rstrip()):
        raise ValueError("La consulta contiene operaciones no permitidas en "
                         "modo lectura (escrituras, ATTACH o lectura de archivos).")


def _mensaje_error(e: Exception) -> str:
    """Mensaje de error seguro para UI y logs: nunca incluye el DSN.

    Las excepciones de SQLAlchemy/psycopg2 pueden traer credenciales en el
    DSN (`postgres://user:pass@...`); aqui solo queda el tipo y el texto.
    """
    texto = str(e)
    texto = re.sub(r"(\w+://)[^@\s]+@", r"\1***@", texto)
    return f"{type(e).__name__}: {texto}"


def _dsn_resuelto(cfg: AppConfig, conector: Conector) -> str:
    """Resuelve el DSN al que apunta un conector SQL (motor 'sql'/postgres/mysql).

    - ``sqlite:///ruta`` con ruta relativa se resuelve contra el directorio de
      datos del workspace.
    - Un DSN de postgres/mysql se usa tal cual (debe llevar credenciales).
    """
    dsn = str(conector.fuente or "")
    if dsn.startswith("sqlite:///"):
        rel = dsn[len("sqlite:///"):]
        if not rel.startswith("/") and not rel.startswith("~"):
            dsn = "sqlite:///" + str(cfg.directorio_datos / rel)
    return dsn


def _conectar_sqlalchemy(cfg: AppConfig, conector: Conector) -> pd.DataFrame:
    """Conecta via SQLAlchemy (Postgres, MySQL o SQLite por DSN)."""
    try:
        from sqlalchemy import create_engine
    except ImportError as e:  # noqa: BLE001
        raise RuntimeError(
            "El motor requiere 'sqlalchemy'. Instala: pip install sqlalchemy "
            "(y el driver: psycopg2-binary para Postgres, pymysql para MySQL)."
        ) from e
    dsn = _dsn_resuelto(cfg, conector)
    if not dsn:
        raise ValueError("Un conector SQL requiere un DSN en 'fuente' "
                         "(p. ej. postgresql://user:pass@host:5432/db)")
    if not conector.consulta:
        raise ValueError("Un conector SQL requiere una consulta SQL")
    engine = create_engine(dsn, connect_args={"connect_timeout": 10})
    try:
        validar_solo_lectura(conector.consulta)
        with engine.connect() as conn:
            return pd.read_sql_query(conector.consulta, conn)
    finally:
        engine.dispose()


@dataclass
class Conector:
    """Definición de un conector a un origen de datos externo."""
    nombre: str
    motor: str = "sqlite"
    fuente: Optional[str] = None      # archivo/URL (o DSN para postgres/mysql)
    consulta: Optional[str] = None    # SQL para motores tipo BD
    dataset: str = ""                 # dataset canónico de destino en GIRO
    forzar: bool = False              # sobreescribir la fuente de archivo local
    hoja: Optional[int] = None        # para motores excel
    parametros: Dict = field(default_factory=dict)


def parsear_conectores(cfg: AppConfig) -> List[Conector]:
    """Convierte la lista de dicts del config en objetos Conector."""
    conectores = []
    for item in getattr(cfg, "conectores", None) or []:
        if not isinstance(item, dict):
            continue
        nombre = str(item.get("nombre") or item.get("dataset") or "conector").strip()
        conectores.append(Conector(
            nombre=nombre,
            motor=str(item.get("motor", "sqlite")),
            fuente=item.get("fuente"),
            consulta=item.get("consulta"),
            dataset=str(item.get("dataset", nombre)),
            forzar=bool(item.get("forzar", False)),
            hoja=item.get("hoja"),
            parametros=dict(item.get("parametros") or {}),
        ))
    return conectores


def _resolver_fuente(cfg: AppConfig, conector: Conector) -> Path:
    """Resuelve una fuente relativa contra el directorio de datos del workspace."""
    if not conector.fuente or "://" in str(conector.fuente):
        return Path(str(conector.fuente or ""))
    return cfg.directorio_datos / conector.fuente


def conectar(cfg: AppConfig, conector: Conector) -> pd.DataFrame:
    """Ejecuta un conector y devuelve su DataFrame."""
    motor = conector.motor.lower()
    if motor in MOTORES_SQL_EXTERNOS:
        return _conectar_sqlalchemy(cfg, conector)
    if motor == "sqlite":
        import sqlite3
        ruta = _resolver_fuente(cfg, conector)
        if not ruta.exists():
            raise FileNotFoundError(f"No existe la BD sqlite: {ruta}")
        validar_solo_lectura(conector.consulta)
        # mode=ro: aunque la consulta pasara la validacion, el archivo de la
        # replica del ERP queda fisicamente en solo lectura.
        conn = sqlite3.connect(f"file:{ruta.resolve()}?mode=ro", uri=True, timeout=10)
        try:
            return pd.read_sql_query(conector.consulta, conn)
        finally:
            conn.close()
    if motor == "duckdb":
        import duckdb
        ruta = _resolver_fuente(cfg, conector)
        if not ruta.exists():
            raise FileNotFoundError(f"No existe la BD duckdb: {ruta}")
        validar_solo_lectura(conector.consulta)
        conn = duckdb.connect(str(ruta), read_only=True)
        try:
            return conn.execute(conector.consulta).fetchdf()
        finally:
            conn.close()
    if motor == "csv":
        ruta = _resolver_fuente(cfg, conector)
        if not ruta.exists():
            raise FileNotFoundError(f"No existe el CSV: {ruta}")
        return pd.read_csv(ruta, **conector.parametros)
    if motor == "excel":
        ruta = _resolver_fuente(cfg, conector)
        if not ruta.exists():
            raise FileNotFoundError(f"No existe el Excel: {ruta}")
        kwargs = {}
        if conector.hoja is not None:
            kwargs["sheet_name"] = conector.hoja
        return pd.read_excel(ruta, **kwargs)
    if motor == "url":
        url = str(conector.fuente or "")
        if not url:
            raise ValueError("Un conector url requiere una URL")
        return pd.read_csv(url, **conector.parametros)
    raise ValueError(f"Motor de conector no soportado: '{motor}'")


def _string_a_detalle(df: pd.DataFrame, tipo: str) -> pd.DataFrame:
    """Normalizacion basica de tipos para datasets provenientes de conectores."""
    df = df.loc[:, ~df.columns.duplicated()].copy()
    if tipo in ("facturas", "ventas"):
        if "fecha" in df.columns:
            df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        for col in ("total", "descuento"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    if tipo == "clientes" and "fecha_registro" in df.columns:
        df["fecha_registro"] = pd.to_datetime(df["fecha_registro"], errors="coerce")
    for col in ("id", "cliente_id", "vehiculo_id", "servicio_id"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def ejecutar_conectores(cfg: AppConfig, ya_cargados: Optional[set] = None):
    """Ejecuta todos los conectores del workspace.

    Devuelve ``(datos, errores)``:
      - ``datos``: {dataset canónico: DataFrame}
      - ``errores``: {nombre conector: mensaje}

    Los conectores con ``forzar: false`` solo pueblan datasets que el ETL de
    archivos no haya cargado (gap-filling); con ``forzar: true`` reemplazan la
    fuente local.
    """
    datos: Dict[str, pd.DataFrame] = {}
    errores: Dict[str, str] = {}
    ya = set(ya_cargados or ())
    for c in parsear_conectores(cfg):
        if c.dataset in ya and not c.forzar:
            continue
        try:
            df = conectar(cfg, c)
            if not df.empty:
                datos[c.dataset] = _string_a_detalle(df, c.dataset)
        except Exception as e:  # noqa: BLE001
            log.warning("Conector %s fallo: %s", c.nombre, _mensaje_error(e))
            errores[c.nombre] = _mensaje_error(e)
    return datos, errores


def sincronizar_conectores(cfg: AppConfig, store=None) -> List[dict]:
    """Trae los conectores al almacén DuckDB y devuelve el resumen por conector."""
    from ..storage import DataStore
    cerrar = store is None
    if store is None:
        store = DataStore(cfg.db_path, cfg.cache_dir, usar_cache=cfg.usar_cache)
    resumen: List[dict] = []
    try:
        datos, errores = ejecutar_conectores(cfg)
        for dataset, df in datos.items():
            store.registrar_tabla(dataset, df)
        conectores = {c.nombre: c for c in parsear_conectores(cfg)}
        for dataset, df in datos.items():
            conector = conectores.get(dataset) or next(
                (c for c in conectores.values() if c.dataset == dataset), None)
            resumen.append({
                "nombre": conector.nombre if conector else dataset,
                "dataset": dataset, "filas": len(df),
                "ok": True, "error": None,
            })
        for nombre, err in errores.items():
            conector = conectores.get(nombre)
            resumen.append({
                "nombre": nombre, "dataset": conector.dataset if conector else nombre,
                "filas": 0, "ok": False, "error": err,
            })
        return resumen
    finally:
        if cerrar:
            store.cerrar()


# ----------------------------------------------------------------------
#  Snapshot "ERP" y gestion del config
# ----------------------------------------------------------------------

def crear_snapshot_erp(cfg: AppConfig, destino: Optional[Path] = None,
                       sobreescribir: bool = True):
    """Exporta los datasets del workspace a un archivo SQLite.

    Simula la exportación/replica de lectura de un ERP comercial. Cada dataset
    viaja como una tabla (con las columnas canónicas) y se guarda una tabla
    ``giro_metadatos`` con la información de la exportación.
    """
    import sqlite3

    from ..data_loader import load_all

    destino = Path(destino) if destino else cfg.directorio_datos / "erp.sqlite"
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and not sobreescribir:
        raise FileExistsError(f"Ya existe {destino}")

    datos = load_all(cfg)
    conectados, _ = ejecutar_conectores(cfg)
    datos.update(conectados)

    conectores_ok = not getattr(cfg, "conectores", None) or any(
        c.motor in MOTORES_LOCALES and (_resolver_fuente(cfg, c).exists()
                                        or str(c.fuente or "").startswith("http"))
        for c in parsear_conectores(cfg))

    with contextlib.closing(sqlite3.connect(str(destino))) as conn, conn:
        conteos = {}
        for nombre, df in datos.items():
            if df is None or df.empty or not nombre:
                continue
            # identificador del ERP: mismo criterio estricto que el store
            nombre_tabla = re.sub(r"\W+", "_", str(nombre)).strip("_").lower()
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", nombre_tabla or ""):
                log.warning("Dataset %r con nombre no valido para SQLite; se omite",
                            nombre)
                continue
            df.to_sql(nombre_tabla, conn, if_exists="replace", index=False)
            conteos[nombre] = int(len(df))

        metas = []
        for nombre, n in conteos.items():
            metas.append({
                "dataset": nombre, "filas": n,
                "exportado_el": datetime.now().isoformat(timespec="seconds"),
                "workspace": cfg.clave,
            })
        pd.DataFrame(metas).to_sql("giro_metadatos", conn, if_exists="replace", index=False)

    log.info("Snapshot ERP creado en %s (%d datasets)", destino, len(conteos))
    return destino, conteos


def conectores_desde_snapshot(cfg: AppConfig, ruta: Path) -> List[dict]:
    """Genera la lista de conectores (sqlite, forzar=true) para un snapshot."""
    import sqlite3
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el snapshot: {ruta}")
    conn = sqlite3.connect(f"file:{ruta.resolve()}?mode=ro", uri=True)
    try:
        tablas = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name <> 'giro_metadatos' ORDER BY name").fetchall()
        ]
    finally:
        conn.close()
    try:
        relativa = ruta.relative_to(cfg.directorio_datos)
    except ValueError:
        relativa = ruta
    # Solo tablas con nombre de identificador normal: el nombre viaja al
    # SQL del conector y al nombre del dataset.
    seguras = [t for t in tablas
               if re.fullmatch(r"[a-z_][a-z0-9_]*", str(t).lower())]
    if len(seguras) != len(tablas):
        log.warning("Se ignoran %d tabla(s) de nombre no estandar en el snapshot",
                    len(tablas) - len(seguras))
    return [
        {
            "nombre": f"erp_{t}",
            "motor": "sqlite",
            "fuente": str(relativa),
            "consulta": f'SELECT * FROM "{t}"',
            "dataset": t,
            "forzar": True,
        }
        for t in seguras
    ]


def ruta_config_workspace(cfg: AppConfig) -> Path:
    """Ruta del config.yaml del workspace activo."""
    base = Path(__file__).resolve().parent.parent.parent
    if cfg.clave and cfg.clave != "principal":
        return base / "workspaces" / cfg.clave / "config" / "config.yaml"
    return base / "config" / "config.yaml"


def escribir_conectores(cfg: AppConfig, conectores: list, reemplazar: bool = False):
    """Persiste (merge o reemplazo) la lista de conectores en el config."""
    ruta = ruta_config_workspace(cfg)
    raw = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    existentes = raw.get("conectores") or []
    nuevos = [] if reemplazar else [c for c in existentes if isinstance(c, dict)]
    vistos = {json.dumps(c, default=str, sort_keys=True) for c in nuevos}
    for c in conectores:
        clave = json.dumps(c, default=str, sort_keys=True)
        if clave not in vistos and c.get("nombre"):
            nuevos.append(c)
            vistos.add(clave)
    raw["conectores"] = nuevos
    ruta.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    return ruta, nuevos