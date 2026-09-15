"""Cargadores de datos: soportan CSV, Excel y PSPP/SPSS (.sav, .zsav, .por)."""

from .base import BaseLoader, CargaResultado
from .csv_loader import CSVLoader
from .excel_loader import ExcelLoader
from .pspp_loader import PSPPLoader
from .factory import get_loader, cargar_archivo

__all__ = [
    "BaseLoader",
    "CargaResultado",
    "CSVLoader",
    "ExcelLoader",
    "PSPPLoader",
    "get_loader",
    "cargar_archivo",
]