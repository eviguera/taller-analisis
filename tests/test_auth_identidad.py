"""Pruebas de la identidad trasladada tras un puerto: ``src.core.auth`` sin streamlit.

Cuatro frentes:

1. El nucleo no arrastra streamlit al importarse (regla de direccion del
   hexagono: la API HTTP y el CLI no deben pagar el coste de la UI).
2. La politica de exposicion (env -> argv -> config.toml -> default) y la
   consola OIDC se leen con ``tomllib`` con la misma cascada que Streamlit.
   La defensa no se debilita: si la config no se puede leer, se asume
   expuesta y la autenticacion sigue puesta.
3. El registro del proveedor de identidad: federada primero, registro local
   despues, y sin proveedor registrado no hay via OIDC.
4. La UI con el proveedor registrado (``AppTest``): login local y llegada de
   ``identidad_ui()`` a ``inicio_de_sesion``.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.core import auth
from src.puertos import PuertoIdentidad

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    # Las pruebas pueden cambiar de directorio de trabajo: el repo queda fijo.
    sys.path.insert(0, str(REPO))

SECRETO_DE_PRUEBAS = "secreto-de-pruebas-giro-0123456789"


class _Aislado(unittest.TestCase):
    """Base: HOME, directorio de trabajo y variables de Streamlit aislados.

    Sin esto, un ``config.toml`` o un ``secrets.toml`` de la maquina entraria
    en la politica de exposicion y las pruebas dejarian de ser reproducibles.
    """

    def setUp(self):
        super().setUp()
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(os.chdir, self._cwd)
        self.raiz = Path(self._tmp.name)

        for parche in (
            mock.patch.dict(os.environ, {
                "HOME": str(self.raiz),
                "STREAMLIT_SERVER_ADDRESS": "",
                "STREAMLIT_CONFIG_FILE": "",
                "STREAMLIT_SECRETS_FILE": "",
                "GIRO_AUTH": "",
            }),
            mock.patch.object(sys, "argv", ["prueba"]),
        ):
            parche.start()
            self.addCleanup(parche.stop)
        os.chdir(self.raiz)

    def escribir(self, ruta: Path, contenido: str) -> Path:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(contenido, encoding="utf-8")
        return ruta

    @staticmethod
    def excepciones(prueba):
        return [f"{type(e.value).__name__}: {e.value}" for e in prueba.exception]


class _ProveedorFederado:
    """Proveedor sintetico del ``PuertoIdentidad``: misma respuesta siempre.

    Si la identidad es una excepcion, la lanza: sirve para probar la caida al
    registro local cuando la federacion falla.
    """

    def __init__(self, identidad):
        self.identidad = identidad
        self.consultas = 0

    def identidad_ui(self):
        self.consultas += 1
        if isinstance(self.identidad, Exception):
            raise self.identidad
        return self.identidad


class TestElNucleoNoArrastraStreamlit(unittest.TestCase):
    """Regla de direccion: ningun modulo de ``src/`` debe cargar streamlit."""

    def _importar(self, codigo: str) -> str:
        r = subprocess.run([sys.executable, "-c", codigo], cwd=REPO,
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_importar_auth_no_carga_streamlit(self):
        salida = self._importar(
            "import sys; import src.core.auth; print('streamlit' in sys.modules)")
        self.assertEqual(salida, "False")

    def test_ningun_paquete_de_src_carga_streamlit(self):
        salida = self._importar(
            "import importlib, pkgutil, sys; sys.path.insert(0, '.'); "
            "[importlib.import_module(m.name) "
            "for m in pkgutil.walk_packages(['src'], 'src.')]; "
            "print('streamlit' in sys.modules)")
        self.assertEqual(salida, "False")


class TestEscuchaSoloLoopback(_Aislado):
    """La defensa contra ``GIRO_AUTH=0`` expuesto, leida sin streamlit."""

    def test_config_toml_expuesto_no_permite_apagar_la_auth(self):
        self.escribir(self.raiz / ".streamlit" / "config.toml",
                      '[server]\naddress = "0.0.0.0"\n')
        self.assertFalse(auth._escucha_solo_loopback())
        with mock.patch.dict(os.environ, {"GIRO_AUTH": "0"}):
            # El modo abierto NO se activa: la app esta expuesta a la red.
            self.assertTrue(auth.auth_activada())

    def test_config_toml_en_loopback_si_permite_apagar_la_auth(self):
        self.escribir(self.raiz / ".streamlit" / "config.toml",
                      '[server]\naddress = "127.0.0.1"\n')
        self.assertTrue(auth._escucha_solo_loopback())
        with mock.patch.dict(os.environ, {"GIRO_AUTH": "0"}):
            self.assertFalse(auth.auth_activada())

    def test_sin_config_se_asume_el_default_de_streamlit_loopback(self):
        # Sin fichero, streamlit escucha en loopback: mismo criterio que antes.
        self.assertTrue(auth._escucha_solo_loopback())
        with mock.patch.dict(os.environ, {"GIRO_AUTH": "0"}):
            self.assertFalse(auth.auth_activada())

    def test_config_malformado_se_asume_expuesta(self):
        # TOML roto: no hay determinacion -> duda -> la auth sigue puesta.
        self.escribir(self.raiz / ".streamlit" / "config.toml",
                      '[server\naddress = "0.0.0.0"\n')
        self.assertFalse(auth._escucha_solo_loopback())
        with mock.patch.dict(os.environ, {"GIRO_AUTH": "0"}):
            self.assertTrue(auth.auth_activada())

    def test_address_de_tipo_inesperado_se_asume_expuesta(self):
        # Un address que no es texto no se puede evaluar: duda -> expuesta.
        self.escribir(self.raiz / ".streamlit" / "config.toml",
                      "[server]\naddress = 0\n")
        self.assertFalse(auth._escucha_solo_loopback())

    def test_la_variable_de_entorno_gana_sobre_el_config(self):
        self.escribir(self.raiz / ".streamlit" / "config.toml",
                      '[server]\naddress = "0.0.0.0"\n')
        with mock.patch.dict(os.environ, {"STREAMLIT_SERVER_ADDRESS": "127.0.0.1"}):
            self.assertTrue(auth._escucha_solo_loopback())

    def test_el_flag_de_argv_gana_sobre_el_config(self):
        self.escribir(self.raiz / ".streamlit" / "config.toml",
                      '[server]\naddress = "127.0.0.1"\n')
        for argv in (["app", "--server.address", "0.0.0.0"],
                     ["app", "--server.address=0.0.0.0"]):
            with self.subTest(argv=argv), mock.patch.object(sys, "argv", argv):
                self.assertFalse(auth._escucha_solo_loopback())

    def test_streamlit_config_file_se_respeta_y_sustituye_al_local(self):
        expuesto = self.escribir(self.raiz / "otro_config.toml",
                                 '[server]\naddress = "0.0.0.0"\n')
        self.escribir(self.raiz / ".streamlit" / "config.toml",
                      '[server]\naddress = "127.0.0.1"\n')
        with mock.patch.dict(os.environ, {"STREAMLIT_CONFIG_FILE": str(expuesto)}):
            self.assertFalse(auth._escucha_solo_loopback())

    def test_el_config_global_se_sobreescribe_por_el_del_directorio(self):
        global_ = self.raiz / ".streamlit_global"
        self.escribir(global_ / "config.toml", '[server]\naddress = "0.0.0.0"\n')
        self.escribir(self.raiz / ".streamlit" / "config.toml",
                      '[server]\naddress = "::1"\n')
        con_ruta = mock.patch.dict(os.environ,
                                   {"STREAMLIT_CONFIG_FILE": str(global_ / "config.toml")})
        # Sin el override, manda el del directorio de trabajo (cascada de
        # streamlit: home lo sobreescribe el proyecto). Con override, manda
        # el fichero forzado.
        self.assertTrue(auth._escucha_solo_loopback())
        with con_ruta:
            self.assertFalse(auth._escucha_solo_loopback())


class TestConsolaOidc(_Aislado):
    """``tiene_consola_oidc`` lee secrets.toml con tomllib, sin streamlit."""

    def test_sin_fichero_de_secretos_no_hay_consola(self):
        self.assertFalse(auth.tiene_consola_oidc())

    def test_auth_en_el_directorio_de_trabajo(self):
        self.escribir(self.raiz / ".streamlit" / "secrets.toml",
                      '[auth]\nclient_id = "abc123"\nclient_secret = "nunca"\n')
        self.assertTrue(auth.tiene_consola_oidc())

    def test_auth_en_el_directorio_global(self):
        self.escribir(self.raiz / ".streamlit" / "secrets.toml",
                      '[auth]\nclient_id = "abc123"\n')
        self.assertTrue(auth.tiene_consola_oidc())

    def test_fichero_sin_seccion_auth_o_vacia(self):
        self.escribir(self.raiz / ".streamlit" / "secrets.toml",
                      '[otro]\nclave = "valor"\n')
        self.assertFalse(auth.tiene_consola_oidc())
        self.escribir(self.raiz / ".streamlit" / "secrets.toml", "[auth]\n")
        self.assertFalse(auth.tiene_consola_oidc())

    def test_streamlit_secrets_file_se_respeta(self):
        ruta = self.escribir(self.raiz / "otros_secrets.toml",
                             '[auth]\nclient_id = "abc123"\n')
        with mock.patch.dict(os.environ, {"STREAMLIT_SECRETS_FILE": str(ruta)}):
            self.assertTrue(auth.tiene_consola_oidc())
        with mock.patch.dict(os.environ,
                             {"STREAMLIT_SECRETS_FILE": str(self.raiz / "no_existe.toml")}):
            self.assertFalse(auth.tiene_consola_oidc())

    def test_secrets_malformado_no_activa_la_consola_y_no_filtra_el_contenido(self):
        marcador = "SECRETO-QUE-NUNCA-APARECE"
        self.escribir(self.raiz / ".streamlit" / "secrets.toml",
                      f'[auth]\nclient_id = "{marcador}"\n[roto\n')
        with self.assertLogs("taller.auth", level="WARNING") as capturada:
            self.assertFalse(auth.tiene_consola_oidc())
        texto = "\n".join(capturada.output)
        self.assertNotIn(marcador, texto, "se filtro el contenido de secrets.toml")
        self.assertIn("secrets.toml", texto)


class TestProveedorIdentidad(_Aislado):
    """El registro: federada primero, local despues, sin proveedor sin OIDC."""

    def setUp(self):
        super().setUp()
        anterior = auth._proveedor_identidad
        auth.fijar_proveedor_identidad(None)
        self.addCleanup(auth.fijar_proveedor_identidad, anterior)
        for parche in (
            mock.patch.dict(os.environ, {"GIRO_AUTH_SECRET": SECRETO_DE_PRUEBAS}),
            # Secretos vacios: la unica forma de que haya consola OIDC en
            # estas pruebas es la que indique la propia prueba.
            mock.patch.dict(os.environ, {"STREAMLIT_SECRETS_FILE":
                                         str(self.raiz / "no_existe.toml")}),
        ):
            parche.start()
            self.addCleanup(parche.stop)

    def _usuario_local(self) -> auth.Usuario:
        registro = self.raiz / "usuarios.yaml"
        parche = mock.patch.dict(os.environ, {"GIRO_AUTH_USERS": str(registro)})
        parche.start()
        self.addCleanup(parche.stop)
        return auth.crear_usuario("local_prueba", "contrasena-larga-1",
                                  nombre="Local Prueba", rol=auth.ROL_ADMIN)

    def _consola_oidc_activa(self, contenido: str = '[auth]\nclient_id = "abc"\n'):
        ruta = self.escribir(self.raiz / "secrets.toml", contenido)
        parche = mock.patch.dict(os.environ, {"STREAMLIT_SECRETS_FILE": str(ruta)})
        parche.start()
        self.addCleanup(parche.stop)

    def test_sin_proveedor_no_hay_oidc(self):
        # El comportamiento de API y CLI: el registro local sigue intacto.
        self._usuario_local()
        token = auth.emitir_cookie(auth.Usuario(username="local_prueba",
                                                nombre="Local Prueba",
                                                hash="", rol=auth.ROL_ADMIN))
        self._consola_oidc_activa()  # Aunque hubiera secrets, sin proveedor no hay OIDC
        sesion = auth.inicio_de_sesion(token)
        self.assertEqual(sesion.usuario.username, "local_prueba")

    def test_con_proveedor_federado_gana_sobre_el_registro_local(self):
        self._consola_oidc_activa()
        token = auth.emitir_cookie(auth.Usuario(username="local_prueba",
                                                nombre="Local Prueba",
                                                hash="", rol=auth.ROL_ADMIN))
        proveedor = _ProveedorFederado({"email": "ana@empresa.com",
                                        "nombre": "Ana"})
        auth.fijar_proveedor_identidad(proveedor)
        sesion = auth.inicio_de_sesion(token)
        self.assertEqual(proveedor.consultas, 1)
        self.assertEqual(sesion.usuario.username, "ana@empresa.com")
        self.assertEqual(sesion.usuario.nombre, "Ana")

    def test_sin_consesola_oidc_el_proveedor_no_se_consulta(self):
        # secrets.toml sin seccion [auth]: ni se llama al proveedor (asi no
        # se colaba un warning de "identidad federada" por peticion).
        self._consola_oidc_activa("[otro]\nclave = 1\n")
        proveedor = _ProveedorFederado({"email": "ana@empresa.com", "nombre": "Ana"})
        auth.fijar_proveedor_identidad(proveedor)
        self._usuario_local()
        token = auth.emitir_cookie(auth.Usuario(username="local_prueba",
                                                nombre="Local Prueba",
                                                hash="", rol=auth.ROL_ADMIN))
        sesion = auth.inicio_de_sesion(token)
        self.assertEqual(proveedor.consultas, 0)
        self.assertEqual(sesion.usuario.username, "local_prueba")

    def test_si_el_proveedor_falla_se_usa_el_registro_local(self):
        self._consola_oidc_activa()
        auth.fijar_proveedor_identidad(_ProveedorFederado(RuntimeError("idp caido")))
        self._usuario_local()
        token = auth.emitir_cookie(auth.Usuario(username="local_prueba",
                                                nombre="Local Prueba",
                                                hash="", rol=auth.ROL_ADMIN))
        with self.assertLogs("taller.auth", level="WARNING") as capturada:
            sesion = auth.inicio_de_sesion(token)
        self.assertTrue(any("Identidad federada no disponible" in linea
                            for linea in capturada.output))
        self.assertEqual(sesion.usuario.username, "local_prueba")

    def test_si_el_proveedor_no_tiene_sesion_se_usa_el_registro_local(self):
        self._consola_oidc_activa()
        auth.fijar_proveedor_identidad(_ProveedorFederado(None))
        self._usuario_local()
        token = auth.emitir_cookie(auth.Usuario(username="local_prueba",
                                                nombre="Local Prueba",
                                                hash="", rol=auth.ROL_ADMIN))
        sesion = auth.inicio_de_sesion(token)
        self.assertEqual(sesion.usuario.username, "local_prueba")

    def test_el_puerto_es_estructural(self):
        # Un adaptador solo tiene que implementar el metodo: sin heredar nada.
        self.assertIsInstance(_ProveedorFederado(None), PuertoIdentidad)

        class _SinMetodo:
            pass

        self.assertNotIsInstance(_SinMetodo(), PuertoIdentidad)


class TestAdaptadorStreamlit(_Aislado):
    """El adaptador de la UI cumple el puerto y se registra al importar."""

    def setUp(self):
        super().setUp()
        import ui.login as ui_login
        self.ui_login = ui_login
        anterior = auth._proveedor_identidad
        self.addCleanup(auth.fijar_proveedor_identidad, anterior)

    def test_importar_ui_login_registra_el_proveedor(self):
        self.assertIsInstance(auth._proveedor_identidad,
                              self.ui_login.IdentidadStreamlit)

    def test_sin_consesola_oidc_devuelve_none(self):
        with mock.patch.object(self.ui_login.auth, "tiene_consola_oidc",
                               return_value=False):
            self.assertIsNone(self.ui_login.IdentidadStreamlit().identidad_ui())

    def test_sin_sesion_federada_devuelve_none(self):
        with mock.patch.object(self.ui_login.auth, "tiene_consola_oidc",
                               return_value=True), \
                mock.patch.object(self.ui_login.st, "user") as usuario:
            usuario.is_logged_in = False
            self.assertIsNone(self.ui_login.IdentidadStreamlit().identidad_ui())

    def test_con_sesion_federada_devuelve_email_y_nombre(self):
        with mock.patch.object(self.ui_login.auth, "tiene_consola_oidc",
                               return_value=True), \
                mock.patch.object(self.ui_login.st, "user") as usuario:
            usuario.is_logged_in = True
            usuario.email = "ana@empresa.com"
            usuario.name = "Ana"
            self.assertEqual(self.ui_login.IdentidadStreamlit().identidad_ui(),
                             {"email": "ana@empresa.com", "nombre": "Ana"})

    def test_el_adaptador_cumple_el_puerto(self):
        self.assertIsInstance(self.ui_login.IdentidadStreamlit(), PuertoIdentidad)


class TestSesionEnLaUi(_Aislado):
    """``AppTest``: el login de la UI con el proveedor ya registrado."""

    TIEMPO = 120

    def setUp(self):
        super().setUp()
        import ui.login as ui_login
        self.ui_login = ui_login
        anterior = auth._proveedor_identidad
        auth.fijar_proveedor_identidad(ui_login.IdentidadStreamlit())
        self.addCleanup(auth.fijar_proveedor_identidad, anterior)
        for parche in (
            mock.patch.dict(os.environ, {
                "GIRO_AUTH_USERS": str(self.raiz / "usuarios.yaml"),
                "GIRO_AUTH_SECRET": SECRETO_DE_PRUEBAS,
            }),
        ):
            parche.start()
            self.addCleanup(parche.stop)
        auth.crear_usuario("prueba_ui", "contrasena-larga-1",
                           nombre="Prueba UI", rol=auth.ROL_ADMIN)

    def _abrir(self):
        import streamlit.testing.v1 as at
        prueba = at.AppTest.from_file(str(REPO / "dashboard.py"),
                                      default_timeout=self.TIEMPO)
        prueba.run()
        return prueba

    def test_login_local_con_el_proveedor_registrado(self):
        prueba = self._abrir()
        self.assertEqual(self.excepciones(prueba), [])
        usuario = next(w for w in prueba.text_input if w.label == "Usuario")
        clave = next(w for w in prueba.text_input if w.label == "Contrasena")
        usuario.set_value("prueba_ui")
        clave.set_value("contrasena-larga-1")
        next(b for b in prueba.button if b.label == "Entrar").click()
        prueba.run()
        self.assertEqual(self.excepciones(prueba), [])
        self.assertIn("auth_token", prueba.session_state,
                      "el login no emitio la cookie de sesion")
        etiquetas = [b.label for b in prueba.button]
        self.assertNotIn("Entrar", etiquetas,
                         f"sigue en la pantalla de acceso: {etiquetas}")

    def test_identidad_ui_llega_a_inicio_de_sesion(self):
        # Forma sintetica: secrets.toml con [auth] y un proveedor que devuelve
        # una identidad. Sin consultar al IdP real, la UI entra directamente.
        secrets = self.escribir(self.raiz / "secrets.toml",
                                '[auth]\nclient_id = "abc123"\n')
        with mock.patch.dict(os.environ, {"STREAMLIT_SECRETS_FILE": str(secrets)}):
            auth.fijar_proveedor_identidad(
                _ProveedorFederado({"email": "ana@empresa.com",
                                    "nombre": "Ana Federada"}))
            prueba = self._abrir()
        self.assertEqual(self.excepciones(prueba), [])
        etiquetas = [b.label for b in prueba.button]
        self.assertNotIn("Entrar", etiquetas,
                         f"no paso del gate de sesion: {etiquetas}")
        # La federada no usa la cookie local: el token no existe, pero si hay
        # sesion (el gate solo se pasa con identidad).
        self.assertNotIn("auth_token", prueba.session_state,
                         "la sesion federada no usa la cookie local")


if __name__ == "__main__":
    unittest.main()
