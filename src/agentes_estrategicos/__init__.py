"""Agentes de decisiones estratégicas para GIRO.

Este módulo implementa un equipo de agentes que, a partir de los datos ya
cargados en el almacén de un workspace, entrega al dueño de la pyme los
indicadores y recomendaciones que necesita para tomar decisiones sobre su
negocio, sin requerir alfabetización analítica.

Arquitectura (pipeline multi-agente):

    datos -> Analyst Agent -> Insights Agent -> Strategy Agent ->
    Governance Agent -> Report Agent -> dossier de decisión

Cada agente es una función pura sobre datos ya cargados. Ninguno importa
streamlit, duckdb ni fastapi. El punto único de decisión de motor sigue
siendo get_store() en src.data_loader.

Reglas del repo respetadas:
- Aislamiento por workspace: cada agente recibe el cfg del workspace activo.
- Sin secretos en el código: todo por os.environ o argumentos.
- Cero efectos secundarios en import.
- SQL parametrizado si hay SQL.
- Python 3.11 compatible.
- Dependencias ya presentes: pandas, numpy, scikit-learn, plotly, jinja2.
"""
from __future__ import annotations

from .pipeline import ejecutar_pipeline_de_decisiones
from .analyst import analizar_datos_negocio
from .strategy import generar_dossier_de_decision
from .governance import validar_recomendaciones
from .report import generar_reporte_ejecutivo
from .data_engineer_tooling import (
    cargar_con_dlt,
    validar_con_daffy,
    crear_regla_calidad,
    validar_dataframe_con_contrato,
    ReglaCalidad,
    ResultadoCalidad,
)
# Importar agentes_base para que el registro de BaseAgent ocurra al cargar el paquete.
from . import agentes_base  # noqa: F401 — registro de agentes BaseAgent
from src.core.agente import (
    BaseAgent,
    ResultadoAgente,
    listar_agentes,
    obtener_agente,
)

__all__ = [
    "ejecutar_pipeline_de_decisiones",
    "analizar_datos_negocio",
    "generar_dossier_de_decision",
    "validar_recomendaciones",
    "generar_reporte_ejecutivo",
    "cargar_con_dlt",
    "validar_con_daffy",
    "crear_regla_calidad",
    "validar_dataframe_con_contrato",
    "ReglaCalidad",
    "ResultadoCalidad",
    # Arquitectura BaseAgent (nueva, compatible con la API existente).
    "listar_agentes",
    "obtener_agente",
    "ResultadoAgente",
]
