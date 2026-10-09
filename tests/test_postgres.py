"""PostgreSQL como segundo implementador de `PuertoAlmacen`.

Tres niveles:

1. `TestDialectoDuckDB` / `TestDialectoPostgres` — el SQL de cada dialecto,
   sin servidor: DuckDB debe seguir devolviendo literalmente el SQL de
   `schema.py`, y el de Postgres no debe contener restos de sintaxis
   DuckDB (TRY_CAST, strftime, STRING_SPLIT, date_diff...).
2. `TestAlmacenPostgres` — el adaptador contra un PostgreSQL real: DDL,
   binds, firmas, construir_estructura. Se salta con aviso si no hay
   servidor alcanzable.
3. `TestEquivalenciaVistas` — la prueba de verdad: los datos de ejemplo
   (`data/*.csv`) cargados en AMBOS motores y las 11 vistas `analitica.*`
   comparadas fila a fila.

Credenciales (regla 2: nunca en el codigo): `GIRO_PG_HOST/PORT/USER/
PASSWORD/DBNAME`, con defaults locales no secretos para el contenedor
`giro-pg` (127.0.0.1:55432, usuario/BD `giro`). La password solo existe en
el entorno: si no esta, las pruebas de servidor se omiten en lugar de
romperse.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import psycopg2

from src.storage import AlmacenPostgres, DataStore, DialectoDuckDB, DialectoPostgres
from src.storage.schema import ORDEN_CARGA, SQL_ARRANQUE, VISTAS_ANALITICA, ddl_tabla_core, sql_tipo

RAIZ = Path(__file__).resolve().parent.parent
DIR_DATOS = RAIZ / "data"
DATOS_DE_EJEMPLO = ("clientes", "servicios", "vehiculos", "facturas", "inventario")

#: Las cinco vistas pedidas en la comparacion (mas las demas, abajo).
VISTAS_CLAVE = ["ingresos_mensuales", "rfm_clientes", "detalle_servicios",
                "inventario_estado", "facturas_con_dimensiones"]


# ------------------------------------------------------------------
#  Conexion al PostgreSQL local (cada prueba decide si se salta)
# ------------------------------------------------------------------

def _parametros_pg() -> Dict:
    return {
        "host": os.environ.get("GIRO_PG_HOST", "127.0.0.1"),
        "port": os.environ.get("GIRO_PG_PORT", "55432"),
        "user": os.environ.get("GIRO_PG_USER", "giro"),
        "dbname": os.environ.get("GIRO_PG_DBNAME", "giro"),
        "password": (os.environ.get("GIRO_PG_PASSWORD")
                     or os.environ.get("PGPASSWORD") or None),
    }


def _motivo_de_salto() -> Optional[str]:
    """``None`` si hay un PostgreSQL alcanzable; si no, el por que."""
    params = _parametros_pg()
    try:
        conn = psycopg2.connect(**params, connect_timeout=3)
    except psycopg2.Error as e:
        return (f"PostgreSQL no alcanzable en {params['host']}:{params['port']} "
                f"({type(e).__name__}): {e}. Exporta GIRO_PG_PASSWORD (y "
                f"GIRO_PG_* si el contenedor local usa otros valores).")
    conn.close()
    return None


def _abrir_almacen_pg() -> AlmacenPostgres:
    return AlmacenPostgres(**_parametros_pg(), timeout_segundos=3)


def _limpiar_postgres(almacen: AlmacenPostgres, tablas_main: List[str]) -> None:
    """Borra exactamente los objetos que crearon las pruebas (nada mas)."""
    for vista in DialectoPostgres().vistas():
        almacen.ejecutar(f'DROP VIEW IF EXISTS analitica."{vista}" CASCADE')
    for tabla in list(ORDEN_CARGA) + ["factura_detalle"]:
        almacen.ejecutar(f'DROP TABLE IF EXISTS core."{tabla}" CASCADE')
    for tabla in tablas_main:
        almacen.ejecutar(f'DROP TABLE IF EXISTS main."{tabla}" CASCADE')


# ------------------------------------------------------------------
#  1. Dialectos (sin servidor)
# ------------------------------------------------------------------

def _muestra_tipos() -> pd.DataFrame:
    return pd.DataFrame({
        "id": pd.Series([1, 2], dtype="int64"),
        "total": pd.Series([1.5, 2.5], dtype="float64"),
        "activo": pd.Series([True, False], dtype="bool"),
        "fecha": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "nombre": ["Ana", 'Luis "el Dos"'],
    })


class TestDialectoDuckDB(unittest.TestCase):
    """DuckDB tiene que seguir haciendo exactamente lo que hacia."""

    def test_las_vistas_son_el_sql_actual_byte_a_byte(self):
        self.assertEqual(DialectoDuckDB().vistas(), VISTAS_ANALITICA)

    def test_el_arranque_es_el_actual(self):
        self.assertEqual(DialectoDuckDB().sql_arranque(), SQL_ARRANQUE)

    def test_sql_tipo_es_el_de_schema(self):
        dialecto = DialectoDuckDB()
        for col in _muestra_tipos().columns:
            dtype = _muestra_tipos()[col].dtype
            self.assertEqual(dialecto.sql_tipo(dtype), sql_tipo(dtype))

    def test_el_ddl_es_el_de_schema(self):
        df = _muestra_tipos()
        dialecto = DialectoDuckDB()
        for claves in (True, False):
            self.assertEqual(
                dialecto.ddl_tabla_core("facturas", df, con_claves=claves),
                ddl_tabla_core("facturas", df, con_claves=claves))

    def test_los_helpers_describen_el_sql_que_las_vistas_usan(self):
        # Amarra helpers <-> SQL declarado: si alguien cambia una vista a
        # mano sin tocar el helper (o al reves), esto lo pilla.
        dialecto = DialectoDuckDB()
        self.assertEqual(dialecto.fecha_a_mes('f."fecha"'),
                         "strftime(f.\"fecha\", '%Y-%m')")
        self.assertIn(dialecto.fecha_a_mes('f."fecha"'),
                      VISTAS_ANALITICA["ingresos_mensuales"])
        self.assertEqual(dialecto.try_cast("split_part(t.det, ':', 1)", "BIGINT"),
                         "TRY_CAST(split_part(t.det, ':', 1) AS BIGINT)")
        self.assertIn(dialecto.try_cast("split_part(t.det, ':', 1)", "BIGINT"),
                      VISTAS_ANALITICA["detalle_servicios"])
        self.assertEqual(dialecto.redondea('SUM(f."total")', 2),
                         'round(SUM(f."total"), 2)')
        self.assertIn(dialecto.redondea('SUM(f."total")', 2),
                      VISTAS_ANALITICA["ingresos_mensuales"])


class TestDialectoPostgres(unittest.TestCase):
    """El dialecto PG: sin sintaxis DuckDB y con los helpers puestos."""

    def test_mismas_vistas_que_el_duckdb_y_en_el_mismo_orden(self):
        self.assertEqual(list(DialectoPostgres().vistas()),
                         list(VISTAS_ANALITICA))

    def test_tipos(self):
        dialecto = DialectoPostgres()
        for col in _muestra_tipos().columns:
            dtype = _muestra_tipos()[col].dtype
            esperado = ("DOUBLE PRECISION" if sql_tipo(dtype) == "DOUBLE"
                        else sql_tipo(dtype))
            self.assertEqual(dialecto.sql_tipo(dtype), esperado)
        self.assertEqual(dialecto.sql_tipo("float64"), "DOUBLE PRECISION")
        self.assertEqual(dialecto.sql_tipo("int64"), "BIGINT")
        self.assertEqual(dialecto.sql_tipo("object"), "VARCHAR")

    def test_el_arranque_crea_esquemas_y_funciones(self):
        arranque = DialectoPostgres().sql_arranque()
        unidos = "\n".join(arranque)
        for esquema in ("core", "analitica", "giro_meta", "main"):
            self.assertIn(f"CREATE SCHEMA IF NOT EXISTS {esquema};", arranque)
        self.assertIn("giro_meta.giro_try_entero", unidos)
        self.assertIn("giro_meta.giro_try_decimalo", unidos)
        self.assertIn("giro_meta.giro_redondea", unidos)

    def test_helpers(self):
        dialecto = DialectoPostgres()
        self.assertEqual(dialecto.fecha_a_mes('f."fecha"'),
                         "to_char(f.\"fecha\", 'YYYY-MM')")
        self.assertEqual(dialecto.try_cast("x", "BIGINT"),
                         "giro_meta.giro_try_entero(x)")
        self.assertEqual(dialecto.try_cast("x", "DOUBLE"),
                         "giro_meta.giro_try_decimalo(x)")
        self.assertEqual(dialecto.redondea("x", 2),
                         "giro_meta.giro_redondea(x, 2)")
        with self.assertRaises(ValueError):
            dialecto.try_cast("x", "TEXT")

    def test_el_ddl_usa_double_precision(self):
        ddl = DialectoPostgres().ddl_tabla_core("inventario", _muestra_tipos())
        self.assertIn("DOUBLE PRECISION", ddl)
        self.assertNotRegex(ddl, r"\bDOUBLE\b(?! PRECISION)")

    def test_ninguna_vista_conserva_sintaxis_duckdb(self):
        for nombre, vista in DialectoPostgres().vistas().items():
            bajo = vista.lower()
            for prohibido in ("strftime(", "try_cast(", "string_split",
                              "date_diff(", "unnest(string_split"):
                self.assertNotIn(prohibido, bajo,
                                 f"{nombre}: sobra sintaxis DuckDB {prohibido!r}")

    def test_las_vistas_pg_usan_los_transcritos_verificados(self):
        vistas = DialectoPostgres().vistas()
        for nombre, vista in vistas.items():
            # Postgres no permite cambiar las columnas en CREATE OR REPLACE
            # (DuckDB si): cada vista se limpia antes.
            self.assertIn(f"DROP VIEW IF EXISTS analitica.{nombre}", vista)
        detalle = vistas["detalle_servicios"].lower()
        self.assertIn("left join lateral unnest(string_to_array(", detalle)
        self.assertIn("giro_meta.giro_try_entero(", detalle)
        self.assertIn("to_char(", vistas["ingresos_mensuales"])
        self.assertIn("to_char(", vistas["demanda_servicios_mensual"])
        rfm = vistas["rfm_clientes"]
        self.assertIn("AS date", rfm)          # date_diff no existe en PG16
        self.assertIn("giro_meta.giro_redondea(", rfm)
        # Postgres divide enteros a enteros (trunca); DuckDB no.
        self.assertIn("::double precision / NULLIF",
                      vistas["inventario_estado"])


# ------------------------------------------------------------------
#  2. Adaptador contra PostgreSQL real
# ------------------------------------------------------------------

class TestAlmacenPostgres(unittest.TestCase):
    def setUp(self):
        motivo = _motivo_de_salto()
        if motivo:
            raise unittest.SkipTest(motivo)
        self.almacen = _abrir_almacen_pg()
        self.tablas_main: List[str] = []

    def tearDown(self):
        if hasattr(self, "almacen"):
            _limpiar_postgres(self.almacen, self.tablas_main)
            self.almacen.cerrar()

    def test_registrar_tabla_y_leer_de_vuelta(self):
        self.tablas_main.append("prueba_postgres")
        df = pd.DataFrame({"año": [2024], "total MXN": [100.5],
                           "notas": ['comillas "dobles']})
        self.almacen.registrar_tabla("prueba_postgres", df, cache=False)
        leido = self.almacen.consultar_objeto("main", "prueba_postgres")
        self.assertEqual(list(leido.columns), ["año", "total MXN", "notas"])
        self.assertEqual(int(leido["año"].iloc[0]), 2024)
        self.assertEqual(leido["notas"].iloc[0], 'comillas "dobles')
        self.assertEqual(self.almacen.tabla("prueba_postgres").shape, (1, 3))

    def test_identificadores_invalidos_lanzan(self):
        with self.assertRaises(ValueError):
            self.almacen.registrar_tabla('x"; DROP TABLE core.facturas; --',
                                         pd.DataFrame({"a": [1]}))
        with self.assertRaises(ValueError):
            self.almacen.consultar_vista("vista; DROP TABLE core.facturas")
        with self.assertRaises(ValueError):
            self.almacen.consultar_objeto("main", "tabla inexistente")

    def test_las_firmas_van_con_bind_no_con_interpolacion(self):
        self.almacen.guardar_firma("firma de prueba", "datos")
        self.assertEqual(self.almacen.firma_carga("datos"), "firma de prueba")
        # Un valor con sintaxis SQL es solo un valor.
        malicia = "'; DROP TABLE core.facturas; --"
        self.almacen.guardar_firma(malicia, malicia)
        self.assertEqual(self.almacen.firma_carga(malicia), malicia)
        with self.almacen._conn.cursor() as cur:  # limpieza de la prueba
            cur.execute("DELETE FROM giro_meta.carga WHERE clave = %s",
                        (malicia,))
            cur.execute("DELETE FROM giro_meta.carga WHERE clave = %s",
                        ("datos",))
        self.assertEqual(self.almacen.firma_carga("datos"), "")

    def test_consulta_de_lectura_devuelve_dataframe(self):
        res = self.almacen.consulta("SELECT 42 AS respuesta, '%lit%'::text AS pct")
        self.assertEqual(int(res["respuesta"].iloc[0]), 42)
        self.assertEqual(res["pct"].iloc[0], "%lit%")

    def test_construir_estructura_y_vistas_clave(self):
        from src.core.hechos import construir_factura_detalle

        tablas = {
            "clientes": pd.DataFrame({
                "id": [1, 2], "nombre": ["Ana", "Luis"],
                "email": ["a@x.com", "b@x.com"], "telefono": ["5551", "5552"],
                "fecha_registro": pd.to_datetime(["2024-01-01", "2024-02-01"])}),
            "servicios": pd.DataFrame({
                "id": [10], "nombre": ["Cambio de aceite"],
                "precio_base": [100.5], "tiempo_estimado_min": [30]}),
            "vehiculos": pd.DataFrame({
                "id": [100], "cliente_id": [1], "marca": ["Kia"],
                "modelo": ["Rio"], "anio": [2020], "placa": ["X1"],
                "color": ["Gris"], "kilometraje": [1000]}),
            "facturas": pd.DataFrame({
                "id": [1000], "cliente_id": [1], "vehiculo_id": [100],
                "fecha": pd.to_datetime(["2024-03-05"]),
                "total": [100.5], "descuento": [0.0], "estado": ["Pagada"],
                "detalles": ["10:1:100.50"]}),
            "inventario": pd.DataFrame({
                "id": [7], "producto": ["Aceite"], "categoria": ["Aceites"],
                "precio_costo": [120], "precio_venta": [350],
                "stock_actual": [5], "stock_minimo": [8],
                "ultima_venta": ["2024-01-01"]}),
        }
        self.tablas_main = list(tablas) + ["factura_detalle"]
        hechos = construir_factura_detalle(tablas["facturas"], tablas["servicios"])
        self.almacen.registrar_tablas(tablas)
        self.almacen.registrar_tabla("factura_detalle", hechos, cache=False)
        self.almacen.registrar_tabla_core("factura_detalle", hechos)

        filas = self.almacen.construir_estructura(tablas)
        self.assertEqual(filas["facturas"], 1)
        self.assertEqual(self.almacen.vistas_fallidas, [])

        ingresos = self.almacen.consultar_vista("ingresos_mensuales")
        self.assertEqual(ingresos["anio_mes"].tolist(), ["2024-03"])
        self.assertAlmostEqual(float(ingresos["ingresos"].iloc[0]), 100.5)

        # LATERAL + giro_try_entero sobre el string de detalles.
        detalle = self.almacen.consultar_vista("detalle_servicios")
        self.assertEqual(int(detalle["servicio_id"].iloc[0]), 10)
        self.assertEqual(int(detalle["cantidad"].iloc[0]), 1)
        self.assertAlmostEqual(float(detalle["subtotal"].iloc[0]), 100.5)
        self.assertEqual(detalle["servicio"].iloc[0], "Cambio de aceite")

        # Division en punto flotante: en Postgres 350-120/120 trunca si no
        # se sube a double; aqui tiene que dar 191.7, como DuckDB.
        inventario = self.almacen.consultar_vista("inventario_estado")
        self.assertAlmostEqual(float(inventario["margen_pct"].iloc[0]), 191.7)
        self.assertEqual(inventario["estado_stock"].iloc[0], "Bajo")

        rfm = self.almacen.consultar_vista("rfm_clientes")
        self.assertEqual(int(rfm["recencia_dias"].iloc[0]), 0)

        info = self.almacen.info_estructura()
        self.assertTrue(((info["esquema"] == "analitica")
                         & (info["objeto"] == "ingresos_mensuales")
                         & (info["tipo"] == "VIEW")).any())


# ------------------------------------------------------------------
#  3. Equivalencia de vistas entre motores (la prueba de verdad)
# ------------------------------------------------------------------

def cargar_datos_de_ejemplo() -> Optional[Dict[str, pd.DataFrame]]:
    """Los `data/*.csv` tal y como los carga el pipeline (mismo loader,
    misma ``_limpiar``); ``None`` si faltan los ficheros."""
    if not all((DIR_DATOS / f"{n}.csv").exists() for n in DATOS_DE_EJEMPLO):
        return None
    from src.core.pipeline import _limpiar
    from src.loaders import get_loader

    tablas = {}
    for nombre in DATOS_DE_EJEMPLO:
        ruta = DIR_DATOS / f"{nombre}.csv"
        cr = get_loader(ruta).cargar(ruta)
        tablas[nombre] = _limpiar(cr.datos, nombre)
    return tablas


def preparar_almacen(store, tablas: Dict[str, pd.DataFrame]) -> None:
    """Replica el ``_construir_almacen`` del pipeline: registro, hechos
    ``factura_detalle`` y ``construir_estructura``."""
    from src.core.hechos import construir_factura_detalle

    store.registrar_tablas(tablas)
    hechos = construir_factura_detalle(tablas["facturas"], tablas.get("servicios"))
    if not hechos.empty:
        store.registrar_tabla("factura_detalle", hechos, cache=False)
        store.registrar_tabla_core("factura_detalle", hechos)
    store.construir_estructura(tablas)


def _normalizar(df: pd.DataFrame) -> pd.DataFrame:
    """Tipos comparables entre motores: numericos a float64, texto a
    object con los valores intactos (un ``None`` de un motor contra una
    cadena vacia del otro es una diferencia real, no se maquilla)."""
    out = df.copy()
    for col in out.columns:
        serie = out[col]
        if pd.api.types.is_datetime64_any_dtype(serie):
            continue
        if pd.api.types.is_numeric_dtype(serie):
            out[col] = serie.astype("float64")
        else:
            out[col] = serie.astype("object")
    return out


def _ordenar(df: pd.DataFrame) -> pd.DataFrame:
    """Orden estable por clave de todas las columnas (las vistas no
    garantizan orden de filas entre motores)."""
    clave = df.astype(str).agg("\x1f".join, axis=1)
    return (df.assign(_clave=clave)
              .sort_values("_clave", kind="stable")
              .drop(columns="_clave")
              .reset_index(drop=True))


def comparar_vistas(a, b, nombres: List[str]) -> List[Dict]:
    """Compara vistas homónimas entre dos almacenes. Devuelve
    ``[{"vista", "ok", "detalle"}]`` — el detalle explica el primer
    motivo de diferencia."""
    resultados = []
    for nombre in nombres:
        try:
            df_a = a.consultar_vista(nombre)
        except Exception as e:  # noqa: BLE001 — se reporta, no se traga
            resultados.append({"vista": nombre, "ok": False,
                               "detalle": f"lectura en {a.__class__.__name__}: {e}"})
            continue
        try:
            df_b = b.consultar_vista(nombre)
        except Exception as e:  # noqa: BLE001
            resultados.append({"vista": nombre, "ok": False,
                               "detalle": f"lectura en {b.__class__.__name__}: {e}"})
            continue
        if list(df_a.columns) != list(df_b.columns):
            resultados.append({
                "vista": nombre, "ok": False,
                "detalle": (f"columnas {list(df_a.columns)} != "
                            f"{list(df_b.columns)}")})
            continue
        if len(df_a) != len(df_b):
            resultados.append({"vista": nombre, "ok": False,
                               "detalle": f"filas {len(df_a)} != {len(df_b)}"})
            continue
        na, nb = _ordenar(_normalizar(df_a)), _ordenar(_normalizar(df_b))
        try:
            pd.testing.assert_frame_equal(
                na, nb, check_dtype=False, check_exact=False,
                rtol=1e-9, atol=1e-6, obj=f"vista {nombre}")
        except AssertionError as e:
            resultados.append({"vista": nombre, "ok": False,
                               "detalle": str(e)[:1000]})
            continue
        resultados.append({"vista": nombre, "ok": True,
                           "detalle": f"{len(df_a)} filas, {len(df_a.columns)} columnas"})
    return resultados


class TestEquivalenciaVistas(unittest.TestCase):
    """Mismos datos de ejemplo en DuckDB y en PostgreSQL: mismas vistas."""

    @classmethod
    def setUpClass(cls):
        motivo = _motivo_de_salto()
        if motivo:
            raise unittest.SkipTest(motivo)
        cls.datos = cargar_datos_de_ejemplo()
        if cls.datos is None:
            raise unittest.SkipTest("faltan data/*.csv (datos de ejemplo)")
        cls.tmp = Path(tempfile.mkdtemp(prefix="giro_equivalencia_"))
        cls.duck = DataStore(cls.tmp / "almacen.duckdb", cls.tmp / "cache",
                             usar_cache=False)
        cls.pg = _abrir_almacen_pg()
        preparar_almacen(cls.duck, cls.datos)
        preparar_almacen(cls.pg, cls.datos)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "duck"):
            cls.duck.cerrar()
            shutil.rmtree(cls.tmp, ignore_errors=True)
        if hasattr(cls, "pg"):
            _limpiar_postgres(cls.pg, list(cls.datos) + ["factura_detalle"])
            cls.pg.cerrar()

    def test_ninguna_vista_falla_en_ningun_motor(self):
        self.assertEqual(self.duck.vistas_fallidas, [], "vistas caidas en DuckDB")
        self.assertEqual(self.pg.vistas_fallidas, [], "vistas caidas en PostgreSQL")

    def test_las_cinco_vistas_clave_tienen_filas_en_ambos_motores(self):
        for nombre in VISTAS_CLAVE:
            with self.subTest(vista=nombre):
                self.assertGreater(len(self.duck.consultar_vista(nombre)), 0)
                self.assertGreater(len(self.pg.consultar_vista(nombre)), 0)

    def test_las_11_vistas_coinciden_entre_motores(self):
        nombres = list(VISTAS_ANALITICA)
        resultados = comparar_vistas(self.duck, self.pg, nombres)
        fallidas = [f"{r['vista']}: {r['detalle']}" for r in resultados if not r["ok"]]
        self.assertEqual(fallidas, [],
                         "vistas que NO cuadran entre DuckDB y PostgreSQL:\n"
                         + "\n".join(fallidas))


if __name__ == "__main__":
    unittest.main()
