"""Casos de uso de conectores ERP/SQL.

Las operaciones de conectores (snapshot ERP, registro en config,
sincronizacion con el almacen) vivian en ``src.core.conector_sql`` y
cada adaptador de entrada las llamaba directamente. Aqui se agrupan como
casos de uso para que la UI, la API y el CLI entren por ``src.aplicacion``.

No hay ``import streamlit`` ni ``import sqlalchemy``: el DSN y la
configuracion llegan como parametros.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from pathlib import Path

if TYPE_CHECKING:
    from ..core.config import AppConfig

from ..core.conector_sql import (
    conectores_desde_snapshot as _conectores_desde_snapshot,
    crear_snapshot_erp as _crear_snapshot_erp,
    escribir_conectores as _escribir_conectores,
    parsear_conectores as _parsear_conectores,
    sincronizar_conectores as _sincronizar_conectores,
)


def parsear_conectores(cfg: "AppConfig") -> list[dict]:
    """Convierte la lista de dicts del config en objetos Conector."""
    return _parsear_conectores(cfg)


def conectores_desde_snapshot(cfg: "AppConfig", ruta: Path) -> list[dict]:
    """Genera la lista de conectores (sqlite, forzar=true) para un snapshot."""
    return _conectores_desde_snapshot(cfg, ruta)


def crear_snapshot_erp(cfg: "AppConfig", destino: Optional[Path] = None,
                       sobreescribir: bool = True) -> tuple[Path, dict]:
    """Exporta los datasets del workspace a un archivo SQLite (simula ERP)."""
    return _crear_snapshot_erp(cfg, destino, sobreescribir)


def escribir_conectores(cfg: "AppConfig", conectores: list[dict],
                        reemplazar: bool = False) -> tuple[Path, list[dict]]:
    """Persiste (merge o reemplazo) la lista de conectores en el config."""
    return _escribir_conectores(cfg, conectores, reemplazar)


def sincronizar_conectores(cfg: "AppConfig") -> list[dict]:
    """Trae los conectores al almacen y devuelve el resumen por conector."""
    return _sincronizar_conectores(cfg)


__all__ = [
    "parsear_conectores",
    "conectores_desde_snapshot",
    "crear_snapshot_erp",
    "escribir_conectores",
    "sincronizar_conectores",
]
