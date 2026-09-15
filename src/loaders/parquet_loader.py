"""Cargador de archivos Parquet (cache local de alto rendimiento)."""

import pandas as pd
from pathlib import Path

from .base import BaseLoader, CargaResultado


class ParquetLoader(BaseLoader):
    formato = "parquet"

    def cargar(self, ruta: Path, **kwargs) -> CargaResultado:
        df = pd.read_parquet(ruta)
        return CargaResultado(
            datos=df,
            metadatos={"filas": len(df), "columnas": int(df.shape[1])},
            columnas_originales=list(df.columns),
            formato="parquet",
        )