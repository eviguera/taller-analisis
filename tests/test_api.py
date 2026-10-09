"""Pruebas del adaptador de entrada HTTP (``src/api``).

Dos promesas se verifican aqui, porque son las que rompidas dejan una
empresa viendo los datos de otra:

1. **Aislamiento.** El ``?workspace=`` es una peticion, no una decision:
   se valida la clave y despues manda ``auth.workspace_permitido``. La
   configuracion sale de ``config_del_workspace``, nunca de
   ``workspaces.config_actual`` (que en docker-compose prefiere
   ``GIRO_WORKSPACE=principal`` y habria leido la config de la demo para
   todos los clientes).
2. **Autorizacion.** ``GET /api/salud`` es el unico endpoint publico; el
   resto exige sesion y ``POST /api/consulta`` exige ademas el permiso
   ``consola_sql``.

Nada depende de ficheros gitignorados: los workspaces y el registro de
usuarios se crean en un temporal dentro de cada ``setUp``.

El cliente ASGI es propio porque ``starlette.testclient.TestClient``
necesita ``httpx``, que no esta en el venv de este repo y anadir una
dependencia no corresponde a esta tarea.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Optional
from unittest import mock
from urllib.parse import urlparse

import numpy as np
import pandas as pd

from src import workspaces
from src.api import crear_app
from src.api.esquemas import a_jsonable, registros
from src.aplicacion import VISTAS_PARA_EXPORTAR
from src.core import auth

# Registro de usuarios de las pruebas: un admin y un cliente acotado a
# 'empresa2'. El hash nunca se verifica en la API (solo se firma el token),
# pero tiene que estar para que el registro sea valido.
_REGISTRO = """
usuarios:
- username: admin_api
  nombre: Administradora API
  email: ''
  rol: admin
  workspaces: []
  permisos: []
  activo: true
  hash: scrypt$32768$8$1$YWJjZGVmZ2hpamtsbQ$aGF6
- username: cliente_api
  nombre: Cliente API
  email: ''
  rol: cliente
  workspaces:
  - empresa2
  permisos: []
  activo: true
  hash: scrypt$32768$8$1$YWJjZGVmZ2hpamtsbQ$aGF6
