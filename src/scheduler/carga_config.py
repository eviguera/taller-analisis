"""Carga la AppConfig de un workspace para los jobs del scheduler.

Se separa en su propio modulo para evitar importaciones circulares:
scheduler -> carga_config -> core.config_manager (no importa scheduler).
"""

from __future__ import annotations

from pathlib import Path

from ..core.config_manager import cargar_config


def carga_config_para_accion(directorio_datos) -> object:
    """Devuelve la AppConfig del workspace cuyo directorio de datos es
    `directorio_datos`. Resuelve el config.yaml dentro de ese directorio
    (o su carpeta padre config/)."""
    directorio_datos = Path(directorio_datos)
    # El config.yaml vive en <raiz_workspace>/config/config.yaml.
    # directorio_datos es <raiz_workspace>/data, así que subimos un nivel.
    raiz = directorio_datos.parent
    ruta_config = raiz / "config" / "config.yaml"
    if not ruta_config.exists():
        # Fallback: config.yaml junto al directorio de datos (caso principal)
        ruta_config = directorio_datos / "config.yaml"
    if not ruta_config.exists():
        # Ultimo fallback: config raiz del repositorio
        ruta_config = Path(__file__).resolve().parent.parent.parent / "config" / "config.yaml"
    return cargar_config(ruta_config)
