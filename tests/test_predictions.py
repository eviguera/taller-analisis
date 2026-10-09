"""Regresion: reutilizar un modelo persistido exige coincidencia de features.

El bug real (detectado al verificar la API): ``predecir_churn`` comparaba
solo ``n_muestras``. Un ``churn.json`` antiguo con 5 features y las mismas
muestras que el esquema actual de 4 revienta en ``predict_proba`` — y lo
hace tambien en la pagina de Alertas y en el CLI, no solo en la API.
"""
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.exceptions import UndefinedMetricWarning

from src.core.config import AppConfig
from src.model_registry import ModelRegistry
from src.predictions import Predictor

FEATURES = ["frecuencia", "monto", "usuario_activo_dias", "promedio_gasto"]


def _data() -> dict:
    """9 clientes: 5 con ultima visita antigua (churn) y 4 recientes."""
    filas = []
    fid = 1
    for c in range(9):
        antiguo = c < 5
        for d in (0, 1, 2):
            dia = (10 + c * 3 + d) if antiguo else (170 + c + d)
            filas.append({
                "id": fid,
                "fecha": pd.Timestamp("2026-01-01") + pd.Timedelta(days=dia),
                "cliente_id": f"C{c}",
                "nombre": f"Cliente {c}",
                "total": 100.0 + fid,
                "estado": "Emitida",
            })
            fid += 1
    return {"facturas": pd.DataFrame(filas)}


class TestReutilizacionDeModelos(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cfg = AppConfig(
            clave="test", db_path=Path(self._tmp.name) / "almacen.duckdb")
        self.data = _data()

    def tearDown(self):
        self._tmp.cleanup()

    def _registro(self) -> ModelRegistry:
        return ModelRegistry(str(Path(self.cfg.db_path).parent / "models"))

    def test_modelo_persistido_con_otras_features_no_se_reutiliza(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UndefinedMetricWarning)
            primera = Predictor(self.data, cfg=self.cfg).predecir_churn()
        self.assertEqual(primera["modelo"], "Random Forest")
        self.assertEqual(primera["registro"]["features"], FEATURES)

        # Se simula el modelo heredado que rompia: mismas n_muestras,
        # 5 features (los churn.json antiguos incluian 'recencia').
        modelo_viejo = RandomForestClassifier(n_estimators=5, random_state=0)
        modelo_viejo.fit(
            np.random.RandomState(0).rand(9, 5),
            np.array([1, 1, 1, 1, 1, 0, 0, 0, 0]))
        self._registro().guardar("churn", modelo_viejo, {
            "n_muestras": primera["registro"]["n_muestras"],
            "features": FEATURES + ["recencia"],
            "evaluacion": {"nota": "heredado"},
        })

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UndefinedMetricWarning)
            segunda = Predictor(self.data, cfg=self.cfg).predecir_churn()

        # Sin el fix, esto revienta en predict_proba; con el, reentrena.
        self.assertEqual(segunda["modelo"], "Random Forest")
        self.assertEqual(segunda["registro"]["features"], FEATURES)
        self.assertNotEqual(
            segunda["registro"].get("evaluacion", {}).get("nota"), "heredado")

    def test_una_meta_sin_features_tambien_reentrena(self):
        # Registros antiguos, anteriores a guardar 'features'.
        self._registro().guardar("churn", RandomForestClassifier(), {
            "n_muestras": 9, "evaluacion": {"nota": "heredado"}})

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UndefinedMetricWarning)
            resultado = Predictor(self.data, cfg=self.cfg).predecir_churn()

        self.assertEqual(resultado["registro"]["features"], FEATURES)

    def test_un_modelo_entrenado_con_una_sola_clase_no_revienta(self):
        # El split temporal sin stratify puede dejar y_train mono-clase:
        # predict_proba devuelve entonces Nx1 y `[:, 1]` era un IndexError.
        n_muestras = len(self.data["facturas"]["cliente_id"].unique())
        modelo_mono = RandomForestClassifier(n_estimators=5, random_state=0)
        modelo_mono.fit(
            np.random.RandomState(1).rand(n_muestras, len(FEATURES)),
            np.zeros(n_muestras, dtype=int))
        self._registro().guardar("churn", modelo_mono, {
            "n_muestras": n_muestras, "features": FEATURES,
            "evaluacion": {"nota": "mono-clase"}})

        resultado = Predictor(self.data, cfg=self.cfg).predecir_churn()

        # No conoce la clase 1: todos los riesgos a cero, sin excepcion.
        self.assertTrue((resultado["resultados"]["prob_churn"] == 0).all())


if __name__ == "__main__":
    unittest.main()
