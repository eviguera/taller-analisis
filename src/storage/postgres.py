"""Segundo implementador de `PuertoAlmacen`: PostgreSQL.

Mismo contrato que ``DataStore`` (DuckDB embebido), otro motor. El esquema
``core``/``analitica`` y su orquestacion son compartidos
(``store.construir_estructura_compartida``); lo que cambia es el SQL, que
aporta ``DialectoPostgres``.

Aislamiento multi-tenant (regla 1): la unidad de aislamiento es la base de
datos, equivalente al fichero ``.duckdb`` por workspace de DuckDB — un
``AlmacenPostgres`` por workspace (``GIRO_PG_DBNAME`` o ``dbname=``), con
sus esquemas ``main``/``core``/``analitica``/``giro_meta`` dentro.

Seguridad (reglas 2 y 4):
  * credenciales solo desde ``os.environ`` (``GIRO_PG_*``) o argumentos
    explicitos del llamador; nunca en el codigo, ni por defecto;
  * todo valor via bind (``%s``); los identificadores dinámicos pasan por
    ``_nombre_valido`` (allowlist) y ``_columna`` (entre comillas, con ``"``
    duplicada); las listas de columnas salen del catalogo, no del input.

Nota sobre ``%``: psycopg2 solo procesa placeholders cuando se le pasan
parametros. Las consultas de usuario de ``consulta()`` van sin parametros,
asi que un ``LIKE '%...%'`` literal no se toca.
"""

from __future__ import annotations

import logging
import math
import os
from typing import Any, Dict, Iterator, Optional, Tuple

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.errors
from psycopg2.extras import execute_values

from ..puertos import PuertoAlmacen
from .dialecto import DialectoPostgres
from .store import (
    DataStore,
    construir_estructura_compartida,
    registrar_tabla_core_compartido,
)

log = logging.getLogger("taller.storage")


def _de_entorno(clave: str) -> Optional[str]:
    """Valor de ``GIRO_PG_*`` del entorno, o ``None`` si no esta puesto."""
    return os.environ.get(clave, "").strip() or None


def _celda(valor: Any) -> Any:
    """Convierte una celda de pandas a un tipo python que psycopg2 adapta.

    psycopg2 no sabe adaptar escalares de numpy ni ``NaT``/``NA``: sin esta
    conversion el INSERT se cae con ``can't adapt type``. Los nulos van a
    ``None`` (NULL), igual que los trata DuckDB.
    """
    if valor is None or valor is pd.NaT or valor is pd.NA:
        return None
    if isinstance(valor, float) and math.isnan(valor):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.to_pydatetime()
    if isinstance(valor, np.generic):
        return valor.item()
    return valor


def _filas(df: pd.DataFrame) -> Iterator[Tuple[Any, ...]]:
    """Filas del dataframe, celda a celda, listas para ``execute_values``."""
    for fila in df.itertuples(index=False, name=None):
        yield tuple(_celda(v) for v in fila)


