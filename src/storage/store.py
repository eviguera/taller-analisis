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

import logging
import re

import duckdb
import pandas as pd
from pathlib import Path
from typing import Any, Dict, Optional

from ..puertos import PuertoAlmacen
from .dialecto import DialectoDuckDB
from .schema import ORDEN_CARGA

log = logging.getLogger("taller.storage")


# ------------------------------------------------------------------
#  Orquestacion del esquema, compartida por los adaptadores
#  (DuckDB y PostgreSQL). El motor aporta `dialecto`, `ejecutar`,
#  `insertar_dataframe`, `existe_tabla`, `tabla`, `registrar_tabla_core`
#  y `vistas_fallidas`; el orden, el fallback sin claves y las vistas
#  no destructivas viven aqui, una sola vez.
# ------------------------------------------------------------------

def registrar_tabla_core_compartido(almacen: "DataStore", nombre: str,
                                    df: pd.DataFrame,
                                    con_claves: bool = True) -> str:
    """Materializa una tabla derivada en ``core`` con claves (o sin ellas).

    Si la carga con claves falla (datos referencialmente imperfectos),
    reintenta sin claves para no perder informacion. Si tambien falla,
    lanza ``ValueError`` con todos los errores: ninguno se traga.
    """
    nombre = almacen._nombre_valido(nombre)
    clean = almacen._saneada(df)
    almacen.ejecutar(f'DROP TABLE IF EXISTS core."{nombre}" CASCADE')
    errores = []
    for claves in (con_claves, False):
        try:
            almacen.ejecutar(
                almacen.dialecto.ddl_tabla_core(nombre, clean, con_claves=claves))
            almacen.insertar_dataframe("core", nombre, clean)
            return nombre
        except Exception as e:  # noqa: BLE001 — se recoge y se relanza abajo
            errores.append(str(e))
    raise ValueError(f"No se pudo registrar core.{nombre}: " + " | ".join(errores))


def construir_estructura_compartida(almacen: "DataStore",
                                    tablas: Dict[str, pd.DataFrame]) -> Dict[str, int]:
    """Materializa ``core.*`` con claves y crea las vistas ``analitica.*``.

    Devuelve ``{tabla: filas}`` del esquema core. Si la carga con claves
    falla (datos referencialmente imperfectos), se reconstruye el esquema
    completo sin claves para no perder informacion. Una vista que
    referencie un objeto inexistente (p. ej. un workspace sin
    factura_detalle) no aborta el ETL: se registra en
    ``almacen.vistas_fallidas`` y se continua con las demas.
    """
    dialecto = almacen.dialecto
    almacen.ejecutar(dialecto.sql_arranque())
    # Es dependiente (FK hacia facturas/clientes): se elimina primero.
    almacen.ejecutar('DROP TABLE IF EXISTS core."factura_detalle" CASCADE')
    for nombre in reversed(ORDEN_CARGA):
        almacen.ejecutar(f'DROP TABLE IF EXISTS core."{nombre}" CASCADE')

    con_claves = True
    for nombre in ORDEN_CARGA:
        df = tablas.get(nombre)
        if df is None or df.empty:
            continue
        df = almacen._saneada(df)
        try:
            almacen.ejecutar(
                dialecto.ddl_tabla_core(nombre, df, con_claves=con_claves))
            almacen.insertar_dataframe("core", nombre, df)
        except Exception as e:  # noqa: BLE001 — fallback visible, no un pass
            log.warning(
                "Fallo al crear tabla %s con claves (%s). "
                "Reintentando sin PK/FK — puede indicar datos duplicados o huerfanos.",
                nombre, e,
            )
            con_claves = False
            break

    if not con_claves:
        for nombre in reversed(ORDEN_CARGA):
            almacen.ejecutar(f'DROP TABLE IF EXISTS core."{nombre}" CASCADE')
        for nombre in ORDEN_CARGA:
            df = tablas.get(nombre)
            if df is None or df.empty:
                continue
            df = almacen._saneada(df)
            almacen.ejecutar(dialecto.ddl_tabla_core(nombre, df, con_claves=False))
            almacen.insertar_dataframe("core", nombre, df)

    # Hechos relacionales: provienen de main."factura_detalle" (cargada
    # por el pipeline). Se materializan en core tras las dimensiones para
    # que sus claves foraneas sean validas y las vistas puedan leerlos.
    if almacen.existe_tabla("factura_detalle"):
        hechos = almacen.tabla("factura_detalle")
        almacen.registrar_tabla_core("factura_detalle", hechos)

    # Vistas: una que referencie un objeto inexistente (p. ej. un
    # workspace sin factura_detalle) no debe abortar todo el ETL; se
    # registra y se continua con las demas.
    vistas_fallidas = []
    for nombre_vista, vista in dialecto.vistas().items():
        try:
            almacen.ejecutar(vista)
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo crear la vista %s: %s", nombre_vista, e)
            vistas_fallidas.append(nombre_vista)
    almacen.vistas_fallidas = vistas_fallidas

    return {
        nombre: len(tablas[nombre])
        for nombre in ORDEN_CARGA
        if nombre in tablas and tablas[nombre] is not None and not tablas[nombre].empty
    }


