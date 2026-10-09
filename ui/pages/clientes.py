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
            "Todavia no hay facturas con clientes para analizar.",
            icono=":material/groups:",
            detalle="El analisis necesita facturas con un cliente asociado.",
            cta="Importa tus facturas en la pagina 'Mis datos'",
        )
        return

    total_clientes = len(rfm)
    gasto_total = rfm["monto"].sum()
    top_seg = rfm["segmento"].value_counts().idxmax() if total_clientes else "N/A"
    gasto_prom = gasto_total / max(total_clientes, 1)

    # La tendencia del KPI debe medir lo mismo que el KPI: solo facturas con
    # cliente (el RFM agrupa por cliente y excluye las que no tienen).
    con_cliente = analyzer.df.dropna(subset=["cliente_id", "nombre"])
    mensual = con_cliente.groupby("anio_mes")["total"].sum().tail(8)
    tendencia_monto = mensual.tolist() if not mensual.empty else None

    c.cabecera(
        "Clientes",
        "Segmentacion RFM, valor economico y riesgo de abandono",
        icono=":material/groups:",
    )
    c.kpi_grid([
        ("Clientes", c.miles(total_clientes), None, None, "Clientes en la base"),
        ("Gasto total", c.moneda(gasto_total, cfg.moneda), None, tendencia_monto,
         "Gasto acumulado de todos los clientes"),
        ("Gasto promedio por cliente", c.moneda(gasto_prom, cfg.moneda), None, None,
         "Promedio de gasto por cliente"),
        ("Segmento dominante", top_seg, None, None, "Segmento RFM mas comun"),
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
                    c.mostrar_grafico(c.grafico_pastel(conteo, "Segmento", "Cantidad"),
                                    width="stretch", height="stretch")
            with col2:
                with c.panel("Mapa RFM", "Frecuencia vs gasto por cliente"):
                    c.mostrar_grafico(c.grafico_dispersion(
                        rfm, "frecuencia", "monto", color="segmento", hover=["nombre"], log_y=True,
                    ), width="stretch", height="stretch")

            with c.panel("Detalle RFM", "Cliente, recencia, visitas, gasto y segmento"):
                st.dataframe(
                    rfm[["nombre", "recencia_dias", "frecuencia", "monto", "rfm_score", "segmento"]],
                    width="stretch", height=320,
                    column_config={
                        "nombre": "Cliente",
                        "recencia_dias": st.column_config.NumberColumn("Recencia (dias)"),
                        "frecuencia": st.column_config.NumberColumn("Visitas"),
                        "monto": st.column_config.NumberColumn("Monto", format=c.formato_moneda(cfg.moneda)),
                        "rfm_score": st.column_config.NumberColumn("Puntaje RFM"),
                        "segmento": "Segmento",
                    },
                )
            with st.expander("Que significan los segmentos?", icon=":material/help:"):
                st.markdown("""
| Segmento | Descripcion | Accion sugerida |
|---|---|---|
| Campeones | Mas frecuentes y de mayor valor | Programa de fidelidad y referidos |
| Alto Valor | Gastan mucho, visitan menos | Visitas personalizadas y ofertas exclusivas |
| Cliente Leal | Frecuentes pero gasto medio | Venta cruzada de servicios |
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
                c.mostrar_grafico(c.grafico_barras(
                    top, "nombre", "total_gastado", color="facturas", color_cont="Blues",
                    etiquetas={"nombre": "Cliente", "total_gastado": "Gasto total"},
                ), width="stretch", height="stretch")
                st.dataframe(
                    top, width="stretch", height=320,
                    column_config={
                        "cliente_id": "ID cliente",
                        "nombre": "Cliente",
                        "facturas": st.column_config.NumberColumn("Facturas"),
                        "total_gastado": st.column_config.NumberColumn("Gasto total", format=c.formato_moneda(cfg.moneda)),
                        "ultima_visita": "Ultima visita",
                    },
                )

    with tab_frec:
        if tab_frec.open:
            frec = analyzer.frecuencia_visitas_clientes()
            with c.panel("Clientes por numero de visitas", "Frecuencia de regreso",
                         icono=":material/repeat:"):
                c.mostrar_grafico(c.grafico_barras(
                    frec.head(15), "nombre", "facturas", color_cont="Purples",
                    etiquetas={"nombre": "Cliente", "facturas": "Visitas"},
                ), width="stretch", height="stretch")
                st.dataframe(
                    frec, width="stretch", height=320,
                    column_config={
                        "nombre": "Cliente",
                        "facturas": st.column_config.NumberColumn("Visitas"),
                        "promedio_dias_entre_visitas": st.column_config.NumberColumn(
                            "Dias entre visitas (promedio)", format="%.1f"),
                    },
                )

    with tab_plan:
        if tab_plan.open:
            sugerencias = predictor.proxima_factura_demanda()
            if not sugerencias.empty:
                with c.panel("Clientes sugeridos para contacto",
                             "Acciones recomendadas por recencia de visita",
                             icono=":material/campaign:"):
                    st.dataframe(
                        sugerencias, width="stretch", height=300,
                        column_config={
                            "cliente": "Cliente",
                            "dias_sin_visita": st.column_config.NumberColumn("Dias sin visita"),
                            "sugerencia": "Sugerencia",
                        },
                    )
            else:
                st.success("No hay campanas de reactivacion pendientes por ahora.")


if __name__ == "__main__":
    principal()