"""


def _constante_invalida(valor: str):
    """Rechaza ``NaN``/``Infinity`` al parsear: JSON estricto o nada."""
    raise AssertionError(f"El cuerpo trae una constante no estandar de JSON: {valor}")


class _Respuesta:
    """Respuesta HTTP minima que devuelve el cliente ASGI."""

    def __init__(self, estado: int, cabeceras: Dict[str, str], cuerpo: bytes):
        self.estado = estado
        self.cabeceras = cabeceras
        self._cuerpo = cuerpo

    @property
    def texto(self) -> str:
        return self._cuerpo.decode("utf-8", "replace")

    def json(self) -> Any:
        return json.loads(self.texto)

    def json_estricto(self) -> Any:
        """Como ``json`` pero que revienta con ``NaN``/``Infinity``.

        FastAPI renderiza con ``allow_nan=False``; aun asi se comprueba
        aqui para que un ``nan`` de un KPI no pueda colarse en un cuerpo
        que otro cliente interpretaria a su manera.
        """
        return json.loads(self.texto, parse_constant=_constante_invalida)


class _ClienteASGI:
    """Cliente ASGI minimo: scope + receive + send dentro de ``asyncio.run``.

    Reproduce lo que hace ``starlette.testclient`` sin depender de
    ``httpx``. Tolera la excepcion que ``ServerErrorMiddleware`` re-lanza
    *despues* de enviar la respuesta: en ese caso el cuerpo ya esta
    completo y se devuelve tal cual.
    """

    def __init__(self, app):
        self.app = app

    def get(self, ruta: str, headers: Optional[Dict[str, str]] = None) -> _Respuesta:
        return asyncio.run(self._peticion("GET", ruta, headers, None))

    def post(self, ruta: str, cuerpo: Any = None,
             headers: Optional[Dict[str, str]] = None) -> _Respuesta:
        return asyncio.run(self._peticion("POST", ruta, headers, cuerpo))

    async def _peticion(self, metodo: str, ruta: str,
                        headers: Optional[Dict[str, str]], cuerpo_json: Any) -> _Respuesta:
        partes = urlparse(ruta)
        cuerpo = b""
        cabeceras = []
        if cuerpo_json is not None:
            cuerpo = json.dumps(cuerpo_json, allow_nan=False).encode("utf-8")
            cabeceras.append((b"content-type", b"application/json"))
            cabeceras.append((b"content-length", str(len(cuerpo)).encode("ascii")))
        for clave, valor in (headers or {}).items():
            cabeceras.append((clave.lower().encode("latin-1"),
                              valor.encode("latin-1")))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": metodo,
            "scheme": "http",
            "path": partes.path,
            "raw_path": partes.path.encode("utf-8"),
            "query_string": partes.query.encode("utf-8"),
            "root_path": "",
            "headers": cabeceras,
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "state": {},
            "extensions": {"http.response.debug": {}},
        }

        entregado = {"cuerpo": False}

        async def receive() -> Dict[str, Any]:
            if not entregado["cuerpo"]:
                entregado["cuerpo"] = True
                return {"type": "http.request", "body": cuerpo, "more_body": False}
            return {"type": "http.disconnect"}

        estado = {"codigo": None, "cabeceras": {}, "trozos": []}

        async def send(mensaje: Dict[str, Any]) -> None:
            tipo = mensaje["type"]
            if tipo == "http.response.start":
                estado["codigo"] = mensaje["status"]
                estado["cabeceras"] = {
                    k.decode("latin-1"): v.decode("latin-1")
                    for k, v in mensaje.get("headers", [])
                }
            elif tipo == "http.response.body":
                estado["trozos"].append(mensaje.get("body", b""))

        fallo: Optional[BaseException] = None
        try:
            await self.app(scope, receive, send)
        except Exception as e:  # noqa: BLE001 — se re-lanza abajo si no hubo respuesta
            fallo = e

        if estado["codigo"] is None:
            if fallo is None:
                raise AssertionError(f"El servidor no respondio nada a {metodo} {ruta}")
            raise fallo

        return _Respuesta(estado["codigo"], estado["cabeceras"],
                          b"".join(estado["trozos"]))


def _datos_pequenos() -> Dict[str, pd.DataFrame]:
    """Tres facturas de dos clientes: suficiente para KPIs y cartera."""
    return {
        "facturas": pd.DataFrame({
            "id": [1, 2, 3],
            "cliente_id": [1, 2, 1],
            "vehiculo_id": [10, 11, 10],
            "fecha": ["2026-01-05", "2026-02-10", "2026-03-15"],
            "total": [150.5, 300.0, 90.25],
            "descuento": [0.0, 10.0, 5.0],
            "estado": ["Pagada", "Pagada", "Pendiente"],
            "detalles": ["Cambio de aceite", "Frenos; Pastillas", "Revision"],
        }),
        "clientes": pd.DataFrame({"id": [1, 2], "nombre": ["Ana", "Beto"]}),
        "vehiculos": pd.DataFrame({"id": [10, 11],
                                   "marca": ["Toyota", "Kia"],
                                   "modelo": ["Corolla", "Rio"]}),
    }


_ALERTA_DE_PRUEBA = {
    "tipo": "stock_bajo", "severidad": "critica",
    "titulo": "Pastillas requiere reabastecimiento",
    "detalle": "stock 0 vs minimo 4", "categoria": "Frenos", "valor": "x6",
}


class _BaseAPI(unittest.TestCase):
    """Entorno comun: workspaces y registro en temporal, app construida."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="giro_api_")
        self.addCleanup(tmp.cleanup)
        raiz = Path(tmp.name)

        # Raiz de workspaces propia: la del repo esta en .gitignore y no
        # existe en un clone limpio.
        raiz_ws = raiz / "workspaces"
        raiz_ws.mkdir()
        parche = mock.patch.object(workspaces, "RAIZ_WORKSPACES", raiz_ws)
        parche.start()
        self.addCleanup(parche.stop)

        workspaces.crear_workspace("empresa2", nombre="Empresa Dos", moneda="CLP")
        workspaces.crear_workspace("empresa-nueva", nombre="Empresa Nueva", moneda="USD")

        registro = raiz / "usuarios.yaml"
        registro.write_text(_REGISTRO, encoding="utf-8")

        self._entorno = mock.patch.dict(os.environ, {
            "GIRO_AUTH": "1",
            "GIRO_AUTH_SECRET": "secreto-de-pruebas-giro-0123456789",
            "GIRO_AUTH_USERS": str(registro),
            "GIRO_API_HOST": "",
            "GIRO_API_PORT": "8503",
            # Tal y como queda en docker-compose: por eso la API no puede
            # pasar por workspaces.config_actual.
            "GIRO_WORKSPACE": "principal",
            "STREAMLIT_SERVER_ADDRESS": "127.0.0.1",
        })
        self._entorno.start()
        self.addCleanup(self._entorno.stop)

        self.api = _ClienteASGI(crear_app())

    # -- utilidades ------------------------------------------------

    @staticmethod
    def _token(username: str) -> str:
        """Token firmado para un usuario. El registro ya lo contiene."""
        rol = auth.ROL_ADMIN if username.startswith("admin") else auth.ROL_CLIENTE
        return auth.emitir_cookie(auth.Usuario(username=username, nombre=username,
                                               hash="", rol=rol))

    @staticmethod
    def _cabeceras(username: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {_BaseAPI._token(username)}"}

    def _como(self, username: str, ruta: str) -> _Respuesta:
        return self.api.get(ruta, headers=self._cabeceras(username))


class TestSalud(_BaseAPI):
    """El unico endpoint publico."""

    def test_salud_no_pide_sesion(self):
        r = self.api.get("/api/salud")
        self.assertEqual(r.estado, 200)
        self.assertEqual(r.json()["estado"], "ok")

    def test_salud_no_expone_nada_del_negocio(self):
        r = self.api.get("/api/salud")
        cuerpo = r.texto
        for palabreja in ("total_ingresos", "kpis", "workspace", "factura", "cliente"):
            self.assertNotIn(palabreja, cuerpo)
        self.assertNotIn("secreto-de-pruebas", cuerpo)


class TestAutenticacion(_BaseAPI):
    """401 salvo para /api/salud."""

    def test_sin_sesion_devuelve_401_y_no_carga_datos(self):
        with mock.patch("src.api.rutas.cargar_datos") as cargar:
            r = self.api.get("/api/estado")
        self.assertEqual(r.estado, 401)
        self.assertIn("detail", r.json())
        self.assertNotIn("total_ingresos", r.texto)
        cargar.assert_not_called()

    def test_token_falsificado_devuelve_401(self):
        inventado = "eyJ1IjoiYWRtaW4ifQ" + "." + "f" * 64
        r = self.api.get("/api/estado", headers={"Authorization": f"Bearer {inventado}"})
        self.assertEqual(r.estado, 401)
        self.assertNotIn("kpis", r.texto)

    def test_token_de_un_usuario_que_no_existe_devuelve_401(self):
        token = auth.emitir_cookie(auth.Usuario(username="nadie", nombre="nadie",
                                                hash="", rol=auth.ROL_ADMIN))
        r = self.api.get("/api/estado", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.estado, 401)

    def test_bearer_y_cookie_valen_lo_mismo(self):
        token = self._token("admin_api")
        with mock.patch("src.api.rutas.cargar_datos", return_value={}):
            r_bearer = self.api.get("/api/estado",
                                    headers={"Authorization": f"Bearer {token}"})
            r_cookie = self.api.get("/api/estado",
                                    headers={"Cookie": f"{auth.NOMBRE_COOKIE}={token}"})
        self.assertEqual(r_bearer.estado, 200)
        self.assertEqual(r_cookie.estado, 200)
        self.assertEqual(r_bearer.json()["workspace"], r_cookie.json()["workspace"])

    def test_modo_abierto_en_loopback_no_pide_credencial(self):
        with mock.patch.dict(os.environ, {"GIRO_AUTH": "0"}), \
                mock.patch("src.api.rutas.cargar_datos", return_value={}):
            r = self.api.get("/api/estado")
        self.assertEqual(r.estado, 200)

    def test_modo_abierto_con_la_api_expuesta_devuelve_401(self):
        # GIRO_AUTH=0 mira la direccion de Streamlit (loopback), pero este
        # proceso escucha en 0.0.0.0: sin la comprobacion propia la API
        # quedaria abierta sin credencial.
        with mock.patch.dict(os.environ, {"GIRO_AUTH": "0", "GIRO_API_HOST": "0.0.0.0"}), \
                mock.patch("src.api.rutas.cargar_datos") as cargar:
            r = self.api.get("/api/estado")
        self.assertEqual(r.estado, 401)
        cargar.assert_not_called()

    def test_el_secreto_de_firma_nunca_aparece_en_respuesta(self):
        with mock.patch("src.api.rutas.cargar_datos", return_value={}):
            for ruta in ("/api/salud", "/api/estado", "/api/empresas"):
                r = self.api.get(ruta, headers=self._cabeceras("admin_api"))
                self.assertNotIn(os.environ["GIRO_AUTH_SECRET"], r.texto)


class TestWorkspaces(_BaseAPI):
    """La regla 1: el alcance lo decide el servidor."""

    def test_el_admin_elige_la_empresa_que_quiera(self):
        with mock.patch("src.api.rutas.cargar_datos", return_value={}):
            r = self._como("admin_api", "/api/estado?workspace=empresa2")
        self.assertEqual(r.estado, 200)
        self.assertEqual(r.json()["workspace"], "empresa2")

    def test_un_cliente_que_pide_otra_empresa_se_le_corrige(self):
        # 'empresa-nueva' existe y el admin la ve; el cliente no.
        with mock.patch("src.api.rutas.cargar_datos", return_value={}) as cargar:
            r = self._como("cliente_api", "/api/estado?workspace=empresa-nueva")
        self.assertEqual(r.estado, 200)
        self.assertEqual(r.json()["workspace"], "empresa2")
        # Y ademas los datos salen de la config corregida, no de la pedida.
        self.assertEqual(cargar.call_args[0][0].clave, "empresa2")

    def test_tampoco_porque_la_empresa_no_exista_se_le_escapa(self):
        with mock.patch("src.api.rutas.cargar_datos", return_value={}) as cargar:
            r = self._como("cliente_api", "/api/estado?workspace=empresa-que-no-existe")
        self.assertEqual(r.estado, 200)
        self.assertEqual(r.json()["workspace"], "empresa2")
        self.assertEqual(cargar.call_args[0][0].clave, "empresa2")

    def test_un_admin_que_pide_una_empresa_inexistente_recibe_404(self):
        r = self._como("admin_api", "/api/estado?workspace=empresa-que-no-existe")
        self.assertEqual(r.estado, 404)

    def test_una_clave_con_ruta_devuelve_400_y_no_toca_el_sistema_de_archivos(self):
        for clave in ("../../etc", "..", "a/b", "empresa%2F..%2Fraiz"):
            with self.subTest(clave=clave):
                r = self._como("admin_api", f"/api/estado?workspace={clave}")
                self.assertEqual(r.estado, 400)

    def test_sin_workspace_pedido_se_usa_el_de_la_sesion(self):
        with mock.patch("src.api.rutas.cargar_datos", return_value={}):
            r = self._como("cliente_api", "/api/estado")
        self.assertEqual(r.json()["workspace"], "empresa2")


class TestVistas(_BaseAPI):
    """Allowlist contra VISTAS_PARA_EXPORTAR."""

    def test_listado_solo_con_sesion(self):
        self.assertEqual(self.api.get("/api/vistas").estado, 401)
        r = self._como("admin_api", "/api/vistas")
        self.assertEqual(r.estado, 200)
        self.assertEqual(r.json()["vistas"], VISTAS_PARA_EXPORTAR)

    def test_vista_fuera_de_la_allowlist_es_404_sin_cargar_nada(self):
        with mock.patch("src.api.rutas.cargar_datos") as cargar, \
                mock.patch("src.aplicacion.vista") as vista:
            r = self._como("admin_api", "/api/vistas/no_existe")
        self.assertEqual(r.estado, 404)
        cargar.assert_not_called()
        vista.assert_not_called()

    def test_vista_permitida_devuelve_registros(self):
        marco = pd.DataFrame({"anio_mes": ["2026-01", "2026-02"],
                              "total": [100.5, 200.0]})
        with mock.patch("src.api.rutas.cargar_datos", return_value={}), \
                mock.patch("src.aplicacion.vista", return_value=marco) as vista:
            r = self._como("admin_api", "/api/vistas/ingresos_mensuales?limite=1")
        self.assertEqual(r.estado, 200)
        dato = r.json_estricto()
        self.assertEqual(dato["vista"], "ingresos_mensuales")
        self.assertEqual(dato["total_filas"], 2)
        self.assertEqual(dato["columnas"], ["anio_mes", "total"])
        self.assertEqual(dato["registros"], [{"anio_mes": "2026-01", "total": 100.5}])
        vista.assert_called_once()

    def test_limite_fuera_de_rango_es_422(self):
        r = self._como("admin_api", "/api/vistas/ingresos_mensuales?limite=0")
        self.assertEqual(r.estado, 422)


class TestConsultaSQL(_BaseAPI):
    """Consola: permiso aparte, validacion del caso de uso."""

    def test_el_admin_consulta_y_recibe_registros(self):
        marco = pd.DataFrame({"x": [1, 2]})
        with mock.patch("src.api.rutas.cargar_datos", return_value={}), \
                mock.patch("src.aplicacion.consulta_sql",
                           return_value=marco) as consulta:
            r = self.api.post("/api/consulta", cuerpo={"sql": "SELECT 1"},
                              headers=self._cabeceras("admin_api"))
        self.assertEqual(r.estado, 200)
        dato = r.json_estricto()
        self.assertEqual(dato["columnas"], ["x"])
        self.assertEqual(dato["total_filas"], 2)
        self.assertEqual(dato["registros"], [{"x": 1}, {"x": 2}])
        self.assertEqual(consulta.call_args[0][2], "SELECT 1")

    def test_un_cliente_no_tiene_consola(self):
        with mock.patch("src.api.rutas.cargar_datos") as cargar, \
                mock.patch("src.aplicacion.consulta_sql") as consulta:
            r = self.api.post("/api/consulta", cuerpo={"sql": "SELECT 1"},
                              headers=self._cabeceras("cliente_api"))
        self.assertEqual(r.estado, 403)
        cargar.assert_not_called()
        consulta.assert_not_called()

    def test_sin_sesion_es_401(self):
        r = self.api.post("/api/consulta", cuerpo={"sql": "SELECT 1"})
        self.assertEqual(r.estado, 401)

    def test_una_escritura_devuelve_400_y_no_llega_a_cargar(self):
        for sql in ("DROP TABLE hechos", "DELETE FROM hechos", "ATTACH 'x.db'"):
            with self.subTest(sql=sql), \
                    mock.patch("src.api.rutas.cargar_datos") as cargar, \
                    mock.patch("src.aplicacion.consulta_sql") as consulta:
                r = self.api.post("/api/consulta", cuerpo={"sql": sql},
                                  headers=self._cabeceras("admin_api"))
                self.assertEqual(r.estado, 400)
                self.assertIn("lectura", r.json()["detail"])
                cargar.assert_not_called()
                consulta.assert_not_called()

    def test_dos_sentencias_juntas_devuelven_400(self):
        # El ";" intermedio separa sentencias: la validacion es del caso de
        # uso, asi que llega antes de tocar el almacen.
        with mock.patch("src.api.rutas.cargar_datos") as cargar, \
                mock.patch("src.aplicacion.consulta_sql") as consulta:
            r = self.api.post("/api/consulta", cuerpo={"sql": "select 1; delete from t"},
                              headers=self._cabeceras("admin_api"))
        self.assertEqual(r.estado, 400)
        self.assertIn("sentencia", r.json()["detail"])
        cargar.assert_not_called()
        consulta.assert_not_called()

    def test_una_consola_vacia_devuelve_400(self):
        with mock.patch("src.api.rutas.cargar_datos") as cargar:
            r = self.api.post("/api/consulta", cuerpo={"sql": "   "},
                              headers=self._cabeceras("admin_api"))
        self.assertEqual(r.estado, 400)
        cargar.assert_not_called()

    def test_un_select_con_la_tabla_mal_puesta_no_es_un_error_interno(self):
        # El administrador tiene que poder corregir su SQL: un 500 generico
        # le diria que el servidor esta roto cuando el fallo es suyo.
        error_almacen = RuntimeError("Catalog Error: Table with name hechos does not exist")
        with mock.patch("src.api.rutas.cargar_datos", return_value={}), \
                mock.patch("src.aplicacion.consulta_sql", side_effect=error_almacen):
            with self.assertLogs("taller.api", level="WARNING") as registro:
                r = self.api.post("/api/consulta",
                                  cuerpo={"sql": "SELECT * FROM hechos"},
                                  headers=self._cabeceras("admin_api"))
        self.assertEqual(r.estado, 400)
        self.assertIn("Verifica la sintaxis SQL", r.json()["detail"])
        self.assertIn("Table with name hechos", r.json()["detail"])
        # Y la traza entera queda en el log, no se traga.
        self.assertIsNotNone(registro.records[0].exc_info)

    def test_el_limite_del_cuerpo_tambien_se_valida(self):
        r = self.api.post("/api/consulta",
                          cuerpo={"sql": "SELECT 1", "limite": 0},
                          headers=self._cabeceras("admin_api"))
        self.assertEqual(r.estado, 422)


class TestEmpresas(_BaseAPI):
    """El catalogo de la sesion, el mismo que el selector de la UI."""

    def test_sin_sesion_no_hay_listado(self):
        self.assertEqual(self.api.get("/api/empresas").estado, 401)

    def test_el_admin_ve_todas_las_empresas(self):
        r = self._como("admin_api", "/api/empresas")
        self.assertEqual(r.estado, 200)
        claves = [e["clave"] for e in r.json()["empresas"]]
        self.assertEqual(claves, ["empresa-nueva", "empresa2", "principal"])
        self.assertEqual(r.json()["actual"], "principal")
        principal = [e for e in r.json()["empresas"] if e["clave"] == "principal"][0]
        self.assertTrue(principal["principal"])

    def test_el_cliente_solo_ve_la_suya(self):
        r = self._como("cliente_api", "/api/empresas")
        self.assertEqual(r.estado, 200)
        self.assertEqual([e["clave"] for e in r.json()["empresas"]],
                         ["empresa2", "principal"])
        self.assertEqual(r.json()["actual"], "empresa2")


class TestEstado(_BaseAPI):
    """Radiografia analitica: KPIs, cartera, calidad y alertas."""

    def test_devuelve_kpis_en_json_estricto(self):
        with mock.patch("src.api.rutas.cargar_datos", return_value=_datos_pequenos()), \
                mock.patch("src.api.rutas.evaluar_alertas",
                           return_value=[_ALERTA_DE_PRUEBA]) as alertas:
            r = self._como("admin_api", "/api/estado")
        self.assertEqual(r.estado, 200)
        dato = r.json_estricto()
        self.assertEqual(dato["workspace"], "principal")
        self.assertIsInstance(dato["negocio"]["nombre"], str)
        self.assertTrue(dato["negocio"]["nombre"])
        self.assertEqual(dato["kpis"]["total_facturas"], 3)
        self.assertEqual(dato["kpis"]["total_ingresos"], 540.75)
        self.assertEqual(dato["cartera"]["clientes_activos"], 2)
        self.assertEqual(dato["calidad"]["facturas"]["registros"], 3)
        self.assertEqual(dato["alertas"]["total"], 1)
        self.assertEqual(dato["alertas"]["por_tipo"], {"stock_bajo": 1})
        self.assertIsNone(dato["aviso"])
        alertas.assert_called_once()

    def test_un_fallo_de_las_alertas_no_tumba_los_kpis_y_se_avisa(self):
        # Un modelo persistido con otra lista de features hace reventar
        # ``predecir_churn``: los KPIs siguen siendo validos y no pueden
        # pagar el error, pero el fallo no puede quedarse mudo.
        with mock.patch("src.api.rutas.cargar_datos", return_value=_datos_pequenos()), \
                mock.patch("src.api.rutas.evaluar_alertas",
                           side_effect=ValueError("X has 4 features, but the "
                                                  "model is expecting 5")):
            with self.assertLogs("taller.api", level="ERROR") as registro:
                r = self._como("admin_api", "/api/estado")
        self.assertEqual(r.estado, 200)
        dato = r.json_estricto()
        self.assertEqual(dato["kpis"]["total_facturas"], 3)
        self.assertEqual(dato["alertas"]["total"], 0)
        self.assertIn("alertas", dato["aviso"])
        # La traza entera queda registrada: sin ella el aviso bastaria
        # para esconder el bug del nucleo.
        self.assertIsNotNone(registro.records[0].exc_info)

    def test_sin_facturas_no_se_entrena_nada_y_el_nan_es_null(self):
        vacio = {"facturas": pd.DataFrame()}
        with mock.patch("src.api.rutas.cargar_datos", return_value=vacio), \
                mock.patch("src.api.rutas.evaluar_alertas") as alertas:
            r = self._como("admin_api", "/api/estado")
        self.assertEqual(r.estado, 200)
        dato = r.json_estricto()
        self.assertEqual(dato["kpis"]["total_facturas"], 0)
        self.assertEqual(dato["alertas"]["total"], 0)
        # Sin facturas el ticket promedio es NaN; JSON exige null.
        self.assertIsNone(dato["kpis"]["valor_cliente_promedio"])
        alertas.assert_not_called()

    def test_un_fallo_de_carga_es_un_500_generico_y_se_registra(self):
        with mock.patch("src.api.rutas.cargar_datos",
                        side_effect=OSError("/secretos/empresa2/datos.csv")):
            with self.assertLogs("taller.api", level="ERROR"):
                r = self._como("admin_api", "/api/estado")
        self.assertEqual(r.estado, 500)
        self.assertIn("No se pudieron cargar los datos", r.json()["detail"])
        self.assertNotIn("/secretos", r.texto)

    def test_una_excepcion_no_prevista_devuelve_500_en_json(self):
        with mock.patch("src.api.rutas.cargar_datos", return_value={}), \
                mock.patch("src.aplicacion.vista",
                           side_effect=RuntimeError("fallo interno con ruta privada")):
            with self.assertLogs("taller.api", level="ERROR") as registro:
                r = self._como("admin_api", "/api/vistas/ingresos_mensuales")
        self.assertEqual(r.estado, 500)
        self.assertEqual(r.json()["error"], "Error interno del servidor.")
        self.assertNotIn("ruta privada", r.texto)
        # La traza tiene que quedar registrada: sin ella el 500 seria un
        # error invisible para el operador.
        self.assertIsNotNone(registro.records[0].exc_info)


class TestSerializacion(unittest.TestCase):
    """numpy/pandas no pueden llegar tal cual a json.dumps."""

    def test_numpy_nan_y_fechas_se_normalizan(self):
        crudo = {
            "entero": np.int64(7),
            "decimal": np.float64(1.5),
            "nan": np.float64("nan"),
            "inf": float("inf"),
            "booleano": np.bool_(True),
            "fecha": pd.Timestamp("2026-01-02T03:04:05"),
            "sin_fecha": pd.NaT,
            "sin_valor": pd.NA,
            "serie": np.array([1, 2]),
            "mezcla": {"anidado": np.int64(3)},
        }
        puro = a_jsonable(crudo)
        texto = json.dumps(puro, allow_nan=False)
        dato = json.loads(texto)
        self.assertEqual(dato["entero"], 7)
        self.assertEqual(dato["decimal"], 1.5)
        self.assertIsNone(dato["nan"])
        self.assertIsNone(dato["inf"])
        self.assertIs(dato["booleano"], True)
        self.assertEqual(dato["fecha"], "2026-01-02T03:04:05")
        self.assertIsNone(dato["sin_fecha"])
        self.assertIsNone(dato["sin_valor"])
        self.assertEqual(dato["serie"], [1, 2])
        self.assertEqual(dato["mezcla"], {"anidado": 3})

    def test_registros_trunca_y_normaliza_celda_a_celda(self):
        marco = pd.DataFrame({"a": [1, 2, 3], "b": [np.nan, 2.0, 3.0]})
        filas = registros(marco, 2)
        self.assertEqual(len(filas), 2)
        self.assertIsNone(filas[0]["b"])
        json.dumps(filas, allow_nan=False)

    def test_un_objeto_desconocido_no_se_escapa_como_objeto_opaco(self):
        class _Rara:
            def __repr__(self):
                return "<rara>"
        salida = a_jsonable(_Rara())
        self.assertIsInstance(salida, str)


if __name__ == "__main__":
    unittest.main()
