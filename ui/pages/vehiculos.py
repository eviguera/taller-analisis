"""Pagina: Vehiculos (marcas, antiguedad y kilometraje)."""

from datetime import date

import pandas as pd
import streamlit as st

from ui import components as c
from ui.context import obtener_estado


def principal():
    cfg, data, analyzer, predictor = obtener_estado()

    vehiculos = data.get("vehiculos", pd.DataFrame())
    if vehiculos.empty:
        c.vacio(
            "No hay datos de vehiculos.",
            icono=":material/directions_car:",
            detalle="Importa un archivo 'vehiculos' en la pagina de Datos para continuar.",
        )
        return

    vehiculos = vehiculos.copy()
    vehiculos["anio"] = pd.to_numeric(vehiculos["anio"], errors="coerce")
    vehiculos["kilometraje"] = pd.to_numeric(vehiculos["kilometraje"], errors="coerce").fillna(0)
    anio_actual = date.today().year
    vehiculos["edad"] = (anio_actual - vehiculos["anio"]).clip(lower=0)

    n_veh = len(vehiculos)
    n_marcas = vehiculos["marca"].nunique()
    km_prom = vehiculos["kilometraje"].mean()
    edad_prom = vehiculos["edad"].mean()

    c.cabecera(
        "Vehiculos",
        "Flota atendida por marca, antiguedad y kilometraje",
        icono=":material/directions_car:",
    )
    c.kpi_grid([
        ("Vehiculos", f"{n_veh}", None, None, "Vehiculos en la base"),
        ("Marcas", f"{n_marcas}", None, None, "Marcas distintas"),
        ("Km promedio", f"{c.miles(km_prom)} km", None, None, "Kilometraje promedio"),
        ("Edad promedio", f"{edad_prom:.1f} anios", None, None, "Antiguedad promedio de la flota"),
    ])

    tab_marcas, tab_ingresos, tab_edad, tab_km, tab_lista = st.tabs(
        ["Marca", "Ingresos por vehiculo", "Antiguedad", "Kilometraje", "Listado"],
        key="tabs_vehiculos", on_change="rerun",
    )

    with tab_marcas:
        if tab_marcas.open:
            por_marca = analyzer.ingresos_por_marca()
            if not por_marca.empty:
                with c.panel("Ingresos por marca", "Facturacion, facturas y promedio por marca",
                             icono=":material/savings:"):
                    st.plotly_chart(c.grafico_barras(
                        por_marca, "marca", "ingresos", color="facturas", color_cont="Greens",
                        etiquetas={"marca": "Marca", "ingresos": "Ingresos"},
                    ), width="stretch", height="stretch")
            conteo = vehiculos["marca"].value_counts().reset_index()
            conteo.columns = ["Marca", "Vehiculos"]
            col1, col2 = st.columns(2, vertical_alignment="center")
            with col1:
                with c.panel("Vehiculos por marca", "Concentracion de la flota"):
                    st.plotly_chart(c.grafico_pastel(conteo.head(8), "Marca", "Vehiculos"),
                                    width="stretch", height="stretch")
            with col2:
                with c.panel("Conteo por marca", "Ranking de marcas"):
                    st.dataframe(conteo, width="stretch", height=280)

    with tab_ingresos:
        if tab_ingresos.open:
            ing = analyzer.ingresos_por_vehiculo(n=50)
            if ing.empty:
                c.vacio("Sin facturas con vehiculo asociado para calcular ingresos.",
                        icono=":material/savings:")
            else:
                total_ing = ing["ingresos"].sum()
                n_veh_ing = len(ing)
                ticket_veh = ing["ingresos"].mean()
                top_veh = ing.iloc[0]
                c.kpi_grid([
                    ("Ingresos por vehiculos", c.moneda(total_ing, cfg.moneda), None, None,
                     "Suma de facturas de vehiculos con ingresos"),
                    ("Vehiculos con ingresos", f"{n_veh_ing}", None, None,
                     "Vehiculos que generaron facturacion"),
                    ("Promedio x vehiculo", c.moneda(ticket_veh, cfg.moneda), None, None,
                     "Ingreso promedio por vehiculo"),
                    ("Top vehiculo",
                     f"{c.miles(top_veh['ingresos'])} · {top_veh.get('placa') or 's/clave'}",
                     None, None,
                     f"{top_veh.get('marca') or ''} {top_veh.get('modelo') or ''} ({top_veh.get('anio') or '?'})"),
                ])

                with c.panel("Top 15 vehiculos por ingreso", "Los que mas facturan",
                             icono=":material/savings:"):
                    st.plotly_chart(c.grafico_barras(
                        ing.head(15), "vehiculo_id", "ingresos", color="facturas",
                        color_cont="Blues",
                        etiquetas={"vehiculo_id": "ID vehiculo", "ingresos": "Ingresos"},
                    ), width="stretch", height="stretch")

                st.markdown("**Detalle de ingresos por vehiculo**")
                st.dataframe(
                    ing, width="stretch", height=380,
                    column_config={
                        "ingresos": st.column_config.NumberColumn("Ingresos", format="$#,##0"),
                        "facturas": st.column_config.NumberColumn("Visitas"),
                        "anio": st.column_config.NumberColumn("Anio"),
                        "kilometraje": st.column_config.NumberColumn("Kilometraje", format="%d km"),
                    },
                )
                st.caption("Descarga el detalle en CSV, Excel o PSPP (.sav).")
                c.descargar(ing, "ingresos_por_vehiculo")

    with tab_edad:
        if tab_edad.open:
            bins = [0, 3, 6, 10, 15, 200]
            labels = ["0-3 anios", "4-6 anios", "7-10 anios", "11-15 anios", "15+"]
            vehiculos["rango_edad"] = pd.cut(vehiculos["edad"], bins=bins, labels=labels, right=True)
            conteo_edad = vehiculos["rango_edad"].value_counts().sort_index().reset_index()
            conteo_edad.columns = ["Rango de Edad", "Cantidad"]
            with c.panel("Distribucion por antiguedad", "Edad de la flota atendida",
                         icono=":material/calendar_month:"):
                st.plotly_chart(c.grafico_barras(
                    conteo_edad, "Rango de Edad", "Cantidad", color_cont="Brwnyl",
                    etiquetas={"Cantidad": "Vehiculos"},
                ), width="stretch", height="stretch")
            st.dataframe(conteo_edad, width="stretch")

    with tab_km:
        if tab_km.open:
            with c.panel("Distribucion de kilometraje", "Recorrido acumulado de la flota",
                         icono=":material/speed:"):
                st.plotly_chart(c.grafico_hist(vehiculos, "kilometraje", 25,
                                               xlabel="Kilometraje (km)"),
                                width="stretch", height="stretch")
            st.caption(f"**Km promedio:** {c.miles(km_prom)} km · **Km maximo:** "
                       f"{c.miles(vehiculos['kilometraje'].max())} km")

    with tab_lista:
        if tab_lista.open:
            st.dataframe(
                vehiculos.drop(columns=["rango_edad"], errors="ignore"),
                width="stretch", height=340,
                column_config={
                    "kilometraje": st.column_config.NumberColumn("Kilometraje", format="%d km"),
                    "anio": st.column_config.NumberColumn("Anio"),
                    "edad": st.column_config.NumberColumn("Edad"),
                },
            )


if __name__ == "__main__":
    principal()