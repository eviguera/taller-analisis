"""Topologia de Postgres: una base por workspace, creada por la CLI.

Prueba ``asegurar_base_workspace`` (creacion, idempotencia y el error
accionable cuando el usuario no tiene ``CREATEDB``) y el cableado del
CLI (``workspace crear`` con ``GIRO_ALMACEN_MOTOR=postgres`` y
``workspace init-db``). Como en ``test_postgres``, todo lo que necesita
servidor se salta con aviso si no hay un PostgreSQL alcanzable: con el
contenedor de pruebas (``GIRO_PG_*`` en el entorno) no se salta nada.

Solo se tocan workspaces y bases de PRUEBA (``prueba-*``); ni
``principal`` ni los workspaces reales se borran ni se modifican.
"""

import os
import secrets
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest import mock

import psycopg2
from psycopg2 import sql

from src.data_loader import dbname_postgres
from src.storage.postgres import asegurar_base_workspace

RAIZ = Path(__file__).resolve().parent.parent

#: Clave del workspace de prueba (nunca ``principal`` ni uno real).
CLAVE_PRUEBA = "prueba-initdb"

#: Rol de prueba sin CREATEDB: password generada en cada setUp, jamas
#: escrita en el codigo (regla 2).
ROL_SIN_CREATEDB = "giro_prueba_sin_createdb"


# ------------------------------------------------------------------
#  Conexion al PostgreSQL local (igual criterio que test_postgres)
# ------------------------------------------------------------------

def _parametros_pg(dbname: Optional[str] = None) -> dict:
    return {
        "host": os.environ.get("GIRO_PG_HOST", "127.0.0.1"),
        "port": os.environ.get("GIRO_PG_PORT", "55432"),
        "user": os.environ.get("GIRO_PG_USER", "giro"),
        "dbname": dbname or os.environ.get("GIRO_PG_DBNAME") or "postgres",
        "password": (os.environ.get("GIRO_PG_PASSWORD")
                     or os.environ.get("PGPASSWORD") or None),
    }


def _entorno_pg(**extra: str) -> dict:
    """``GIRO_PG_*`` completos para parchear ``os.environ``.

    ``asegurar_base_workspace`` y la CLI leen solo el entorno: sin
    parchearlo, la suite dependiera de que quien la ejecute haya exportado
    tambien ``GIRO_PG_USER``, y el defecto de libpq (usuario del sistema)
    no es el del contenedor de pruebas.
    """
    params = _parametros_pg()
    entorno = {
        "GIRO_PG_HOST": str(params["host"]),
        "GIRO_PG_PORT": str(params["port"]),
        "GIRO_PG_USER": str(params["user"]),
        "GIRO_PG_DBNAME": "postgres",
    }
    if params["password"]:
        entorno["GIRO_PG_PASSWORD"] = params["password"]
    entorno.update(extra)
    return entorno


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


def _existe_base(nombre: str) -> bool:
    conn = psycopg2.connect(**_parametros_pg(), connect_timeout=3)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                        (nombre,))
            return cur.fetchone() is not None
    finally:
        conn.close()


def _crear_base(nombre: str) -> None:
    """Crea la base por SQL directo (el camino del operador, a mano)."""
    conn = psycopg2.connect(**_parametros_pg(), connect_timeout=3)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE DATABASE {}")
                        .format(sql.Identifier(nombre)))
    finally:
        conn.close()


def _borrar_base(nombre: str) -> None:
    """Borra SOLO la base indicada (FORCE desconecta a los demas)."""
    conn = psycopg2.connect(**_parametros_pg(), connect_timeout=3)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)")
                        .format(sql.Identifier(nombre)))
    finally:
        conn.close()


# ------------------------------------------------------------------
#  asegurar_base_workspace
# ------------------------------------------------------------------

class TestAsegurarBaseWorkspace(unittest.TestCase):
    def setUp(self):
        motivo = _motivo_de_salto()
        if motivo:
            raise unittest.SkipTest(motivo)
        self.cfg = SimpleNamespace(clave=CLAVE_PRUEBA)
        self.nombre = dbname_postgres(self.cfg)
        _borrar_base(self.nombre)  # arranque limpio si un run anterior dejo basura
        self.addCleanup(_borrar_base, self.nombre)

    def test_la_crea_si_falta_y_la_segunda_vez_ya_existia(self):
        with mock.patch.dict(os.environ, _entorno_pg()):
            self.assertFalse(_existe_base(self.nombre))
            self.assertTrue(asegurar_base_workspace(self.cfg))
            self.assertTrue(_existe_base(self.nombre))
            self.assertFalse(asegurar_base_workspace(self.cfg))
            self.assertTrue(_existe_base(self.nombre))

    def test_no_destruye_lo_que_hay_dentro_de_una_base_existente(self):
        # Si "asegurar" recreara la base, las tablas del tenant
        # desaparecerian: solo se crea la base cuando NO existe.
        _crear_base(self.nombre)
        conn = psycopg2.connect(**_parametros_pg(self.nombre), connect_timeout=3)
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("CREATE TABLE marcador (x integer)")
                cur.execute("INSERT INTO marcador VALUES (42)")
        finally:
            conn.close()

        with mock.patch.dict(os.environ, _entorno_pg()):
            self.assertFalse(asegurar_base_workspace(self.cfg))

        conn = psycopg2.connect(**_parametros_pg(self.nombre), connect_timeout=3)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT x FROM marcador")
                self.assertEqual(cur.fetchone(), (42,))
        finally:
            conn.close()

    def test_el_nombre_creado_es_exactamente_el_de_dbname_postgres(self):
        # El CREATE DATABASE no admite bind: el identificador solo puede
        # salir de dbname_postgres (que sanea la clave y valida 63 bytes).
        with mock.patch.dict(os.environ, _entorno_pg()):
            self.assertTrue(asegurar_base_workspace(self.cfg))
        self.assertEqual(self.nombre, dbname_postgres(self.cfg))
        self.assertRegex(self.nombre, r"^[a-z0-9_]{1,63}$")


