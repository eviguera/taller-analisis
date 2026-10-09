"""Pruebas de la marca white-label: lo que se escribe en el config del tenant."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import yaml

from src.reporting import branding as br


def _cfg(reporteado: dict | None = None) -> SimpleNamespace:
    """Config minimo que necesitan `marca` y `guardar_branding`."""
    return SimpleNamespace(
        clave="demo",
        negocio_nombre="Taller de prueba",
        slogan="",
        moneda="CLP",
        sector="automotriz",
        tema={},
        directorio_datos=Path("."),
        reportes=reporteado or {},
    )


class TestGuardadoDeMarca(unittest.TestCase):
    """El escritorio de marca vive en el nucleo, no en la pagina."""

    def _escribir(self, cambios, config_existente=None):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "config.yaml"
            if config_existente is not None:
                ruta.write_text(yaml.safe_dump(config_existente),
                                encoding="utf-8")
            else:
                ruta.write_text("{}", encoding="utf-8")
            with mock.patch("src.core.conector_sql.ruta_config_workspace",
                            return_value=ruta):
                br.guardar_branding(_cfg(), cambios)
            return yaml.safe_load(ruta.read_text(encoding="utf-8"))

    def _rechaza(self, cambios):
        """Aplica cambios que deben fallar y devuelve (motivo, fichero tras el intento)."""
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "config.yaml"
            ruta.write_text("{}", encoding="utf-8")
            with mock.patch("src.core.conector_sql.ruta_config_workspace",
                            return_value=ruta):
                with self.assertRaises(ValueError) as ctx:
                    br.guardar_branding(_cfg(), cambios)
            return str(ctx.exception), yaml.safe_load(
                ruta.read_text(encoding="utf-8"))

    def test_un_campo_desconocido_se_rechaza(self):
        # Dejar que un llamador meta claves arbitrarias en el config del
        # tenant es una puerta de entrada, no una comodidad.
        motivo, fichero = self._rechaza({"conectores": [{"dsn": "x"}]})
        self.assertIn("conectores", motivo)
        # Y no ha escrito nada.
        self.assertEqual(fichero, {})

    def test_un_color_que_no_es_hex_se_rechaza(self):
        # El color acaba dentro de un bloque CSS del documento: un valor
        # como "red;} body{display:none" inyectaria reglas.
        motivo, fichero = self._rechaza(
            {"color_primario": "red;} body{display:none"})
        self.assertIn("#RGB", motivo)
        self.assertEqual(fichero, {})

    def test_un_color_hex_corto_se_acepta(self):
        escrito = self._escribir({"color_primario": "#abc"})
        self.assertEqual(escrito["reportes"]["branding"]["color_primario"], "#abc")
        marca = br.marca(_cfg({"branding": {"color_primario": "#abc"}}))
        self.assertEqual(marca["color_primario"], "#abc")

    def test_los_valores_vacios_no_borran_lo_existente(self):
        # Un text_input en blanco significa "no lo toques", no "borralo".
        previo = {"reportes": {"branding": {"consultora": "Consultora SA"}}}
        resultado = self._escribir({"consultora": "", "contacto": None},
                                   config_existente=previo)
        self.assertEqual(
            resultado["reportes"]["branding"]["consultora"], "Consultora SA")

    def test_lo_que_guarda_lo_vuelve_a_leer_marca(self):
        self._escribir({"consultora": "Analitica Norte", "web": "https://norte.cl",
                        "color_primario": "#123456"})
        marca = br.marca(_cfg({"branding": {
            "consultora": "Analitica Norte", "web": "https://norte.cl",
            "color_primario": "#123456"}}))
        self.assertEqual(marca["consultora"], "Analitica Norte")
        self.assertEqual(marca["web"], "https://norte.cl")
        self.assertEqual(marca["color_primario"], "#123456")

    def test_no_mezcla_la_seccion_conectores(self):
        # Read-modify-write sobre el mismo YAML que usa conector_sql:
        # guardar marca no puede borrar los conectores del tenant.
        previo = {"conectores": [{"nombre": "erp", "motor": "sqlite"}]}
        resultado = self._escribir({"consultora": "Norte"},
                                   config_existente=previo)
        self.assertEqual(resultado["conectores"],
                         [{"nombre": "erp", "motor": "sqlite"}])
        self.assertEqual(resultado["reportes"]["branding"]["consultora"], "Norte")


if __name__ == "__main__":
    unittest.main()
