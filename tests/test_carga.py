"""Casos de uso de carga extraidos de ``ui/pages/datos.py``.

La subida con cuota, la deteccion de origenes, la lectura de ``.sav``, la
exportacion a PSPP y la fila de la tabla de conectores vivian dentro de una
pagina de Streamlit: aqui se prueban sobre el nucleo, sin arrancar la UI.
"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd

from src import aplicacion
from src.core import catalog
from src.loaders.pspp_loader import exportar_sav


def _cfg(directorio: Path) -> SimpleNamespace:
    """Config minima para los casos de uso que solo necesitan rutas."""
    return SimpleNamespace(directorio_datos=directorio,
                           db_path=str(Path(directorio) / "almacen.duckdb"))


class TestGuardarSubidas(unittest.TestCase):
    """Cuota, deduplicacion y confinamiento: las garantias de la subida."""

    def setUp(self):
        self.destino = Path(tempfile.mkdtemp(prefix="giro_subida_"))

    def _subir(self, nombre, contenido, **kwargs):
        subida = (nombre, len(contenido), memoryview(contenido))
        return aplicacion.guardar_subidas([subida], self.destino, **kwargs)

    def test_escribe_lo_nuevo_y_no_reescribe_si_no_cambia(self):
        guardados, sin_cambios, _, _ = self._subir("a.csv", b"x,y\n1,2\n")
        self.assertEqual((guardados, sin_cambios), (1, 0))
        mtime = (self.destino / "a.csv").stat().st_mtime_ns
        guardados, sin_cambios, _, _ = self._subir("a.csv", b"x,y\n1,2\n")
        # Reescribir en cada rerun moveria el mtime y cambiaria la firma
        # de firma_fuentes sin cambiar nada: la cache se invalidaria sola.
        self.assertEqual((guardados, sin_cambios), (0, 1))
        self.assertEqual((self.destino / "a.csv").stat().st_mtime_ns, mtime)

    def test_contenido_distinto_si_se_reescribe(self):
        self._subir("a.csv", b"v1")
        guardados, sin_cambios, _, _ = self._subir("a.csv", b"v2")
        self.assertEqual((guardados, sin_cambios), (1, 0))
        self.assertEqual((self.destino / "a.csv").read_bytes(), b"v2")

    def test_mismo_tamano_pero_distinto_contenido(self):
        self._subir("a.csv", b"aaaa")
        guardados, _, _, _ = self._subir("a.csv", b"bbbb")
        self.assertEqual(guardados, 1)

    def test_el_archivo_sobre_el_limite_no_se_guarda(self):
        guardados, _, por_archivo, _ = self._subir("g.csv", b"12345",
                                                    limite_bytes=4)
        self.assertEqual((guardados, por_archivo), (0, 1))
        self.assertFalse((self.destino / "g.csv").exists())

    def test_la_cuota_del_workspace_tambien_cuenta(self):
        (self.destino / "viejo.csv").write_bytes(b"1234")
        guardados, _, _, por_cuota = self._subir("nuevo.csv", b"12345",
                                                  cuota_bytes=5)
        self.assertEqual((guardados, por_cuota), (0, 1))
        self.assertFalse((self.destino / "nuevo.csv").exists())

    def test_el_almacen_duckdb_no_come_la_cuota(self):
        (self.destino / "almacen.duckdb").write_bytes(b"1234")
        cfg = _cfg(self.destino)
        guardados, _, _, por_cuota = self._subir(
            "n.csv", b"12", excluidos=aplicacion.derivados_almacen(cfg),
            cuota_bytes=5)
        self.assertEqual((guardados, por_cuota), (1, 0))

    def test_un_nombre_con_ruta_no_sale_del_workspace(self):
        guardados, _, _, _ = self._subir("../../fuera.csv", b"x")
        self.assertEqual(guardados, 1)
        self.assertTrue((self.destino / "fuera.csv").exists())
        self.assertFalse((self.destino.parent / "fuera.csv").exists())


class TestDerivadosYFirma(unittest.TestCase):
    """Los ficheros derivados se excluyen igual en la subida y en la firma."""

    def test_los_derivados_son_almacen_wal_y_tmp(self):
        cfg = SimpleNamespace(db_path="/x/y/almacen.duckdb")
        self.assertEqual(aplicacion.derivados_almacen(cfg),
                         {"almacen.duckdb", "almacen.duckdb.wal",
                          "almacen.duckdb.tmp"})

    def test_escribir_en_el_almacen_no_cambia_la_firma(self):
        tmp = Path(tempfile.mkdtemp(prefix="giro_firma_"))
        (tmp / "facturas.csv").write_text("total\n1\n", encoding="utf-8")
        cfg = _cfg(tmp)
        cfg.datasets = {}
        antes = aplicacion.firma_fuentes(cfg)
        (tmp / "almacen.duckdb").write_bytes(b"reescrito por el ETL")
        self.assertEqual(aplicacion.firma_fuentes(cfg), antes)
        (tmp / "nuevo.csv").write_text("total\n2\n", encoding="utf-8")
        self.assertNotEqual(aplicacion.firma_fuentes(cfg), antes)


class TestDirectorioDatosPermitido(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="giro_dir_"))
        self.cfg = _cfg(self.tmp)

    def test_acepta_el_directorio_del_workspace_y_sus_subcarpetas(self):
        self.assertTrue(aplicacion.directorio_datos_permitido(self.cfg, self.tmp))
        self.assertTrue(aplicacion.directorio_datos_permitido(
            self.cfg, self.tmp / "export" / "2026"))

    def test_rechaza_cualquier_ruta_fuera_del_workspace(self):
        self.assertFalse(aplicacion.directorio_datos_permitido(
            self.cfg, self.tmp.parent / "otro_taller"))
        self.assertFalse(aplicacion.directorio_datos_permitido(
            self.cfg, self.tmp / ".." / "otro_taller"))
        self.assertFalse(aplicacion.directorio_datos_permitido(self.cfg, "/"))


class TestFilasDetectadas(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="giro_detect_"))
        (self.tmp / "clientes.csv").write_text(
            "cliente,nombre,telefono,email,cliente_id\n1,Ana,555,a@b.c,1\n",
            encoding="utf-8")
        (self.tmp / "indefinido.csv").write_text("alfa,beta\n1,2\n",
                                                 encoding="utf-8")

    def test_clasifica_cada_archivo_contra_el_esquema_canonico(self):
        filas = aplicacion.filas_detectadas(catalog.escanear_directorio(self.tmp))
        por_nombre = {f["archivo"]: f for f in filas}
        self.assertEqual(por_nombre["clientes.csv"]["dataset"], "clientes")
        self.assertGreater(por_nombre["clientes.csv"]["confianza"], 0.45)
        self.assertEqual(por_nombre["clientes.csv"]["formato"], "csv")
        self.assertIsInstance(por_nombre["clientes.csv"]["tamano_kb"], float)

    def test_un_archivo_sin_marcadores_queda_sin_dataset(self):
        filas = aplicacion.filas_detectadas(catalog.escanear_directorio(self.tmp))
        indefinido = {f["archivo"]: f for f in filas}["indefinido.csv"]
        self.assertIsNone(indefinido["dataset"])
        self.assertEqual(indefinido["confianza"], 0.0)


class TestFilasConectores(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="giro_conect_"))
        self.cfg = SimpleNamespace(directorio_datos=self.tmp, conectores=[
            {"nombre": "erp", "motor": "sqlite", "fuente": "origen.sqlite",
             "dataset": "facturas"},
            {"nombre": "web", "motor": "url",
             "fuente": "https://datos.example/x.csv", "dataset": "clientes"},
            {"nombre": "consulta", "motor": "sql", "fuente": None,
             "consulta": "SELECT 1", "dataset": "servicios"},
        ])

    def test_distingue_archivo_local_url_y_consulta(self):
        filas = aplicacion.filas_conectores(self.cfg)
        self.assertEqual([f["fuente"] for f in filas],
                         ["origen.sqlite", "https://datos.example/x.csv",
                          "(consulta)"])
        self.assertEqual([f["existe"] for f in filas], [False, True, False])

    def test_la_fuente_local_se_comprueba_en_disco(self):
        (self.tmp / "origen.sqlite").write_bytes(b"x")
        self.assertTrue(aplicacion.filas_conectores(self.cfg)[0]["existe"])


class TestExportarDatasetsSav(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="giro_sav_"))
        self.datos = {"facturas": pd.DataFrame({"total": [10.0, 20.0]})}

    def test_exporta_los_no_vacios_y_ignora_los_vacios(self):
        datos = dict(self.datos, vacio=pd.DataFrame())
        exportados, fallos = aplicacion.exportar_datasets_sav(
            datos, self.tmp / "export")
        self.assertEqual(exportados, ["facturas"])
        self.assertEqual(fallos, {})
        self.assertTrue((self.tmp / "export" / "facturas.sav").exists())

    def test_un_dataset_que_no_se_puede_escribir_no_tumba_los_demas(self):
        with mock.patch("src.loaders.pspp_loader.exportar_sav",
                        side_effect=RuntimeError("pyreadstat dice que no")):
            exportados, fallos = aplicacion.exportar_datasets_sav(
                self.datos, self.tmp / "export")
        self.assertEqual(exportados, [])
        self.assertEqual(fallos, {"facturas": "pyreadstat dice que no"})

    def test_un_directorio_de_destino_nuevo_se_crea(self):
        destino = self.tmp / "no_existe" / "todavia"
        aplicacion.exportar_datasets_sav(self.datos, destino)
        self.assertTrue(destino.is_dir())


class TestLeerArchivosPspp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="giro_pspp_"))

    def test_resumen_de_un_sav_con_etiquetas(self):
        exportar_sav(pd.DataFrame({"estado": [1, 2], "total": [10.0, 20.0]}),
                     self.tmp / "facturas.sav",
                     etiquetas_valores={"estado": {1: "Pagada", 2: "Pendiente"}},
                     label_archivo="facturas")
        resumenes = aplicacion.leer_archivos_pspp(self.tmp)
        self.assertEqual(len(resumenes), 1)
        r = resumenes[0]
        self.assertEqual((r["nombre"], r["formato"]), ("facturas.sav", "sav"))
        self.assertIsNone(r["error"])
        self.assertEqual(len(r["datos"]), 2)
        self.assertEqual(list(r["datos"].columns), ["estado", "total"])
        self.assertEqual(set(r["etiquetas"]), {"estado"})
        self.assertEqual(list(r["etiquetas"]["estado"].values()),
                         ["Pagada", "Pendiente"])

    def test_un_sav_corrupto_se_lista_con_error_y_no_lanza(self):
        (self.tmp / "roto.sav").write_bytes(b"esto no es un sav")
        resumenes = aplicacion.leer_archivos_pspp(self.tmp)
        self.assertEqual(len(resumenes), 1)
        self.assertIsNotNone(resumenes[0]["error"])
        self.assertIsNone(resumenes[0]["datos"])

    def test_solo_los_formatos_pspp_y_el_directorio_vacio(self):
        (self.tmp / "clientes.csv").write_text("nombre\nAna\n", encoding="utf-8")
        self.assertEqual(aplicacion.leer_archivos_pspp(self.tmp), [])


class TestResumenReglas(unittest.TestCase):
    @staticmethod
    def _calidad():
        return pd.DataFrame([
            {"dataset": "facturas", "campo": "total", "dimension": "validez",
             "regla": "numero", "evaluadas": 10, "cumplen": 10, "tasa": 1.0,
             "estado": "OK"},
            {"dataset": "clientes", "campo": "email", "dimension": "completitud",
             "regla": "no nulo", "evaluadas": 5, "cumplen": 4, "tasa": 0.8,
             "estado": "REVISAR"},
        ])

    def test_cuenta_por_estado_y_devuelve_solo_las_que_fallan(self):
        res, fallas = aplicacion.resumen_reglas(self._calidad())
        self.assertEqual(res, {"total": 2, "ok": 1, "revisar": 1, "error": 0})
        self.assertEqual(fallas["dataset"].tolist(), ["clientes"])

    def test_calidad_vacia_o_ausente_devuelve_ceros(self):
        for calidad in (None, pd.DataFrame()):
            with self.subTest(calidad=type(calidad).__name__):
                res, fallas = aplicacion.resumen_reglas(calidad)
                self.assertEqual(res["total"], 0)
                self.assertTrue(fallas.empty)


class TestEjecutarEtl(unittest.TestCase):
    def test_el_caso_de_uso_delega_en_el_pipeline(self):
        cfg = SimpleNamespace(directorio_datos=Path(tempfile.mkdtemp()))
        with mock.patch("src.core.pipeline.procesar_etl",
                        return_value="resultado") as procesar:
            self.assertEqual(aplicacion.ejecutar_etl(cfg), "resultado")
        procesar.assert_called_once_with(cfg)


class TestEjemplosSql(unittest.TestCase):
    def test_los_ejemplos_cumplen_la_misma_regla_de_solo_lectura(self):
        self.assertTrue(aplicacion.EJEMPLOS_SQL)
        for etiqueta, consulta in aplicacion.EJEMPLOS_SQL.items():
            with self.subTest(ejemplo=etiqueta):
                aplicacion.validar_sql_solo_lectura(consulta)


if __name__ == "__main__":
    unittest.main()
