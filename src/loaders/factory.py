"""Factory de cargadores: elige el loader segun la extension o formato del archivo."""

from pathlib import Path
from typing import Optional

from .base import BaseLoader, CargaResultado

FORMATO_POR_EXT = {
    ".csv": "csv",
    ".tsv": "csv",
    ".xlsx": "excel",
    ".xls": "excel",
    ".sav": "sav",
    ".zsav": "zsav",
    ".por": "por",
}


def get_loader(ruta: Path, formato: Optional[str] = None, fallback: Optional[BaseLoader] = None) -> BaseLoader:
    """Devuelve el cargador adecuado para `ruta`.

    Prioridad: `formato` explicito > extension del archivo > `fallback`.
    """
    fmt = (formato or "").lower()
    if fmt != "auto" and fmt:
        return _instanciar(fmt)

    ext = Path(ruta).suffix.lower()
    if ext in FORMATO_POR_EXT:
        return _instanciar(FORMATO_POR_EXT[ext])

    if fallback is not None:
        return _instanciar(fallback.formato) or fallback

    raise ValueError(f"Formato no soportado para: {ruta}")


def _instanciar(fmt: str) -> BaseLoader:
    if fmt == "csv":
        from .csv_loader import CSVLoader
        return CSVLoader()
    if fmt in ("excel", "xlsx", "xls"):
        from .excel_loader import ExcelLoader
        return ExcelLoader()
    if fmt in ("sav", "zsav", "por"):
        from .pspp_loader import PSPPLoader
        return PSPPLoader()
    if fmt == "parquet":
        from .parquet_loader import ParquetLoader
        return ParquetLoader()
    raise ValueError(f"Cargador no disponible para formato: {fmt}")


def cargar_archivo(ruta: Path, formato: Optional[str] = None, **kwargs) -> CargaResultado:
    """Utilidad de un solo paso: detecta, carga y devuelve el resultado."""
    loader = get_loader(ruta, formato)
    return loader.cargar(ruta, **kwargs)