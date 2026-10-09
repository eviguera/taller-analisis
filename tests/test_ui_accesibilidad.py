"""Pruebas globales de accesibilidad del shell: skip-link, foco, targets y tablas.

Son las mas lentas de la interfaz (AppTest contra el dashboard completo),
van al final junto a las de ``test_ui``.
"""

import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import streamlit as st
import streamlit.testing.v1 as at
from streamlit.elements.lib.mutable_tab_container import TabContainer

from ui import components as c
from ui import theme as tema

# Clase del proxy de contexto: expone ``theme`` (StreamlitTheme) y es donde
# se simula el tema oscuro que el navegador mandaria en runtime.
_ContextProxy = type(st.context)

REPO = Path(__file__).resolve().parents[1]
DASHBOARD = REPO / "dashboard.py"
TIEMPO = 120

#: Paginas migradas al wrapper ``c.dataframe`` y con pestañas perezosas: en
#: AppTest no se puede pulsar una pestana (no es un widget manipulable), asi
#: que se fuerza ``Tab.open`` y se ejecuta el contenido de todas.
PAGINAS_MIGRADAS = ("resumen", "clientes", "alertas", "predicciones")


def setUpModule():
    # GIRO_AUTH=0 en loopback abre la sesion sin login: las paginas necesitan
    # sesion para llegar a sus datos. Se restaura al terminar el modulo para
    # no afectar al resto de la suite.
    os.environ["GIRO_AUTH"] = "0"


def tearDownModule():
    os.environ.pop("GIRO_AUTH", None)


def _excepciones(prueba):
    return [f"{type(e.value).__name__}: {e.value}" for e in prueba.exception]


def _salto_contenido_renderizado(prueba) -> bool:
    html = "\n".join(str(m.value) for m in prueba.markdown)
    return 'class="skip-link"' in html and 'id="contenido"' in html


def _correr_pagina(nombre: str):
    """Ejecuta ``principal()`` de una pagina con todas sus pestanas abiertas."""
    origen = (
        "import importlib\n"
        f"importlib.import_module('ui.pages.{nombre}').principal()\n"
    )
    prueba = at.AppTest.from_string(origen, default_timeout=TIEMPO)
    with mock.patch.object(TabContainer, "open",
                           new_callable=mock.PropertyMock, return_value=True):
        prueba.run()
    return prueba


class TestCssGlobal(unittest.TestCase):
    """El CSS de accesibilidad existe en claro y en oscuro, sin outline: none."""

    def test_anillo_de_foco_visible_en_ambos_modos(self):
        for oscuro in (False, True):
            css = tema._css_accesibilidad(oscuro)
            self.assertIn(":focus-visible", css)
            self.assertIn("outline: 3px solid", css)
            self.assertNotIn("outline: none", css)

    def test_el_anillo_usa_el_color_del_tema_segun_el_modo(self):
        self.assertIn("#2563eb", tema._css_accesibilidad(False))
        self.assertIn("#60a5fa", tema._css_accesibilidad(True))

    def test_targets_interactivos_de_44px(self):
        for oscuro in (False, True):
            self.assertIn("min-height: 44px", tema._css_accesibilidad(oscuro))

    def test_skip_link_oculto_hasta_que_recibe_foco(self):
        css = tema._css_accesibilidad(False)
        self.assertIn(".skip-link", css)
        self.assertIn(".skip-link:focus", css)
        self.assertIn("left: -9999px", css)
        self.assertIn("left: 0", css)


class TestWrapperDataframe(unittest.TestCase):
    """``c.dataframe`` centraliza ancho fluido, indice oculto y etiquetas."""

    def _capturar(self, **kwargs):
        df = kwargs.pop("_df", "DF")
        with mock.patch.object(c.st, "dataframe") as captura:
            c.dataframe(df, **kwargs)
        return captura.call_args

    def test_ancho_fluido_e_indice_oculto_por_defecto(self):
        args = self._capturar()
        self.assertEqual(args.kwargs["width"], "stretch")
        self.assertTrue(args.kwargs["hide_index"])

    def test_etiquetas_se_funden_en_column_config(self):
        args = self._capturar(etiquetas={"total": "Total facturado"})
        self.assertEqual(args.kwargs["column_config"], {"total": "Total facturado"})

    def test_column_config_explicito_manda_sobre_la_etiqueta(self):
        args = self._capturar(etiquetas={"total": "Total"},
                              column_config={"total": "TOTAL XX"})
        self.assertEqual(args.kwargs["column_config"], {"total": "TOTAL XX"})

    def test_sin_column_config_no_se_inventa(self):
        args = self._capturar()
        self.assertIsNone(args.kwargs["column_config"])

    def test_indice_visible_lo_puede_forzar_la_pagina(self):
        args = self._capturar(indice_visible=True)
        self.assertFalse(args.kwargs["hide_index"])

    def test_alto_se_traduce_a_height(self):
        args = self._capturar(alto=320)
        self.assertEqual(args.kwargs["height"], 320)
        args = self._capturar()
        self.assertNotIn("height", args.kwargs)


