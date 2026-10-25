"""Contraste de los valores secundarios de KPI en claro y oscuro."""

import unittest

from ui import components as c


def _luminancia(hex_color):
    canales = [int(hex_color[indice:indice + 2], 16) / 255
               for indice in (1, 3, 5)]
    lineales = [valor / 12.92 if valor <= 0.04045
                else ((valor + 0.055) / 1.055) ** 2.4 for valor in canales]
    return sum(peso * valor for peso, valor in zip((0.2126, 0.7152, 0.0722), lineales))


def _contraste(primer_color, segundo_color):
    claras = sorted((_luminancia(primer_color), _luminancia(segundo_color)), reverse=True)
    return (claras[0] + 0.05) / (claras[1] + 0.05)


class TestContrasteKpi(unittest.TestCase):
    def test_valor_secundario_alcanza_wcag_aa_en_modo_claro(self):
        color = c._color_valor_kpi(oscuro=False)
        self.assertGreaterEqual(_contraste(color, "#FFFFFF"), 4.5)

    def test_valor_secundario_alcanza_wcag_aa_en_modo_oscuro(self):
        color = c._color_valor_kpi(oscuro=True)
        self.assertGreaterEqual(_contraste(color, "#0B1120"), 4.5)


if __name__ == "__main__":
    unittest.main()
