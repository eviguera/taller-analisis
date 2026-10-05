"""Almacen: el esquema va declarado, no al estilo ``SELECT *``.

Cada lectura lleva lista explicita de columnas (DDL/DML y catalogo). Si un
dia vuelve el ``SELECT *``, el orden del DataFrame en memoria manda y estas
pruebas lo pillan.
"""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.storage import DataStore


class TestEsquemaExplicito(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="giro_store_"))
        self.store = DataStore(self.tmp / "almacen.duckdb",
                               self.tmp / "cache", usar_cache=False)

    def tearDown(self):
        self.store.cerrar()

    def test_las_columnas_se_leen_en_el_orden_de_la_tabla(self):
        self.store.registrar_tabla("hechos", pd.DataFrame(
            {"b": [2, 4], "a": [1, 3]}), cache=False)
        self.assertEqual(self.store.columnas("main", "hechos"), ["b", "a"])
        leido = self.store.consultar_objeto("main", "hechos")
        self.assertEqual(list(leido.columns), ["b", "a"])
        self.assertEqual(leido["a"].tolist(), [1, 3])
        self.assertEqual(leido["b"].tolist(), [2, 4])

    def test_identificadores_que_necesitan_comillas(self):
        self.store.registrar_tabla("ventas", pd.DataFrame(
            {"año": [2026], "total MXN": [100.0]}), cache=False)
        self.assertEqual(self.store.columnas("main", "ventas"),
                         ["año", "total MXN"])
        leido = self.store.consultar_objeto("main", "ventas")
        self.assertEqual(leido["año"].tolist(), [2026])
        self.assertEqual(leido["total MXN"].tolist(), [100.0])

    def test_objeto_inexistente_lanza_en_vez_de_devolver_vacio(self):
        self.store.registrar_tabla("hechos", pd.DataFrame({"a": [1]}),
                                   cache=False)
        with self.assertRaises(ValueError):
            self.store.consultar_objeto("main", "no_existe")

    def test_capa_core_con_las_columnas_barajadas(self):
        self.store.registrar_tabla_core(
            "inventario_aux", pd.DataFrame({"zeta": [3], "alfa": [1]}),
            con_claves=False)
        leido = self.store.consultar_objeto("core", "inventario_aux")
        self.assertEqual(list(leido.columns), ["zeta", "alfa"])
        self.assertEqual(int(leido["alfa"].iloc[0]), 1)

    def test_consulta_de_lectura_devuelve_dataframe(self):
        self.store.registrar_tabla("hechos", pd.DataFrame({"a": [1, 2]}),
                                   cache=False)
        res = self.store.consulta("SELECT SUM(a) AS total FROM hechos")
        self.assertEqual(int(res["total"].iloc[0]), 3)


class TestCacheParquet(unittest.TestCase):
    def test_el_cache_va_al_directorio_configurado(self):
        tmp = Path(tempfile.mkdtemp(prefix="giro_cache_"))
        cache_dir = tmp / "cache"
        store = DataStore(tmp / "almacen.duckdb", cache_dir, usar_cache=True)
        try:
            store.registrar_tabla("hechos", pd.DataFrame({"a": [1]}),
                                  cache=True)
            self.assertTrue((cache_dir / "hechos.parquet").exists())
        finally:
            store.cerrar()


if __name__ == "__main__":
    unittest.main()