class TestTituloSeccion(unittest.TestCase):
    """Regresion: ``titulo_seccion`` emite h2 (bajo el h1 de cabecera)."""

    def test_sigue_emitiendo_h2(self):
        with mock.patch.object(c.st, "markdown") as md:
            c.titulo_seccion("Ingresos")
        md.assert_called_once_with("## Ingresos")


@unittest.skipUnless(DASHBOARD.exists(), "sin dashboard.py en la raiz")
class TestSkipLinkEnShell(unittest.TestCase):
    """El skip-link y su ancla se inyectan en el render del dashboard."""

    @classmethod
    def setUpClass(cls):
        # Kiosco: entra sin login y recorre el mismo _navegar que la vista
        # completa, donde se inyecta el skip-link.
        cls.kiosco = at.AppTest.from_file(str(DASHBOARD), default_timeout=TIEMPO)
        cls.kiosco.query_params["kiosco"] = "1"
        cls.kiosco.run()

    def test_no_lanza_excepciones(self):
        self.assertEqual(_excepciones(self.kiosco), [])

    def test_el_skip_link_y_el_ancla_estan_en_el_render(self):
        self.assertTrue(_salto_contenido_renderizado(self.kiosco),
                        " falta 'class=\"skip-link\"' o 'id=\"contenido\"' en el render")

    def test_el_css_de_accesibilidad_se_inyecta_en_el_render(self):
        html = "\n".join(str(m.value) for m in self.kiosco.markdown)
        self.assertIn(".skip-link:focus", html)
        self.assertIn("min-height: 44px", html)
        self.assertIn(":focus-visible", html)

    def test_el_css_de_accesibilidad_se_inyecta_en_modo_oscuro(self):
        """AppTest solo renderiza con el tema claro que manda el cliente.

        Aqui se simula el mensaje de tema oscuro parcheando ``st.context``:
        lo que se verifica es que ``aplicar`` emite el anillo ``#60a5fa``
        cuando el runtime reporta ``dark``. El contraste real contra el
        fondo renderizado no se puede medir sin navegador.
        """
        oscuro = SimpleNamespace(type="dark")
        con_tema = at.AppTest.from_file(str(DASHBOARD), default_timeout=TIEMPO)
        con_tema.query_params["kiosco"] = "1"
        with mock.patch.object(_ContextProxy, "theme",
                               new_callable=mock.PropertyMock,
                               return_value=oscuro):
            con_tema.run()
        self.assertEqual(_excepciones(con_tema), [])
        html = "\n".join(str(m.value) for m in con_tema.markdown)
        self.assertIn("outline: 3px solid #60a5fa", html)


@unittest.skipUnless(DASHBOARD.exists(), "sin dashboard.py en la raiz")
class TestPaginasMigradas(unittest.TestCase):
    """Cada pagina migrada renderiza sin excepciones con todas sus pestanas."""

    def test_paginas_sin_excepciones(self):
        for nombre in PAGINAS_MIGRADAS:
            with self.subTest(pagina=nombre):
                prueba = _correr_pagina(nombre)
                self.assertEqual(_excepciones(prueba), [],
                                 f"excepciones en {nombre}: {_excepciones(prueba)}")

    def test_las_tablas_migradas_se_renderizan_como_dataframes(self):
        # clientes y predicciones emiten tablas en varias pestanas: con el
        # mock de Tab.open todas deben llegar al arbol como dataframe.
        for nombre, minimo in (("clientes", 4), ("predicciones", 5)):
            with self.subTest(pagina=nombre):
                prueba = _correr_pagina(nombre)
                self.assertGreaterEqual(
                    len(prueba.dataframe), minimo,
                    f"{nombre}: {len(prueba.dataframe)} dataframes en el render")


if __name__ == "__main__":
    unittest.main()
