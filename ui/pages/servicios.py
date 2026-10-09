"""Pagina: Servicios (mas solicitados, ingresos por servicio y series de tiempo)."""

import pandas as pd
import streamlit as st

from ui import components as c
from ui.context import obtener_estado


def principal():
    cfg, data, analyzer, predictor = obtener_estado()

    servicios = data.get("servicios", pd.DataFrame())
    n_servicios = len(servicios)
    detalle = analyzer.detalle_servicios() if not data.get("facturas", pd.DataFrame()).empty else pd.DataFrame()

    if detalle.empty:
        c.vacio(
            "No hay detalle de servicios en las facturas.",
            icono=":material/build:",
            detalle="Revisa que tus facturas incluyan la columna 'detalles' con el formato servicio:cantidad:subtotal.",
            cta="Importa o procesa tus facturas en la pagina 'Mis datos'",
        )
        return

    ingreso_total_serv = detalle["subtotal"].sum()
    n_fact_serv = detalle["factura_id"].nunique()

    # La tendencia del KPI debe medir lo mismo que el KPI: ingresos de los
    # servicios detallados, no la facturacion total del mes.
    mensual = detalle.groupby(detalle["fecha"].dt.to_period("M"))["subtotal"].sum().tail(8)
    tendencia_ing = mensual.tolist() if not mensual.empty else None

    c.cabecera(
        "Servicios",
        "Que servicios se requieren mas y donde esta el dinero",
        icono=":material/build:",
    )

    c.kpi_grid([
        ("Ingresos por servicios", c.moneda(ingreso_total_serv, cfg.moneda), None,
         tendencia_ing, "Ingresos generados por los servicios facturados"),
        ("Facturas con servicios", c.miles(n_fact_serv), None, None,
         "Facturas que incluyen al menos un servicio"),
        ("Ticket promedio", c.moneda(ingreso_total_serv / max(n_fact_serv, 1), cfg.moneda),
         None, None, "Ingreso promedio por factura con servicios"),
        ("Servicios en catalogo", c.miles(n_servicios), None, None,
         "Servicios ofrecidos por el negocio"),
    ])

    tab_populares, tab_ingresos, tab_series, tab_catalogo = st.tabs(
        ["Mas solicitados", "Ingresos por servicio", "Series de tiempo", "Catalogo"],
        key="tabs_servicios", on_change="rerun",
    )

    with tab_populares:
        if tab_populares.open:
            pop = analyzer.servicios_mas_solicitados()
            if not pop.empty:
                with c.panel("Servicios mas solicitados", "Demanda acumulada por servicio",
                             icono=":material/task:"):
                    c.mostrar_grafico(c.grafico_barras(
                        pop, "servicio", "frecuencia", color="frecuencia", color_cont="YlOrRd",
                        etiquetas={"servicio": "Servicio", "frecuencia": "Veces"},
                    ), width="stretch", height="stretch")
                    st.dataframe(pop, width="stretch", height=280,
                                 column_config={
                                     "servicio": "Servicio",
                                     "frecuencia": st.column_config.NumberColumn("Veces"),
                                 })
            else:
                c.vacio("Sin datos de demanda de servicios.", icono=":material/query_stats:",
                        detalle="Se necesitan facturas con el detalle de servicios.")

    with tab_ingresos:
        if tab_ingresos.open:
            ing = detalle.groupby("servicio")["subtotal"].sum().sort_values(ascending=False).reset_index()
            with c.panel("Ingresos generados por servicio", "Donde se concentra la facturacion",
                         icono=":material/savings:"):
                c.mostrar_grafico(c.grafico_barras(
                    ing.head(15), "servicio", "subtotal", color="subtotal", color_cont="Blues",
                    etiquetas={"servicio": "Servicio", "subtotal": "Ingresos"},
                ), width="stretch", height="stretch")
                st.dataframe(
                    ing, width="stretch", height=280,
                    column_config={
                        "servicio": "Servicio",
                        "subtotal": st.column_config.NumberColumn("Ingresos", format=c.formato_moneda(cfg.moneda)),
                    },
                )

    with tab_series:
        if tab_series.open:
            ts = detalle[["fecha", "servicio", "subtotal"]].copy()
            ts["Periodo"] = ts["fecha"].dt.to_period("M").astype(str)
            ts_agg = ts.groupby(["Periodo", "servicio"])["subtotal"].sum().reset_index()
            if ts_agg.empty:
                c.vacio("Sin datos de series.", icono=":material/timeline:",
                        detalle="Se necesitan facturas con fecha y servicios.")
            else:
                todos = list(ts_agg["servicio"].dropna().unique())
                elegidos = st.multiselect(
                    "Servicios para graficar", todos, default=todos[:5] if todos else todos,
                    max_selections=8,
                    help="Compara la evolucion de hasta 8 servicios a la vez.",
                )
                if not elegidos:
                    c.vacio(
                        "Selecciona al menos un servicio para ver su evolucion.",
                        icono=":material/timeline:",
                        detalle="Puedes comparar hasta 8 servicios a la vez.",
                    )
                else:
                    sub = ts_agg[ts_agg["servicio"].isin(elegidos)]
                    with c.panel("Evolucion mensual", "Ingresos por servicio a lo largo del tiempo",
                                 icono=":material/timeline:"):
                        c.mostrar_grafico(c.grafico_linea(
                            sub, "Periodo", "subtotal", color="servicio",
                            etiquetas={"Periodo": "Mes", "subtotal": "Ingresos"},
                        ), width="stretch", height="stretch")

    with tab_catalogo:
        if tab_catalogo.open:
            cat = servicios.copy()
            if cat.empty or "precio_base" not in cat.columns:
                c.vacio(
                    "Tu catalogo de servicios esta vacio.",
                    icono=":material/build:",
                    detalle="Carga el archivo de servicios desde la pagina 'Mis datos'.",
                    cta="Ve a la pagina 'Mis datos'",
                )
            else:
                with c.panel("Servicios del catalogo", "Precio base y tiempo estimado de cada servicio",
                             icono=":material/format_list_bulleted:"):
                    cat["precio_base"] = pd.to_numeric(cat["precio_base"], errors="coerce")
                    st.dataframe(
                        cat, width="stretch",
                        column_config={
                            "id": "ID",
                            "nombre": "Servicio",
                            "precio_base": st.column_config.NumberColumn("Precio base", format=c.formato_moneda(cfg.moneda)),
                            "tiempo_estimado_min": st.column_config.NumberColumn("Tiempo estimado (min)"),
                        },
                    )
                    st.caption(f"**{c.miles(len(cat))}** servicios en el catalogo")


if __name__ == "__main__":
    principal()