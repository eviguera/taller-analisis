"""Recorrido de la pagina de datos con ``AppTest``: pestanas, cero excepciones.

La pagina es la que mas logica de negocio concentraba; tras extraerla al
nucleo aqui se comprueba lo que queda en la UI: que cada pestana abre y
renderiza sin excepcion siendo administrador (las pestanas de conectores y
SQL solo existen con permiso).
"""

import unittest
from pathlib import Path
from unittest import mock

import streamlit.testing.v1 as at

from src.core import auth

REPO = Path(__file__).resolve().parents[1]
PAGINA = REPO / "ui" / "pages" / "datos.py"
TIEMPO = 120

#: Titulos en el mismo orden en que los monta ``principal``.
PESTANAS = ["Importar / detectar", "Procesar (ETL)", "Esquema de datos",
            "Calidad de datos", "Integracion PSPP/SPSS",
            "Conectores ERP/SQL", "Consultas SQL"]


def _excepciones(prueba):
    return [f"{type(e.value).__name__}: {e.value}" for e in prueba.exception]


@unittest.skipUnless(PAGINA.exists(), "sin ui/pages/datos.py")
class TestRecorridoPaginaDatos(unittest.TestCase):
    """Abre las siete pestanas de la pagina como administrador.

    El registro de usuarios (``config/usuarios.yaml``) es un archivo local
    que puede no existir, asi que la sesion se construye con el registro
    parcheado en memoria: la prueba no depende de credenciales reales ni
    escribe en el registro.
    """

    def setUp(self):
        self.admin = auth.Usuario(username="admin_pagina", nombre="Admin",
                                  hash="x", rol=auth.ROL_ADMIN)
        parche = mock.patch.object(
            auth, "cargar_registro",
            return_value={self.admin.username: self.admin})
        parche.start()
        self.addCleanup(parche.stop)
        self.prueba = at.AppTest.from_file(str(PAGINA), default_timeout=TIEMPO)
        self.prueba.session_state["auth_token"] = auth.emitir_cookie(self.admin)
        self.prueba.run()

    def test_una_sesion_admin_ve_las_siete_pestanas(self):
        self.assertEqual(_excepciones(self.prueba), [])
        self.assertEqual([t.label for t in self.prueba.tabs], PESTANAS)

    def test_cada_pestana_abre_sin_excepciones(self):
        self.assertEqual(_excepciones(self.prueba), [], "pestana inicial")
        for etiqueta in PESTANAS:
            with self.subTest(pestana=etiqueta):
                # ``st.tabs(..., on_change="rerun")`` deja el estado de la
                # pestana abierta en su clave: cambiarla y re-ejecutar es
                # lo mismo que el usuario haga clic en su titulo.
                self.prueba.session_state["tabs_datos"] = etiqueta
                self.prueba.run()
                self.assertEqual(_excepciones(self.prueba), [],
                                 f"excepcion al abrir «{etiqueta}»")

    def test_al_abrir_consultas_sql_se_ve_el_aviso_de_solo_lectura(self):
        # Ademas de no lanzar, la pestana tiene que renderizar lo suyo: es
        # la comprobacion de que cambiar ``tabs_datos`` abre la de verdad.
        self.prueba.session_state["tabs_datos"] = "Consultas SQL"
        self.prueba.run()
        textos = [i.value for i in self.prueba.info]
        self.assertTrue(any("solo lectura" in t for t in textos), textos)

    def test_al_abrir_el_etl_se_ofrece_el_boton_de_procesar(self):
        self.prueba.session_state["tabs_datos"] = "Procesar (ETL)"
        self.prueba.run()
        etiquetas = [b.label for b in self.prueba.button]
        self.assertIn("Procesar datos ahora", etiquetas)


if __name__ == "__main__":
    unittest.main()
