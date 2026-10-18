"""Pruebas del caso de uso de warehouse y de la regla de direccion.

Tres frentes:

1. Regla de direccion del hexagono: ningun modulo de ``ui`` importa
   ``src.core.warehouse`` ni ``src.core.pipeline`` directamente. Ambos
   son nucleo: la UI orquesta a traves de ``src.aplicacion``, igual que
   la API y el CLI.
2. Delegacion: el caso de uso pasa el DSN, los esquemas y el prefijo
   al nucleo sin tocarlos (el DSN es del operador, no del tenant).
3. Integracion con sqlite: publicar dos workspaces al mismo warehouse
   no los pisa (el prefijo lleva la clave, regla 1) y cada uno solo
   ve sus propias tablas.
"""

import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd

from src import aplicacion
from src.data_loader import get_store

REPO = Path(__file__).resolve().parents[1]

CSV_CLIENTES = "id,nombre\n1,Ana\n2,Luis\n"


def _cfg_workspace(tmp: Path, clave: str) -> SimpleNamespace:
    """Config de un workspace minimo: un CSV de clientes y su almacen."""
    data_dir = tmp / clave / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "clientes.csv").write_text(CSV_CLIENTES, encoding="utf-8")
    return SimpleNamespace(
        clave=clave,
        db_path=str(tmp / clave / "almacen.duckdb"),
        cache_dir=str(tmp / clave / "cache"),
        usar_cache=True,
        directorio_datos=str(data_dir),
        datasets={"clientes": SimpleNamespace(
            nombre="clientes", archivo="clientes.csv", formato="auto",
            hoja=None, mapeo={}, fuentes_alternativas=[])},
    )


def _con_datos_en_almacen(cfg) -> None:
    """Deja el almacen con una tabla para que el warehouse no ejecute el ETL.

    Publicar no depende del ETL: lee los ficheros de ``cfg.datasets``
    directamente. Asi la prueba es rapida y no depende de que el pipeline
    toleren datasets incompletos.
    """
    store = get_store(cfg)
    try:
        store.registrar_tabla(
            "clientes", pd.DataFrame({"id": [1, 2], "nombre": ["Ana", "Luis"]}))
    finally:
        store.cerrar()


class TestReglaDeDireccionUI(unittest.TestCase):
    """La UI no importa ``src.core.warehouse`` ni ``src.core.pipeline``."""

    PROHIBIDOS = re.compile(
        r"^\s*(?:from|import)\s+src\.core\.(?:warehouse|pipeline)\b"
        r"|^\s*from\s+src\.core\s+import\s+[^#\n]*\b(?:warehouse|pipeline)\b",
        re.M,
    )

    def test_ningun_modulo_de_ui_importa_ese_nucleo(self):
        culpables = []
        for ruta in sorted(REPO.joinpath("ui").rglob("*.py")):
            if self.PROHIBIDOS.search(ruta.read_text(encoding="utf-8")):
                culpables.append(str(ruta.relative_to(REPO)))
        self.assertEqual(culpables, [])


class TestDelegacionEnElNucleo(unittest.TestCase):
    """El caso de uso pasa los argumentos al nucleo sin tocarlos."""

    def test_publicar_pasa_dsn_esquemas_y_prefijo(self):
        cfg = SimpleNamespace(clave="demo")
        with mock.patch("src.core.warehouse.sincronizar",
                        return_value=[{"tabla": "giro_demo_clientes"}]) as m:
            publicados = aplicacion.publicar_warehouse(
                cfg, "sqlite:///wh.db", esquemas=("datasets",), prefijo="mi_")
        m.assert_called_once_with(cfg, "sqlite:///wh.db",
                                  esquemas=("datasets",), prefijo="mi_")
        self.assertEqual(publicados, [{"tabla": "giro_demo_clientes"}])

    def test_ver_pasa_dsn_y_prefijo(self):
        cfg = SimpleNamespace(clave="demo")
        with mock.patch("src.core.warehouse.ver",
                        return_value=pd.DataFrame({"tabla": []})) as m:
            df = aplicacion.ver_warehouse(cfg, "sqlite:///wh.db", prefijo="mi_")
        m.assert_called_once_with(cfg, "sqlite:///wh.db", prefijo="mi_")
        self.assertTrue(df.empty)

    def test_los_esquemas_por_defecto_son_los_tres(self):
        self.assertEqual(aplicacion.ESQUEMAS_WAREHOUSE,
                         ("datasets", "core", "analitica"))


class TestPublicacionRealConSqlite(unittest.TestCase):
    """Integracion: dos workspaces comparten warehouse sin pisarse."""

    def test_dos_workspaces_no_se_pisan_en_el_mismo_warehouse(self):
        import tempfile
        from sqlalchemy import create_engine, inspect, text

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dsn = f"sqlite:///{tmp}/compartido.db"

            cfg_a = _cfg_workspace(tmp, "tallerx")
            _con_datos_en_almacen(cfg_a)
            aplicacion.publicar_warehouse(cfg_a, dsn)

            # Otro workspace, MISMO warehouse: si el prefijo no llevara la
            # clave, el if_exists="replace" de to_sql lo borraria.
            cfg_b = _cfg_workspace(tmp, "tallery")
            _con_datos_en_almacen(cfg_b)
            aplicacion.publicar_warehouse(cfg_b, dsn)

            # Cada workspace solo ve sus propias tablas (filtro por prefijo
            # con la clave del workspace: regla 1 de aislamiento por tenant).
            tablas = set(aplicacion.ver_warehouse(cfg_a, dsn)["tabla"])
            self.assertNotIn("giro_tallery_clientes", tablas)

            solo_b = aplicacion.ver_warehouse(cfg_b, dsn)
            self.assertEqual(set(solo_b["tabla"]), {"giro_tallery_clientes"})

            # Limpieza: borrar tablas huérfanas (sin clave de workspace)
            # que el publicado pudo dejar en el destino, para no ensuciar
            # el output de los tests con el aviso de _avisar_huerfanas.
            eng = create_engine(dsn)
            try:
                insp = inspect(eng)
                claves = {f"giro_{cfg_a.clave}_", f"giro_{cfg_b.clave}_"}
                for t in insp.get_table_names():
                    if t.startswith("giro_") and not any(
                            t.startswith(c) for c in claves):
                        with eng.begin() as conn:
                            conn.execute(text(f'DROP TABLE IF EXISTS "{t}"'))
            finally:
                eng.dispose()


if __name__ == "__main__":
    unittest.main()
