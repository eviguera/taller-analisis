"""Analitica: mismos numeros que los datos, y sin caer con datasets vacios.

Los metodos reescritos para ir mas rapido (RFM, frecuencia de visitas,
inventario) se comprueban contra el calculo directo con pandas: si un dia la
vectorizacion cambia un resultado, aqui se ve.
"""

import unittest

import pandas as pd

from src.analyzer import Analyzer
from src.core.config import AppConfig
from src.data_loader import COLUMNAS_HECHOS, enriquecer_facturas
from src.predictions import Predictor

COLUMNAS_RFM = ["cliente_id", "nombre", "recencia_dias", "frecuencia", "monto",
                "R", "F", "M", "rfm_score", "segmento"]
SEGMENTOS = {"Campeones", "Cliente Leal", "Alto Valor", "En Riesgo",
             "Perdido", "Activo", "Promedio"}


def _datos():
    """Cinco clientes (los cuantiles del RFM necesitan al menos cuatro)."""
    facturas = pd.DataFrame({
        "id": [1, 2, 3, 4, 5, 6, 7, 8, 9],
        "cliente_id": [1, 1, 1, 2, 2, 3, 3, 4, 5],
        "vehiculo_id": [10, 10, 10, 11, 11, 12, 12, 13, 14],
        "fecha": pd.to_datetime([
            "2026-01-05", "2026-02-10", "2026-03-15",   # Ana: 3 visitas
            "2026-01-20", "2026-03-01",                 # Beto: 2
            "2026-02-02", "2026-04-04",                 # Caro: 2
            "2026-03-10",                               # Diego: 1
            "2026-04-15"]),                             # Eva: 1 (cancelada)
        "total": [1000.0, 1500.0, 500.0, 2000.0, 800.0,
                  1200.0, 300.0, 900.0, 700.0],
        "descuento": [0.0] * 9,
        "estado": ["Pagada"] * 8 + ["Cancelada"],
        "detalles": ["Cambio de aceite: 500", "Rotulacion: 200",
                     "Cambio de aceite: 500", "Frenos: 300",
                     "Cambio de aceite: 500", "Diagnostico: 100",
                     "Frenos: 300", "Rotulacion: 200", "Diagnostico: 100"],
    })
    return {
        "facturas": facturas,
        "clientes": pd.DataFrame({
            "id": [1, 2, 3, 4, 5],
            "nombre": ["Ana", "Beto", "Caro", "Diego", "Eva"],
            "telefono": ["55-1", "55-2", "55-3", "55-4", "55-5"],
            "email": ["a@x.mx", "b@x.mx", "c@x.mx", "d@x.mx", "e@x.mx"],
            "fecha_registro": pd.to_datetime(["2025-01-01"] * 5),
        }),
        "vehiculos": pd.DataFrame({
            "id": [10, 11, 12, 13, 14],
            "cliente_id": [1, 2, 3, 4, 5],
            "marca": ["VW", "Nissan", "Toyota", "Ford", "Mazda"],
            "modelo": ["Golf", "Versa", "Corolla", "Focus", "3"],
            "anio": [2018, 2019, 2020, 2017, 2021],
            "placa": ["AAA-001", "BBB-002", "CCC-003", "DDD-004", "EEE-005"],
            "color": ["blanco", "rojo", "gris", "azul", "negro"],
            "kilometraje": [80000, 120000, 45000, 200000, 30000],
        }),
        "inventario": pd.DataFrame({
            "id": [1, 2, 3],
            "producto": ["Aceite 5W30", "Filtro de aire", "Bateria"],
            "categoria": ["lubricante", "filtro", "electricidad"],
            "precio_costo": [100.0, 50.0, 400.0],
            "precio_venta": [180.0, 90.0, 650.0],
            "stock_actual": [5, 20, 3],
            "stock_minimo": [10, 5, 2],
            "ultima_venta": pd.to_datetime(["2026-01-01", "2026-03-01",
                                            "2026-04-01"]),
        }),
    }


