"""Pagina: Resumen general.

Diseño minimalista inspirado en Plausible + Stripe + Linear:
- Un número principal enorme arriba a la izquierda (aguja principal).
- Un solo gráfico hero (ingresos por mes).
- Clientes principales y alertas como tablas simples dentro de un expander.
- Todo lo demás colapsable para no abrumar al usuario al entrar.
"""
from datetime import timedelta

import pandas as pd
import streamlit as st

from src.negocio import planes_activos
from ui import components as c
from ui.context import obtener_estado


def _rango_desde_popover(df):
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
    except Exception as e:
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

    # Protege contra fechas nulas.
    try:
        fecha_max = pd.Timestamp(df["fecha"].max())
        if pd.isna(fecha_max):
            raise ValueError("La columna fecha no tiene valores válidos.")
        fecha_max = fecha_max.date()
    except Exception:
        c.mensaje_error(
            "Los datos de facturas tienen fechas inválidas.",
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

    # ---- KPI esenciales (aguja principal + 2 secundarios) ----
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

    # ---- Un solo grafico hero visible ----
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

    # ---- Detalles opcionales: tablas simples (estilo Stripe) ----
    with st.expander("Ver más detalles", icon=":material/expand_more:"):
        col_a, col_b = st.columns(2)

        with col_a:
            try:
                n_clientes = _nunique(filtrado, "cliente_id")
                c.kpi_grid([
                    ("Clientes activos", c.miles(n_clientes), None, None,
                     "Clientes distintos en el periodo"),
                ])
            except Exception:
                pass

            try:
                top_clientes = (
                    filtrado.groupby(["cliente_id", "nombre"])["total"]
                    .sum().sort_values(ascending=False).head(5).reset_index()
                )
                if not top_clientes.empty:
                    top_clientes = top_clientes.rename(
                        columns={"nombre": "Cliente", "total": "Gasto"})
                    top_clientes["Gasto"] = top_clientes["Gasto"].apply(
                        lambda v: c.moneda(v, cfg.moneda))
                    with c.panel("Top clientes", icono=":material/groups:"):
                        c.dataframe(
                            top_clientes[["Cliente", "Gasto"]],
                            alto=200, indice_visible=False,
                        )
            except Exception:
                pass

        with col_b:
            try:
                n_vehiculos = _nunique(filtrado, "vehiculo_id")
                c.kpi_grid([
                    ("Vehículos atendidos", c.miles(n_vehiculos), None, None,
                     "Vehículos distintos en el periodo"),
                ])
            except Exception:
                pass

            try:
                alertas = []
                if "estado" in filtrado.columns:
                    pendientes = filtrado[filtrado["estado"] == "Pendiente"]
                    if not pendientes.empty:
                        alertas.append(
                            ("rojo", f"{len(pendientes)} facturas pendientes",
                             f"Monto pendiente: {c.moneda(pendientes['total'].sum(), cfg.moneda)}")
                        )
                if alertas:
                    with c.panel("Alertas activas", icono=":material/notifications_active:"):
                        for tipo, titulo, detalle in alertas:
                            st.markdown(
                                f"{c.badge(tipo.upper(), tipo)} **{titulo}**"
                            )
                            st.caption(detalle)
            except Exception:
                pass

    # ---- Vista previa de datos crudos ----
    with st.expander("Ver datos crudos (filtrados)", icon=":material/table_rows:"):
        c.dataframe(filtrado.drop(columns=["detalles"], errors="ignore"),
                    alto=300)

    # ---- Precios y contratacion ----
    st.divider()
    st.markdown("### Planes de GIRO")
    planes = planes_activos(cfg)
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        with c.panel("Core", "Para pyme que empieza", icono=":material/credit_card:"):
            precio_core = planes.get("Core")
            if precio_core:
                st.markdown(f"**{c.moneda(precio_core, cfg.moneda)}/mes**")
                st.caption("ETL + almacen DuckDB · 9 dashboards · 1 modelo")
                if st.button("Contratar Core", key="contratar_core", width="stretch"):
                    st.info("Pronto: pago con tarjeta desde aquí.")
            else:
                st.info("Plan no disponible")
    with col_p2:
        with c.panel("Pro", "Para pyme en crecimiento", icono=":material/trending_up:"):
            precio_pro = planes.get("Pro")
            if precio_pro:
                st.markdown(f"**{c.moneda(precio_pro, cfg.moneda)}/mes**")
                st.caption("Todo Core + Giro Recomienda · Mantenimiento predictivo · Alertas + email")
                if st.button("Contratar Pro", key="contratar_pro", width="stretch"):
                    st.info("Pronto: pago con tarjeta desde aquí.")
            else:
                st.info("Plan no disponible")


if __name__ == "__main__":
    principal()
