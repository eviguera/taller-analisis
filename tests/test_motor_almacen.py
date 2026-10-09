"""Pruebas de la decision de motor de almacen y del aislamiento por workspace."""

import os
import unittest
from types import SimpleNamespace
from unittest import mock

from src.data_loader import (
    MOTOR_DUCKDB,
    MOTOR_POSTGRES,
    dbname_postgres,
    get_store,
    motor_almacen,
)


def _cfg(clave="demo", **extra):
    return SimpleNamespace(clave=clave, **extra)


class TestMotor(unittest.TestCase):
    def test_el_defecto_es_duckdb_embebido(self):
        # Es lo que permite que el producto se levante en un contenedor
        # unico, sin servidor de base de datos.
        with mock.patch.dict(os.environ, {"GIRO_ALMACEN_MOTOR": ""}):
            self.assertEqual(motor_almacen(_cfg()), MOTOR_DUCKDB)

    def test_postgres_es_opt_in_por_entorno(self):
        with mock.patch.dict(os.environ, {"GIRO_ALMACEN_MOTOR": "postgres"}):
            self.assertEqual(motor_almacen(_cfg()), MOTOR_POSTGRES)

    def test_los_alias_del_mismo_motor(self):
        for alias in ("postgresql", "PG", "Postgres"):
            with mock.patch.dict(os.environ, {"GIRO_ALMACEN_MOTOR": alias}):
                self.assertEqual(motor_almacen(_cfg()), MOTOR_POSTGRES, alias)

    def test_un_motor_desconocido_no_se_toma_por_duckdb(self):
        # Tragarselo y caer a DuckDB dejaria al operador pensando que su
        # Postgres no funciona cuando en realidad la palabra estaba mal.
        with mock.patch.dict(os.environ, {"GIRO_ALMACEN_MOTOR": "mysql"}):
            with self.assertRaises(ValueError) as ctx:
                motor_almacen(_cfg())
        self.assertIn("mysql", str(ctx.exception))

    def test_la_config_tambien_puede_fijarlo(self):
        with mock.patch.dict(os.environ, {"GIRO_ALMACEN_MOTOR": ""}):
            self.assertEqual(
                motor_almacen(_cfg(motor_almacen="postgres")), MOTOR_POSTGRES)

    def test_el_entorno_manda_sobre_la_config(self):
        cfg = _cfg(motor_almacen="postgres")
        with mock.patch.dict(os.environ, {"GIRO_ALMACEN_MOTOR": "duckdb"}):
            self.assertEqual(motor_almacen(cfg), MOTOR_DUCKDB)

    def test_get_store_por_defecto_sigue_devolviendo_duckdb(self):
        import tempfile

        from src.storage import DataStore

        with tempfile.TemporaryDirectory() as tmp:
            cfg = _cfg(clave="demo",
                       db_path=f"{tmp}/almacen.duckdb",
                       cache_dir=f"{tmp}/cache",
                       usar_cache=True)
            with mock.patch.dict(os.environ, {"GIRO_ALMACEN_MOTOR": ""}):
                store = get_store(cfg)
            try:
                self.assertIsInstance(store, DataStore)
            finally:
                store.cerrar()


class TestAislamientoPorWorkspace(unittest.TestCase):
    """Regla 1: cada workspace en su propia base de datos."""

    def test_dos_workspaces_no_comparten_base(self):
        # Si compartieran, el DROP+CREATE de uno borraria las tablas del
        # otro y la firma de giro_meta haria que leyera sus datos.
        self.assertNotEqual(dbname_postgres(_cfg("taller-sur")),
                            dbname_postgres(_cfg("taller-norte")))

    def test_el_prefijo_se_anteponen(self):
        with mock.patch.dict(os.environ, {"GIRO_PG_DBPREFIX": "acme"}):
            self.assertEqual(dbname_postgres(_cfg("demo")), "acme_demo")

    def test_el_defecto_del_prefijo_es_giro(self):
        with mock.patch.dict(os.environ, {"GIRO_PG_DBPREFIX": ""}):
            self.assertEqual(dbname_postgres(_cfg("demo")), "giro_demo")

    def test_un_guion_no_acaba_en_el_nombre(self):
        # PATRON_CLAVE permite '-'; aqui se normaliza para no depender de
        # que el nombre viaje siempre entre comillas.
        with mock.patch.dict(os.environ, {"GIRO_PG_DBPREFIX": "giro"}):
            self.assertEqual(dbname_postgres(_cfg("taller-sur")), "giro_taller_sur")

    def test_un_workspace_sin_clave_es_un_error(self):
        # Sin clave no hay por donde separar tenants.
        with self.assertRaises(ValueError) as ctx:
            dbname_postgres(_cfg(""))
        self.assertIn("clave", str(ctx.exception))

    def test_un_nombre_sobre_63_caracteres_es_un_error(self):
        # Postgres trunca a 63 bytes y la colision seria silenciosa.
        with mock.patch.dict(os.environ, {"GIRO_PG_DBPREFIX": "p" * 60}):
            with self.assertRaises(ValueError) as ctx:
                dbname_postgres(_cfg("demo"))
        self.assertIn("63", str(ctx.exception))

    def test_el_resultado_es_un_identificador_valido(self):
        import re
        with mock.patch.dict(os.environ, {"GIRO_PG_DBPREFIX": "giro"}):
            nombre = dbname_postgres(_cfg("taller-sur_2"))
        self.assertRegex(nombre, r"^[a-z0-9_]+$")
        self.assertTrue(re.fullmatch(r"[a-z0-9_]{1,63}", nombre))


if __name__ == "__main__":
    unittest.main()
