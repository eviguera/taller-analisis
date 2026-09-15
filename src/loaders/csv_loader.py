"""Cargador de archivos CSV/TSV."""

import pandas as pd
from pathlib import Path
from typing import Optional

from .base import BaseLoader, CargaResultado


class CSVLoader(BaseLoader):
    formato = "csv"

    def cargar(self, ruta: Path, sep: Optional[str] = None, encoding: Optional[str] = None,
               **kwargs) -> CargaResultado:
        if sep is None:
            sep = "\t" if str(ruta).lower().endswith(".tsv") else ","
        try:
            df = pd.read_csv(ruta, sep=sep, encoding=encoding or "utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(ruta, sep=sep, encoding="latin-1")
        except pd.errors.ParserError:
            df = pd.read_csv(ruta, sep=None, engine="python")
        return CargaResultado(
            datos=df,
            metadatos={"filas": len(df), "columnas": int(df.shape[1])},
            columnas_originales=list(df.columns),
            formato="csv",
        )