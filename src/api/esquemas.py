"""Esquemas de la API HTTP: modelos pydantic y paso a JSON estricto.

Dos responsabilidades, ninguna del nucleo:

1. **Contrato.** Los modelos describen lo que entra (``ConsultaSQL``) y lo
   que sale de cada endpoint. FastAPI los usa ademas para generar el
   OpenAPI de ``/docs``, de modo que la documentacion no puede desviarse
   del codigo: esta en el mismo sitio.
2. **Serializacion.** ``a_jsonable`` convierte el mundo pandas/numpy
   (``np.int64``, ``np.float64``, ``NaN``, ``pd.NaT``, ``Timestamp``) en
   tipos que ``json.dumps`` acepta con ``allow_nan=False``, que es como
   renderiza FastAPI. Sin esto, un KPI ``nan`` (p. ej. el ticket promedio
   de un workspace sin facturas) tumbaba la respuesta con un 500 en vez de
   devolver ``null``.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

# ------------------------------------------------------------------
#  Peticiones
# ------------------------------------------------------------------

class ConsultaSQL(BaseModel):
    """Cuerpo de ``POST /api/consulta``.

    La ``sql`` no se valida aqui a proposito: la regla de solo lectura es
    una propiedad del caso de uso (``aplicacion.validar_sql_solo_lectura``)
    y tiene que ser la misma que aplica la consola de la UI y los
    conectores. Duplicarla en el esquema crearia una segunda lista de
    sentencias que puede relajarse sin que la otra se entere.
    """

    sql: str = Field(description="Consulta de solo lectura (SELECT, WITH, ...).")
    limite: int = Field(default=1000, ge=1, le=10000,
                        description="Maximo de filas devueltas.")


# ------------------------------------------------------------------
#  Respuestas
# ------------------------------------------------------------------

class Salud(BaseModel):
    """``GET /api/salud``: unico endpoint publico."""

    estado: str
    servicio: str
    version: str


class Estado(BaseModel):
    """``GET /api/estado``: radiografia analitica del workspace.

    ``aviso`` es la degradacion controlada: si alguna parte del calculo no
    pudo ejecutarse, el resto del cuerpo llega completo y aqui se dice
    explicitamente que falta algo. ``null`` significa que no hay nada que
    avisar.
    """

    workspace: str
    negocio: Dict[str, Any]
    kpis: Dict[str, Any]
    cartera: Dict[str, Any]
    calidad: Dict[str, Any]
    alertas: Dict[str, Any]
    aviso: Optional[str] = None


class ListadoVistas(BaseModel):
    """``GET /api/vistas``: allowlist de vistas consultables."""

    workspace: str
    vistas: List[str]


class DatosVista(BaseModel):
    """``GET /api/vistas/{nombre}``."""

    workspace: str
    vista: str
    total_filas: int
    columnas: List[str]
    registros: List[Dict[str, Any]]


class ConsultaResultado(BaseModel):
    """``POST /api/consulta``."""

    workspace: str
    sql: str
    total_filas: int
    columnas: List[str]
    registros: List[Dict[str, Any]]


class Empresa(BaseModel):
    """Una empresa visible para la sesion."""

    clave: str
    nombre: str
    moneda: str
    sector: str
    principal: bool


class ListadoEmpresas(BaseModel):
    """``GET /api/empresas``."""

    actual: str
    empresas: List[Empresa]


# ------------------------------------------------------------------
#  Serializacion
# ------------------------------------------------------------------

def a_jsonable(valor: Any) -> Any:
    """Normaliza ``valor`` a tipos JSON nativos, recursivamente.

    * ``NaN``/``inf`` -> ``None``: JSON no los admite y FastAPI renderiza con
      ``allow_nan=False``, asi que dejarse un ``nan`` es un 500 garantizado.
    * escalares de numpy -> escalares de Python: ``np.int64`` no subclasea a
      ``int`` en todas las plataformas, y ``json`` lo rechaza.
    * fechas -> ISO 8601.
    * lo demas -> texto. Nunca un objeto opaco: el adaptador no puede
      filtrar una representacion que no controla.
    """
    if valor is None or valor is pd.NA or valor is pd.NaT:
        return None
    if isinstance(valor, (bool, np.bool_)):
        return bool(valor)
    if isinstance(valor, (int, np.integer)):
        return int(valor)
    if isinstance(valor, (float, np.floating)):
        numero = float(valor)
        return numero if math.isfinite(numero) else None
    if isinstance(valor, str):
        return valor
    if isinstance(valor, bytes):
        return valor.decode("utf-8", "replace")
    if isinstance(valor, np.datetime64):
        if np.isnat(valor):
            return None
        return pd.Timestamp(valor).isoformat()
    if isinstance(valor, (pd.Timestamp, datetime)):
        try:
            if pd.isna(valor):
                return None
        except (TypeError, ValueError):
            pass
        return valor.isoformat()
    if isinstance(valor, dict):
        return {str(k): a_jsonable(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set, frozenset, np.ndarray, pd.Series, pd.Index)):
        return [a_jsonable(v) for v in valor]
    try:
        if bool(pd.isna(valor)):
            return None
    except (TypeError, ValueError):
        # pd.isna de un objeto sin forma escalar (p. ej. un frame) no es
        # un booleano: se ignora la comprobacion y se cae al texto.
        pass
    return str(valor)


def columnas(df: pd.DataFrame) -> List[str]:
    """Nombres de columna como texto, en el orden del frame."""
    return [str(c) for c in df.columns]


def registros(df: pd.DataFrame, limite: int) -> List[Dict[str, Any]]:
    """Primeras ``limite`` filas del frame como ``list`` de dicts JSON-safe.

    El limite va aqui y no en el ``SELECT``: el frame ya esta en memoria y
    truncarlo cuesta lo que cuesta ``head``. Cortar en el adaptador evita
    ademas que una vista de millones de filas se serialice entera.
    """
    filas = df.head(limite).to_dict(orient="records")
    return [{str(k): a_jsonable(v) for k, v in fila.items()} for fila in filas]


__all__ = [
    "ConsultaSQL", "Salud", "Estado", "ListadoVistas", "DatosVista",
    "ConsultaResultado", "Empresa", "ListadoEmpresas",
    "a_jsonable", "columnas", "registros",
]
