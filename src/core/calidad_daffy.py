"""Validación de calidad de datos usando reglas declarativas (estilo daffy).

Este módulo proporciona validación de DataFrames con contratos declarativos,
inspirado en la librería daffy (https://github.com/mgillr/daffy), pero
implementado de forma nativa con pandas para evitar problemas de compatibilidad
y dependencias externas innecesarias.

Permite definir reglas de validación de forma declarativa:

    from src.core.calidad_daffy import ReglaCalidad, validar_con_daffy

    reglas = [
        ReglaCalidad(campo="id", tipo="int", nulo=False, unicidad=True),
        ReglaCalidad(campo="total", tipo="float", minimo=0),
        ReglaCalidad(campo="email", tipo="str", patron=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    ]

    resultado = validar_con_daffy(df_clientes, reglas)
    if resultado.valido:
        print("Todos los datos son válidos")
    else:
        for error in resultado.errores:
            print(f"Error en {error['campo']}: {error['mensaje']}")
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class ReglaCalidad:
    """Una regla de validación de calidad para un campo del DataFrame.

    Attributes:
        campo: Nombre de la columna a validar.
        tipo: Tipo esperado ("int", "float", "str", "bool", "datetime").
        nulo: Si el campo permite valores nulos.
        minimo: Valor mínimo permitido (para numéricos).
        maximo: Valor máximo permitido (para numéricos).
        patron: Expresión regular que debe cumplir (para strings).
        unicidad: Si el campo debe tener valores únicos.
        descripcion: Descripción legible de la regla.
    """

    campo: str
    tipo: Optional[str] = None
    nulo: bool = True
    minimo: Optional[float] = None
    maximo: Optional[float] = None
    patron: Optional[str] = None
    unicidad: bool = False
    descripcion: Optional[str] = None


@dataclass
class ResultadoCalidad:
    """Resultado de la validación de calidad.

    Attributes:
        valido: True si todas las reglas pasaron.
        total_reglas: Número total de reglas evaluadas.
        reglas_ok: Número de reglas que pasaron.
        reglas_fallidas: Número de reglas que fallaron.
        errores: Lista de errores encontrados.
        detalles: Detalles completos de cada regla evaluada.
    """

    valido: bool
    total_reglas: int
    reglas_ok: int
    reglas_fallidas: int
    errores: List[Dict[str, Any]] = field(default_factory=list)
    detalles: List[Dict[str, Any]] = field(default_factory=list)


def _mapear_tipo_pandas(tipo: Optional[str]) -> Any:
    """Mapea un tipo de string a un tipo de pandas/numpy."""
    if tipo is None:
        return None
    mapeo = {
        "int": "int64",
        "integer": "int64",
        "float": "float64",
        "decimal": "float64",
        "str": "object",
        "string": "object",
        "bool": "bool",
        "booleano": "bool",
        "datetime": "datetime64[ns]",
        "fecha": "datetime64[ns]",
    }
    return mapeo.get(tipo, tipo)


def _validar_tipo(
    df: pd.DataFrame, campo: str, tipo_esperado: str
) -> tuple[bool, str]:
    """Valida que una columna tenga el tipo esperado."""
    if campo not in df.columns:
        return False, f"Columna '{campo}' no existe en el DataFrame"

    tipo_esperado_mapeado = _mapear_tipo_pandas(tipo_esperado)
    if tipo_esperado_mapeado is None:
        return True, ""  # No se puede validar tipo desconocido

    tipo_actual = str(df[campo].dtype)

    # Mapeo simplificado para comparación
    tipos_equivalentes = {
        "int64": ["int64", "Int64"],
        "float64": ["float64", "Float64"],
        "object": ["object", "string"],
        "bool": ["bool", "boolean"],
        "datetime64[ns]": ["datetime64[ns]", "datetime64"],
    }

    tipos_aceptables = tipos_equivalentes.get(tipo_esperado_mapeado, [tipo_esperado_mapeado])
    if tipo_actual in tipos_aceptables:
        return True, ""

    return False, f"Columna '{campo}' tiene tipo {tipo_actual}, se esperaba {tipo_esperado}"


def _validar_nulos(df: pd.DataFrame, campo: str, nulo: bool) -> tuple[bool, str]:
    """Valida que una columna tenga o no valores nulos."""
    if campo not in df.columns:
        return False, f"Columna '{campo}' no existe en el DataFrame"

    nulos = df[campo].isna().sum()
    if nulo:
        return True, ""  # Los nulos están permitidos
    if nulos > 0:
        return False, f"Columna '{campo}' tiene {nulos} valor(es) nulo(s) pero no se permiten"
    return True, ""


def _validar_minimo(df: pd.DataFrame, campo: str, minimo: float) -> tuple[bool, str]:
    """Valida que una columna numérica tenga valores >= minimo."""
    if campo not in df.columns:
        return False, f"Columna '{campo}' no existe en el DataFrame"

    try:
        valores = pd.to_numeric(df[campo], errors="coerce").dropna()
        if valores.empty:
            return True, ""
        min_valor = valores.min()
        if min_valor < minimo:
            return False, f"Columna '{campo}' tiene valores menores a {minimo}: mínimo encontrado {min_valor}"
        return True, ""
    except Exception:
        return False, f"No se pudo validar mínimo de columna '{campo}'"


def _validar_maximo(df: pd.DataFrame, campo: str, maximo: float) -> tuple[bool, str]:
    """Valida que una columna numérica tenga valores <= maximo."""
    if campo not in df.columns:
        return False, f"Columna '{campo}' no existe en el DataFrame"

    try:
        valores = pd.to_numeric(df[campo], errors="coerce").dropna()
        if valores.empty:
            return True, ""
        max_valor = valores.max()
        if max_valor > maximo:
            return False, f"Columna '{campo}' tiene valores mayores a {maximo}: máximo encontrado {max_valor}"
        return True, ""
    except Exception:
        return False, f"No se pudo validar máximo de columna '{campo}'"


def _validar_patron(df: pd.DataFrame, campo: str, patron: str) -> tuple[bool, str]:
    """Valida que una columna de strings cumpla un patron regex."""
    if campo not in df.columns:
        return False, f"Columna '{campo}' no existe en el DataFrame"

    try:
        valores = df[campo].dropna().astype(str)
        coinciden = valores.str.match(patron, na=False)
        no_coinciden = (~coinciden).sum()
        if no_coinciden > 0:
            return False, f"Columna '{campo}' tiene {no_coinciden} valor(es) que no cumplen el patron '{patron}'"
        return True, ""
    except Exception as e:
        return False, f"Error validando patron en columna '{campo}': {e}"


def _validar_unicidad(df: pd.DataFrame, campo: str) -> tuple[bool, str]:
    """Valida que una columna tenga valores únicos."""
    if campo not in df.columns:
        return False, f"Columna '{campo}' no existe en el DataFrame"

    duplicados = df[campo].duplicated().sum()
    if duplicados > 0:
        return False, f"Columna '{campo}' tiene {duplicados} valor(es) duplicado(s)"
    return True, ""


def validar_con_daffy(
    df: pd.DataFrame,
    reglas: List[ReglaCalidad],
    nombre_dataset: str = "datos",
) -> ResultadoCalidad:
    """Valida un DataFrame usando reglas de calidad declarativas.

    Esta función implementa validación similar a daffy pero de forma nativa
    con pandas, evitando problemas de compatibilidad con versiones de
    dependencias.

    Argumentos:
        df: DataFrame de pandas a validar.
        reglas: Lista de reglas de calidad a aplicar.
        nombre_dataset: Nombre del dataset para mensajes de error.

    Retorna:
        ResultadoCalidad con el resultado de la validación.
    """
    errores: List[Dict[str, Any]] = []
    detalles: List[Dict[str, Any]] = []
    reglas_ok = 0
    reglas_fallidas = 0

    for regla in reglas:
        try:
            # 1. Validar que la columna exista
            if regla.campo not in df.columns:
                reglas_fallidas += 1
                errores.append({
                    "campo": regla.campo,
                    "regla": regla.descripcion or regla.campo,
                    "mensaje": f"Columna '{regla.campo}' no existe en el dataset '{nombre_dataset}'",
                })
                detalles.append({
                    "campo": regla.campo,
                    "regla": regla.descripcion or regla.campo,
                    "estado": "ERROR",
                    "detalle": f"Columna '{regla.campo}' no existe en el dataset",
                })
                continue

            # 2. Validar tipo
            if regla.tipo:
                valido, mensaje = _validar_tipo(df, regla.campo, regla.tipo)
                if not valido:
                    reglas_fallidas += 1
                    errores.append({
                        "campo": regla.campo,
                        "regla": regla.descripcion or regla.campo,
                        "mensaje": mensaje,
                    })
                    detalles.append({
                        "campo": regla.campo,
                        "regla": regla.descripcion or regla.campo,
                        "estado": "ERROR",
                        "detalle": mensaje,
                    })
                    continue

            # 3. Validar nulos
            if not regla.nulo:
                valido, mensaje = _validar_nulos(df, regla.campo, regla.nulo)
                if not valido:
                    reglas_fallidas += 1
                    errores.append({
                        "campo": regla.campo,
                        "regla": regla.descripcion or regla.campo,
                        "mensaje": mensaje,
                    })
                    detalles.append({
                        "campo": regla.campo,
                        "regla": regla.descripcion or regla.campo,
                        "estado": "ERROR",
                        "detalle": mensaje,
                    })
                    continue

            # 4. Validar mínimo
            if regla.minimo is not None:
                valido, mensaje = _validar_minimo(df, regla.campo, regla.minimo)
                if not valido:
                    reglas_fallidas += 1
                    errores.append({
                        "campo": regla.campo,
                        "regla": regla.descripcion or regla.campo,
                        "mensaje": mensaje,
                    })
                    detalles.append({
                        "campo": regla.campo,
                        "regla": regla.descripcion or regla.campo,
                        "estado": "ERROR",
                        "detalle": mensaje,
                    })
                    continue

            # 5. Validar máximo
            if regla.maximo is not None:
                valido, mensaje = _validar_maximo(df, regla.campo, regla.maximo)
                if not valido:
                    reglas_fallidas += 1
                    errores.append({
                        "campo": regla.campo,
                        "regla": regla.descripcion or regla.campo,
                        "mensaje": mensaje,
                    })
                    detalles.append({
                        "campo": regla.campo,
                        "regla": regla.descripcion or regla.campo,
                        "estado": "ERROR",
                        "detalle": mensaje,
                    })
                    continue

            # 6. Validar patron
            if regla.patron:
                valido, mensaje = _validar_patron(df, regla.campo, regla.patron)
                if not valido:
                    reglas_fallidas += 1
                    errores.append({
                        "campo": regla.campo,
                        "regla": regla.descripcion or regla.campo,
                        "mensaje": mensaje,
                    })
                    detalles.append({
                        "campo": regla.campo,
                        "regla": regla.descripcion or regla.campo,
                        "estado": "ERROR",
                        "detalle": mensaje,
                    })
                    continue

            # 7. Validar unicidad
            if regla.unicidad:
                valido, mensaje = _validar_unicidad(df, regla.campo)
                if not valido:
                    reglas_fallidas += 1
                    errores.append({
                        "campo": regla.campo,
                        "regla": regla.descripcion or regla.campo,
                        "mensaje": mensaje,
                    })
                    detalles.append({
                        "campo": regla.campo,
                        "regla": regla.descripcion or regla.campo,
                        "estado": "ERROR",
                        "detalle": mensaje,
                    })
                    continue

            # Si llegamos aquí, la regla pasó
            reglas_ok += 1
            detalles.append({
                "campo": regla.campo,
                "regla": regla.descripcion or regla.campo,
                "estado": "OK",
                "detalle": "Validación exitosa",
            })

        except Exception as e:
            reglas_fallidas += 1
            errores.append({
                "campo": regla.campo,
                "regla": regla.descripcion or regla.campo,
                "mensaje": str(e),
            })
            detalles.append({
                "campo": regla.campo,
                "regla": regla.descripcion or regla.campo,
                "estado": "ERROR",
                "detalle": str(e),
            })

    valido = reglas_fallidas == 0

    return ResultadoCalidad(
        valido=valido,
        total_reglas=len(reglas),
        reglas_ok=reglas_ok,
        reglas_fallidas=reglas_fallidas,
        errores=errores,
        detalles=detalles,
    )


__all__ = ["ReglaCalidad", "ResultadoCalidad", "validar_con_daffy"]