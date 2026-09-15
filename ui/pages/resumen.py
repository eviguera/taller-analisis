"""Pagina: Resumen general (KPIs + tendencias)."""

from datetime import timedelta

import pandas as pd
import streamlit as st

from ui import components as c
from ui.context import obtener_estado


def _rango_desde_popover(df):
    """Selector de periodo dentro de un popover (presets + rango personalizado)."""
    fecha_max = df["fecha"].max().date()
    fecha_min = df["fecha"].min().date()
    presets = {
        "Ultimo mes": 1, "Ultimos 3 meses": 3, "Ultimos 6 meses": 6,
        "Ultimo ano": 12, "Todo": None,
    }
    modo = st.segmented_control(
        "Periodo", list(presets) + ["Personalizado"], default="Ultimo ano",
        key="resumen_periodo", label_visibility="collapsed", width="stretch",
    )
    modo = modo or "Ultimo ano"

    if modo == "Personalizado":
        col1, col2 = st.columns(2)
        f1 = col1.date_input("Desde", value=fecha_min, min_value=fecha_min, max_value=fecha_max)
        f2 = col2.date_input("Hasta", value=fecha_max, min_value=fecha_min, max_value=fecha_max)
        return f1, f2

    meses = presets[modo]
    if meses is None:
        return fecha_min, fecha_max
    f1 = (pd.Timestamp(fecha_max) - pd.DateOffset(months=meses - 1)).date()
    return f1, fecha_max


def _nunique(df, columna):
    return df[columna].nunique() if columna in df.columns else 0


