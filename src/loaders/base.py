"""Interfaz base para los cargadores de datos.

Para agregar una nueva fuente solo hay que crear una clase que herede de
`BaseLoader` e implementar `cargar(ruta, **kwargs)`. El resto del sistema
(catalogo, pipeline, dashboard) funciona sin cambios.

El contrato vive en `src.puertos.carga` (el nucleo exige el puerto, el
adaptador lo implementa). Aqui se reexporta para que los imports existentes
(`from .base import BaseLoader, CargaResultado`) sigan valiendo.
"""

from abc import ABC
from pathlib import Path

from ..puertos.carga import CargaResultado, PuertoCarga

__all__ = ["BaseLoader", "CargaResultado"]


class BaseLoader(PuertoCarga, ABC):
    """Contrato de un cargador. Nuevos formatos = nuevas subclases."""

    def actualizar_formato(self, ruta: Path) -> "BaseLoader":
        """Devuelve un loader acorde al formato real del archivo."""
        from .factory import get_loader
        return get_loader(ruta, fallback=self)