class AlmacenPostgres(PuertoAlmacen):
    """Almacen analitico sobre PostgreSQL (un servidor, un esquema por base).

    Implementa `PuertoAlmacen`. Los metodos internos (`ejecutar`,
    `columnas`, `listar_tablas`, `existe_tabla`, `insertar_dataframe`)
    son el lado opuesto a los homólogos de ``DataStore``: la orquestacion
    compartida los llama por igual en los dos motores.
    """

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None,
                 user: Optional[str] = None, password: Optional[str] = None,
                 dbname: Optional[str] = None,
                 timeout_segundos: int = 5):
        """Conexion a PostgreSQL. Sin secretos por defecto: todo por
        argumento o por ``GIRO_PG_HOST/PORT/USER/PASSWORD/DBNAME``.

        La password no tiene valor por defecto ni siquica en el entorno
        obligatorio: si no llega, decide libpq (PGPASSWORD, .pgpass,
        trust). En ningun caso se escribe una credencial aqui.
        """
        self.vistas_fallidas: list[str] = []
        self.dialecto = DialectoPostgres()
        self._conn = None
        parametros = {
            "host": host if host is not None else _de_entorno("GIRO_PG_HOST"),
            "port": port if port is not None else _de_entorno("GIRO_PG_PORT"),
            "user": user if user is not None else _de_entorno("GIRO_PG_USER"),
            "password": password if password is not None else _de_entorno("GIRO_PG_PASSWORD"),
            "dbname": dbname if dbname is not None else _de_entorno("GIRO_PG_DBNAME"),
        }
        try:
            self._conn = psycopg2.connect(
                **{k: v for k, v in parametros.items() if v is not None},
                connect_timeout=timeout_segundos,
            )
            # Autocommit: DDL y cargas se confirman solos, igual que cada
            # `execute` de DuckDB; no hay transaccion abierta que dejar
            # colgada si algo falla a mitad de construir_estructura.
            self._conn.autocommit = True
            for stmt in self.dialecto.sql_arranque():
                self.ejecutar(stmt)
        except Exception:
            # El constructor no puede dejar una conexion abierta a medias.
            self.cerrar()
            raise

    # ---------- registro ----------

    def registrar_tabla(self, nombre: str, df: pd.DataFrame,
                        sobreescribir: bool = True, cache: bool = True) -> str:
        """Carga un dataframe como tabla ``main.<nombre>``.

        Como en DuckDB, la tabla queda reescrita siempre: el ``CREATE OR
        REPLACE TABLE`` de DuckDB sustituye la tabla entera, de modo que
        ``sobreescribir=False`` no conserva filas previas en ninguno de los
        dos motores. ``cache`` no aplica: la cache parquet es exclusiva de
        DuckDB.
        """
        clean = self._saneada(df)
        nombre = self._nombre_valido(nombre)
        self.ejecutar(f'DROP TABLE IF EXISTS main.{self._columna(nombre)}')
        self.ejecutar(self.dialecto.ddl_tabla("main", nombre, clean,
                                              con_claves=False))
        self.insertar_dataframe("main", nombre, clean)
        return nombre

    def registrar_tablas(self, tablas: Dict[str, pd.DataFrame]) -> None:
        for nombre, df in tablas.items():
            self.registrar_tabla(nombre, df)

    def registrar_tabla_core(self, nombre: str, df: pd.DataFrame,
                             con_claves: bool = True) -> str:
        """Materializa una tabla derivada en ``core`` (misma orquestacion
        compartida que DuckDB: claves si pueden, sin claves si no)."""
        return registrar_tabla_core_compartido(self, nombre, df,
                                               con_claves=con_claves)

    def insertar_dataframe(self, esquema: str, nombre: str,
                           df: pd.DataFrame) -> None:
        """Inserta ``df`` en ``esquema.nombre`` con bind parameters.

        Columnas explicitas (nombres y orden escritos en el SQL) y valores
        siempre como ``%s``: nunca se interpolan literales de datos.
        """
        esquema = self._nombre_valido(esquema)
        nombre = self._nombre_valido(nombre)
        if df.empty:
            return  # el DDL ya creo la tabla; no hay nada que insertar
        columnas = ", ".join(self._columna(c) for c in df.columns)
        sql = (f'INSERT INTO {self._columna(esquema)}.{self._columna(nombre)} '
               f'({columnas}) VALUES %s')
        with self._conn.cursor() as cur:
            execute_values(cur, sql, _filas(df), page_size=1000)

    # ---------- firma de la ultima carga ----------

    def firma_carga(self, clave: str = "datos") -> str:
        """Firma guardada de la ultima carga, o '' si no la hay."""
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT firma FROM giro_meta.carga WHERE clave = %s",
                    (clave,))
                fila = cur.fetchone()
        except psycopg2.errors.UndefinedTable:
            # La tabla de firmas aun no existe: misma respuesta que el
            # almacen DuckDB. Cualquier otro error SQL sube y se ve.
            return ""
        return fila[0] if fila else ""

    def guardar_firma(self, firma: str, clave: str = "datos") -> None:
        """Persiste la firma de la ultima carga en el propio almacen."""
        self.ejecutar(
            'CREATE TABLE IF NOT EXISTS giro_meta.carga '
            '(clave VARCHAR PRIMARY KEY, firma VARCHAR)')
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM giro_meta.carga WHERE clave = %s",
                        (clave,))
            cur.execute(
                "INSERT INTO giro_meta.carga (clave, firma) VALUES (%s, %s)",
                (clave, firma))

    # ---------- esquema y consulta ----------

    def construir_estructura(self, tablas: Dict[str, pd.DataFrame]) -> Dict[str, int]:
        """Materializa ``core.*`` y crea las vistas ``analitica.*``.

        Misma orquestacion que DuckDB (orden ``ORDEN_CARGA``, fallback sin
        PK/FK, vistas que no abortan el ETL); el SQL lo aporta
        ``DialectoPostgres``.
        """
        return construir_estructura_compartida(self, tablas)

    def ejecutar(self, sql: Any) -> None:
        """Ejecuta una o varias sentencias SQL (DDL/DML) sin devolver datos.

        Los identificadores interpolados ya vienen validados por
        ``_nombre_valido``/``_columna`` y aqui no se pasan parametros: una
        vista (DROP + CREATE) viaja como una sola cadena, que psycopg2
        ejecuta de corrido.
        """
        if isinstance(sql, str):
            sql = [sql]
        with self._conn.cursor() as cur:
            for stmt in sql:
                cur.execute(stmt)

    def consulta(self, sql: str) -> pd.DataFrame:
        """Ejecuta una consulta PostgreSQL y devuelve un dataframe.

        SQL arbitrario del dialecto del adaptador: validar que es de solo
        lectura le toca al llamador
        (``src/core/conector_sql.validar_solo_lectura``), como dicta el
        puerto.
        """
        with self._conn.cursor() as cur:
            cur.execute(sql)
            filas = cur.fetchall()
            columnas = [d[0] for d in cur.description] if cur.description else []
        return pd.DataFrame(filas, columns=columnas)

    def columnas(self, esquema: str, nombre: str) -> list[str]:
        """Columnas de un objeto del almacen, leidas del catalogo.

        Alimenta ``SELECT`` explicitos: la lista sale del
        ``information_schema`` (con su orden), no del orden que tenga el
        DataFrame en memoria. Esquema y nombre van como bind.
        """
        esquema = self._nombre_valido(esquema)
        nombre = self._nombre_valido(nombre)
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s "
                "ORDER BY ordinal_position",
                (esquema, nombre))
            filas = cur.fetchall()
        return [str(f[0]) for f in filas]

    def consultar_vista(self, nombre: str) -> pd.DataFrame:
        """Consulta una vista del esquema ``analitica``."""
        nombre = self._nombre_valido(nombre)
        columnas = self.columnas("analitica", nombre)
        if not columnas:
            raise ValueError(f"Vista sin columnas: analitica.{nombre}")
        cols_str = ", ".join(self._columna(c) for c in columnas)
        return self.consulta(
            f'SELECT {cols_str} FROM analitica.{self._columna(nombre)}')

    def consultar_objeto(self, esquema: str, nombre: str) -> pd.DataFrame:
        """Lee ``<esquema>.<nombre>`` con lista explicita de columnas."""
        columnas = self.columnas(esquema, nombre)
        if not columnas:
            raise ValueError(f"Objeto sin columnas: {esquema}.{nombre}")
        lista = ", ".join(self._columna(c) for c in columnas)
        return self.consulta(
            f'SELECT {lista} FROM {self._columna(esquema)}.{self._columna(nombre)}')

    def info_estructura(self) -> pd.DataFrame:
        """Catalogo del almacen: esquema, objeto y tipo (tabla/vista)."""
        # Mismo SQL que el almacen DuckDB: information_schema comun.
        return self.consulta("""
        SELECT table_schema AS esquema, table_name AS objeto, table_type AS tipo
        FROM information_schema.tables
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog', 'giro_meta')
        ORDER BY 1, 2
        """)

    def tabla(self, nombre: str) -> pd.DataFrame:
        nombre = self._nombre_valido(nombre)
        if not self.existe_tabla(nombre):
            raise ValueError(f"Tabla no existe: {nombre}")
        columnas = self.columnas("main", nombre)
        cols_str = ", ".join(self._columna(c) for c in columnas)
        return self.consulta(
            f'SELECT {cols_str} FROM main.{self._columna(nombre)}')

    # ---------- catalogo interno ----------

    def listar_tablas(self) -> list[str]:
        """Tablas del esquema ``main`` (el equivalente al esquema por
        defecto de DuckDB, cuyo ``SHOW TABLES`` solo lista el actual)."""
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND table_type = %s",
                ("main", "BASE TABLE"))
            filas = cur.fetchall()
        return [str(f[0]) for f in filas]

    def existe_tabla(self, nombre: str) -> bool:
        return self._nombre_valido(nombre) in self.listar_tablas()

    # ---------- ciclo de vida ----------

    def cerrar(self) -> None:
        """Libera la conexion. Idempotente."""
        if self._conn is None or self._conn.closed:
            return
        try:
            self._conn.close()
        except psycopg2.Error as e:
            log.warning("Error al cerrar conexion PostgreSQL: %s", e)

    # ---------- utilidades (mismas que DuckDB, una sola fuente) ----------
    # El saneo y la validacion de identificadores viven en DataStore: si
    # cada motor tuviera el suyo, los dataframes y los nombres podrian
    # divergir y las vistas dejarian de cuadrar.

    @staticmethod
    def _nombre_valido(nombre: str) -> str:
        """Normaliza y valida un identificador (allowlist). Ver
        ``DataStore._nombre_valido``."""
        return DataStore._nombre_valido(nombre)

    @staticmethod
    def _saneada(df: pd.DataFrame) -> pd.DataFrame:
        """Mismo saneo que DuckDB. Ver ``DataStore._saneada``."""
        return DataStore._saneada(df)

    @staticmethod
    def _columna(col: str) -> str:
        """Identificador entre comillas (``"`` duplicada). Ver
        ``DataStore._columna``."""
        return DataStore._columna(col)


__all__ = ["AlmacenPostgres"]
