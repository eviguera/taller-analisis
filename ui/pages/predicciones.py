"""Pagina: Predicciones (ventas esperadas).

Version simple para PYMEs: una sola pregunta respondida.
"Cuanto voy a vender el mes que viene?" basada en el promedio de los
ultimos 3 meses de facturacion.
"""
import pandas as pd
import streamlit as st

from ui import components as c
from ui.context import obtener_estado


def principal():
    try:
        cfg, data, analyzer, predictor = obtener_estado()
    except Exception as e:  # nunca falle silenciosamente
        c.mensaje_error(
            "No se pudieron cargar los datos de predicciones.",
            detalle=str(e) if str(e) else "Revisa que el almacén del workspace esté disponible.",
        )
        return

    hechos = analyzer.df
    if hechos.empty or "fecha" not in hechos.columns or "total" not in hechos.columns:
        c.vacio(
            "Aún no hay facturas para calcular predicciones.",
            icono=":material/auto_graph:",
            detalle="Importa tus facturas en 'Mis datos' y procesa el ETL para habilitar esta página.",
        )
        return

    df = hechos.copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha"])
    if df.empty:
        c.vacio(
            "No hay facturas con fechas válidas para calcular predicciones.",
            icono=":material/auto_graph:",
            detalle="Revisa que tu archivo de facturas tenga la columna 'fecha' con valores parseables.",
        )
        return

    df = df[df["estado"] != "Cancelada"] if "estado" in df.columns else df

    # Ventas de los últimos 3 meses completos como base
    hoy = pd.Timestamp.today()
    hace_3_meses = hoy - pd.DateOffset(months=3)
    recientes = df[df["fecha"] >= hace_3_meses]

    if recientes.empty:
        c.vacio(
            "No hay ventas en los últimos 3 meses para proyectar.",
            icono=":material/auto_graph:",
            detalle="Importa más facturas en 'Mis datos' y vuelve aquí.",
        )
        return

    ventas_mes_1 = recientes["total"].sum() / 3.0
    ventas_mes_proximo = ventas_mes_1  # proyección simple: mismo promedio

    # Variación simple: comparar mes más reciente vs mes anterior
    por_mes = df.groupby(df["fecha"].dt.to_period("M"))["total"].sum().sort_index()
    if len(por_mes) >= 2:
        ultimo = float(por_mes.iloc[-1])
        anterior = float(por_mes.iloc[-2])
        variacion = ((ultimo - anterior) / anterior * 100) if anterior > 0 else 0.0
    else:
        variacion = 0.0

    c.cabecera(
        "Ventas esperadas",
        "¿Cuánto vas a vender el mes que viene?",
        icono=":material/trending_up:",
    )

    # ---- KPI principal: venta esperada mes que viene ----
    delta = f"{variacion:+.0f}% vs mes pasado" if variacion != 0 else None
    c.kpi_grid([
        ("Ventas esperadas (próximo mes)", c.moneda(ventas_mes_proximo, cfg.moneda),
         delta, None,
         "Promedio de los últimos 3 meses de facturación"),
    ])

    st.caption(
        f":material/calendar_month: Basado en {c.miles(len(recientes))} facturas de los últimos 3 meses · "
        f"promedio mensual {c.moneda(ventas_mes_1, cfg.moneda)}"
    )

    # ---- Gráfico simple: ventas mensuales históricas ----
    try:
        serie = por_mes.reset_index()
        serie.columns = ["Mes", "Ventas"]
        serie["Mes"] = serie["Mes"].astype(str)
        with c.panel("Ventas por mes (historial)", "Tendencia real de facturación",
                     icono=":material/show_chart:"):
            c.mostrar_grafico(c.grafico_linea(
                serie, "Mes", "Ventas",
                etiquetas={"Mes": "Mes", "Ventas": "Ventas"},
            ), width="stretch", height="stretch")
    except Exception as ex:
        c.mensaje_error(
            "No se pudo renderizar el gráfico de ventas.",
            detalle=str(ex) if str(ex) else "Revisa que las columnas de fecha y total tengan valores válidos.",
        )

    # ---- Recomendación simple ----
    st.divider()
    if variacion > 10:
        c.confirmacion_exito(
            "Tus ventas están creciendo.",
            "Sigue así. Considera asegurar inventario para la próxima temporada.",
        )
    elif variacion < -10:
        c.mensaje_error(
            "Tus ventas cayeron respecto al mes pasado.",
            "Revisa qué cambió: ¿menos clientes? ¿menos servicios? ¿temporada baja?",
        )
    else:
        st.info(
            "Tus ventas son estables. "
            "Usa la página 'Alertas' para vigilar clientes en riesgo y stock bajo.",
            icon=":material/info:",
        )


if __name__ == "__main__":
    principal()
