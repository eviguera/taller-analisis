"""Reglas de calidad: se aplican donde hay columna y no se tragan errores.

Comprueba las dos propiedades que hacen util al modulo: que una regla solo
juzga a un dataset que tenga el campo (nada de reglas del vertico), y que una
regla rota se reporta como ERROR en vez de tumbar el ETL.
"""

import unittest

import pandas as pd

from src.core import calidad
from src.core.calidad import ESTADO_ERROR, ESTADO_OK, ESTADO_REVISAR


def _facturas():
    """Un dataset generico: sin stock, sin email, sin precios de servicio."""
    return pd.DataFrame({
        "id": [1, 2, 3],
        "cliente_id": [10, 11, 10],
        "fecha": pd.to_datetime(["2026-01-05", "2026-02-11", "2026-03-02"]),
        "total": [1200.0, 0.0, 850.5],
    })


class TestAplicacion(unittest.TestCase):
    def test_solo_juzga_lo_que_el_dataset_tiene(self):
        res = calidad.evaluar_dataset("servicios", pd.DataFrame(
            {"id": [1, 2], "precio_base": [100.0, -5.0]}))
        # Sin fecha ni total ni cliente_id: esas reglas no aplican.
        self.assertEqual(set(res["campo"]), {"id", "precio_base"})

    def test_las_reglas_que_si_pasan_estan_evaluadas(self):
        res = calidad.evaluar_dataset("facturas", _facturas())
        self.assertEqual(set(res["campo"]),
                         {"id", "cliente_id", "fecha", "total"})
        self.assertFalse(set(res["campo"]) & {"stock_actual", "email"})

    def test_dataset_sin_reglas_aplicables_devuelve_vacio(self):
        res = calidad.evaluar_dataset("extra", pd.DataFrame({"zeta": [1]}))
        self.assertTrue(res.empty)


class TestResultados(unittest.TestCase):
    def test_todo_correcto_da_ok_al_cien_por_ciento(self):
        res = calidad.evaluar_dataset("clientes", pd.DataFrame(
            {"id": [1, 2], "email": ["a@b.co", "c@d.mx"], "total": [1.0, 2.0]}))
        self.assertTrue((res["estado"] == ESTADO_OK).all())
        self.assertTrue((res["tasa"] == 1.0).all())

    def test_total_en_cero_no_pasa_el_rango_estricto(self):
        res = calidad.evaluar_dataset("facturas", _facturas())
        fila = res[res["campo"] == "total"].iloc[0]
        self.assertEqual(fila["estado"], ESTADO_REVISAR)
        self.assertEqual(int(fila["cumplen"]), 2)
        self.assertEqual(int(fila["evaluadas"]), 3)

    def test_no_texto_que_no_es_numero_no_se_convierte_en_cero(self):
        res = calidad.evaluar_dataset("facturas", pd.DataFrame(
            {"id": [1], "total": ["no es numero"]}))
        self.assertEqual(res[res["campo"] == "total"].iloc[0]["estado"],
                         ESTADO_REVISAR)

    def test_fecha_en_el_futuro_no_pasa(self):
        res = calidad.evaluar_dataset("facturas", pd.DataFrame(
            {"id": [1],
             "fecha": [pd.Timestamp.today() + pd.Timedelta(days=45)]}))
        self.assertEqual(res[res["campo"] == "fecha"].iloc[0]["estado"],
                         ESTADO_REVISAR)

    def test_email_sin_formato_no_pasa(self):
        res = calidad.evaluar_dataset("clientes", pd.DataFrame(
            {"id": [1, 2], "email": ["carmen@dominio", "ok@dominio.mx"]}))
        fila = res[res["campo"] == "email"].iloc[0]
        self.assertEqual(fila["estado"], ESTADO_REVISAR)
        self.assertEqual(int(fila["cumplen"]), 1)

    def test_id_repetido_y_vacio_se_ven(self):
        res = calidad.evaluar_dataset("clientes", pd.DataFrame(
            {"id": [7, 7, None]}))
        por_regla = {r["dimension"]: r for _, r in res.iterrows()}
        self.assertEqual(por_regla["unicidad"]["estado"], ESTADO_REVISAR)
        self.assertEqual(por_regla["completitud"]["estado"], ESTADO_REVISAR)


class TestRobustez(unittest.TestCase):
    def test_una_regla_rota_se_reporta_y_no_tumba(self):
        def _rota(df):
            raise KeyError("columna que no existe")

        regla = calidad.Regla(campo="total", dimension="validez",
                              descripcion="regla rota", evaluar=_rota)
        with self.assertLogs("taller.calidad", level="WARNING") as avisos:
            res = calidad.evaluar_dataset("facturas", _facturas(), [regla])
        self.assertEqual(len(res), 1)
        self.assertEqual(res.iloc[0]["estado"], ESTADO_ERROR)
        self.assertIn("regla rota", avisos.output[0])

    def test_conjunto_vacio_devuelve_el_esquema_de_resultado(self):
        res = calidad.evaluar_conjunto({})
        self.assertTrue(res.empty)
        self.assertEqual(list(res.columns), calidad.COLUMNAS_RESULTADO)

    def test_conjunto_concatena_los_datasets(self):
        res = calidad.evaluar_conjunto({"facturas": _facturas(),
                                        "clientes": pd.DataFrame({"id": [1]})})
        self.assertEqual(set(res["dataset"]), {"facturas", "clientes"})

    def test_resumen_cuenta_estados_sin_perder_filas(self):
        res = calidad.evaluar_dataset("facturas", _facturas())
        cuenta = calidad.resumen(res)
        self.assertEqual(cuenta["total"], len(res))
        self.assertEqual(cuenta["ok"] + cuenta["revisar"] + cuenta["error"],
                         cuenta["total"])

    def test_resumen_de_nada_es_cero(self):
        self.assertEqual(calidad.resumen(pd.DataFrame()), {
            "total": 0, "ok": 0, "revisar": 0, "error": 0})


if __name__ == "__main__":
    unittest.main()