class TestSinPermisoCreatedb(unittest.TestCase):
    """Sin ``CREATEDB`` el error tiene que decirle al operador que hacer."""

    def setUp(self):
        motivo = _motivo_de_salto()
        if motivo:
            raise unittest.SkipTest(motivo)
        self.cfg = SimpleNamespace(clave=CLAVE_PRUEBA)
        self.nombre = dbname_postgres(self.cfg)
        _borrar_base(self.nombre)
        self.addCleanup(_borrar_base, self.nombre)
        # Password generada aqui: nunca un literal en el repo.
        self.password = secrets.token_urlsafe(16)
        conn = psycopg2.connect(**_parametros_pg(), connect_timeout=3)
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                # Constante del propio test, no entrada de usuario.
                cur.execute("DROP ROLE IF EXISTS giro_prueba_sin_createdb")
                cur.execute(
                    "CREATE ROLE giro_prueba_sin_createdb LOGIN PASSWORD %s "
                    "NOSUPERUSER NOCREATEDB", (self.password,))
        finally:
            conn.close()
        self.addCleanup(self._borrar_rol)

    @staticmethod
    def _borrar_rol() -> None:
        conn = psycopg2.connect(**_parametros_pg(), connect_timeout=3)
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("DROP ROLE IF EXISTS giro_prueba_sin_createdb")
        finally:
            conn.close()

    def test_el_error_es_accionable_y_no_crea_nada(self):
        entorno = _entorno_pg(GIRO_PG_USER=ROL_SIN_CREATEDB,
                              GIRO_PG_PASSWORD=self.password)
        with mock.patch.dict(os.environ, entorno):
            with self.assertRaises(RuntimeError) as ctx:
                asegurar_base_workspace(self.cfg)
        mensaje = str(ctx.exception)
        self.assertIn("CREATEDB", mensaje)
        # El comando exacto, con el nombre exacto de la base.
        self.assertIn(f'CREATE DATABASE "{self.nombre}";', mensaje)
        self.assertIn("ALTER USER", mensaje)
        self.assertFalse(_existe_base(self.nombre))


# ------------------------------------------------------------------
#  Cableado del CLI: workspace crear + workspace init-db
# ------------------------------------------------------------------

class TestCliFlujoDelOperador(unittest.TestCase):
    """El flujo documentado, ejecutando ``main.py`` tal cual el operador."""

    CLAVE = "prueba-cli"

    def setUp(self):
        motivo = _motivo_de_salto()
        if motivo:
            raise unittest.SkipTest(motivo)
        self.nombre = dbname_postgres(SimpleNamespace(clave=self.CLAVE))
        self.env = dict(os.environ)
        self.env.update(_entorno_pg())
        self.env["GIRO_ALMACEN_MOTOR"] = "postgres"
        _borrar_base(self.nombre)
        shutil.rmtree(RAIZ / "workspaces" / self.CLAVE, ignore_errors=True)
        self.addCleanup(self._limpiar)

    def _limpiar(self) -> None:
        shutil.rmtree(RAIZ / "workspaces" / self.CLAVE, ignore_errors=True)
        _borrar_base(self.nombre)

    def _cli(self, *argumentos: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "main.py", *argumentos],
            cwd=RAIZ, env=self.env, capture_output=True, text=True, timeout=120)

    def test_crear_init_db_y_reparacion_del_desfase(self):
        # 1) crear con motor postgres: la base se crea en el mismo paso.
        r = self._cli("workspace", "crear", self.CLAVE, "--nombre", "Prueba CLI")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"base postgres: {self.nombre} (creada)", r.stdout)
        self.assertTrue(_existe_base(self.nombre))

        # 2) la base se pierde (el desfase): init-db la vuelve a crear.
        _borrar_base(self.nombre)
        r = self._cli("workspace", "init-db")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"- {self.CLAVE}: creada ({self.nombre})", r.stdout)

        # 3) segunda pasada: ya existia y no toca nada.
        r = self._cli("workspace", "init-db")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"- {self.CLAVE}: ya existia ({self.nombre})", r.stdout)

    def test_init_db_con_motor_duckdb_no_hace_nada(self):
        self.env["GIRO_ALMACEN_MOTOR"] = "duckdb"
        r = self._cli("workspace", "init-db")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("duckdb", r.stdout)
        self.assertNotIn("creada", r.stdout)

    def test_init_db_sale_con_error_si_alguna_base_falla(self):
        # Password mala: todas las conexiones fallan y el exit code tiene
        # que ser distinto de cero para que el despliegue automation lo vea.
        self.env["GIRO_PG_PASSWORD"] = "contrasena-mala-de-prueba"
        r = self._cli("workspace", "init-db")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("ERROR:", r.stdout)


if __name__ == "__main__":
    unittest.main()
