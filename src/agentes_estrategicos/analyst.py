"""Analyst Agent.

Analiza los datos cargados del almacén y extrae:
* KPIs globales (ingresos, facturas, ticket promedio, clientes, vehículos).
* Series de tiempo mensuales para detectar tendencias.
* Segmentación RFM para identificar clientes en riesgo.
* Anomalías: caídas de ingresos, clientes perdidos, stock crítico.

Todo sobre datos ya cargados (dict de DataFrames). No importa streamlit,
duckdb ni fastapi. La lógica de negocio está en src/analyzer.py, src/negocio.py
y src/alerts.py; este agente las orquesta y las traduce a un formato plano
listo para el Strategy Agent.
"""
from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from src.analyzer import Analyzer
from src.alerts import evaluar_alertas, resumen_alertas
from src.negocio import salud_cartera


def analizar_datos_negocio(data: dict, cfg: Any = None) -> Dict[str, Any]:
    """Analiza los datos del negocio y devuelve un resumen estructurado.

    Argumentos:
        data: diccionario de DataFrames (facturas, clientes, vehículos,
              servicios, inventario, ...) tal como lo devuelve load_all().
        cfg: configuración del workspace activo (AppConfig). Se usa para
             obtener el umbral de churn y otros parámetros de negocio.

    Devuelve un diccionario con las claves:
        - kpis: métricas globales del negocio.
        - series: series de tiempo mensuales (ingresos, facturas).
        - rfm: segmentación de clientes.
        - alertas: lista de alertas activas evaluadas por el motor de reglas.
        - resumen_alertas: conteo por severidad.
        - salud_cartera: métricas de cartera (ARPU, churn, LTV, riesgo).
        - hecho_clave: el hallazgo más importante para el dueño.
    """
    # Construir el Analyzer sobre los datos ya cargados.
    analyzer = Analyzer(data)

    # KPIs globales.
    kpis = analyzer.kpis_globales()

    # Series de tiempo mensuales para detectar tendencias.
    serie_ingresos = analyzer.ingresos_por_mes()

    # Segmentación RFM para clientes en riesgo.
    rfm = analyzer.clientes_rfm()

    # Alertas de negocio evaluadas por el motor de reglas.
    try:
        predictor_temporal = None  # se evita crear Predictor aquí para no duplicar
        alertas = evaluar_alertas(cfg or {}, data, analyzer=analyzer)
    except Exception:
        alertas = []
    resumen_alertas_obj = resumen_alertas(alertas)

    # Salud de cartera (ARPU, churn, LTV, riesgo).
    salud = salud_cartera(analyzer)

    # Construir el "hecho clave": el hallazgo más importante para el dueño.
    hecho_clave = _construir_hecho_clave(kpis, salud, alertas, rfm)

    return {
        "kpis": kpis,
        "serie_ingresos": serie_ingresos,
        "rfm": rfm,
        "alertas": alertas,
        "resumen_alertas": resumen_alertas_obj,
        "salud_cartera": salud,
        "hecho_clave": hecho_clave,
    }


def _construir_hecho_clave(
    kpis: dict,
    salud: dict,
    alertas: list,
    rfm: pd.DataFrame,
) -> dict:
    """Determina el hallazgo más importante para el dueño del negocio."""
    total_ingresos = kpis.get("total_ingresos", 0)
    total_facturas = kpis.get("total_facturas", 0)

    # Contar alertas críticas.
    criticas = [a for a in alertas if a.get("severidad") == "critica"]

    # Clientes en riesgo del RFM.
    clientes_en_riesgo = 0
    if not rfm.empty and "segmento" in rfm.columns:
        segmentos_riesgo = {"En Riesgo", "Perdido"}
        riesgo = rfm[rfm["segmento"].isin(segmentos_riesgo)]
        clientes_en_riesgo = int(riesgo["cliente_id"].nunique())

    # Cartera en riesgo.
    monto_en_riesgo = salud.get("monto_en_riesgo", 0) if salud else 0

    if criticas:
        mas_critica = criticas[0]
        return {
            "tipo": "alerta_critica",
            "titulo": mas_critica.get("titulo", "Alerta crítica"),
            "detalle": mas_critica.get("detalle", ""),
            "severidad": "critica",
        }

    if monto_en_riesgo > 0:
        return {
            "tipo": "cartera_en_riesgo",
            "titulo": "Hay cartera en riesgo",
            "detalle": (
                f"Hay ${monto_en_riesgo:,.0f} de cartera en riesgo. "
                f"Considera contactar a esos clientes."
            ),
            "severidad": "media",
        }

    if clientes_en_riesgo > 0:
        return {
            "tipo": "clientes_en_riesgo",
            "titulo": f"{clientes_en_riesgo} clientes en riesgo",
            "detalle": (
                f"{clientes_en_riesgo} clientes no han visitado en más de 60 días. "
                "Considera enviarles una oferta de reactivación."
            ),
            "severidad": "media",
        }

    if total_facturas > 0 and total_ingresos > 0:
        return {
            "tipo": "todo_bien",
            "titulo": "Negocio estable",
            "detalle": (
                f"Tus ingresos son de ${total_ingresos:,.0f} con "
                f"{total_facturas} facturas. Todo bajo control."
            ),
            "severidad": "ok",
        }

    return {
        "tipo": "sin_datos",
        "titulo": "Sin datos suficientes",
        "detalle": "Importa tus facturas en 'Mis datos' para empezar a ver indicadores.",
        "severidad": "revisar",
    }


__all__ = ["analizar_datos_negocio"]
