"""Pipeline de decisiones estratégicas.

Orquesta a los cuatro agentes en secuencia:

    1. Analyst Agent      - analiza los datos y extrae KPIs, hechos y anomalías.
    2. Strategy Agent     - construye el dossier de decisión con escenarios.
    3. Governance Agent   - valida que las recomendaciones no contradigan reglas.
    4. Report Agent       - genera el reporte ejecutivo HTML white-label.

Cada agente recibe el resultado del anterior y devuelve un diccionario
estructurado. Ninguno importa streamlit, duckdb ni fastapi.
"""
from __future__ import annotations

from typing import Any, Dict

from .analyst import analizar_datos_negocio
from .strategy import generar_dossier_de_decision
from .governance import validar_recomendaciones
from .report import generar_reporte_ejecutivo


def ejecutar_pipeline_de_decisiones(
    data: dict,
    cfg: Any,
    analyzer_result: Dict | None = None,
) -> Dict[str, Any]:
    """Ejecuta el pipeline completo de agentes de decisión.

    Argumentos:
        data: diccionario de DataFrames (facturas, clientes, vehículos, ...)
              tal como lo devuelve load_all() del pipeline ETL.
        cfg: configuración del workspace activo (AppConfig).
        analyzer_result: resultado opcional de un análisis previo. Si no se
            pasa, se ejecuta el Analyst Agent sobre data.

    Devuelve:
        Diccionario con las claves:
            - analisis: resultado del Analyst Agent.
            - dossier: resultado del Strategy Agent.
            - validacion: resultado del Governance Agent.
            - reporte: resultado del Report Agent (ruta del HTML generado).
            - resumen_ejecutivo: texto listo para mostrar al dueño.

    Nunca traga excepciones. Si un agente falla, la excepción sube con
    contexto claro para que el adaptador de entrada (UI o CLI) la muestre.
    """
    # 1. Analyst Agent: entender qué pasó en los datos.
    analisis = analizar_datos_negocio(data, cfg=cfg)
    if analyzer_result is not None:
        analisis["resultado_externo"] = analyzer_result

    # 2. Strategy Agent: construir el dossier de decisión.
    dossier = generar_dossier_de_decision(analisis, cfg=cfg)

    # 3. Governance Agent: validar que no hay recomendaciones imposibles.
    validacion = validar_recomendaciones(dossier, data=data, cfg=cfg)

    # 4. Report Agent: generar el reporte ejecutivo HTML.
    reporte = generar_reporte_ejecutivo(
        analisis=analisis,
        dossier=dossier,
        validacion=validacion,
        cfg=cfg,
    )

    # Resumen ejecutivo listo para mostrar en UI.
    resumen_ejecutivo = _construir_resumen_ejecutivo(
        analisis=analisis,
        dossier=dossier,
        validacion=validacion,
    )

    return {
        "analisis": analisis,
        "dossier": dossier,
        "validacion": validacion,
        "reporte": reporte,
        "resumen_ejecutivo": resumen_ejecutivo,
    }


def _construir_resumen_ejecutivo(
    analisis: Dict[str, Any],
    dossier: Dict[str, Any],
    validacion: Dict[str, Any],
) -> Dict[str, Any]:
    """Construye un resumen ejecutivo listo para renderizar en UI."""
    kpis = analisis.get("kpis", {})
    alertas = analisis.get("alertas", [])
    decisiones = dossier.get("decisiones", [])

    n_criticas = sum(1 for a in alertas if a.get("severidad") == "critica")
    n_media = sum(1 for a in alertas if a.get("severidad") == "media")
    n_actuar = sum(1 for d in decisiones if d.get("accion") == "actuar")
    n_revisar = sum(1 for d in decisiones if d.get("accion") == "revisar")

    if n_actuar > 0:
        estado_global = "actuar"
        mensaje_principal = (
            f"Hay {n_actuar} decisión{'s' if n_actuar != 1 else ''} "
            "que requiere tu atención inmediata."
        )
    elif n_criticas > 0:
        estado_global = "revisar"
        mensaje_principal = (
            f"Hay {n_criticas} alerta{'s' if n_criticas != 1 else ''} crítica. "
            "Revisa antes de tomar decisiones de gasto."
        )
    elif n_media > 0 or n_revisar > 0:
        estado_global = "revisar"
        mensaje_principal = "Todo va bien, pero hay puntos que vale la pena revisar."
    else:
        estado_global = "ok"
        mensaje_principal = "Todo va bien. Sigue monitoreando semanalmente."

    return {
        "estado_global": estado_global,
        "mensaje_principal": mensaje_principal,
        "kpis_principales": {
            k: v for k, v in kpis.items()
            if k in ("total_ingresos", "ticket_promedio", "clientes_activos")
        },
        "n_alertas_criticas": n_criticas,
        "n_alertas_medias": n_media,
        "n_decisiones_actuar": n_actuar,
        "n_decisiones_revisar": n_revisar,
    }
