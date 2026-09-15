"""Capa de persistencia escalable.

Motor: DuckDB (SQL embebido de alta velocidad) + caché en columna parquet y
roundtrip a pandas para el resto del sistema. Soportando de forma natural
conjuntos de millones de filas sin servidor ni configuracion extra.

Estructura del almacen:
  * ``main.*``      -> tablas "tal cual" cargadas (`registrar_tabla`).
  * ``core.*``      -> tablas normalizadas con claves primarias/foraneas.
  * ``analitica.*`` -> vistas desnormalizadas para los paneles.
"""

from __future__ import annotations

import duckdb
import pandas as pd
from pathlib import Path
from typing import Any, Dict, Optional

from .schema import (
    ORDEN_CARGA,
    SQL_ARRANQUE,
    VISTAS_ANALITICA,
    ddl_tabla_core,
)


class DataStore:
    def __init__(self, db_path: Path, cache_dir: Optional[Path] = None, usar_cache: bool = True):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_dir = Path(cache_dir) if cache_dir else Path(db_path).parent / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.usar_cache = usar_cache
        self._conn = duckdb.connect(str(self.db_path))
        for stmt in SQL_ARRANQUE:
            self._conn.execute(stmt)

    # ---------- registro y consulta ----------
    def registrar_tabla(self, nombre: str, df: pd.DataFrame, sobreescribir: bool = True, cache: bool = True):
        clean = self._saneada(df)
        nombre = self._nombre_valido(nombre)
        if sobreescribir:
            self._conn.execute(f'DROP TABLE IF EXISTS "{nombre}"')
        self._conn.register("__df_tmp", clean)
        self._conn.execute(f'CREATE OR REPLACE TABLE "{nombre}" AS SELECT * FROM __df_tmp')
        self._conn.unregister("__df_tmp")
        if cache and self.usar_cache:
            archivo_cache = self.cache_dir / f"{nombre}.parquet"
            clean.to_parquet(archivo_cache, index=False)
        return nombre

    def registrar_tablas(self, tablas: dict[str, pd.DataFrame]):
        for nombre, df in tablas.items():
            self.registrar_tabla(nombre, df)

    def consulta(self, sql: str) -> pd.DataFrame:
        return self._conn.execute(sql).fetchdf()

    def ejecutar(self, sql: Any) -> None:
        """Ejecuta una o varias sentencias SQL (DDL/DML) sin devolver datos."""
        if isinstance(sql, str):
            sql = [sql]
        for stmt in sql:
            self._conn.execute(stmt)

    # ---------- esquema normalizado (core) y analitica ----------

    def construir_estructura(self, tablas: Dict[str, pd.DataFrame]) -> Dict[str, int]:
        """Materializa ``core.*`` con claves y crea las vistas ``analitica.*``.

        Devuelve ``{tabla: filas}`` del esquema core. Si la carga con claves
        falla (datos referencialmente imperfectos), se reconstruye el esquema
        completo sin claves para no perder informacion.
        """
        self.ejecutar(SQL_ARRANQUE)
        for nombre in reversed(ORDEN_CARGA):
            self.ejecutar(f'DROP TABLE IF EXISTS core."{nombre}" CASCADE')

        con_claves = True
        for nombre in ORDEN_CARGA:
            df = tablas.get(nombre)
            if df is None or df.empty:
                continue
            df = self._saneada(df)
            self._conn.register("__tmp_core", df)
            try:
                self.ejecutar(ddl_tabla_core(nombre, df, con_claves=con_claves))
                self._conn.execute(f'INSERT INTO core."{nombre}" SELECT * FROM __tmp_core')
            except Exception:
                con_claves = False
                self._conn.unregister("__tmp_core")
                break
            self._conn.unregister("__tmp_core")

        if not con_claves:
            for nombre in reversed(ORDEN_CARGA):
                self.ejecutar(f'DROP TABLE IF EXISTS core."{nombre}" CASCADE')
            for nombre in ORDEN_CARGA:
                df = tablas.get(nombre)
                if df is None or df.empty:
                    continue
                df = self._saneada(df)
                self.ejecutar(ddl_tabla_core(nombre, df, con_claves=False))
                self._conn.register("__tmp_core", df)
                self._conn.execute(f'INSERT INTO core."{nombre}" SELECT * FROM __tmp_core')
                self._conn.unregister("__tmp_core")

        for vista in VISTAS_ANALITICA.values():
            self.ejecutar(vista)

        return {
            nombre: len(tablas[nombre])
            for nombre in ORDEN_CARGA
            if nombre in tablas and tablas[nombre] is not None and not tablas[nombre].empty
        }

    def consultar_vista(self, nombre: str) -> pd.DataFrame:
        """Consulta una vista del esquema ``analitica``."""
        return self._conn.execute(f'SELECT * FROM analitica."{self._nombre_valido(nombre)}"').fetchdf()

    def info_estructura(self) -> pd.DataFrame:
        """Catalogo del almacen: esquema, objeto y tipo (tabla/vista)."""
        sql = """
        SELECT table_schema AS esquema, table_name AS objeto, table_type AS tipo
        FROM information_schema.tables
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
        ORDER BY 1, 2
        """
        return self._conn.execute(sql).fetchdf()

    def tabla(self, nombre: str) -> pd.DataFrame:
        return self._conn.execute(f'SELECT * FROM "{nombre}"').fetchdf()

    def leer_cache(self, nombre: str) -> Optional[pd.DataFrame]:
        archivo = self.cache_dir / f"{self._nombre_valido(nombre)}.parquet"
        if archivo.exists():
            return pd.read_parquet(archivo)
        return None

    def listar_tablas(self) -> list[str]:
        return [r[0] for r in self._conn.execute("SHOW TABLES").fetchall()]

    def existe_tabla(self, nombre: str) -> bool:
        return self._nombre_valido(nombre) in self.listar_tablas()

    def query_one(self, sql: str) -> Any:
        return self._conn.execute(sql).fetchone()

    def cerrar(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cerrar()

    # ---------- utilidades ----------
    @staticmethod
    def _nombre_valido(nombre: str) -> str:
        return str(nombre).strip().lower().replace(" ", "_")

    @staticmethod
    def _saneada(df: pd.DataFrame) -> pd.DataFrame:
        """Convierte columnas con tipos incompatibles antes de insertar en DuckDB."""
        limpio = df.copy()
        for col in limpio.columns:
            if limpio[col].dtype == "object":
                muestras_nulos = limpio[col].isna().sum()
                if limpio[col].dropna().empty:
                    limpio[col] = limpio[col].fillna("")
                else:
                    # si es una columna de texto con mezcla, forzar str
                    limpio[col] = limpio[col].where(limpio[col].notna(), "").astype(str)
            elif pd.api.types.is_datetime64_any_dtype(limpio[col]):
                limpio[col] = limpio[col].astype("datetime64[us]")
            elif pd.api.types.is_bool_dtype(limpio[col]):
                limpio[col] = limpio[col].astype("boolean")
        return limpio