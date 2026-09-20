"""Tabla de hechos relacional: descompone los detalles de cada factura en filas.

El esquema legacy guarda los servicios como un string concatenado en
``facturas.detalles`` con el formato ``id_servicio:cantidad:subtotal;...``.
Este modulo lo transforma en una tabla de hechos granular (una fila por
servicio vendido) lista para SQL, inventario real y motores de accion.

Columnas de salida: factura_id, fecha, cliente_id, vehiculo_id, servicio_id,
servicio, cantidad, subtotal.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


def construir_factura_detalle(
    facturas: pd.DataFrame,
    servicios: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Devuelve la tabla de hechos ``factura_detalle`` (una fila por servicio).

    Si ``servicios`` incluye ``id``/``nombre``, se agrega el nombre de cada
    servicio. Robustez: tolera filas vacias, sin ``:`` y tipos inconsistentes.
    """
    if facturas is None or facturas.empty or "detalles" not in facturas.columns:
        return pd.DataFrame()

    f = facturas.copy()
    f["fecha"] = pd.to_datetime(f["fecha"], errors="coerce")

    # Explode el texto concatenado en una fila por detalle
    f["_det"] = f["detalles"].fillna("").astype(str).str.split(";")
    largo = f.explode("_det").reset_index(drop=True)
    largo = largo[largo["_det"].str.strip().ne("")]
    if largo.empty:
        return pd.DataFrame()

    parts = largo["_det"].str.split(":", n=2, expand=True)
    largo["servicio_id"] = pd.to_numeric(parts[0], errors="coerce")
    if parts.shape[1] > 1:
        largo["cantidad"] = pd.to_numeric(parts[1], errors="coerce")
    else:
        largo["cantidad"] = 1
    if parts.shape[1] > 2:
        largo["subtotal"] = pd.to_numeric(parts[2], errors="coerce")
    else:
        largo["subtotal"] = None

    # Nombre real de la columna de id de factura (segun el mapeo normalizado)
    col_id_factura = "factura_id" if "factura_id" in largo.columns else \
                     ("id" if "id" in largo.columns else None)
    if col_id_factura:
        largo["factura_id"] = largo[col_id_factura]

    columnas = ["factura_id", "fecha", "cliente_id", "vehiculo_id",
                "servicio_id", "cantidad", "subtotal"]
    columnas = [c for c in columnas if c in largo.columns]
    hechos = largo[columnas].copy()
    # Clave sustituta: un servicio puede repetirse en la misma factura.
    hechos = hechos.reset_index(drop=True)
    hechos["id"] = range(1, len(hechos) + 1)

    # Subtotal faltante: estimar con el precio base del catalogo
    if "subtotal" not in hechos.columns or hechos["subtotal"].isna().any():
        if servicios is not None and not servicios.empty:
            precios = servicios.set_index("id")["precio_base"].to_dict()
            hechos["subtotal"] = hechos["subtotal"].where(
                hechos["subtotal"].notna(),
                (hechos["servicio_id"].map(precios).fillna(0) * hechos["cantidad"]),
            )
    hechos["subtotal"] = hechos["subtotal"].fillna(0)
    hechos["cantidad"] = pd.to_numeric(hechos["cantidad"], errors="coerce").fillna(1)

    if servicios is not None and not servicios.empty and "id" in servicios.columns:
        nombres = servicios.set_index("id")["nombre"].to_dict()
        hechos["servicio"] = hechos["servicio_id"].map(nombres).fillna(
            hechos["servicio_id"].astype(str)
        )
    else:
        hechos["servicio"] = hechos["servicio_id"].astype(str)

    return hechos


def demanda_producto_categoria(
    hechos: pd.DataFrame,
    mapeo_servicio_categoria: Optional[dict] = None,
    horizonte_meses: int = 3,
    hoy: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Demanda mensual real por categoria, derivada de los servicios vendidos.

    ``mapeo_servicio_categoria`` asocia palabras clave del servicio con la
    categoria de producto (p. ej. 'aceite' -> 'Aceites'). Devuelve el listado
    de servicios con su categoria y demanda mensual estimada.
    """
    if hechos is None or hechos.empty:
        return pd.DataFrame()
    mapeo = mapeo_servicio_categoria or {}
    nombre_servicio = hechos["servicio"].astype(str).str.lower().fillna("")
    hechos = hechos.copy()

    def _categoria(serv):
        nombre = str(serv).lower()
        for clave, categoria in mapeo.items():
            if clave and clave.lower() in nombre:
                return categoria
        return None

    categoria = nombre_servicio.map(_categoria)
    if categoria.notna().any():
        hechos = hechos[categoria.notna()]
        hechos["categoria"] = categoria
    else:
        return pd.DataFrame()

    # Referencia temporal: la fecha maxima de los datos (no "hoy"), para que
    # la demanda del ultimo horizonte sea significativa aunque los datos no
    # lleguen hasta la fecha actual.
    if hoy is None:
        fechas = pd.to_datetime(hechos["fecha"], errors="coerce").dropna()
        hoy = pd.Timestamp(fechas.max()) if not fechas.empty else pd.Timestamp.today()
    hoy = pd.Timestamp(hoy)
    inicio = hoy - pd.DateOffset(months=horizonte_meses)
    recientes = hechos[hechos["fecha"] >= inicio]

    agrupado = recientes.groupby("categoria", as_index=False).agg(
        servicios_vendidos=("cantidad", "sum"),
        subtotal_categoria=("subtotal", "sum"),
    )
    agrupado["demanda_mensual"] = (
        agrupado["servicios_vendidos"] / max(horizonte_meses, 1)
    ).round(2)
    return agrupado