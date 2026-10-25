"""Pruebas end-to-end del pipeline de GIRO.

Verifica que el flujo completo funciona: carga de datos -> ETL -> almacén
-> KPIs -> predicciones -> alertas. Usa datos mínimos creados en temporal.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd
import yaml

from src import workspaces
from src.core.config_manager import cargar_config
from src.core.pipeline import procesar_etl, load_all
from src.analyzer import Analyzer
from src.predictions import Predictor
from src.alerts import evaluar_alertas


class TestE2EPipeline(unittest.TestCase):
    """Pruebas end-to-end del pipeline de GIRO."""

    def setUp(self):
        """Crea un workspace temporal con datos de ejemplo mínimos."""
        self.tmp = tempfile.TemporaryDirectory(prefix="giro_e2e_")
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.datos_dir = self.raiz / "data"
        self.datos_dir.mkdir()
        self._crear_datos_ejemplo()

    def _crear_datos_ejemplo(self):
        """Crea archivos CSV mínimos para prueba E2E."""
        # Clientes
        pd.DataFrame({
            "id": [1, 2, 3],
            "nombre": ["Cliente 1", "Cliente 2", "Cliente 3"],
            "telefono": ["555-0001", "555-0002", "555-0003"],
            "email": ["c1@test.com", "c2@test.com", "c3@test.com"],
            "fecha_registro": ["2024-01-01", "2024-01-15", "2024-02-01"],
        }).to_csv(self.datos_dir / "clientes.csv", index=False)

        # Vehículos
        pd.DataFrame({
            "id": [1, 2, 3],
            "cliente_id": [1, 2, 3],
            "marca": ["Toyota", "Nissan", "Honda"],
            "modelo": ["Corolla", "Versa", "Civic"],
            "anio": [2018, 2019, 2020],
            "placa": ["ABC-123", "DEF-456", "GHI-789"],
            "color": ["Blanco", "Negro", "Rojo"],
            "kilometraje": [45000, 30000, 25000],
        }).to_csv(self.datos_dir / "vehiculos.csv", index=False)

        # Servicios
        pd.DataFrame({
            "id": [1, 2],
            "nombre": ["Cambio de aceite", "Revisión de frenos"],
            "precio_base": [5000, 15000],
            "tiempo_estimado_min": [30, 60],
        }).to_csv(self.datos_dir / "servicios.csv", index=False)

        # Facturas (suficientes para predicciones)
        import datetime
        filas = []
        for i in range(20):
            mes = 1 + (i % 12)
            filas.append({
                "id": i + 1,
                "cliente_id": 1 + (i % 3),
                "vehiculo_id": 1 + (i % 3),
                "fecha": f"2024-{mes:02d}-15",
                "total": 10000 + i * 500,
                "descuento": 0,
                "estado": "Pagada" if i % 4 != 3 else "Pendiente",
                "detalles": f"{1 + (i % 2)}:1",
            })
        pd.DataFrame(filas).to_csv(self.datos_dir / "facturas.csv", index=False)

        # Inventario
        pd.DataFrame({
            "id": [1, 2],
            "producto": ["Aceite 5W30", "Filtro de aceite"],
            "categoria": ["Lubricantes", "Filtros"],
            "precio_costo": [3000, 2000],
            "precio_venta": [5000, 3500],
            "stock_actual": [2, 50],
            "stock_minimo": [10, 5],
        }).to_csv(self.datos_dir / "inventario.csv", index=False)

        # Config
        import yaml
        config = {
            "negocio": {
                "clave": "test-e2e",
                "nombre": "Negocio Test E2E",
                "moneda": "MXN",
            },
            "almacen": {
                "directorio_datos": "data",
                "db": "data/almacen.duckdb",
            },
        }
        (self.raiz / "config.yaml").write_text(
            yaml.dump(config, allow_unicode=True),
            encoding="utf-8",
        )

    def test_etl_completa(self):
        """El ETL completa sin errores y registra tablas."""
        cfg = cargar_config(self.raiz / "config.yaml")
        cfg.directorio_datos = self.datos_dir
        cfg.db_path = self.datos_dir / "almacen.duckdb"

        resultado = procesar_etl(cfg, self.raiz, guardar=True)
        self.assertTrue(resultado.ok)
        self.assertGreater(resultado.tablas_registradas.get("facturas", 0), 0)

    def test_analyzer_kpis(self):
        """El Analyzer calcula KPIs correctamente."""
        cfg = cargar_config(self.raiz / "config.yaml")
        cfg.directorio_datos = self.datos_dir

        data = load_all(cfg)
        self.assertGreater(len(data.get("facturas", [])), 0)

        analyzer = Analyzer(data)
        kpis = analyzer.kpis_globales()
        self.assertGreater(kpis["total_ingresos"], 0)
        self.assertGreater(kpis["total_facturas"], 0)
        self.assertGreater(kpis["clientes_activos"], 0)

    def test_predictions_ejecutan(self):
        """Las predicciones se ejecutan sin errores."""
        cfg = cargar_config(self.raiz / "config.yaml")
        cfg.directorio_datos = self.datos_dir

        data = load_all(cfg)
        predictor = Predictor(data, cfg=cfg)

        res_ingresos = predictor.predecir_ingresos(meses_futuros=3)
        self.assertIn("predicciones", res_ingresos)
        self.assertGreater(len(res_ingresos["predicciones"]), 0)

        res_churn = predictor.predecir_churn()
        self.assertIn("resultados", res_churn)

        res_inv = predictor.predecir_inventario()
        self.assertIsInstance(res_inv, type(pd.DataFrame()))

    def test_alertas_evaluan(self):
        """Las alertas se evalúan sin errores."""
        cfg = cargar_config(self.raiz / "config.yaml")
        cfg.directorio_datos = self.datos_dir

        data = load_all(cfg)
        alertas = evaluar_alertas(cfg, data)
        self.assertIsInstance(alertas, list)


if __name__ == "__main__":
    unittest.main()