class TestKpis(unittest.TestCase):
    def setUp(self):
        self.analyzer = Analyzer(_datos())

    def test_las_canceladas_no_suman(self):
        kpis = self.analyzer.kpis_globales()
        self.assertEqual(kpis["total_facturas"], 8)
        self.assertEqual(kpis["total_ingresos"], 8200.0)
        self.assertEqual(kpis["clientes_activos"], 4)
        self.assertEqual(kpis["vehiculos_atendidos"], 4)
        self.assertEqual(kpis["valor_cliente_promedio"], 2050.0)

    def test_servicios_unicos_se_cuentan_por_nombre(self):
        # Cuatro nombres distintos entre las ocho facturas validas.
        self.assertEqual(
            self.analyzer.kpis_globales()["servicios_unicos"], 4)

    def test_estacionalidad_deja_los_doce_meses(self):
        por_mes = self.analyzer.estacionalidad()["por_mes"]
        self.assertEqual(list(por_mes["mes"]), list(range(1, 13)))
        self.assertEqual(int(por_mes["ingresos"].sum()), 8200.0)


class TestRfm(unittest.TestCase):
    def setUp(self):
        self.rfm = Analyzer(_datos()).clientes_rfm()

    def test_esquema_y_orden_de_columnas(self):
        self.assertEqual(list(self.rfm.columns), COLUMNAS_RFM)

    def test_frecuencia_y_monto_coinciden_con_el_calculo_directo(self):
        esperado = (pd.DataFrame({
            "cliente_id": [1, 1, 1, 2, 2, 3, 3, 4],
            "nombre": ["Ana", "Ana", "Ana", "Beto", "Beto", "Caro", "Caro",
                       "Diego"],
            "total": [1000.0, 1500.0, 500.0, 2000.0, 800.0, 1200.0, 300.0,
                      900.0],
        }).groupby(["cliente_id", "nombre"])
            .agg(frecuencia=("total", "count"), monto=("total", "sum"))
            .reset_index())
        comparar = self.rfm[["cliente_id", "nombre", "frecuencia", "monto"]] \
            .sort_values(["cliente_id", "nombre"]).reset_index(drop=True)
        esperado = esperado.sort_values(["cliente_id", "nombre"]) \
            .reset_index(drop=True)
        pd.testing.assert_frame_equal(comparar, esperado)

    def test_recencia_se_mide_contra_la_ultima_visita_del_negocio(self):
        # Ultima factura valida: 2026-04-04 (Caro). Ana: 2026-03-15 -> 20 dias.
        ana = self.rfm[self.rfm["nombre"] == "Ana"].iloc[0]
        self.assertEqual(int(ana["recencia_dias"]), 20)
        self.assertTrue((self.rfm["recencia_dias"] >= 0).all())

    def test_esta_ordenado_por_puntuacion_y_con_segmento_valido(self):
        self.assertEqual(list(self.rfm["rfm_score"]),
                         sorted(self.rfm["rfm_score"], reverse=True))
        self.assertTrue(set(self.rfm["segmento"]) <= SEGMENTOS)
        # Con cuatro clientes los cuantiles salen: sin ellos R/F/M quedarian
        # en 0, que es la marca de "no calificado".
        self.assertTrue((self.rfm[["R", "F", "M"]] > 0).all().all())


class TestFrecuenciaDeVisitas(unittest.TestCase):
    def setUp(self):
        self.frec = Analyzer(_datos()).frecuencia_visitas_clientes()

    def test_columnas(self):
        self.assertEqual(list(self.frec.columns),
                         ["nombre", "facturas",
                          "promedio_dias_entre_visitas"])

    def test_suma_las_facturas_no_canceladas(self):
        self.assertEqual(int(self.frec["facturas"].sum()), 8)

    def test_promedio_del_diferencial_entre_visitas(self):
        # Ana: 2026-01-05 -> 2026-02-10 (36 dias) -> 2026-03-15 (33 dias).
        ana = self.frec[self.frec["nombre"] == "Ana"].iloc[0]
        self.assertAlmostEqual(float(ana["promedio_dias_entre_visitas"]), 34.5)
        # Una sola visita no tiene dias entre visitas.
        diego = self.frec[self.frec["nombre"] == "Diego"].iloc[0]
        self.assertTrue(pd.isna(diego["promedio_dias_entre_visitas"]))


