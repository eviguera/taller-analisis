"""Ratchet de arquitectura y contrato de las páginas.

Estas pruebas no comprueban comportamiento: congelan las fronteras del
hexágono y evitan que vuelvan a entrar dependencias que la Fase 0 encontró.

La lista ``PERMITIDAS`` es deuda técnica explícita. Cada entrada debe
desaparecer en la Fase 1; si una entrada deja de ser necesaria, la prueba
falla para que se borre. Si aparece una violación nueva, también falla.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]

REGLAS = {
    "src/core": (
        "src.storage",
        "src.loaders",
        "src.adapters",
        "src.api",
        "src.aplicacion",
        "src.data_loader",
        "ui",
        "streamlit",
        "duckdb",
        "fastapi",
        "sqlalchemy",
        "requests",
    ),
    "src/aplicacion": (
        "src.storage",
        "src.loaders",
        "src.adapters",
        "src.api",
        "src.data_loader",
        "ui",
        "streamlit",
        "duckdb",
        "fastapi",
        "sqlalchemy",
        "requests",
    ),
    "src/puertos": (
        "src.storage",
        "src.loaders",
        "src.adapters",
        "src.api",
        "src.aplicacion",
        "src.data_loader",
        "ui",
        "streamlit",
        "duckdb",
        "fastapi",
        "sqlalchemy",
        "requests",
    ),
}

# Deuda de la Fase 0. Se reduce a cero en la Fase 1.
PERMITIDAS = {
    "src/core/conector_sql.py": {"src.data_loader", "sqlalchemy", "duckdb"},
    "src/core/pipeline.py": {"src.data_loader", "src.loaders", "src.storage"},
    "src/core/warehouse.py": {"src.data_loader", "sqlalchemy"},
    "src/aplicacion/almacen.py": {"src.data_loader", "src.loaders"},
    "src/aplicacion/asesor_negocio.py": {"src.adapters"},
    "src/aplicacion/carga.py": {"src.loaders"},
}


def _resolver_import(paquete: str, nivel: int, modulo: str | None) -> str:
    """Resuelve un import relativo a su nombre absoluto."""
    partes = paquete.split(".") if paquete else []
    if nivel:
        base = partes[: len(partes) - (nivel - 1)] if nivel > 1 else partes
        return ".".join(base + ([modulo] if modulo else []))
    return modulo or ""


def _imports_de(ruta: Path) -> list[str]:
    """Devuelve todos los módulos importados por un archivo, incluidos alias."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    paquete = ".".join(ruta.relative_to(RAIZ).with_suffix("").parts[:-1])
    modulos: list[str] = []

    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            modulos.extend(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            modulo = _resolver_import(paquete, nodo.level, nodo.module)
            if modulo:
                modulos.append(modulo)
                modulos.extend(
                    f"{modulo}.{alias.name}"
                    for alias in nodo.names
                    if alias.name != "*"
                )
    return modulos


def _coincide(modulo: str, prefijo: str) -> bool:
    return modulo == prefijo or modulo.startswith(prefijo + ".")


class TestFronterasHexagono(unittest.TestCase):
    def test_no_hay_imports_nuevos_fuera_de_la_allowlist(self):
        fallos: list[str] = []

        for prefijo, prohibidos in REGLAS.items():
            for ruta in sorted((RAIZ / prefijo).rglob("*.py")):
                if "__pycache__" in ruta.parts:
                    continue
                relativa = ruta.relative_to(RAIZ).as_posix()
                importados = _imports_de(ruta)
                presentes = {
                    prohibido
                    for prohibido in prohibidos
                    if any(_coincide(mod, prohibido) for mod in importados)
                }
                esperadas = PERMITIDAS.get(relativa, set())

                nuevas = presentes - esperadas
                obsoletas = esperadas - presentes

                if nuevas:
                    fallos.append(
                        f"{relativa}: importa {sorted(nuevas)}. "
                        "Mueve la dependencia al adaptador o añádela a PERMITIDAS "
                        "con justificación y fecha de retirada."
                    )
                if obsoletas:
                    fallos.append(
                        f"{relativa}: PERMITIDAS declara {sorted(obsoletas)}, "
                        "pero ya no se importan. Borra la entrada obsoleta."
                    )

        self.assertEqual([], fallos, "\n".join(fallos))


class TestContratoUI(unittest.TestCase):
    def test_paginas_no_llaman_a_set_page_config(self):
        fallos = []
        for ruta in sorted((RAIZ / "ui" / "pages").glob("*.py")):
            if "set_page_config" in ruta.read_text(encoding="utf-8"):
                fallos.append(ruta.relative_to(RAIZ).as_posix())
        self.assertEqual([], fallos, "El page_config vive solo en ui/app.py")

    def test_paginas_no_escriben_html_crudo(self):
        fallos = []
        for ruta in sorted((RAIZ / "ui" / "pages").glob("*.py")):
            if "unsafe_allow_html" in ruta.read_text(encoding="utf-8"):
                fallos.append(ruta.relative_to(RAIZ).as_posix())
        self.assertEqual(
            [], fallos, "Usa components.html() en vez de st.markdown(..., unsafe_allow_html=True)"
        )

    def test_paginas_no_usan_plotly_crudo(self):
        fallos = []
        for ruta in sorted((RAIZ / "ui" / "pages").glob("*.py")):
            if "st.plotly_chart" in ruta.read_text(encoding="utf-8"):
                fallos.append(ruta.relative_to(RAIZ).as_posix())
        self.assertEqual(
            [], fallos, "Usa los wrappers grafico_* de ui/components.py"
        )

    def test_no_hay_except_exception_pass(self):
        fallos = []
        for carpeta in ("src", "ui"):
            for ruta in sorted((RAIZ / carpeta).rglob("*.py")):
                if "__pycache__" in ruta.parts:
                    continue
                arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
                for nodo in ast.walk(arbol):
                    if not isinstance(nodo, ast.ExceptHandler):
                        continue
                    if (
                        len(nodo.body) == 1
                        and isinstance(nodo.body[0], ast.Pass)
                        and isinstance(nodo.type, ast.Name)
                        and nodo.type.id == "Exception"
                    ):
                        fallos.append(
                            f"{ruta.relative_to(RAIZ).as_posix()}:{nodo.lineno}"
                        )
        self.assertEqual([], fallos, "Un error tragado oculta un bug visible")


if __name__ == "__main__":
    unittest.main()
