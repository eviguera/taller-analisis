"""Cargador de datos usando dlt (https://dlthub.com).

dlt es una librería ligera de ETL en Python que permite cargar datos desde
múltiples orígenes (Postgres, MySQL, SQLite, APIs REST, CSV, Excel, etc.)
hacia destinos como DuckDB, Parquet, etc.

Este adaptador integra dlt con la arquitectura de GIRO, permitiendo cargar
datos desde orígenes externos sin salir del patrón de PuertoCarga.

Ejemplo de uso en config.yaml:
```yaml
conectores:
  - nombre: "erp_postgres"
    motor: "dlt"
    fuente: "postgresql://user:pass@host:5432/db"
    dataset: "facturas"
    parametros:
      tabla: "facturas"
      incremental: true
```
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import dlt
import pandas as pd

from src.loaders.base import CargaResultado, PuertoCarga


class DltLoader(PuertoCarga):
    """Cargador que utiliza dlt para extraer datos de orígenes externos.

    Soporta cualquier fuente compatible con dlt:
    - Bases de datos: postgres, mysql, sqlite, sql server, etc.
    - Archivos: csv, excel, json, parquet, etc.
    - APIs REST y servicios web
    - Almacenamiento: s3, gcs, azure, etc.
    """

    def __init__(self, formato: str = "dlt"):
        self.formato = formato

    def cargar(self, ruta: Path, **kwargs) -> CargaResultado:
        """Carga datos usando dlt desde un origen externo.

        Argumentos:
            ruta: Puede ser un DSN de conexión, URL de API, o ruta de archivo.
            kwargs: Parámetros adicionales para dlt (tabla, esquema, etc.)

        Retorna:
            CargaResultado con los datos cargados.
        """
        try:
            # Extraer parámetros de dlt
            fuente = str(ruta)
            dataset_name = kwargs.get("dataset", "datos_generados")
            tabla = kwargs.get("tabla")
            incremental = kwargs.get("incremental", False)

            # Construir pipeline de dlt
            pipeline = dlt.pipeline(
                pipeline_name=f"giro_{dataset_name}",
                destination="duckdb",
                dataset_name=dataset_name,
            )

            # Ejecutar carga según el tipo de fuente
            if tabla:
                # Cargar una tabla específica de una base de datos
                info = pipeline.run(
                    dlt.sql_table(
                        table=tabla,
                        connection=fuente,
                        incremental=incremental,
                    )
                )
            else:
                # Cargar desde archivo o fuente genérica
                info = pipeline.run(
                    dlt.files(
                        file_paths=[fuente],
                        file_glob="*",
                    )
                )

            # Obtener los datos como DataFrame
            df = pipeline.dataset().to_pandas()

            metadatos = {
                "filas_cargadas": len(df),
                "columnas": list(df.columns),
                "fuente": fuente,
                "dataset": dataset_name,
                "paquete_dlt": pipeline.pipeline_name,
                "paquete_id": str(pipeline.last_trace.last_run_id)
                if pipeline.last_trace
                else None,
            }

            return CargaResultado(
                datos=df,
                metadatos=metadatos,
                columnas_originales=list(df.columns),
                formato=self.formato,
                etiquetas=metadatos,
            )

        except Exception as e:
            # Si dlt falla, devolvemos un DataFrame vacío con el error
            log = logging.getLogger("taller.loaders.dlt")
            log.error("Error cargando con dlt desde %s: %s", fuente, e)

            return CargaResultado(
                datos=pd.DataFrame(),
                metadatos={
                    "error": str(e),
                    "fuente": fuente,
                    "dataset": kwargs.get("dataset", "datos_generados"),
                },
                columnas_originales=[],
                formato=self.formato,
                etiquetas={"error": str(e)},
            )


__all__ = ["DltLoader"]