"""Simulador what-if (Fase 2): escenarios de 12 meses sobre datos reales.

Proyecta ingresos, clientes y EBITDA a partir de las métricas históricas del
workspace (ticket promedio, clientes activos, churn implícito y estacionalidad)
y parámetros de negocio editables por el usuario.
"""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from .core.config import VENTANA_MESES

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
         "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _df_comercial(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    if "estado" in d.columns:
        d = d[d["estado"] != "Cancelada"]
    return d


def base_datos(df: pd.DataFrame) -> dict:
    """Métricas base de los últimos 12 meses disponibles de facturas."""
    d = _df_comercial(df)
    if d.empty or "fecha" not in d.columns or "total" not in d.columns:
        return {}
    d["fecha"] = pd.to_datetime(d["fecha"], errors="coerce")
    d = d.dropna(subset=["fecha"])
    if d.empty:
        return {}
    fecha_max = d["fecha"].max()
    hist = d[d["fecha"] > fecha_max - pd.DateOffset(months=VENTANA_MESES)].copy()
    if hist.empty:
        hist = d.copy()

    clientes_activos = int(hist["cliente_id"].nunique()) if "cliente_id" in hist else max(1, len(hist))
    ingresos_12m = float(hist["total"].sum())
    ticket_promedio = float(hist["total"].mean()) if not hist.empty else 0.0

    per_mes = hist.groupby(hist["fecha"].dt.to_period("M"))["cliente_id"] \
        .nunique() if "cliente_id" in hist else hist.groupby(hist["fecha"].dt.to_period("M")).size()

    # Churn implicito: comparacion de retencion robusta (3 primeros vs 3
    # ultimos meses) y acotada a un rango de negocios realista.
    churn = 0.02
    if len(per_mes) >= 6:
        primera = float(per_mes.head(3).mean())
        ultima = float(per_mes.tail(3).mean())
        retencion = (ultima / primera) if primera > 0 else 1.0
    elif len(per_mes) >= 2:
        primera = float(per_mes.iloc[0])
        ultima = float(per_mes.iloc[-1])
        retencion = (ultima / primera) if primera > 0 else 1.0
    else:
        retencion = 1.0
    churn = max(0.005, min(0.12, 1 - retencion))

    return {
        "clientes_activos": clientes_activos,
        "ingresos_12m": ingresos_12m,
        "ticket_promedio": ticket_promedio,
        "churn_mensual_historico": round(churn, 4),
        "meses_muestra": int(hist.groupby(hist["fecha"].dt.to_period("M")).ngroups),
        "ultimo_mes": int(fecha_max.month),
        "fecha_max": fecha_max,
    }


def ratios_estacionales(df: pd.DataFrame) -> Optional[Dict[int, float]]:
    """Factor estacional por mes (ingresos del mes / promedio mensual)."""
    d = _df_comercial(df)
    if d.empty or "fecha" not in d.columns:
        return None
    d["fecha"] = pd.to_datetime(d["fecha"], errors="coerce")
    d = d.dropna(subset=["fecha"])
    if d.empty:
        return None
    por_mes = d.groupby(d["fecha"].dt.month)["total"].sum()
    if len(por_mes) < 3 or por_mes.mean() == 0:
        return None
    media = float(por_mes.mean())
    return {int(m): round(float(v) / media, 4) for m, v in por_mes.items()}


def proyectar(df: pd.DataFrame, meses: int = VENTANA_MESES,
              crecimiento_anual: float = 0.10,
              ticket_crecimiento: float = 0.04,
              churn_mensual: Optional[float] = None,
              efecto_giro_nba: float = 0.0,
              margen_bruto: float = 0.35,
              gasto_fijo_mensual: Optional[float] = None,
              ratios: Optional[Dict[int, float]] = None) -> dict:
    """Proyecta mes a mes el escenario y devuelve proyeccion + totales."""
    base = base_datos(df)
    if not base:
        return {}

    churn = base["churn_mensual_historico"] if churn_mensual is None else churn_mensual
    churn = max(0.0, churn * (1 - efecto_giro_nba))

    clientes = float(base["clientes_activos"])
    ticket = float(base["ticket_promedio"]) or 1.0

    if gasto_fijo_mensual is None:
        gasto_fijo_mensual = (base["ingresos_12m"] / max(12, base["meses_muestra"] or 1)) * 0.60

    fecha_base = base["fecha_max"]
    filas = []
    for i in range(1, meses + 1):
        clientes = clientes * (1 + crecimiento_anual / 12.0) * (1 - churn)
        ticket = ticket * (1 + ticket_crecimiento / 12.0)
        mes_abs = (base["ultimo_mes"] - 1 + i) % 12 + 1
        estacional = ratios.get(mes_abs, 1.0) if ratios else 1.0
        ingresos = clientes * ticket * estacional
        costo_variable = ingresos * (1 - margen_bruto)
        ebitda = ingresos - costo_variable - gasto_fijo_mensual

        fecha = fecha_base + pd.DateOffset(months=i)
        filas.append({
            "mes": i,
            "fecha": fecha.strftime("%Y-%m"),
            "mes_nombre": MESES[mes_abs - 1],
            "clientes": round(clientes, 1),
            "ticket": round(ticket, 2),
            "ingresos": round(ingresos, 2),
            "costo_variable": round(costo_variable, 2),
            "gasto_fijo": round(gasto_fijo_mensual, 2),
            "ebitda": round(ebitda, 2),
        })

    proy = pd.DataFrame(filas)
    return {
        "base": base,
        "proyeccion": proy,
        "totales": {
            "ingresos": float(proy["ingresos"].sum()),
            "ebitda": float(proy["ebitda"].sum()),
            "clientes_finales": round(float(proy["clientes"].iloc[-1]), 0),
            "ticket_final": round(float(proy["ticket"].iloc[-1]), 2),
            "margen_ebitda": float(proy["ebitda"].sum()) / float(proy["ingresos"].sum())
            if proy["ingresos"].sum() > 0 else 0.0,
        },
        "parametros": {
            "crecimiento_anual": crecimiento_anual,
            "ticket_crecimiento": ticket_crecimiento,
            "churn_mensual": round(churn, 4),
            "efecto_giro_nba": efecto_giro_nba,
            "margen_bruto": margen_bruto,
            "gasto_fijo_mensual": gasto_fijo_mensual,
        },
    }


PRESETS = {
    "Conservador": {"crecimiento_anual": 0.03, "ticket_crecimiento": 0.01,
                    "churn_ajuste": 1.0, "efecto_giro_nba": 0.0},
    "Base (igual que hoy)": {"crecimiento_anual": 0.08, "ticket_crecimiento": 0.03,
                             "churn_ajuste": 1.0, "efecto_giro_nba": 0.15},
    "Agresivo (+ Giro Recomienda)": {"crecimiento_anual": 0.20, "ticket_crecimiento": 0.06,
                                     "churn_ajuste": 0.7, "efecto_giro_nba": 0.40},
}


def aplicar_preset(base_churn: float, clave_preset: str) -> dict:
    """Convierte un preset en parámetros numéricos concretos."""
    p = PRESETS.get(clave_preset, PRESETS["Base (igual que hoy)"])
    churn = round(base_churn * p["churn_ajuste"], 4)
    return {
        "crecimiento_anual": p["crecimiento_anual"],
        "ticket_crecimiento": p["ticket_crecimiento"],
        "churn_mensual": churn,
        "efecto_giro_nba": p["efecto_giro_nba"],
        "preset": clave_preset,
    }