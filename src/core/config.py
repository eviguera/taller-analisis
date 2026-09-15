"""Nucleo del sistema: configuracion, catalogo de datos y pipeline ETL."""

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class DatasetConfig:
    """Definicion de un dataset en la configuracion."""
    nombre: str
    archivo: Optional[str] = None
    formato: str = "auto"          # auto | csv | excel | sav | zsav | por
    hoja: Optional[int] = None     # para excel
    mapeo: Dict[str, str] = field(default_factory=dict)  # columna_origen -> columna_canonica
    descripcion: str = ""
    fuentes_alternativas: List[str] = field(default_factory=list)  # otros archivos/variantes


@dataclass
class AppConfig:
    """Configuracion global del sistema."""
    negocio_nombre: str = "Mi Negocio"
    sector: str = ""                 # vertical de ejemplo (taller mecanico, retail, ...)
    slogan: str = "Gira tus datos en resultados"
    moneda: str = "MXN"
    directorio_datos: Path = Path("data")
    db_path: Path = Path("data/almacen.duckdb")
    cache_dir: Path = Path("data/cache")
    usar_cache: bool = True
    datasets: Dict[str, DatasetConfig] = field(default_factory=dict)

    # Compat: campo historico `taller_nombre` (se mantiene sincronizado).
    @property
    def taller_nombre(self) -> str:
        return self.negocio_nombre

    @taller_nombre.setter
    def taller_nombre(self, valor: str):
        self.negocio_nombre = valor