"""Pruebas del Asesor IA sin depender de una clave real."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src.aplicacion import asesor_negocio
from src.adapters.llm.openrouter import OpenRouterAdapter


class TestDisponibilidadAsesor(unittest.TestCase):
    def test_sin_clave_no_esta_disponible(self):
        with patch.dict(
            os.environ,
            {"GIRO_IA_API_KEY": "", "OPENROUTER_API_KEY": ""},
        ):
            self.assertFalse(asesor_negocio.asesor_ia_disponible())

    def test_con_clave_en_el_entorno_esta_disponible(self):
        with patch.dict(
            os.environ,
            {"GIRO_IA_API_KEY": "clave-de-prueba", "OPENROUTER_API_KEY": ""},
        ):
            self.assertTrue(asesor_negocio.asesor_ia_disponible())

    def test_adaptador_expone_su_disponibilidad(self):
        self.assertFalse(OpenRouterAdapter(api_key="").disponible())
        self.assertTrue(OpenRouterAdapter(api_key="clave-de-prueba").disponible())

    def test_limite_de_tokens_es_configurable(self):
        with patch.dict(os.environ, {"GIRO_IA_MAX_TOKENS": "4000"}):
            self.assertEqual(4000, OpenRouterAdapter(api_key="clave-de-prueba").max_tokens)


if __name__ == "__main__":
    unittest.main()
