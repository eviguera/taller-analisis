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
        )
        return

    ingreso_total_serv = detalle["subtotal"].sum()
    n_fact_serv = detalle["factura_id"].nunique()

    mensual = analyzer.df.groupby("anio_mes")["total"].sum().tail(8)
    tendencia_ing = mensual.tolist() if not mensual.empty else None

    c.cabecera(
        "Servicios",
        "Que servicios se requieren mas y donde esta el dinero",
        icono=":material/build:",
    )

    c.kpi_grid([
        ("Servicios en catalogo", f"{n_servicios}", None, None, "Servicios ofrecidos por el negocio"),
        ("Ingresos por servicios", c.moneda(ingreso_total_serv, cfg.moneda), None,
         tendencia_ing, "Ingresos generados por servicios"),
        ("Ordenes con servicios", c.miles(n_fact_serv), None, None, "Facturas con servicios"),
        ("Ticket promedio", c.moneda(ingreso_total_serv / max(n_fact_serv, 1), cfg.moneda),
         None, None, "Ingresos por servicios entre ordenes"),
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
                    st.plotly_chart(c.grafico_barras(
                        pop, "servicio", "frecuencia", color="frecuencia", color_cont="YlOrRd",
                        etiquetas={"servicio": "Servicio", "frecuencia": "Veces"},
                    ), width="stretch", height="stretch")
                st.dataframe(pop, width="stretch", height=280,
                             column_config={"frecuencia": st.column_config.NumberColumn("Veces")})
            else:
                c.vacio("Sin datos de demanda de servicios.", icono=":material/query_stats:")

    with tab_ingresos:
        if tab_ingresos.open:
            ing = detalle.groupby("servicio")["subtotal"].sum().sort_values(ascending=False).reset_index()
            with c.panel("Ingresos generados por servicio", "Donde se concentra la facturacion",
                         icono=":material/savings:"):
                st.plotly_chart(c.grafico_barras(
                    ing.head(15), "servicio", "subtotal", color="subtotal", color_cont="Blues",
                    etiquetas={"servicio": "Servicio", "subtotal": "Ingresos"},
                ), width="stretch", height="stretch")
            st.dataframe(
                ing, width="stretch", height=280,
                column_config={
                    "servicio": "Servicio",
                    "subtotal": st.column_config.NumberColumn("Ingresos", format="$#,##0"),
                },
            )

    with tab_series:
        if tab_series.open:
            c.titulo_seccion("Series de tiempo de servicios",
                             "Selecciona servicios para comparar su evolucion",
                             icono=":material/timeline:")
            ts = detalle[["fecha", "servicio", "subtotal"]].copy()
            ts["Periodo"] = ts["fecha"].dt.to_period("M").astype(str)
            ts_agg = ts.groupby(["Periodo", "servicio"])["subtotal"].sum().reset_index()
            todos = list(ts_agg["servicio"].dropna().unique())
            elegidos = st.multiselect(
                "Servicios para graficar", todos, default=todos[:5] if todos else todos,
                max_selections=8,
            )
            if ts_agg.empty:
                c.vacio("Sin datos de series.", icono=":material/timeline:")
            elif elegidos:
                sub = ts_agg[ts_agg["servicio"].isin(elegidos)]
                with c.panel("Evolucion mensual", "Ingresos por servicio a lo largo del tiempo",
                             icono=":material/timeline:"):
                    st.plotly_chart(c.grafico_linea(
                        sub, "Periodo", "subtotal", color="servicio",
                        etiquetas={"Periodo": "Mes", "subtotal": "Ingresos"},
                    ), width="stretch", height="stretch")

    with tab_catalogo:
        if tab_catalogo.open:
            cat = servicios.copy()
            cat["precio_base"] = pd.to_numeric(cat["precio_base"], errors="coerce")
            st.dataframe(
                cat, width="stretch",
                column_config={
                    "precio_base": st.column_config.NumberColumn("Precio base", format="$#,##0"),
                },
            )
            st.caption(f"**{len(cat)}** servicios en el catalogo")


if __name__ == "__main__":
    principal()