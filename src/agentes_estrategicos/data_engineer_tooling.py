"""Integracion de herramientas de data engineering de awesome-data-engineering.

Este modulo integra herramientas externas de alta calidad para mejorar el
pipeline de datos de GIRO:

* **dlt** (https://dlthub.com): Carga de datos desde multiples orígenes
  (Postgres, MySQL, SQLite, APIs REST, archivos, etc.) hacia DuckDB.
* **daffy** (https://github.com/mgillr/daffy): Validacion de DataFrames
  con contratos declarativos (tipos, rangos, unicidad, patrones).

Estas herramientas se integran sin romper la arquitectura hexagonal existente:
se usan como adaptadores dentro de src/aplicacion y src/loaders.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.loaders.dlt_loader import DltLoader
from src.core.calidad_daffy import ReglaCalidad, ResultadoCalidad, validar_con_daffy


def cargar_con_dlt(
    fuente: str,
    dataset: str = "datos_generados",
    tabla: Optional[str] = None,
    incremental: bool = False,
    **kwargs,
) -> pd.DataFrame:
    """Carga datos desde un origen externo usando dlt.

    Argumentos:
        fuente: DSN de conexion, URL de API, o ruta de archivo.
        dataset: Nombre del dataset en el destino.
        tabla: Nombre de la tabla a cargar (para bases de datos).
        incremental: Si usar carga incremental.
        kwargs: Argumentos adicionales para dlt.

    Retorna:
        DataFrame de pandas con los datos cargados.

    Ejemplo:
        >>> df = cargar_con_dlt(
        ...     fuente="postgresql://user:pass@host:5432/db",
        ...     dataset="facturas",
        ...     tabla="facturas",
        ...     incremental=True,
        ... )
    """
    loader = DltLoader(formato="dlt")
    resultado = loader.cargar(
        Path(fuente),
        dataset=dataset,
        tabla=tabla,
        incremental=incremental,
        **kwargs,
    )
    return resultado.datos


def validar_con_daffy(
    df: pd.DataFrame,
    reglas: List[ReglaCalidad],
    nombre_dataset: str = "datos",
) -> ResultadoCalidad:
    """Valida un DataFrame usando reglas de daffy.

    Esta es una envoltura alrededor de src.core.calidad_daffy.validar_con_daffy
    para proporcionar una interfaz unificada desde el modulo de herramientas
    de data engineering.

    Argumentos:
        df: DataFrame de pandas a validar.
        reglas: Lista de reglas de calidad a aplicar.
        nombre_dataset: Nombre del dataset para mensajes de error.

    Retorna:
        ResultadoCalidad con el resultado de la validacion.
    """
    from src.core.calidad_daffy import validar_con_daffy as _validar

    return _validar(df, reglas, nombre_dataset)


def crear_regla_calidad(
    campo: str,
    tipo: Optional[str] = None,
    nulo: bool = True,
    minimo: Optional[float] = None,
    maximo: Optional[float] = None,
    patron: Optional[str] = None,
    unicidad: bool = False,
    descripcion: Optional[str] = None,
) -> ReglaCalidad:
    """Crea una regla de calidad de datos lista para usar con daffy.

    Argumentos:
        campo: Nombre de la columna a validar.
        tipo: Tipo esperado ("int", "float", "str", "bool", "datetime").
        nulo: Si el campo permite valores nulos.
        minimo: Valor minimo permitido (para numericos).
        maximo: Valor maximo permitido (para numericos).
        patron: Expresion regular que debe cumplir (para strings).
        unicidad: Si el campo debe tener valores unicos.
        descripcion: Descripcion legible de la regla.

    Retorna:
        Una instancia de ReglaCalidad lista para usar.
    """
    return ReglaCalidad(
        campo=campo,
        tipo=tipo,
        nulo=nulo,
        minimo=minimo,
        maximo=maximo,
        patron=patron,
        unicidad=unicidad,
        descripcion=descripcion,
    )


def validar_dataframe_con_contrato(
    df: pd.DataFrame,
    contrato: Dict[str, Dict[str, Any]],
    nombre_dataset: str = "datos",
) -> ResultadoCalidad:
    """Valida un DataFrame usando un contrato de calidad definido como diccionario.

    Argumentos:
        df: DataFrame de pandas a validar.
        contrato: Diccionario que mapea nombres de columna a sus reglas.
            Ejemplo:
                {
                    "id": {"tipo": "int", "nulo": False, "unicidad": True},
                    "total": {"tipo": "float", "minimo": 0},
                    "email": {"tipo": "str", "patron": r"^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$"},
                }
        nombre_dataset: Nombre del dataset para mensajes de error.

    Retorna:
        ResultadoCalidad con el resultado de la validacion.
    """
    reglas: List[ReglaCalidad] = []
    for campo, config in contrato.items():
        regla = ReglaCalidad(
            campo=campo,
            tipo=config.get("tipo"),
            nulo=config.get("nulo", True),
            minimo=config.get("minimo"),
            maximo=config.get("maximo"),
            patron=config.get("patron"),
            unicidad=config.get("unicidad", False),
            descripcion=config.get("descripcion"),
        )
        reglas.append(regla)

    return validar_con_daffy(df, reglas, nombre_dataset)


__all__ = [
    "cargar_con_dlt",
    "validar_con_daffy",
    "crear_regla_calidad",
    "validar_dataframe_con_contrato",
    "ReglaCalidad",
    "ResultadoCalidad",
]
