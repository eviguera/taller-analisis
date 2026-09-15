"""Cargador de archivos de PSPP/SPSS: .sav, .zsav y .por.

Usa `pyreadstat` (envoltura de la libreria C ReadStat), que es el mismo formato
que produce PSPP. Preserva etiquetas de variables y de valores, y permite
exportar DataFrames de vuelta a formato .sav para PSPP.
"""

import pandas as pd
from pathlib import Path
from typing import Optional

from .base import BaseLoader, CargaResultado


class PSPPLoader(BaseLoader):
    formato = "sav"

    def cargar(self, ruta: Path, aplicar_etiquetas: bool = True, **kwargs) -> CargaResultado:
        import pyreadstat

        ext = Path(ruta).suffix.lower()
        kwargs.pop("formato", None)

        if ext in (".sav", ".zsav"):
            df, meta = pyreadstat.read_sav(
                str(ruta),
                apply_value_formats=aplicar_etiquetas,
                formats_as_category=True,
                user_missing=False,
                **kwargs,
            )
        elif ext == ".por":
            df, meta = pyreadstat.read_por(str(ruta), **kwargs)
        else:
            raise ValueError(f"Extension no soportada por PSPP/SPSS: {ext}")

        # Normalizar nombres de columnas (SPSS usa @ para caracteres especiales)
        df.columns = [str(c).strip() for c in df.columns]

        etiquetas_columnas = dict(getattr(meta, "column_names_to_labels", None) or {})
        etiquetas_valores = dict(getattr(meta, "variable_value_labels", None) or {})

        return CargaResultado(
            datos=df,
            metadatos={
                "filas": len(df),
                "columnas": int(df.shape[1]),
                "nombre_archivo": getattr(meta, "file_label", ""),
                "fecha_creacion": str(getattr(meta, "creation_time", "")),
                "notas": getattr(meta, "notes", ""),
                "etiquetas_columnas": etiquetas_columnas,
                "etiquetas_valores": etiquetas_valores,
            },
            columnas_originales=list(df.columns),
            formato=ext.lstrip("."),
            etiquetas={
                "columnas": etiquetas_columnas,
                "valores": etiquetas_valores,
            },
        )


def exportar_sav(df: pd.DataFrame, ruta: Path, etiquetas_columnas: Optional[dict] = None,
                 etiquetas_valores: Optional[dict] = None, label_archivo: str = ""):
    """Exporta un DataFrame a formato .sav para abrir en PSPP/SPSS."""
    import pyreadstat
    df_limpio = df.copy()
    # SPSS no admite ciertos nombres de columna (irregulares) ni tipos raros
    df_limpio.columns = [str(c).replace(" ", "_").replace(".", "_") for c in df_limpio.columns]
    for c in df_limpio.columns:
        if df_limpio[c].dtype == "object":
            df_limpio[c] = df_limpio[c].astype(str)
    pyreadstat.write_sav(
        df_limpio,
        str(ruta),
        column_labels=etiquetas_columnas,
        variable_value_labels=etiquetas_valores or {},
        file_label=label_archivo,
    )
    return Path(ruta)


def exportar_por(df: pd.DataFrame, ruta: Path, **kwargs):
    """Exporta a formato portable .por para PSPP.

    Nota: el formato POR limita los nombres de variables a 8 caracteres,
    por lo que se truncan automaticamente (columnas puede ser >8).
    """
    import pyreadstat
    df_limpio = df.copy()
    nuevos = {}
    for c in df_limpio.columns:
        base = str(c).replace(" ", "_").replace(".", "_")
        nuevos[c] = base[:8] if len(base) > 8 else base
    df_limpio.columns = [nuevos[c] for c in df_limpio.columns]
    pyreadstat.write_por(df_limpio, str(ruta), **kwargs)
    return Path(ruta)