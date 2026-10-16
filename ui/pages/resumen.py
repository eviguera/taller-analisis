"""Pagina: Resumen general (KPIs principales + tendencia principal).

Version minimalista: solo lo esencial esta visible. Los detalles secundarios
viven dentro de "Ver mas detalles" para no abrumar al usuario al entrar.
"""

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
        "Último mes": 1, "Últimos 3 meses": 3, "Últimos 6 meses": 6,
        "Último año": 12, "Todo": None,
    }
    modo = st.segmented_control(
        "Periodo", list(presets) + ["Personalizado"], default="Último año",
        key="resumen_periodo", label_visibility="collapsed", width="stretch",
    )
    modo = modo or "Último año"

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
    try:
        cfg, data, analyzer, predictor = obtener_estado()
    except Exception as e:  # nunca falle silenciosamente
        c.mensaje_error(
            "No se pudieron cargar los datos del resumen.",
            detalle=str(e) if str(e) else "Revisa que el almacén del workspace esté disponible y vuelve a intentar.",
        )
        return

    df = analyzer.df
    if df.empty or "fecha" not in df.columns:
        c.vacio(
            "Aún no hay facturas para el resumen.",
            icono=":material/receipt_long:",
            detalle="Importa tus facturas en la página 'Mis datos' y procesa el ETL.",
        )
        return

    # Protege contra fechas nulas (datos subidos por el usuario sin fecha valida).
    try:
        fecha_max = pd.Timestamp(df["fecha"].max())
        if pd.isna(fecha_max):
            raise ValueError("La columna fecha no tiene valores validos.")
        fecha_max = fecha_max.date()
    except Exception:
        c.mensaje_error(
            "Los datos de facturas tienen fechas invalidas.",
            detalle="Revisa que el archivo de facturas tenga una columna 'fecha' con valores parseables.",
        )
        return

    col_titulo, col_filtros = st.columns([3, 1], vertical_alignment="center")
    with col_titulo:
        c.cabecera(
            "Resumen general",
            f"{cfg.negocio_nombre} · Panorama de ingresos y facturación",
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
            detalle="Prueba con un periodo más amplio o sin filtros.",
        )
        return

    # ---- KPIs esenciales (solo tres, mas aire) ----
    total_ingresos = filtrado["total"].sum()
    total_facturas = len(filtrado)
    ticket = filtrado["total"].mean()

    n_dias = (f2 - f1).days + 1
    prev_ini = (pd.Timestamp(f1) - timedelta(days=n_dias)).date()
    prev_fin = (pd.Timestamp(f1) - timedelta(days=1)).date()
    monto_prev = df[(df["fecha"].dt.date >= prev_ini) & (df["fecha"].dt.date <= prev_fin)]["total"].sum()
    delta_ing = f"{100 * (total_ingresos - monto_prev) / monto_prev:+.0f}%" if monto_prev > 0 else None

    st.caption(
        f":material/calendar_month: Periodo **{f1} → {f2}** · "
        f"{c.miles(total_facturas)} facturas consideradas"
    )

    c.kpi_grid([
        ("Ingresos totales", c.moneda(total_ingresos, cfg.moneda), delta_ing,
         None, "Facturación acumulada en el periodo"),
        ("Facturas emitidas", c.miles(total_facturas), None, None,
         "Numero de facturas en el periodo"),
        ("Ticket promedio", c.moneda(ticket, cfg.moneda), None, None,
         "Ingreso promedio por factura"),
    ])

    # ---- Un solo grafico principal visible ----
    try:
        serie = filtrado.groupby("anio_mes").agg(
            ingresos=("total", "sum"), facturas=("id", "count")).reset_index()
        with c.panel("Ingresos por mes", "Tendencia de facturación",
                     icono=":material/show_chart:"):
            c.mostrar_grafico(c.grafico_linea(
                serie, "anio_mes", "ingresos",
                etiquetas={"anio_mes": "Mes", "ingresos": "Ingresos"}),
                width="stretch", height="stretch")
    except Exception as e:
        c.mensaje_error(
            "No se pudo renderizar el gráfico principal.",
            detalle=str(e) if str(e) else "Revisa que las columnas de fecha y total tengan valores válidos.",
        )

    # ---- Detalles opcionales (colapsables) ----
    with st.expander("Ver más detalles", icon=":material/expand_more:"):
        col1, col2 = st.columns(2)
        with col1:
            try:
                n_clientes = _nunique(filtrado, "cliente_id")
                st.metric("Clientes activos", c.miles(n_clientes))
            except Exception:
                pass
        with col2:
            try:
                n_vehiculos = _nunique(filtrado, "vehiculo_id")
                st.metric("Vehículos atendidos", c.miles(n_vehiculos))
            except Exception:
                pass

        try:
            mensual = df.groupby("anio_mes").agg(
                ingresos=("total", "sum"),
                facturas=("id", "count"),
                ticket=("total", "mean"),
            ).tail(8)

            def tendencia(columna):
                return mensual[columna].tolist() if not mensual.empty else None

            c.kpi_grid([
                ("Facturas", c.miles(total_facturas), None, tendencia("facturas"),
                 "Numero de facturas emitidas"),
                ("Ticket promedio", c.moneda(ticket, cfg.moneda), None, tendencia("ticket"),
                 "Ingreso promedio por factura"),
            ])
        except Exception:
            pass

        try:
            col_a, col_b = st.columns(2)
            with col_a:
                por_marca = filtrado.groupby("marca").agg(
                    ingresos=("total", "sum")).sort_values("ingresos", ascending=False).reset_index()
                with c.panel("Ingresos por marca", "Marcas que más aportan",
                             icono=":material/directions_car:"):
                    c.mostrar_grafico(c.grafico_barras(
                        por_marca, "marca", "ingresos",
                        etiquetas={"marca": "Marca", "ingresos": "Ingresos"}),
                        width="stretch", height="stretch")
            with col_b:
                estado_df = filtrado["estado"].value_counts().reset_index()
                estado_df.columns = ["Estado", "Cantidad"]
                with c.panel("Estado de facturas", "Distribución",
                             icono=":material/check_circle:"):
                    c.mostrar_grafico(c.grafico_pastel(estado_df, "Estado", "Cantidad"),
                                    width="stretch", height="stretch")
        except Exception:
            pass

    # ---- Vista previa de datos crudos ----
    with st.expander("Ver datos crudos (filtrados)", icon=":material/table_rows:"):
        c.dataframe(filtrado.drop(columns=["detalles"], errors="ignore"),
                    alto=300)


if __name__ == "__main__":
    principal()
