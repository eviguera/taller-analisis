"""Pagina: Clientes (RFM, top clientes, frecuencia y plan de accion)."""

import pandas as pd
import streamlit as st

from ui import components as c
from ui.context import obtener_estado


def principal():
    cfg, data, analyzer, predictor = obtener_estado()

    rfm = analyzer.clientes_rfm()
    if rfm.empty:
        c.vacio(
            "Datos insuficientes para el analisis de clientes.",
            icono=":material/groups:",
            detalle="Se necesitan facturas con clientes asociados.",
        )
        return

    total_clientes = len(rfm)
    gasto_total = rfm["monto"].sum()
    top_seg = rfm["segmento"].value_counts().idxmax() if total_clientes else "N/A"
    gasto_prom = gasto_total / max(total_clientes, 1)

    mensual = analyzer.df.groupby("anio_mes")["total"].sum().tail(8)
    tendencia_monto = mensual.tolist() if not mensual.empty else None

    c.cabecera(
        "Clientes",
        "Segmentacion RFM, valor economico y riesgo de abandono",
        icono=":material/groups:",
    )
    c.kpi_grid([
        ("Clientes", f"{total_clientes}", None, None, "Clientes en la base"),
        ("Gasto total", c.moneda(gasto_total, cfg.moneda), None, tendencia_monto,
         "Ingresos acumulados de clientes"),
        ("Segmento dominante", top_seg, None, None, "Segmento RFM mas comun"),
        ("Gasto promedio/cliente", c.moneda(gasto_prom, cfg.moneda), None, None,
         "Gasto total entre numero de clientes"),
    ])

    tab_seg, tab_top, tab_frec, tab_plan = st.tabs(
        ["Segmentacion RFM", "Top clientes", "Frecuencia de visitas", "Plan de accion"],
        key="tabs_clientes", on_change="rerun",
    )

    with tab_seg:
        if tab_seg.open:
            conteo = rfm["segmento"].value_counts().reset_index()
            conteo.columns = ["Segmento", "Cantidad"]
            col1, col2 = st.columns([1, 1.4], vertical_alignment="center")
            with col1:
                with c.panel("Distribucion de segmentos", "Concentracion por perfil"):
                    st.plotly_chart(c.grafico_pastel(conteo, "Segmento", "Cantidad"),
                                    width="stretch", height="stretch")
            with col2:
                with c.panel("Mapa RFM", "Frecuencia vs gasto por cliente"):
                    st.plotly_chart(c.grafico_dispersion(
                        rfm, "frecuencia", "monto", color="segmento", hover=["nombre"], log_y=True,
                    ), width="stretch", height="stretch")

            st.markdown("**Detalle RFM**")
            st.dataframe(
                rfm[["nombre", "recencia_dias", "frecuencia", "monto", "rfm_score", "segmento"]],
                width="stretch", height=320,
                column_config={
                    "monto": st.column_config.NumberColumn("Monto", format="$#,##0"),
                    "recencia_dias": st.column_config.NumberColumn("Recencia (dias)"),
                },
            )
            with st.expander("Que significan los segmentos?", icon=":material/help:"):
                st.markdown("""
| Segmento | Descripcion | Accion sugerida |
|---|---|---|
| Campeones | Mas frecuentes y de mayor valor | Programa de fidelidad y referidos |
| Alto Valor | Gastan mucho, visitan menos | Visitas personalizadas y ofertas exclusivas |
| Cliente Leal | Frecuentes pero gasto medio | Cross-selling de servicios |
| Activo | Visitas regulares | Mantener comunicacion |
| En Riesgo | Frecuencia en descenso | Recordatorios + descuentos de reactivacion |
| Perdido | Mucho tiempo sin venir | Campana de recuperacion agresiva |
| Promedio | Comportamiento estandar | Monitoreo |
""")

    with tab_top:
        if tab_top.open:
            top = analyzer.clientes_top(n=15)
            with c.panel("Top 15 por gasto", "Clientes de mayor valor economico",
                         icono=":material/leaderboard:"):
                st.plotly_chart(c.grafico_barras(
                    top, "nombre", "total_gastado", color="facturas", color_cont="Blues",
                    etiquetas={"nombre": "Cliente", "total_gastado": "Gasto total"},
                ), width="stretch", height="stretch")
            st.dataframe(
                top, width="stretch", height=320,
                column_config={
                    "total_gastado": st.column_config.NumberColumn("Gasto total", format="$#,##0"),
                    "facturas": st.column_config.NumberColumn("Facturas"),
                },
            )

    with tab_frec:
        if tab_frec.open:
            frec = analyzer.frecuencia_visitas_clientes()
            with c.panel("Clientes por numero de visitas", "Frecuencia de regreso",
                         icono=":material/repeat:"):
                st.plotly_chart(c.grafico_barras(
                    frec.head(15), "nombre", "facturas", color_cont="Purples",
                    etiquetas={"nombre": "Cliente", "facturas": "Visitas"},
                ), width="stretch", height="stretch")
            st.dataframe(frec, width="stretch", height=320)

    with tab_plan:
        if tab_plan.open:
            sugerencias = predictor.proxima_factura_demanda()
            if not sugerencias.empty:
                c.titulo_seccion("Clientes sugeridos para contacto",
                                 "Acciones recomendadas por recencia de visita",
                                 icono=":material/campaign:")
                st.dataframe(sugerencias, width="stretch", height=300)
            else:
                st.success("No hay campanas de reactivacion pendientes por ahora.")


if __name__ == "__main__":
    principal()