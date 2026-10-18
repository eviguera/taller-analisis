"""Indicadores de decisión para el dueño del negocio (CEO de su pyme).

Este módulo entrega, a partir de los datos ya cargados en el almacén, los
indicadores que un dueño de pyme necesita para decidir hoy:

* ¿Mis ingresos crecieron o cayeron este mes?
* ¿Qué clientes están en riesgo de irse?
* ¿Cuánto dinero tengo pendiente de cobrar?
* ¿Qué productos se me están acabando?
* ¿Cuánto voy a facturar el mes que viene?

Cada indicador viene con una recomendación de acción (Actuar / Revisar / Todo bien)
para que el dueño sepa qué hacer sin tener que interpretar gráficos complejos.

No importa streamlit, duckdb ni fastapi. Solo opera sobre datos ya cargados.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from ..aplicacion import VISTAS_PARA_EXPORTAR  # noqa: F401  (compat con tests)


# ------------------------------------------------------------------
#  Tipos de resultado
# ------------------------------------------------------------------

@dataclass
class Indicador:
    """Un indicador de decisión con su recomendación de acción.

    accion: "actuar" (requiere atención inmediata),
            "revisar" (merece atención pronto),
            "ok" (todo bien).
    """
    nombre: str
    valor: str
    accion: str  # "actuar" | "revisar" | "ok"
    detalle: str


@dataclass
class ResumenDecision:
    """Conjunto de indicadores listos para mostrar al dueño del negocio."""
    indicadores: list[Indicador]
    resumen_texto: str  # Texto legible para el dueño ("Tus ventas subieron...")


# ------------------------------------------------------------------
#  Helpers internos
# ------------------------------------------------------------------

def _seguro_numero(valor) -> float:
    """Convierte a float de forma segura; devuelve 0 si no se puede."""
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def _mes_anterior(fecha_maxima: pd.Timestamp) -> pd.Timestamp:
    """Devuelve el primer día del mes anterior al de fecha_maxima."""
    primero_del_mes = fecha_maxima.replace(day=1)
    return primero_del_mes - timedelta(days=1)


# ------------------------------------------------------------------
#  Indicadores individuales
# ------------------------------------------------------------------

def _ingresos_por_mes(df: pd.DataFrame) -> pd.Series:
    """Serie mensual de ingresos (fecha como Period, total como valor)."""
    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha"])
    if df.empty:
        return pd.Series(dtype=float)
    serie = df.groupby(df["fecha"].dt.to_period("M"))["total"].sum()
    return serie.sort_index()


def indicador_ingresos(df: pd.DataFrame) -> Indicador:
    """Comparación de ingresos del mes actual vs mes anterior."""
    serie = _ingresos_por_mes(df)
    if len(serie) < 2:
        return Indicador(
            nombre="Ingresos",
            valor="Sin datos suficientes",
            accion="revisar",
            detalle="Necesitas al menos 2 meses de facturas para comparar.",
        )
    mes_actual = float(serie.iloc[-1])
    mes_anterior = float(serie.iloc[-2])
    variacion = ((mes_actual - mes_anterior) / mes_anterior * 100) if mes_anterior > 0 else 0.0

    if variacion >= 5:
        accion = "ok"
        detalle = f"Tus ingresos subieron {variacion:.0f}% respecto al mes pasado. Sigue así."
    elif variacion <= -10:
        accion = "actuar"
        detalle = f"Tus ingresos cayeron {abs(variacion):.0f}% respecto al mes pasado. Revisa qué cambió."
    else:
        accion = "revisar"
        detalle = f"Tus ingresos están estables ({variacion:+.0f}% respecto al mes pasado)."

    return Indicador(
        nombre="Ingresos del mes",
        valor=f"{mes_actual:,.0f}",
        accion=accion,
        detalle=detalle,
    )


def indicador_clientes_en_riesgo(df: pd.DataFrame) -> Indicador:
    """Clientes que no han comprado en los últimos 60 días."""
    if df.empty or "cliente_id" not in df.columns or "fecha" not in df.columns:
        return Indicador(
            nombre="Clientes en riesgo",
            valor="0",
            accion="ok",
            detalle="Sin datos de clientes para evaluar.",
        )

    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha"])
    if df.empty:
        return Indicador(
            nombre="Clientes en riesgo",
            valor="0",
            accion="ok",
            detalle="Sin fechas válidas para evaluar.",
        )

    fecha_limite = df["fecha"].max() - timedelta(days=60)
    clientes_con_visita_reciente = (
        df[df["fecha"] >= fecha_limite]["cliente_id"].nunique()
    )
    clientes_totales = df["cliente_id"].nunique()
    en_riesgo = clientes_totales - clientes_con_visita_reciente

    if en_riesgo == 0:
        accion = "ok"
        detalle = "Todos tus clientes han visitado en los últimos 60 días."
    elif en_riesgo > clientes_totales * 0.3:
        accion = "actuar"
        detalle = f"{en_riesgo} de {clientes_totales} clientes no visitan hace más de 60 días. ¡Actúa rápido!"
    else:
        accion = "revisar"
        detalle = f"{en_riesgo} clientes no visitan hace más de 60 días. Considera contactarlos."

    return Indicador(
        nombre="Clientes en riesgo",
        valor=str(en_riesgo),
        accion=accion,
        detalle=detalle,
    )


def indicador_facturas_pendientes(df: pd.DataFrame) -> Indicador:
    """Facturas con estado 'Pendiente' y antigüedad > 60 días."""
    if df.empty or "estado" not in df.columns or "fecha" not in df.columns:
        return Indicador(
            nombre="Facturas pendientes",
            valor="0",
            accion="ok",
            detalle="Sin datos de facturas para evaluar.",
        )

    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha"])
    if df.empty:
        return Indicador(
            nombre="Facturas pendientes",
            valor="0",
            accion="ok",
            detalle="Sin fechas válidas para evaluar.",
        )

    pendientes = df[df["estado"] == "Pendiente"].copy()
    if pendientes.empty:
        return Indicador(
            nombre="Facturas pendientes",
            valor="0",
            accion="ok",
            detalle="No tienes facturas pendientes.",
        )

    pendientes["dias"] = (pd.Timestamp.today() - pendientes["fecha"]).dt.days
    vencidas = pendientes[pendientes["dias"] > 60]
    monto_vencido = _seguro_numero(vencidas["total"].sum())

    if len(vencidas) == 0:
        accion = "ok"
        detalle = "Todas tus facturas pendientes están al día."
    elif len(vencidas) > 10 or monto_vencido > 1_000_000:
        accion = "actuar"
        detalle = f"{len(vencidas)} facturas vencidas por ${monto_vencido:,.0f}. Cobrar urgente."
    else:
        accion = "revisar"
        detalle = f"{len(vencidas)} facturas pendientes con más de 60 días."

    return Indicador(
        nombre="Facturas pendientes",
        valor=str(len(vencidas)),
        accion=accion,
        detalle=detalle,
    )


def indicador_stock_bajo(df_inventario: pd.DataFrame) -> Indicador:
    """Productos con stock por debajo del mínimo."""
    if df_inventario is None or df_inventario.empty:
        return Indicador(
            nombre="Stock bajo",
            valor="0",
            accion="ok",
            detalle="Sin datos de inventario.",
        )

    columnas_necesarias = {"stock_actual", "stock_minimo"}
    if not columnas_necesarias.issubset(set(df_inventario.columns)):
        return Indicador(
            nombre="Stock bajo",
            valor="0",
            accion="revisar",
            detalle="Faltan columnas de stock en el inventario.",
        )

    inventario = df_inventario.copy()
    inventario["stock_actual"] = pd.to_numeric(inventario["stock_actual"], errors="coerce")
    inventario["stock_minimo"] = pd.to_numeric(inventario["stock_minimo"], errors="coerce")
    inventario = inventario.dropna(subset=["stock_actual", "stock_minimo"])

    bajo = inventario[inventario["stock_actual"] <= inventario["stock_minimo"]]
    n_bajo = len(bajo)

    if n_bajo == 0:
        accion = "ok"
        detalle = "Todos tus productos tienen stock suficiente."
    elif n_bajo > 5:
        accion = "actuar"
        detalle = f"{n_bajo} productos necesitan reabastecimiento urgente."
    else:
        accion = "revisar"
        detalle = f"{n_bajo} productos con stock bajo. Revisa cuáles pedir primero."

    return Indicador(
        nombre="Productos con stock bajo",
        valor=str(n_bajo),
        accion=accion,
        detalle=detalle,
    )


def indicador_ticket_promedio(df: pd.DataFrame) -> Indicador:
    """Ticket promedio y su tendencia."""
    if df.empty or "total" not in df.columns:
        return Indicador(
            nombre="Ticket promedio",
            valor="0",
            accion="revisar",
            detalle="Sin datos de facturación.",
        )

    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha", "total"])
    if df.empty:
        return Indicador(
            nombre="Ticket promedio",
            valor="0",
            accion="revisar",
            detalle="Sin datos válidos.",
        )

    ticket = _seguro_numero(df["total"].mean())
    por_mes = df.groupby(df["fecha"].dt.to_period("M"))["total"].mean().sort_index()
    if len(por_mes) >= 2:
        variacion = ((float(por_mes.iloc[-1]) - float(por_mes.iloc[-2])) / float(por_mes.iloc[-2]) * 100) if float(por_mes.iloc[-2]) > 0 else 0.0
        if variacion > 0:
            detalle = f"Tu ticket promedio subió {variacion:.0f}% este mes."
            accion = "ok"
        elif variacion < 0:
            detalle = f"Tu ticket promedio bajó {abs(variacion):.0f}% este mes."
            accion = "revisar"
        else:
            detalle = "Tu ticket promedio se mantuvo estable."
            accion = "ok"
    else:
        detalle = f"Promedio por factura basado en {len(df)} facturas."
        accion = "ok"

    return Indicador(
        nombre="Ticket promedio",
        valor=f"{ticket:,.0f}",
        accion=accion,
        detalle=detalle,
    )


# ------------------------------------------------------------------
#  Función principal
# ------------------------------------------------------------------

def indicadores_decision(data: dict) -> ResumenDecision:
    """Calcula todos los indicadores de decisión a partir de los datos cargados.

    data: diccionario de DataFrames tal como lo devuelve load_all() del pipeline.
    """
    facturas = data.get("facturas", pd.DataFrame())
    inventario = data.get("inventario", pd.DataFrame())

    indicadores = [
        indicador_ingresos(facturas),
        indicador_clientes_en_riesgo(facturas),
        indicador_facturas_pendientes(facturas),
        indicador_stock_bajo(inventario),
        indicador_ticket_promedio(facturas),
    ]

    # Contar cuántas requieren acción inmediata
    n_actuar = sum(1 for i in indicadores if i.accion == "actuar")
    n_revisar = sum(1 for i in indicadores if i.accion == "revisar")

    if n_actuar > 0:
        resumen_texto = (
            f"Tienes {n_actuar} área{'s' if n_actuar != 1 else ''} que requiere{'n' if n_actuar != 1 else ''} "
            f"tu atención inmediata. Prioriza lo que está en rojo."
        )
    elif n_revisar > 0:
        resumen_texto = (
            f"Todo va bien en general, pero hay {n_revisar} área{'s' if n_revisar != 1 else ''} "
            "que vale la pena revisar esta semana."
        )
    else:
        resumen_texto = "Todo va bien. Sigue monitoreando tus indicadores semanalmente."

    return ResumenDecision(
        indicadores=indicadores,
        resumen_texto=resumen_texto,
    )


__all__ = ["Indicador", "ResumenDecision", "indicadores_decision"]