class DataStore(PuertoAlmacen):
    """Almacen analitico sobre DuckDB embebido.

    Implementa `PuertoAlmacen`: el resto del sistema depende del contrato,
    no de este motor. Los metodos que no estan en el puerto (`ejecutar`,
    `columnas`, `listar_tablas`, `existe_tabla`, `query_one`, `leer_cache`)
    son detalle interno de esta implementacion.
    """

    def __init__(self, db_path: Path, cache_dir: Optional[Path] = None, usar_cache: bool = True):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_dir = Path(cache_dir) if cache_dir else Path(db_path).parent / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.usar_cache = usar_cache
        self.vistas_fallidas: list[str] = []
        self.dialecto = DialectoDuckDB()
        self._conn = duckdb.connect(str(self.db_path))
        for stmt in self.dialecto.sql_arranque():
            self._conn.execute(stmt)

    # ---------- registro y consulta ----------
    @classmethod
    def _lista_columnas(cls, df: pd.DataFrame) -> str:
        """Columnas del dataframe entre comillas, para DDL/DML explicito.

        El ``SELECT *`` meta las columnas en el orden que tenga el DataFrame:
        si el DDL y el dataframe no calzan, el INSERT falla o rellena columna
        a columna en otro orden. Lista explicita (y con lista de columnas en
        el INSERT): el contrato queda escrito y el desalineamiento se ve.
        """
        return ", ".join(cls._columna(c) for c in df.columns)

    def registrar_tabla(self, nombre: str, df: pd.DataFrame, sobreescribir: bool = True, cache: bool = True):
        clean = self._saneada(df)
        nombre = self._nombre_valido(nombre)
        if sobreescribir:
            self._conn.execute(f'DROP TABLE IF EXISTS "{nombre}"')
        self._conn.register("__df_tmp", clean)
        columnas = self._lista_columnas(clean)
        self._conn.execute(
            f'CREATE OR REPLACE TABLE "{nombre}" AS SELECT {columnas} FROM __df_tmp')
        self._conn.unregister("__df_tmp")
        if cache and self.usar_cache:
            archivo_cache = self.cache_dir / f"{nombre}.parquet"
            clean.to_parquet(archivo_cache, index=False)
        return nombre

    def registrar_tablas(self, tablas: dict[str, pd.DataFrame]):
        for nombre, df in tablas.items():
            self.registrar_tabla(nombre, df)

    # ---------- firma de la ultima carga (evita reconstruir sin cambios) ----------

    def firma_carga(self, clave: str = "datos") -> str:
        """Firma guardada de la ultima carga, o '' si no la hay."""
        try:
            fila = self._conn.execute(
                "SELECT firma FROM giro_meta.carga WHERE clave=?", [clave]
            ).fetchone()
        except duckdb.Error:
            return ""
        return fila[0] if fila else ""

    def guardar_firma(self, firma: str, clave: str = "datos") -> None:
        """Persiste la firma de la ultima carga en el propio almacen."""
        self.ejecutar(
            'CREATE TABLE IF NOT EXISTS giro_meta.carga '
            '(clave VARCHAR PRIMARY KEY, firma VARCHAR)')
        self._conn.execute("DELETE FROM giro_meta.carga WHERE clave=?", [clave])
        self._conn.execute(
            "INSERT INTO giro_meta.carga VALUES (?, ?)", [clave, firma])

    def registrar_tabla_core(self, nombre: str, df: pd.DataFrame, con_claves: bool = True) -> str:
        """Registra una tabla derivada en el esquema ``core`` con claves.

        Util para los hechos relacionales (``factura_detalle``) construidos
        por el pipeline y que no provienen de un archivo fuente. Si la carga
        con claves falla (datos referencialmente imperfectos), reintenta sin
        claves para no perder informacion.

        La orquestacion es la misma que usa el adaptador PostgreSQL:
        ``registrar_tabla_core_compartido``.
        """
        return registrar_tabla_core_compartido(self, nombre, df, con_claves=con_claves)

    def insertar_dataframe(self, esquema: str, nombre: str, df: pd.DataFrame) -> None:
        """Inserta ``df`` en ``esquema.nombre`` con lista explicita de columnas.

        El dataframe va registrado como tabla temporal de DuckDB y el
        INSERT selecciona de ella: el contrato de columnas (nombres y
        orden) queda escrito en el SQL, igual que en ``registrar_tabla``.
        """
        esquema = self._nombre_valido(esquema)
        nombre = self._nombre_valido(nombre)
        self._conn.register("__tmp_core", df)
        try:
            columnas = self._lista_columnas(df)
            self._conn.execute(
                f'INSERT INTO {esquema}.{self._columna(nombre)} ({columnas}) '
                f'SELECT {columnas} FROM __tmp_core')
        finally:
            self._conn.unregister("__tmp_core")

    def consulta(self, sql: str) -> pd.DataFrame:
        # Camino de SQL arbitrario (consola). Ademas de la denylist de
        # conector_sql, se corta el acceso externo de DuckDB: sin esto,
        # read_text('/etc/...'), sniff_csv o un FROM con literal de ruta
        # leen ficheros del servidor pese a pasar la validacion.
        try:
            self._conn.execute("SET enable_external_access=false")
        except duckdb.Error as e:
            import logging
            logging.getLogger("taller.storage").warning(
                "No se pudo restringir el acceso externo de DuckDB: %s", e)
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

        La orquestacion (orden de carga, fallback sin PK/FK, vistas no
        destructivas) es la misma que usa el adaptador PostgreSQL:
        ``construir_estructura_compartida``; aqui solo cambia el SQL, que
        aporta ``self.dialecto``.
        """
        return construir_estructura_compartida(self, tablas)

    @staticmethod
    def _columna(col: str) -> str:
        """Identificador de columna entre comillas (comillas dobles escapadas)."""
        return '"' + str(col).replace('"', '""') + '"'

    def consultar_vista(self, nombre: str) -> pd.DataFrame:
        """Consulta una vista del esquema ``analitica``."""
        nombre = self._nombre_valido(nombre)
        columnas = [r[0] for r in self._conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='analitica' AND table_name=?",
            [nombre]
        ).fetchall()]
        cols_str = ", ".join(self._columna(c) for c in columnas)
        return self._conn.execute(
            f'SELECT {cols_str} FROM analitica.{self._columna(nombre)}').fetchdf()

    def columnas(self, esquema: str, nombre: str) -> list[str]:
        """Columnas de un objeto del almacen, leidas del catalogo.

        Alimenta ``SELECT`` explicitos: la lista sale del information_schema
        (con su orden), no del orden que tenga el DataFrame en memoria.
        """
        esquema = self._nombre_valido(esquema)
        nombre = self._nombre_valido(nombre)
        filas = self._conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=? AND table_name=? ORDER BY ordinal_position",
            [esquema, nombre],
        ).fetchall()
        return [str(r[0]) for r in filas]

    def consultar_objeto(self, esquema: str, nombre: str) -> pd.DataFrame:
        """Lee ``<esquema>.<nombre>`` con lista explicita de columnas."""
        columnas = self.columnas(esquema, nombre)
        if not columnas:
            raise ValueError(f"Objeto sin columnas: {esquema}.{nombre}")
        lista = ", ".join(self._columna(c) for c in columnas)
        return self._conn.execute(
            f'SELECT {lista} FROM {self._columna(esquema)}.{self._columna(nombre)}'
        ).fetchdf()

    def info_estructura(self) -> pd.DataFrame:
        """Catalogo del almacen: esquema, objeto y tipo (tabla/vista)."""
        sql = """
        SELECT table_schema AS esquema, table_name AS objeto, table_type AS tipo
        FROM information_schema.tables
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog', 'giro_meta')
        ORDER BY 1, 2
        """
        return self._conn.execute(sql).fetchdf()

    def tabla(self, nombre: str) -> pd.DataFrame:
        nombre = self._nombre_valido(nombre)
        if not self.existe_tabla(nombre):
            raise ValueError(f"Tabla no existe: {nombre}")
        columnas = [r[0] for r in self._conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name=?",
            [nombre]
        ).fetchall()]
        cols_str = ", ".join(self._columna(c) for c in columnas)
        return self._conn.execute(
            f'SELECT {cols_str} FROM {self._columna(nombre)}').fetchdf()

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
        except Exception as e:
            import logging
            logging.getLogger("taller.storage").warning("Error al cerrar conexion DuckDB: %s", e)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cerrar()

    # ---------- utilidades ----------
    @staticmethod
    def _nombre_valido(nombre: str) -> str:
        """Normaliza y valida un identificador de tabla.

        Los nombres provienen de archivos/config del usuario y viajan
        interpolados en SQL (identificadores y literales): sin allowlist
        estricta, un ``"`` o ``'`` rompe o inyecta. Ante la duda, lanza.
        """
        limpio = (str(nombre).strip().lower()
                  .replace(" ", "_").replace("-", "_"))
        if not re.fullmatch(r"[a-z0-9_]+", limpio) or not limpio:
            raise ValueError(
                f"Nombre de dataset/tabla no valido: {nombre!r}. "
                "Usa solo letras, numeros y guiones bajos.")
        return limpio

    @staticmethod
    def _saneada(df: pd.DataFrame) -> pd.DataFrame:
        """Convierte columnas con tipos incompatibles antes de insertar en el almacen.

        Es el mismo saneo en todos los adaptadores (DuckDB y PostgreSQL):
        los dos motores deben ver dataframes identicos o las vistas dejan
        de cuadrar.
        """
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