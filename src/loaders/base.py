"""Interfaz base para los cargadores de datos.

Para agregar una nueva fuente solo hay que crear una clase que herede de
`BaseLoader` e implementar `cargar(ruta, **kwargs)`. El resto del sistema
(catalogo, pipeline, dashboard) funciona sin cambios.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd


@dataclass
class CargaResultado:
    datos: pd.DataFrame
    metadatos: Dict[str, Any] = field(default_factory=dict)
    columnas_originales: list = field(default_factory=list)
    formato: str = ""
    etiquetas: Dict[str, Any] = field(default_factory=dict)  # etiquetas de valores (PSPP/SPSS)


class BaseLoader(ABC):
    """Contrato de un cargador. Nuevos formatos = nuevas subclases."""

    formato: str = "auto"

    @abstractmethod
    def cargar(self, ruta: Path, **kwargs) -> CargaResultado:
        """Carga un archivo y devuelve el DataFrame mas sus metadatos."""

    def actualizar_formato(self, ruta: Path) -> "BaseLoader":
        """Devuelve un loader acorde al formato real del archivo."""
        from .factory import get_loader
        return get_loader(ruta, fallback=self)