"""Cargador de archivos Excel (.xlsx, .xls)."""

import pandas as pd
from pathlib import Path
from typing import Optional

from .base import BaseLoader, CargaResultado


class ExcelLoader(BaseLoader):
    formato = "excel"

    def cargar(self, ruta: Path, hoja: Optional[str] = None, **kwargs) -> CargaResultado:
        xls = pd.ExcelFile(ruta)
        if hoja is None:
            hoja = xls.sheet_names[0] if xls.sheet_names else None
        if hoja is not None and isinstance(hoja, int):
            hoja = xls.sheet_names[hoja]
        df = xls.parse(hoja) if hoja else pd.DataFrame()
        return CargaResultado(
            datos=df,
            metadatos={
                "filas": len(df),
                "columnas": int(df.shape[1]),
                "hojas": xls.sheet_names,
                "hoja_activa": hoja,
            },
            columnas_originales=list(df.columns),
            formato="excel",
        )