"""Pruebas de interfaz con ``AppTest``: son las mas lentas, van al final."""

import unittest
from pathlib import Path

import streamlit.testing.v1 as at

REPO = Path(__file__).resolve().parents[1]
DASHBOARD = REPO / "dashboard.py"
TIEMPO = 120


def _correr(kiosco=False):
    prueba = at.AppTest.from_file(str(DASHBOARD), default_timeout=TIEMPO)
    if kiosco:
        prueba.query_params["kiosco"] = "1"
    prueba.run()
    return prueba


def _excepciones(prueba):
    return [f"{type(e.value).__name__}: {e.value}" for e in prueba.exception]


@unittest.skipUnless(DASHBOARD.exists(), "sin dashboard.py en la raiz")
class TestLogin(unittest.TestCase):
    def test_sin_sesion_no_entra_y_no_lanza_excepcion(self):
        prueba = _correr()
        self.assertEqual(_excepciones(prueba), [])
        self.assertTrue(prueba.button, "no se ofrecio el boton de entrada")


@unittest.skipUnless(DASHBOARD.exists(), "sin dashboard.py en la raiz")
class TestKiosco(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kiosco = _correr(kiosco=True)

    def test_no_lanza_excepciones(self):
        self.assertEqual(_excepciones(self.kiosco), [])

    def test_se_ve_el_aviso_de_presentacion(self):
        textos = [i.value.lower() for i in self.kiosco.info]
        self.assertTrue(any("presentacion" in t for t in textos),
                        f"sin banner: {textos}")

    def test_no_aparece_la_consola_sql(self):
        etiquetas = [b.label.lower() for b in self.kiosco.button]
        self.assertFalse(any("consola" in e for e in etiquetas),
                         f"boton de consola en kiosco: {etiquetas}")


if __name__ == "__main__":
    unittest.main()