def principal():
    cfg, data, analyzer, predictor = obtener_estado()

    df = analyzer.df
    if df.empty or "fecha" not in df.columns:
        c.vacio(
            "Sin datos de facturas para el resumen.",
            icono=":material/receipt_long:",
            detalle="Importa tus facturas en la pagina 'Datos y configuracion' y procesa el ETL.",
        )
        return

    col_titulo, col_filtros = st.columns([3, 1], vertical_alignment="center")
    with col_titulo:
        c.cabecera(
            "Resumen general",
            f"{cfg.taller_nombre} · Panorama de ingresos, clientes y facturacion",
            icono=":material/dashboard:",
        )
    with col_filtros:
        with st.popover("Filtros", icon=":material/tune:"):
            f1, f2 = _rango_desde_popover(df)

    filtrado = df[(df["fecha"].dt.date >= f1) & (df["fecha"].dt.date <= f2)]

    if filtrado.empty:
        c.vacio(
            "No hay datos en el rango de fechas seleccionado.",
            icono=":material/schedule:",
            detalle="Prueba con un periodo mas amplio o sin filtros.",
        )
        return

    st.caption(f":material/calendar_month: Periodo **{f1} → {f2}** · "
               f"{c.miles(len(filtrado))} facturas consideradas")

    # ----- KPIs del periodo filtrado -----
    total_ingresos = filtrado["total"].sum()
    total_facturas = len(filtrado)
    ticket = filtrado["total"].mean()
    n_clientes = _nunique(filtrado, "cliente_id")
    n_vehiculos = _nunique(filtrado, "vehiculo_id")

    # Tendencia mensual (contexto global para los sparklines)
    mensual = df.groupby("anio_mes").agg(
        ingresos=("total", "sum"),
        facturas=("id", "count"),
        ticket=("total", "mean"),
    ).tail(8)

    def tendencia(columna):
        return mensual[columna].tolist() if not mensual.empty else None

    # Variacion vs periodo equivalente anterior
    n_dias = (f2 - f1).days + 1
    prev_ini = (pd.Timestamp(f1) - timedelta(days=n_dias)).date()
    prev_fin = (pd.Timestamp(f1) - timedelta(days=1)).date()
    monto_prev = df[(df["fecha"].dt.date >= prev_ini) & (df["fecha"].dt.date <= prev_fin)]["total"].sum()
    delta_ing = f"{100 * (total_ingresos - monto_prev) / monto_prev:+.0f}%" if monto_prev > 0 else None

    c.kpi_grid([
        ("Ingresos totales", c.moneda(total_ingresos, cfg.moneda), delta_ing,
         tendencia("ingresos"), "Ingresos acumulados en el periodo"),
        ("Facturas", c.miles(total_facturas), None, tendencia("facturas"),
         "Numero de facturas emitidas"),
        ("Ticket promedio", c.moneda(ticket, cfg.moneda), None, tendencia("ticket"),
         "Ingreso promedio por factura"),
        ("Clientes activos", f"{n_clientes}", None, None,
         "Clientes distintos en el periodo"),
        ("Vehiculos atendidos", f"{n_vehiculos}", None, None,
         "Vehiculos distintos en el periodo"),
        ("Valor x cliente", c.moneda(total_ingresos / max(n_clientes, 1), cfg.moneda),
         None, None, "Ingresos entre clientes activos"),
    ])

    # ----- Tendencia de ingresos y facturas -----
    serie = filtrado.groupby("anio_mes").agg(
        ingresos=("total", "sum"), facturas=("id", "count")).reset_index()

    col1, col2 = st.columns(2, vertical_alignment="center")
    with col1:
        with c.panel("Ingresos por mes", "Series mensuales de facturacion",
                     icono=":material/show_chart:"):
            st.plotly_chart(c.grafico_linea(
                serie, "anio_mes", "ingresos",
                etiquetas={"anio_mes": "Mes", "ingresos": "Ingresos"}),
                width="stretch", height="stretch")
    with col2:
        with c.panel("Facturas por mes", "Volumen mensual de ordenes",
                     icono=":material/bar_chart:"):
            st.plotly_chart(c.grafico_barras(
                serie, "anio_mes", "facturas", color_cont="Blues",
                etiquetas={"anio_mes": "Mes", "facturas": "Facturas"}),
                width="stretch", height="stretch")

    # ----- Marcas y estacionalidad -----
    est = analyzer.estacionalidad()
    col1, col2 = st.columns(2, vertical_alignment="center")
    with col1:
        with c.panel("Ingresos por marca", "Marcas que mas aportan",
                     icono=":material/directions_car:"):
            por_marca = filtrado.groupby("marca").agg(
                ingresos=("total", "sum")).sort_values("ingresos", ascending=False).reset_index()
            st.plotly_chart(c.grafico_barras(
                por_marca, "marca", "ingresos",
                etiquetas={"marca": "Marca", "ingresos": "Ingresos"}),
                width="stretch", height="stretch")
    with col2:
        with c.panel("Estacionalidad por mes", "Patron anual de ingresos",
                     icono=":material/calendar_month:"):
            mes_df = est["por_mes"].copy()
            mes_df["mes_nombre"] = mes_df["mes"].map(lambda m: c.MESES_ES[int(m) - 1])
            st.plotly_chart(c.grafico_barras(
                mes_df, "mes_nombre", "ingresos",
                etiquetas={"mes_nombre": "Mes", "ingresos": "Ingresos"}),
                width="stretch", height="stretch")

    col1, col2 = st.columns(2, vertical_alignment="center")
    with col1:
        with c.panel("Ingresos por dia de la semana", "Cuando se concentra la demanda",
                     icono=":material/calendar_view_week:"):
            dia_df = est["por_dia_semana"].copy()
            dia_df["dia"] = dia_df["dia_semana"].map(c.DIAS_ES).fillna(dia_df["dia_semana"])
            st.plotly_chart(c.grafico_barras(
                dia_df, "dia", "ingresos", color_cont="Reds",
                etiquetas={"dia": "Dia", "ingresos": "Ingresos"}),
                width="stretch", height="stretch")
    with col2:
        with c.panel("Estado de facturas", "Distribucion por estado",
                     icono=":material/check_circle:"):
            estado_df = filtrado["estado"].value_counts().reset_index()
            estado_df.columns = ["Estado", "Cantidad"]
            st.plotly_chart(c.grafico_pastel(estado_df, "Estado", "Cantidad"),
                            width="stretch", height="stretch")

    # ----- Vista previa de datos crudos -----
    with st.expander("Ver datos crudos (filtrados)", icon=":material/table_rows:"):
        st.dataframe(filtrado.drop(columns=["detalles"], errors="ignore"),
                     width="stretch", height=300)


if __name__ == "__main__":
    principal()