class TestInventario(unittest.TestCase):
    def setUp(self):
        self.inv = Analyzer(_datos()).inventario_data()

    def test_columnas_derivadas(self):
        for columna in ["valor_inventario", "margen", "margen_pct",
                        "estado_stock"]:
            self.assertIn(columna, self.inv.columns)

    def test_estado_de_stock_por_umbral(self):
        por_producto = dict(zip(self.inv["producto"], self.inv["estado_stock"]))
        self.assertEqual(por_producto["Aceite 5W30"], "Bajo")    # 5 <= 10
        self.assertEqual(por_producto["Filtro de aire"], "Optimo")  # 20 > 7.5
        self.assertEqual(por_producto["Bateria"], "Medio")       # 3 <= 3

    def test_valores_calculados(self):
        aceite = self.inv[self.inv["producto"] == "Aceite 5W30"].iloc[0]
        self.assertEqual(float(aceite["valor_inventario"]), 500.0)
        self.assertEqual(float(aceite["margen"]), 80.0)
        self.assertEqual(float(aceite["margen_pct"]), 80.0)


class TestEspaciosVacios(unittest.TestCase):
    """Un cliente recien creado no tiene facturas: la pagina no debe caer."""

    def _vacio_con_cabeceras(self):
        datos = _datos()
        datos["facturas"] = datos["facturas"].iloc[0:0]
        return datos

    def test_analyzer_con_cero_facturas(self):
        analyzer = Analyzer(self._vacio_con_cabeceras())
        self.assertEqual(analyzer.kpis_globales()["total_facturas"], 0)
        with self.assertLogs("taller.analyzer", level="WARNING"):
            self.assertTrue(analyzer.clientes_rfm().empty)

    def test_analyzer_en_un_workspace_recien_creado(self):
        # data/ sin nada: load_all devuelve {}. Antes era un KeyError que la
        # UI mostraba como "No se pudieron cargar los datos".
        analyzer = Analyzer({})
        self.assertTrue(analyzer.df.empty)
        self.assertEqual(analyzer.kpis_globales()["total_facturas"], 0)
        # Sin cuantiles posibles el RFM se marca como no calificado (0).
        with self.assertLogs("taller.analyzer", level="WARNING"):
            self.assertTrue(analyzer.clientes_rfm().empty)
        self.assertTrue(analyzer.frecuencia_visitas_clientes().empty)
        self.assertTrue(analyzer.ingresos_por_marca().empty)
        self.assertTrue(analyzer.ingresos_por_mes().empty)

    def test_predictor_sin_inventario_devuelve_el_esquema_completo(self):
        prediccion = Predictor({}, cfg=AppConfig()).predecir_inventario()
        self.assertTrue(prediccion.empty)
        # La pagina selecciona estas columnas: un frame de dos columnas daba
        # KeyError en cualquier workspace sin inventario.
        for columna in ["producto", "demanda_mensual", "stock_objetivo",
                        "cantidad_recomendada", "recomendacion"]:
            self.assertIn(columna, prediccion.columns)

    def test_enriquecer_con_un_fichero_solo_de_cabeceras(self):
        vacio = self._vacio_con_cabeceras()["facturas"]
        enriquecido = enriquecer_facturas({"facturas": vacio})
        self.assertIn("estado", enriquecido.columns)
        self.assertTrue(enriquecido.empty)

    def test_el_esquema_vacio_es_el_mismo_que_el_de_con_datos(self):
        # Si un dia se anade una columna derivada, aqui se ve: el listado
        # que usa el workspace sin datos tiene que seguir coincidiendo.
        con_datos = enriquecer_facturas(_datos())
        self.assertEqual(list(con_datos.columns), COLUMNAS_HECHOS)
        self.assertEqual(list(enriquecer_facturas({}).columns),
                         COLUMNAS_HECHOS)


if __name__ == "__main__":
    unittest.main()
