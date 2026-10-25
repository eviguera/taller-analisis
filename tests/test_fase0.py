"""Pruebas de regresión de la Fase 0 (bugs de núcleo y contratos)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from src.aplicacion.almacen import firma_fuentes
from src.agentes_estrategicos.strategy import generar_dossier_de_decision
from src.predictions import Predictor


def _facturas(meses: int) -> pd.DataFrame:
    filas = []
    for i in range(meses):
        fecha = pd.Timestamp("2024-01-15") + pd.DateOffset(months=i)
        filas.append(
            {
                "fecha": fecha,
                "total": 1000.0 + (i * 25.0),
                "cliente_id": f"cliente-{i % 3}",
                "estado": "Pagada",
            }
        )
    return pd.DataFrame(filas)


class TestPredicciones(unittest.TestCase):
    def test_pocos_meses_devuelve_insuficiente_sin_nameerror(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = SimpleNamespace(db_path=Path(tmp) / "almacen.duckdb")
            predictor = Predictor({"facturas": _facturas(6)}, cfg=cfg)

            resultado = predictor.predecir_ingresos(meses_futuros=3)

        self.assertEqual("Insuficiente", resultado["modelo"])
        self.assertEqual(6, len(resultado["historial"]))
        self.assertIn("hay 6", resultado["evaluacion"]["nota"])

    def test_doce_meses_entrena_y_predice(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = SimpleNamespace(db_path=Path(tmp) / "almacen.duckdb")
            predictor = Predictor({"facturas": _facturas(14)}, cfg=cfg)

            resultado = predictor.predecir_ingresos(meses_futuros=3)

        self.assertNotEqual("Insuficiente", resultado["modelo"])
        self.assertFalse(resultado["predicciones"].empty)


class TestEstrategia(unittest.TestCase):
    def _analisis(self, facturas: pd.DataFrame) -> dict:
        return {
            "kpis": {
                "total_ingresos": float(facturas["total"].sum()),
                "total_facturas": len(facturas),
                "ticket_promedio": float(facturas["total"].mean()),
            },
            "salud_cartera": {},
            "alertas": [],
        }

    def test_con_datos_crudos_los_escenarios_no_son_cero(self):
        facturas = _facturas(18)
        dossier = generar_dossier_de_decision(
            self._analisis(facturas),
            data={"facturas": facturas},
        )

        self.assertTrue(dossier["escenarios_disponibles"])
        self.assertGreater(dossier["escenario_conservador"]["ingresos"], 0)
        self.assertGreater(dossier["escenario_agresivo"]["ingresos"], 0)
        self.assertGreater(dossier["delta_ingresos"], 0)
        self.assertIsNone(dossier["motivo_sin_escenarios"])

    def test_sin_datos_crudos_marca_escenarios_no_disponibles(self):
        facturas = _facturas(18)
        dossier = generar_dossier_de_decision(self._analisis(facturas))

        self.assertFalse(dossier["escenarios_disponibles"])
        self.assertIsNotNone(dossier["motivo_sin_escenarios"])
        self.assertEqual(0, dossier["escenario_conservador"]["ingresos"])


class TestAlmacen(unittest.TestCase):
    def test_firma_fuentes_avisa_sin_nameerror_si_falta_mapeo(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = SimpleNamespace(
                datasets={"facturas": object()},
                directorio_datos=tmp,
                db_path=str(Path(tmp) / "almacen.duckdb"),
            )
            with self.assertLogs("src.aplicacion.almacen", level="WARNING") as logs:
                firma = firma_fuentes(cfg)

        self.assertEqual("", firma)
        self.assertTrue(any("mapeo" in mensaje for mensaje in logs.output))


if __name__ == "__main__":
    unittest.main()
