"""Aislamiento por workspace, SQL de solo lectura y permisos de sesion.

Es la parte del codigo que, si se rompe, deja una empresa viendo los datos de
otra: por eso se prueba en suite y no a ojo.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.core import auth, conector_sql, warehouse
from src.core.config import AppConfig
from ui import context


def _cfg(titulo_clave="empresa1"):
    """Config de un workspace cuyo directorio de datos vive en un temporal."""
    raiz = Path(tempfile.mkdtemp(prefix="giro_test_"))
    return AppConfig(clave=titulo_clave,
                     directorio_datos=raiz / titulo_clave / "data")


class TestSoloLectura(unittest.TestCase):
    """Una sola lista de sentencias para la consola y para los conectores."""

    permitidas = [
        "SELECT * FROM hechos",
        "TABLE ventas",
        "VALUES (1)",
        "select 1;",
        "WITH a AS (SELECT 1) SELECT * FROM a",
        "SELECT fecha, SUM(total) FROM hechos GROUP BY 1 ORDER BY 1",
        "select * from hechos where direccion = 'C/ Mayor 3'",
    ]
    bloqueadas = [
        "DROP TABLE t",
        "DELETE FROM t",
        "select 1; delete from t",
        "select read_csv('/etc/passwd')",
        "select * from 'clientes.csv'",
        "select * from './datos.csv'",
        "select * from '../otra-empresa/data/x.parquet'",
        "select * from '/tmp/x.csv'",
        "select * from 'https://interno/x.csv'",
        "CALL archivar()",
        "ATTACH 'x.db'",
        "FORCE CHECKPOINT",
        "select * from hive_scan('archivo')",
        "EXPLAIN DELETE FROM t",
    ]

    def _consola(self, consulta):
        try:
            context._validar_sql_solo_lectura(consulta)
            return True
        except ValueError:
            return False

    def test_la_consola_deja_pasar_las_de_lectura(self):
        for consulta in self.permitidas:
            with self.subTest(consulta=consulta):
                self.assertTrue(self._consola(consulta))

    def test_la_consola_bloquea_las_demas(self):
        for consulta in self.bloqueadas:
            with self.subTest(consulta=consulta):
                self.assertFalse(self._consola(consulta))

    def test_los_conectores_usan_la_misma_lista(self):
        for consulta in self.bloqueadas:
            with self.subTest(consulta=consulta):
                with self.assertRaises(ValueError):
                    conector_sql.validar_solo_lectura(consulta, "El conector")
        for consulta in self.permitidas:
            with self.subTest(consulta=consulta):
                conector_sql.validar_solo_lectura(consulta, "El conector")

    def test_el_origen_solo_cambia_el_aviso(self):
        with self.assertRaises(ValueError) as ctx:
            conector_sql.validar_solo_lectura("DROP TABLE t", "El conector")
        self.assertIn("El conector", str(ctx.exception))


class TestConfinamiento(unittest.TestCase):
    """Nada de rutas fuera del directorio de datos de la empresa."""

    def setUp(self):
        self.cfg = _cfg("empresa1")
        self.dentro = self.cfg.directorio_datos / "clientes.csv"
        self.dentro.parent.mkdir(parents=True, exist_ok=True)
        self.dentro.write_text("id,nombre\n", encoding="utf-8")

    def test_ruta_dentro_del_workspace_pasa(self):
        resuelta = conector_sql._dentro_del_workspace(self.cfg, self.dentro)
        self.assertTrue(resuelta.is_relative_to(
            self.cfg.directorio_datos.resolve()))

    def test_ruta_de_otra_empresa_lanza(self):
        ajena = self.cfg.directorio_datos.parent / "empresa2" / "data" / "x.db"
        with self.assertRaises(ValueError) as ctx:
            conector_sql._dentro_del_workspace(self.cfg, ajena)
        self.assertIn("fuera del directorio", str(ctx.exception))

    def test_ruta_absoluta_fuera_lanza(self):
        with self.assertRaises(ValueError):
            conector_sql._dentro_del_workspace(self.cfg, "/etc/passwd")

    def test_dsn_sqlite_fuera_del_workspace_lanza(self):
        conector = conector_sql.Conector(
            nombre="erp", motor="sql", dataset="facturas",
            fuente="sqlite:///../empresa2/data/almacen.db",
            consulta="SELECT 1")
        with self.assertRaises(ValueError):
            conector_sql._dsn_resuelto(self.cfg, conector)

    def test_dsn_sqlite_dentro_se_resuelve_en_el_workspace(self):
        conector = conector_sql.Conector(
            nombre="erp", motor="sql", fuente="sqlite:///erp.db",
            consulta="SELECT 1")
        dsn = conector_sql._dsn_resuelto(self.cfg, conector)
        self.assertTrue(dsn.startswith("sqlite:///"))
        self.assertTrue(Path(dsn[len("sqlite:///"):]).is_relative_to(
            self.cfg.directorio_datos.resolve()))

    def test_dsn_remoto_se_usa_tal_cual(self):
        conector = conector_sql.Conector(
            nombre="erp", motor="postgres",
            fuente="postgresql://usuario:clave@host:5432/negocio",
            consulta="SELECT 1")
        self.assertEqual(conector_sql._dsn_resuelto(self.cfg, conector),
                         conector.fuente)


class TestPrefijoDeTenant(unittest.TestCase):
    """Todas las tablas publicadas llevan la clave del workspace."""

    def test_sin_prefijo_la_adquiere(self):
        self.assertEqual(
            warehouse._prefijo_efectivo(AppConfig(clave="taller_demo"), ""),
            "taller_demo_")

    def test_prefijo_ajeno_lleva_la_clave(self):
        self.assertEqual(
            warehouse._prefijo_efectivo(AppConfig(clave="taller_demo"), "giro_"),
            "giro_taller_demo_")

    def test_clave_como_subcadena_no_sirve(self):
        # Clave "a" y prefijo "datos_": comprobar la subcadena dejaba el
        # prefijo sin clave de tenant y los workspaces se pisaban.
        self.assertEqual(warehouse._prefijo_efectivo(AppConfig(clave="a"),
                                                     "datos_"),
                         "datos_a_")

    def test_no_duplica_la_clave_si_ya_la_lleva(self):
        cfg = AppConfig(clave="taller_demo")
        self.assertEqual(warehouse._prefijo_efectivo(cfg, "taller_demo_"),
                         "taller_demo_")
        self.assertEqual(warehouse._prefijo_efectivo(cfg, "giro_taller_demo_"),
                         "giro_taller_demo_")

    def test_dos_empresas_no_colisionan(self):
        a = warehouse._prefijo_efectivo(AppConfig(clave="empresa1"), "giro_")
        b = warehouse._prefijo_efectivo(AppConfig(clave="empresa2"), "giro_")
        self.assertNotEqual(a, b)
        self.assertNotEqual(warehouse._nombre_tabla(a, "facturas"),
                            warehouse._nombre_tabla(b, "facturas"))

    def test_identificador_que_no_entra_en_la_allowlist_lanza(self):
        # Los identificadores viajan interpolados en DDL/DML: lo que no se
        # pueda reducir a [a-z0-9_] se rechaza en vez de dejarlo pasar.
        with self.assertRaises(ValueError):
            warehouse._nombre_tabla("giro_", "ñ")
        with self.assertRaises(ValueError):
            warehouse._nombre_tabla("giro_", "")

    def test_lo_demas_se_sanea_y_no_deja_inyeccion(self):
        nombre = warehouse._nombre_tabla("giro_", 'x"; DROP TABLE secretos --')
        self.assertEqual(nombre, "giro_x_drop_table_secretos")
        self.assertNotIn(";", nombre)
        self.assertNotIn('"', nombre)


class TestPermisos(unittest.TestCase):
    """El rol no basta: lo que no se concede, no se puede."""

    @staticmethod
    def cliente(workspaces=("empresa1",), permisos=()):
        return auth.Sesion(usuario=auth.Usuario(
            username="carmen", nombre="Carmen", hash="x",
            workspaces=list(workspaces), permisos=list(permisos)))

    def test_cliente_sin_concesion_no_entra_en_otra_empresa(self):
        sesion = self.cliente()
        self.assertFalse(sesion.acceso_total)
        self.assertEqual(sesion.visibles(["empresa1", "empresa2"]),
                         ["empresa1"])
        self.assertEqual(auth.workspace_permitido(sesion, "empresa2"),
                         "empresa1")

    def test_ver_todas_empresas_abre_el_catalogo(self):
        sesion = self.cliente(permisos=[auth.PERMISO_VER_TODAS_EMPRESAS])
        self.assertTrue(sesion.acceso_total)
        self.assertEqual(sesion.visibles(["empresa1", "empresa2"]),
                         ["empresa1", "empresa2"])
        self.assertEqual(auth.workspace_permitido(sesion, "empresa2"),
                         "empresa2")

    def test_una_concesion_no_da_los_demas_permisos(self):
        sesion = self.cliente(permisos=[auth.PERMISO_CONSOLA_SQL])
        self.assertTrue(sesion.puede(auth.PERMISO_CONSOLA_SQL))
        self.assertFalse(sesion.puede(auth.PERMISO_CONECTORES))
        self.assertFalse(sesion.puede(auth.PERMISO_PUBLICAR_WAREHOUSE))
        # ver_todas_empresas no esta concedido: el alcance sigue cerrado
        self.assertFalse(sesion.acceso_total)

    def test_cliente_sin_empresas_no_ve_ninguna(self):
        sesion = self.cliente(workspaces=[])
        self.assertEqual(sesion.workspaces_permitidos(), [])
        self.assertEqual(sesion.visibles(["empresa1", "empresa2"]), [])

    def test_admin_lo_tiene_todo(self):
        sesion = auth.Sesion(usuario=auth.Usuario(
            username="admin", nombre="Admin", hash="x", rol=auth.ROL_ADMIN))
        self.assertTrue(sesion.acceso_total)
        self.assertTrue(sesion.puede(auth.PERMISO_CONSOLA_SQL))

    def test_permiso_desconocido_se_descarga_al_leer(self):
        with self.assertLogs("taller.auth", level="WARNING") as avisos:
            usuario = auth.Usuario(username="carmen", nombre="Carmen", hash="x",
                                   permisos=[auth.PERMISO_CONSOLA_SQL,
                                             "superpoder"])
        self.assertEqual(usuario.permisos, [auth.PERMISO_CONSOLA_SQL])
        self.assertIn("superpoder", avisos.output[0])

    def test_el_kiosco_no_hereda_concesiones(self):
        # El usuario de kiosco se construye con rol cliente y permisos
        # vacios, aunque el operador apunte a una cuenta con privilegios.
        privilegiado = auth.Usuario(username="admin", nombre="Admin", hash="x",
                                    rol=auth.ROL_ADMIN,
                                    permisos=[auth.PERMISO_PUBLICAR_WAREHOUSE])
        with mock.patch.dict("os.environ", {"GIRO_DEMO_USER": "admin"}):
            with mock.patch.object(auth, "buscar_usuario",
                                   return_value=privilegiado):
                demo = auth._usuario_demo()
        self.assertIsNotNone(demo)
        self.assertEqual(demo.rol, auth.ROL_CLIENTE)
        self.assertEqual(demo.permisos, [])
        self.assertFalse(demo.es_admin)


if __name__ == "__main__":
    unittest.main()
