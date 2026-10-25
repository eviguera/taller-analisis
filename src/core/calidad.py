"""Reglas de calidad de datos sobre los datasets cargados por el ETL.

Patron de referencia: ``gchq/gchq-data-quality`` (Apache-2.0), clonado en
``referencias/`` — reglas simples por campo, evaluadas sobre un DataFrame, y
un resultado plano (``evaluadas / cumplen / tasa``) que se puede ordenar,
filtrar y pintar. Aqui no se usa ese paquete ni su codigo: solo pandas, que
ya esta en el stack, y las reglas de GIRO. La licencia del repositorio de
referencia queda en ``referencias/gchq-data-quality/LICENSE.txt``.

Dimensiones (marco DAMA, como en el repositorio de referencia):
  * completitud -> el campo no viene vacio
  * unicidad     -> la clave no se repite
  * validez      -> el valor esta en rango, con formato o no es futuro

Las reglas son defensivas con el esquema: **solo se evaluan si el dataset
tiene ese campo**, asi el producto sirve para cualquier negocio sin meter el
vertico del cliente en la logica (AGENTS.md: nada de taller, vehiculo ni
kilometraje en reglas de negocio). Una regla que lanza no tumba el ETL: se
registra como fila con estado ERROR y se avisa por log.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import pandas as pd

log = logging.getLogger("taller.calidad")

# Esquema del frame de resultados: una fila por regla evaluada.
COLUMNAS_RESULTADO = [
    "dataset", "campo", "dimension", "regla",
    "evaluadas", "cumplen", "tasa", "estado",
]

ESTADO_OK = "OK"
ESTADO_REVISAR = "REVISAR"
ESTADO_ERROR = "ERROR"


@dataclass
class Regla:
    """Una comprobacion sobre un campo, aplicable a uno o a todos los datasets."""

    campo: str
    dimension: str
    descripcion: str
    evaluar: Callable[[pd.DataFrame], pd.Series]
    # "" = se evalua en cualquier dataset que tenga el campo.
    dataset: str = ""

    def aplica(self, nombre: str, df: pd.DataFrame) -> bool:
        if self.dataset and self.dataset != nombre:
            return False
        return self.campo in df.columns


# ------------------------------------------------------------------
#  Constructores de reglas
# ------------------------------------------------------------------
def completitud(campo: str, descripcion: str = "") -> Regla:
    """Dimension completitud: el campo no esta vacio (nulo o solo espacios)."""

    def _evaluar(df: pd.DataFrame) -> pd.Series:
        s = df[campo]
        texto = s.astype("string").str.strip()
        return (s.notna() & texto.ne("").fillna(False)).astype(bool)

    return Regla(campo=campo, dimension="completitud",
                 descripcion=descripcion or f"{campo} sin valores vacios",
                 evaluar=_evaluar)


def unicidad(campo: str, descripcion: str = "") -> Regla:
    """Dimension unicidad: el valor no se repite en el dataset."""

    def _evaluar(df: pd.DataFrame) -> pd.Series:
        return (~df[campo].duplicated(keep=False)).astype(bool)

    return Regla(campo=campo, dimension="unicidad",
                 descripcion=descripcion or f"{campo} sin duplicados",
                 evaluar=_evaluar)


def rango(campo: str, minimo: Optional[float] = None, maximo: Optional[float] = None,
          estricto: bool = False, descripcion: str = "") -> Regla:
    """Dimension validez: numero dentro de los limites.

    Un valor que no se puede convertir a numero **no pasa**: convertirlo a 0
    en silencio falsearia el resultado, igual que en la limpieza del ETL.
    """

    def _evaluar(df: pd.DataFrame) -> pd.Series:
        s = pd.to_numeric(df[campo], errors="coerce")
        mascara = s.notna()
        if minimo is not None:
            mascara &= (s > minimo) if estricto else (s >= minimo)
        if maximo is not None:
            mascara &= (s < maximo) if estricto else (s <= maximo)
        return mascara.fillna(False).astype(bool)

    if minimo is not None and maximo is not None:
        limite = f"entre {minimo} y {maximo}"
    elif minimo is not None:
        limite = (f"mayor que {minimo}" if estricto else f"mayor o igual a {minimo}")
    else:
        limite = (f"menor que {maximo}" if estricto else f"menor o igual a {maximo}")
    return Regla(campo=campo, dimension="validez",
                 descripcion=descripcion or f"{campo} {limite}",
                 evaluar=_evaluar)


def formato(campo: str, patron: str, descripcion: str = "") -> Regla:
    """Dimension validez: el texto cumple una expresion regular."""

    regex = re.compile(patron)

    def _evaluar(df: pd.DataFrame) -> pd.Series:
        texto = df[campo].astype("string").str.strip()
        return texto.str.match(regex, na=False).fillna(False).astype(bool)

    return Regla(campo=campo, dimension="validez",
                 descripcion=descripcion or f"{campo} con formato valido",
                 evaluar=_evaluar)


def no_futuro(campo: str, tolerancia_dias: int = 1, descripcion: str = "") -> Regla:
    """Dimension validez: la fecha no esta por delante de hoy.

    Se admite ``tolerancia_dias`` de holgura para desfases de zona horaria
    (una fecha local de hoy puede ser mañana en UTC). Lo que no se parsea
    como fecha no pasa.
    """

    def _evaluar(df: pd.DataFrame) -> pd.Series:
        fechas = pd.to_datetime(df[campo], errors="coerce", utc=True)
        if getattr(fechas.dtype, "tz", None) is not None:
            fechas = fechas.dt.tz_localize(None)
        limite = (pd.Timestamp.now(tz="UTC").tz_localize(None)
                  + pd.Timedelta(days=tolerancia_dias))
        return (fechas.notna() & (fechas <= limite)).astype(bool)

    return Regla(campo=campo, dimension="validez",
                 descripcion=descripcion or f"{campo} sin fechas futuras",
                 evaluar=_evaluar)


# ------------------------------------------------------------------
#  Reglas por defecto
# ------------------------------------------------------------------
def reglas_por_defecto() -> List[Regla]:
    """Reglas genericas, validas para cualquier esquema de negocio.

    Se aplica la que corresponda: un dataset sin ``total`` no evalua la regla
    de total, y un negocio sin inventario no evalua stock. Ni una regla del
    vertico del cliente.
    """
    return [
        completitud("id", "clave primaria presente en cada fila"),
        unicidad("id", "clave primaria sin repetir"),
        no_futuro("fecha"),
        rango("total", minimo=0, estricto=True, descripcion="total mayor que cero"),
        rango("precio_base", minimo=0, descripcion="precio_base sin valores negativos"),
        rango("precio_venta", minimo=0, descripcion="precio_venta sin valores negativos"),
        rango("stock_actual", minimo=0, descripcion="stock_actual sin existencias negativas"),
        completitud("cliente_id", "cada registro ligado a un cliente"),
        formato("email", r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
                descripcion="email con formato de correo"),
    ]


# ------------------------------------------------------------------
#  Evaluacion
# ------------------------------------------------------------------
def evaluar_dataset(nombre: str, df: pd.DataFrame,
                    reglas: Optional[List[Regla]] = None) -> pd.DataFrame:
    """Evalua las reglas aplicables a un dataset.

    Devuelve el resultado plano (una fila por regla): es lo que se muestra
    en la UI, lo que se imprime por CLI y lo que se guarda en el resultado
    del ETL. Nunca lanza: una regla rota se reporta con estado ERROR.
    """
    reglas = reglas_por_defecto() if reglas is None else reglas
    filas: List[Dict] = []

    for regla in reglas:
        if not regla.aplica(nombre, df):
            continue
        base = {"dataset": nombre, "campo": regla.campo,
                "dimension": regla.dimension, "regla": regla.descripcion}
        evaluadas = int(len(df))
        try:
            mascara = regla.evaluar(df)
            cumplen = int(mascara.sum())
            tasa = (cumplen / evaluadas) if evaluadas else 1.0
            filas.append({**base, "evaluadas": evaluadas, "cumplen": cumplen,
                          "tasa": round(tasa, 4),
                          "estado": ESTADO_OK if cumplen == evaluadas else ESTADO_REVISAR})
        except Exception as e:  # noqa: BLE001  -> se reporta, no se traga
            log.warning("Fallo la regla '%s' sobre %s.%s: %s",
                        regla.descripcion, nombre, regla.campo, e)
            filas.append({**base, "evaluadas": evaluadas, "cumplen": 0,
                          "tasa": 0.0, "estado": ESTADO_ERROR})

    return pd.DataFrame(filas, columns=COLUMNAS_RESULTADO)


def evaluar_conjunto(data: Dict[str, pd.DataFrame],
                     reglas: Optional[List[Regla]] = None) -> pd.DataFrame:
    """Evalua todas las reglas sobre todos los datasets cargados."""
    trozos = [evaluar_dataset(nombre, df, reglas)
              for nombre, df in (data or {}).items()
              if df is not None]
    trozos = [t for t in trozos if not t.empty]
    if not trozos:
        return pd.DataFrame(columns=COLUMNAS_RESULTADO)
    return pd.concat(trozos, ignore_index=True)


def resumen(calidad: pd.DataFrame) -> Dict[str, int]:
    """Conteo de reglas por estado: para el KPI del ETL y la salida de CLI."""
    if calidad is None or calidad.empty:
        return {"total": 0, "ok": 0, "revisar": 0, "error": 0}
    estados = calidad["estado"].value_counts()
    return {"total": int(len(calidad)),
            "ok": int(estados.get(ESTADO_OK, 0)),
            "revisar": int(estados.get(ESTADO_REVISAR, 0)),
            "error": int(estados.get(ESTADO_ERROR, 0))}


# ------------------------------------------------------------------
#  Consistencia referencial (claves foraneas entre datasets)
# ------------------------------------------------------------------

def evaluar_consistencia_referencial(data: Dict[str, pd.DataFrame],
                                     reglas: Optional[List[tuple[str, str, str]]] = None
                                     ) -> pd.DataFrame:
    """Evalua que las claves foraneas existan en el dataset de destino.

    ``reglas`` es una lista de tuplas ``(dataset_origen, campo_origen,
    dataset_destino)``. Por defecto se evalúan las parejas canonicas de
    GIRO (facturas→clientes, facturas→vehiculos, factura_detalle→facturas)
    cuando los datasets correspondientes existen.
    """
    if reglas is None:
        reglas = []
        if "facturas" in data and "clientes" in data:
            reglas.append(("facturas", "cliente_id", "clientes"))
        if "facturas" in data and "vehiculos" in data:
            reglas.append(("facturas", "vehiculo_id", "vehiculos"))
        if "factura_detalle" in data and "facturas" in data:
            reglas.append(("factura_detalle", "factura_id", "facturas"))

    filas: List[Dict] = []
    for origen, campo, destino in reglas:
        if origen not in data or destino not in data:
            continue
        df_origen = data[origen]
        df_destino = data[destino]
        if campo not in df_origen.columns or "id" not in df_destino.columns:
            continue
        claves_validas = set(df_destino["id"].dropna())
        valores = df_origen[campo].dropna()
        evaluadas = int(len(valores))
        if evaluadas == 0:
            continue
        cumplen = int(valores.isin(claves_validas).sum())
        tasa = cumplen / evaluadas
        filas.append({
            "dataset": f"{origen}→{destino}",
            "campo": campo,
            "dimension": "consistencia_referencial",
            "regla": f"{campo} existe en {destino}.id",
            "evaluadas": evaluadas,
            "cumplen": cumplen,
            "tasa": round(tasa, 4),
            "estado": ESTADO_OK if cumplen == evaluadas else ESTADO_REVISAR,
        })
    return pd.DataFrame(filas, columns=COLUMNAS_RESULTADO)


def evaluar_reconciliacion_factura_detalle(data: Dict[str, pd.DataFrame],
                                           tolerancia: float = 0.01
                                           ) -> pd.DataFrame:
    """Regla de reconciliacion: SUM(detalle.subtotal) ≈ factura.total.

    Compara el total de cada factura con la suma de los subtotales de sus
    detalles. Una diferencia mayor a ``tolerancia`` (fracción del total)
    se marca como revisar.
    """
    if "facturas" not in data or "factura_detalle" not in data:
        return pd.DataFrame(columns=COLUMNAS_RESULTADO)

    df_facturas = data["facturas"]
    df_detalle = data["factura_detalle"]

    if "id" not in df_facturas.columns or "total" not in df_facturas.columns:
        return pd.DataFrame(columns=COLUMNAS_RESULTADO)
    if "factura_id" not in df_detalle.columns or "subtotal" not in df_detalle.columns:
        return pd.DataFrame(columns=COLUMNAS_RESULTADO)

    # Agrupar detalles por factura
    detalle_agrupado = df_detalle.groupby("factura_id")["subtotal"].sum()
    detalle_agrupado = detalle_agrupado.rename("subtotal_total")

    # Unir con facturas
    merged = df_facturas[["id", "total"]].merge(
        detalle_agrupado, left_on="id", right_index=True, how="left"
    )
    merged["subtotal_total"] = merged["subtotal_total"].fillna(0)

    # Calcular diferencia relativa
    merged["diferencia_relativa"] = (
        abs(merged["total"] - merged["subtotal_total"]) /
        merged["total"].abs().replace(0, pd.NA)
    ).fillna(1.0)

    filas: List[Dict] = []
    total_filas = len(merged)
    cumplen = int((merged["diferencia_relativa"] <= tolerancia).sum())

    filas.append({
        "dataset": "facturas↔factura_detalle",
        "campo": "total",
        "dimension": "consistencia_referencial",
        "regla": "SUM(detalle.subtotal) ≈ factura.total",
        "evaluadas": total_filas,
        "cumplen": cumplen,
        "tasa": round(cumplen / total_filas, 4) if total_filas else 0.0,
        "estado": ESTADO_OK if cumplen == total_filas else ESTADO_REVISAR,
    })
    return pd.DataFrame(filas, columns=COLUMNAS_RESULTADO)


def evaluar_conjunto(data: Dict[str, pd.DataFrame],
                     reglas: Optional[List[Regla]] = None) -> pd.DataFrame:
    """Evalua todas las reglas sobre todos los datasets cargados."""
    trozos = [evaluar_dataset(nombre, df, reglas)
              for nombre, df in (data or {}).items()
              if df is not None]
    # Consistencia referencial entre datasets (claves foraneas)
    try:
        trozos.append(evaluar_consistencia_referencial(data))
    except Exception as e:  # noqa: BLE001 — se reporta, no se traga
        log.warning("Fallo la evaluacion de consistencia referencial: %s", e)
    # Reconciliacion factura ↔ detalle
    try:
        trozos.append(evaluar_reconciliacion_factura_detalle(data))
    except Exception as e:  # noqa: BLE001 — se reporta, no se traga
        log.warning("Fallo la evaluacion de reconciliacion factura-detalle: %s", e)
    trozos = [t for t in trozos if not t.empty]
    if not trozos:
        return pd.DataFrame(columns=COLUMNAS_RESULTADO)
    return pd.concat(trozos, ignore_index=True)
