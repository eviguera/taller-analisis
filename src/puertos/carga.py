"""Puerto de carga de archivos fuente."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import pandas as pd


@dataclass
class CargaResultado:
    """Resultado inalterado de toda carga: dataframe + metadatos.

    Se define aqui (y no en `loaders/base.py`) porque es el tipo de retorno
    del puerto: los adaptadores dependen del puerto, no al reves.
    `src.loaders.base` lo reexporta, asi que los imports existentes siguen
    valiendo.
    """

    datos: pd.DataFrame
    metadatos: Dict[str, Any] = field(default_factory=dict)
    columnas_originales: list = field(default_factory=list)
    formato: str = ""
    etiquetas: Dict[str, Any] = field(default_factory=dict)  # etiquetas de valores (PSPP/SPSS)


class PuertoCarga(ABC):
    """Contrato de un cargador. Nuevos formatos = nuevas subclases.

    Solo declara lo que el nucleo necesita: el formato detectado y la carga
    en si. `actualizar_formato` **no** forma parte del puerto porque necesita
    el catalogo de cargadores (`loaders.factory`), que ya es un adaptador:
    ponerlo aqui invertiria la dependencia.
    """

    formato: str = "auto"

    @abstractmethod
    def cargar(self, ruta: Path, **kwargs) -> CargaResultado:
        """Carga un archivo y devuelve el DataFrame mas sus metadatos."""
