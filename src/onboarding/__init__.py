"""Onboarding guiado de workspaces para GIRO.

Genera la configuración inicial (config.yaml) de un workspace nuevo según su
sector vertical: alertas por defecto, intervalos de mantenimiento, parámetros
del simulador, conectores y tema de marca. Funciones puras (sin efectos
secundarios en import); la escritura del fichero la hace el llamador (CLI o
UI).

Sectores soportados: taller, clinica, retail, logistica, farmacia, restoran,
constructora.
"""

from __future__ import annotations

from .plantillas import (
    SECTORES,
    configuracion_por_sector,
    aplicar_plantilla,
    validar_sector,
)

__all__ = [
    "SECTORES",
    "configuracion_por_sector",
    "aplicar_plantilla",
    "validar_sector",
]
