"""Construye contexto grounded para el asesor de negocio con IA.

Solo envía agregados, nunca listados completos de facturas con todos los campos.
Siempre filtrado por workspace (el llamado pasa cfg + data ya cargados).
"""
from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from src import aplicacion
from src.agentes_estrategicos.analyst import analizar_datos_negocio
from src.data_loader import enriquecer_facturas


def _safe_float(v: Any) -> float:
    try:
        if v is None:
            return 0.0
        # pandas/numpy
        import numpy as _np

        if isinstance(v, _np.generic):
            v = v.item()
        return float(v)
    except Exception:
        return 0.0


def _safe_int(v: Any) -> int:
    try:
        if v is None:
            return 0
        import numpy as _np

        if isinstance(v, _np.generic):
            v = v.item()
        return int(v)
    except Exception:
        return 0


def construir_contexto_asesor(cfg: Any, data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """Construye un contexto minimalista y grounded con solo agregados."""
    ws = getattr(cfg, "clave", "principal")
    negocio = getattr(cfg, "negocio_nombre", "Mi Negocio")
    moneda = getattr(cfg, "moneda", "MXN")

    # Reutilizamos el pipeline de agentes estratégicos para obtener KPIs/alertas/RFM
    analisis = analizar_datos_negocio(data, cfg=cfg)

    kpis = analisis.get("kpis") or {}
    salud = analisis.get("salud_cartera") or {}
    alertas = analisis.get("alertas") or []
    resumen_alertas = analisis.get("resumen_alertas") or {}
    rfm = analisis.get("rfm")
    serie_ingresos = analisis.get("serie_ingresos")

    # Top clientes (agregado, sin datos sensibles completos)
    top_clientes = []
    try:
        if isinstance(rfm, pd.DataFrame) and not rfm.empty:
            df = rfm.copy()
            if "cliente_id" in df.columns and "ingreso_total" in df.columns:
                df = df.sort_values("ingreso_total", ascending=False).head(10)
                for _, row in df.iterrows():
                    top_clientes.append(
                        {
                            "cliente_id": _safe_int(row.get("cliente_id")),
                            "segmento": str(row.get("segmento", "")),
                            "frecuencia": _safe_int(row.get("frecuencia")),
                            "recencia_dias": _safe_int(row.get("recencia_dias")),
                            "ingreso_total": round(_safe_float(row.get("ingreso_total")), 2),
                            "ticket_promedio": round(_safe_float(row.get("ticket_promedio")), 2),
                        }
                    )
    except Exception:
        top_clientes = []

    # Evolución mensual (agregados)
    evolucion_mensual = []
    try:
        if isinstance(serie_ingresos, pd.DataFrame) and not serie_ingresos.empty:
            # Tomar últimos 12 meses como mucho
            df = serie_ingresos.tail(12).copy()
            for _, row in df.iterrows():
                evolucion_mensual.append(
                    {
                        "anio_mes": str(row.get("anio_mes") or row.get("mes") or ""),
                        "ingresos": round(_safe_float(row.get("ingresos")), 2),
                        "facturas": _safe_int(row.get("facturas")),
                        "ticket_promedio": round(_safe_float(row.get("ticket_promedio")), 2),
                    }
                )
    except Exception:
        evolucion_mensual = []

    # Inventario crítico (solo conteo/agregados)
    inventario_critico = []
    try:
        inv = data.get("inventario")
        if isinstance(inv, pd.DataFrame) and not inv.empty:
            df = inv.copy()
            cols = set(df.columns)
            if {"stock_actual", "stock_minimo"}.issubset(cols):
                df["stock_actual"] = pd.to_numeric(df["stock_actual"], errors="coerce")
                df["stock_minimo"] = pd.to_numeric(df["stock_minimo"], errors="coerce")
                crit = df[df["stock_actual"] <= df["stock_minimo"]].copy()
                if not crit.empty:
                    crit["precio_costo"] = pd.to_numeric(crit.get("precio_costo", 0), errors="coerce")
                    crit["cantidad_recomendada"] = (crit["stock_minimo"] - crit["stock_actual"]).clip(lower=0)
                    for _, row in crit.head(15).iterrows():
                        inventario_critico.append(
                            {
                                "producto_id": str(row.get("producto_id") or row.get("id") or ""),
                                "nombre": str(row.get("nombre") or row.get("producto") or ""),
                                "stock_actual": _safe_float(row.get("stock_actual")),
                                "stock_minimo": _safe_float(row.get("stock_minimo")),
                                "cantidad_recomendada": _safe_float(row.get("cantidad_recomendada")),
                            }
                        )
    except Exception:
        inventario_critico = []

    # Hechos enriquecidos (opcional para contexto rápido)
    hechos_resumen = {}
    try:
        hechos = enriquecer_facturas(data)
        if isinstance(hechos, pd.DataFrame) and not hechos.empty:
            hechos_resumen = {
                "filas": int(len(hechos)),
                "clientes_unicos": _safe_int(hechos["cliente_id"].nunique()) if "cliente_id" in hechos.columns else 0,
                "vehiculos_unicos": _safe_int(hechos["vehiculo_id"].nunique()) if "vehiculo_id" in hechos.columns else 0,
            }
    except Exception:
        hechos_resumen = {}

    # Alertas resumidas (solo lo necesario)
    alertas_resumidas = []
    try:
        for a in alertas[:10]:
            if isinstance(a, dict):
                alertas_resumidas.append(
                    {
                        "tipo": a.get("tipo"),
                        "severidad": a.get("severidad"),
                        "titulo": a.get("titulo"),
                        "detalle": a.get("detalle"),
                    }
                )
    except Exception:
        alertas_resumidas = []

    return {
        "workspace": ws,
        "negocio_nombre": negocio,
        "moneda": moneda,
        "kpis": kpis,
        "salud_cartera": salud,
        "alertas": alertas_resumidas,
        "resumen_alertas": resumen_alertas,
        "top_clientes": top_clientes,
        "evolucion_mensual": evolucion_mensual,
        "inventario_critico": inventario_critico,
        "hechos_resumen": hechos_resumen,
        "hecho_clave": analisis.get("hecho_clave") or {},
        "rfm_resumen": {
            "total": _safe_int(len(rfm)) if isinstance(rfm, pd.DataFrame) else 0,
        },
    }
