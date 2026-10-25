"""Pruebas del límite de memoria del rate limiter HTTP."""

import asyncio
import unittest
from unittest import mock

from starlette.requests import Request
from starlette.responses import Response

from src.api.app import RateLimitMiddleware


class TestRateLimitMiddleware(unittest.TestCase):
    def test_rechaza_ips_nuevas_cuando_el_registro_esta_lleno(self):
        middleware = RateLimitMiddleware(
            app=None, max_requests=10, window_seconds=60, max_clients=2,
        )

        async def pasar(_request):
            return Response("ok")

        async def enviar(ip):
            request = Request({
                "type": "http",
                "method": "GET",
                "path": "/api/salud",
                "headers": [],
                "client": (ip, 12345),
            })
            return await middleware.dispatch(request, pasar)

        async def escenario():
            primera = await enviar("192.0.2.1")
            segunda = await enviar("192.0.2.2")
            tercera = await enviar("192.0.2.3")
            return primera, segunda, tercera

        primera, segunda, tercera = asyncio.run(escenario())

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(tercera.status_code, 429)
        self.assertLessEqual(len(middleware._client_requests), 2)

    def test_intento_rechazado_no_desordena_expiracion_de_otros_clientes(self):
        middleware = RateLimitMiddleware(
            app=None, max_requests=1, window_seconds=10, max_clients=2,
        )

        async def pasar(_request):
            return Response("ok")

        async def enviar(ip):
            request = Request({
                "type": "http",
                "method": "GET",
                "path": "/api/salud",
                "headers": [],
                "client": (ip, 12345),
            })
            return await middleware.dispatch(request, pasar)

        async def escenario():
            primera = await enviar("192.0.2.1")
            segunda = await enviar("192.0.2.2")
            rechazada = await enviar("192.0.2.1")
            tercera = await enviar("192.0.2.3")
            return primera, segunda, rechazada, tercera

        with mock.patch("src.api.app.time.time", return_value=0), \
                mock.patch("src.api.app.time.monotonic", side_effect=[0, 5, 6, 11]):
            primera, segunda, rechazada, tercera = asyncio.run(escenario())

        self.assertEqual([primera.status_code, segunda.status_code], [200, 200])
        self.assertEqual(rechazada.status_code, 429)
        self.assertEqual(tercera.status_code, 200)
        self.assertLessEqual(len(middleware._client_requests), 2)

    def test_limpia_registros_expirados_para_aceptar_ip_nueva(self):
        middleware = RateLimitMiddleware(
            app=None, max_requests=10, window_seconds=1, max_clients=1,
        )
        middleware._client_requests["192.0.2.1"] = [0.0]

        async def pasar(_request):
            return Response("ok")

        request = Request({
            "type": "http",
            "method": "GET",
            "path": "/api/salud",
            "headers": [],
            "client": ("192.0.2.2", 12345),
        })
        resultado = asyncio.run(middleware.dispatch(request, pasar))

        self.assertEqual(resultado.status_code, 200)
        self.assertEqual(list(middleware._client_requests), ["192.0.2.2"])


if __name__ == "__main__":
    unittest.main()
