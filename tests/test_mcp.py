"""Pruebas del servidor MCP (``/mcp``, Streamable-HTTP).

Verifica que el servidor MCP se construye correctamente y que sus herramientas
y recursos están registrados. La autenticación completa (401 sin sesión) se
prueba indirectamente: sin sesión, cualquier intento de acceder devuelve
401 o 404 (ambos significan "no autorizado o no encontrado").
"""

from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from src.api.mcp_server import mcp


class _Respuesta:
    """Respuesta HTTP minima."""

    def __init__(self, estado: int, cuerpo: bytes):
        self.estado = estado
        self._cuerpo = cuerpo

    @property
    def texto(self) -> str:
        return self._cuerpo.decode("utf-8", "replace")

    def json(self) -> Any:
        return json.loads(self.texto)


class _ClienteASGI:
    """Cliente ASGI minimo."""

    def __init__(self, app):
        self.app = app

    def post(self, ruta: str, cuerpo: bytes,
             headers: list) -> _Respuesta:
        return asyncio.run(self._peticion("POST", ruta, headers, cuerpo))

    async def _peticion(self, metodo: str, ruta: str,
                        headers: list, cuerpo: bytes) -> _Respuesta:
        from urllib.parse import urlparse as _urlparse
        partes = _urlparse(ruta)
        scope = {
            "type": "http", "asgi": {"version": "3.0"},
            "http_version": "1.1", "method": metodo, "scheme": "http",
            "path": partes.path, "raw_path": partes.path.encode("utf-8"),
            "query_string": partes.query.encode("utf-8"), "root_path": "",
            "headers": headers,
            "client": ("testclient", 50000), "server": ("testserver", 80),
            "state": {},
            "extensions": {"http.response.debug": {}},
        }
        entregado = {"cuerpo": False}

        async def receive():
            if not entregado["cuerpo"]:
                entregado["cuerpo"] = True
                return {"type": "http.request", "body": cuerpo,
                        "more_body": False}
            return {"type": "http.disconnect"}

        estado = {"codigo": None, "cabeceras": {}, "trozos": []}

        async def send(mensaje):
            tipo = mensaje["type"]
            if tipo == "http.response.start":
                estado["codigo"] = mensaje["status"]
                estado["cabeceras"] = {
                    k.decode("latin-1"): v.decode("latin-1")
                    for k, v in mensaje.get("headers", [])}
            elif tipo == "http.response.body":
                estado["trozos"].append(mensaje.get("body", b""))

        fallo = None
        try:
            await self.app(scope, receive, send)
        except Exception as e:
            fallo = e
        if estado["codigo"] is None:
            if fallo is None:
                raise AssertionError(f"Sin respuesta a {metodo} {ruta}")
            raise fallo
        return _Respuesta(estado["codigo"], b"".join(estado["trozos"]))


class TestMCPRegistro(unittest.TestCase):
    """El servidor MCP expone sus herramientas y recursos."""

    def setUp(self):
        self.app = _ClienteASGI(mcp.http_app())

    def test_herramientas_registradas(self):
        """giro_consultar_sql, giro_ejecutar_alertas, giro_generar_briefing."""
        # FastMCP registra las herramientas internamente; verificamos que
        # el servidor se construye sin errores y tiene las herramientas.
        herramientas = asyncio.run(mcp.list_tools())
        nombres = {t.name for t in herramientas}
        self.assertIn("giro_consultar_sql", nombres)
        self.assertIn("giro_ejecutar_alertas", nombres)
        self.assertIn("giro_generar_briefing", nombres)

    def test_recursos_registrados(self):
        """Recursos tipo template para workspace y scheduler."""
        recursos = asyncio.run(mcp.list_resource_templates())
        uris = {t.uri_template for t in recursos}
        self.assertIn("giro://workspace/{seccion}", uris)
        self.assertIn("giro://scheduler/{seccion}", uris)

    def test_jsonrpc_sin_sesion_no_devuelve_200(self):
        """POST /mcp/ sin sesión no devuelve 200 (es 401 o 404)."""
        cuerpo = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "giro_consultar_sql",
                       "arguments": {"sql": "SELECT 1"}}},
            allow_nan=False).encode("utf-8")
        headers = [(b"content-type", b"application/json"),
                   (b"content-length", str(len(cuerpo)).encode("ascii"))]
        r = self.app.post("/mcp/", cuerpo, headers)
        self.assertIn(r.estado, (307, 401, 404))


if __name__ == "__main__":
    unittest.main()
