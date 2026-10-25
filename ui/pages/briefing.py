"""Pagina: Briefing ejecutivo narrativo.

Resumen en lenguaje natural de lo que esta pasando en el negocio:
llamada principal, hoy, que cambio, que necesita atencion y que esta en
riesgo. Plantillas determinísticas (sin costo de LLM).
"""

import streamlit as st

from ui import components as c
from ui.context import en_kiosco, obtener_estado
from src.alertas_avanzadas import evaluar_alertas_avanzadas, resumen_alertas_avanzadas
from src.analyzer import Analyzer
from src.briefing import generar_briefing
from src.negocio import salud_cartera


def principal():
    c.cabecera(
        "Briefing ejecutivo",
        "Que esta pasando en tu negocio, en lenguaje natural",
        icono=":material/summarize:",
    )

    try:
        cfg, data, analyzer, _predictor = obtener_estado()
    except Exception as e:
        c.mensaje_error(
            "No se pudieron cargar los datos del briefing.",
            detalle=str(e) if str(e) else "Revisa que el almacén del workspace esté disponible.",
        )
        return

    try:
        kpis = analyzer.kpis_globales()
        salud = salud_cartera(analyzer)
        alertas = evaluar_alertas_avanzadas(cfg, data)
        resumen_alertas = resumen_alertas_avanzadas(alertas)
    except Exception as e:  # noqa: BLE001
        c.mensaje_error(
            "No se pudieron calcular los indicadores del briefing.",
            detalle=str(e) if str(e) else "Revisa que existan datos de facturación.",
        )
        return

    # ---- Resumen de alertas como KPIs ----
    c.kpi_grid([
        ("Alertas activas", c.miles(resumen_alertas["total"]),
         None, None, "Todas las reglas disparadas"),
        ("Criticas", c.miles(resumen_alertas["critica"]),
         None, None, "Requieren acción inmediata"),
        ("Medias", c.miles(resumen_alertas["media"]),
         None, None, "Requieren seguimiento"),
    ])

    # ---- Briefing narrativo ----
    st.markdown("## Lectura ejecutiva")
    try:
        texto = generar_briefing(data, kpis, alertas, salud, cfg)
    except Exception as e:  # noqa: BLE001
        c.mensaje_error(
            "No se pudo generar el briefing narrativo.",
            detalle=str(e) if str(e) else "",
        )
        return

    st.markdown(texto)

    # ---- Detalle de alertas activas ----
    st.markdown("## Detalle de alertas")
    if not alertas:
        st.success("Sin alertas activas en este momento.", icon=":material/verified:")
    else:
        for a in alertas:
            with st.container(border=True):
                c.html(
                    f"{c.badge(a['severidad'].upper(), _severidad_color(a['severidad']))} "
                    f"**{a['titulo']}**"
                )
                st.caption(a["detalle"])

    if en_kiosco():
        st.info("Modo presentación: solo lectura.")


def _severidad_color(sev: str) -> str:
    return {"critica": "rojo", "media": "amarillo", "baja": "azul"}.get(sev, "info")


if __name__ == "__main__":
    principal()
