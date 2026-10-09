"""Umbral de churn: lo comparten alertas, recomendaciones y reportes.

Si cada llamador interpretara la config a su manera, el mismo negocio
saldria "en riesgo" en el dashboard y "sano" en el PDF.
"""

import unittest

from src.core.config import UMBRAL_CHURN_DEFECTO, umbral_churn


class TestUmbralChurn(unittest.TestCase):
    def test_sin_config_usa_el_defecto(self):
        self.assertEqual(umbral_churn(None), UMBRAL_CHURN_DEFECTO)
        self.assertEqual(umbral_churn({}), UMBRAL_CHURN_DEFECTO)

    def test_el_tenant_puede_cambiarlo(self):
        self.assertEqual(umbral_churn({"churn_riesgo_umbral": 0.8}), 0.8)

    def test_cadena_vacia_no_reventa_el_reporte(self):
        # Un config.yaml escrito a mano deja "": float("") lanzaria
        # ValueError al generar la seccion de churn del reporte.
        self.assertEqual(umbral_churn({"churn_riesgo_umbral": ""}),
                         UMBRAL_CHURN_DEFECTO)

    def test_cadenas_numericas_se_convierten(self):
        self.assertEqual(umbral_churn({"churn_riesgo_umbral": "0.75"}), 0.75)


if __name__ == "__main__":
    unittest.main()
