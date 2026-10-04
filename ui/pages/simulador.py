"""Pagina: Simulador what-if (proyeccion de 12 meses + EBITDA)."""

import pandas as pd
import streamlit as st

from src.simulador import (aplicar_preset, base_datos, PRESETS,
                           proyectar, ratios_estacionales)

from ui import components as c
from ui.context import obtener_estado


def _slider_int(clave, etiqueta, min_, max_, valor, paso, ayuda=None, formato="%d"):
    vigente = st.session_state.get(clave, valor)
    return st.slider(etiqueta, min_value=min_, max_value=max_, step=paso,
                     value=vigente, key=clave, help=ayuda, format=formato)


def _aplicar_preset(nombre):
    for k in ("sim_crecimiento", "sim_churn", "sim_ticket", "sim_nba",
              "sim_margen", "sim_gasto_fijo"):
        st.session_state.pop(k, None)
    st.session_state["sim_preset"] = nombre
    st.rerun()


def principal():
    cfg, data, analyzer, predictor = obtener_estado()

    df = analyzer.df
    if df.empty or "fecha" not in df.columns or "total" not in df.columns:
        c.vacio(
            "Sin facturas para proyectar.",
            icono=":material/query_stats:",
            detalle="Importa tus facturas y procesa el ETL para habilitar el simulador.",
        )
        return

    c.cabecera(
        "Simulador what-if",
        f"{cfg.negocio_nombre} · Proyecta 12 meses de ingresos y EBITDA sobre tus datos reales",
        icono=":material/science:",
    )

    base = base_datos(df)
    if not base:
        c.vacio("No hay suficientes datos para el simulador.", icono=":material/help:")
        return
    ratios = ratios_estacionales(df)

    c.kpi_grid([
        ("Clientes activos (12m)", c.miles(base["clientes_activos"]), None, None,
         "Clientes distintos en los ultimos 12 meses"),
        ("Ticket promedio", c.moneda(base["ticket_promedio"], cfg.moneda), None, None,
         "Gasto promedio por factura"),
        ("Ingresos 12m", c.moneda(base["ingresos_12m"], cfg.moneda), None, None,
         "Facturacion total de los ultimos 12 meses"),
        ("Churn implicito", f"{base['churn_mensual_historico']*100:.1f}%/mes", None, None,
         "Perdida mensual de clientes inferida de la serie historica"),
    ])

    st.markdown("**Escenario**")
    with st.container(border=True):
        col_p, _, _ = st.columns([2, 1, 1])
        with col_p:
            pc1, pc2, pc3 = st.columns(3)
            for i, nombre in enumerate(["Conservador", "Base (igual que hoy)",
                                        "Agresivo (+ Giro Recomienda)"]):
                with [pc1, pc2, pc3][i]:
                    if st.button(nombre, key=f"btn_preset_{i}", width="stretch",
                                 help="Configura los parametros de abajo con este escenario."):
                        _aplicar_preset(nombre)

        preset = aplicar_preset(base["churn_mensual_historico"],
                                st.session_state.get("sim_preset", "Base (igual que hoy)"))

        # Defaults economicos del sector (benchmark de vertical)
        sim_def = cfg.simulador or {}
        def_margen = int(round((sim_def.get("margen_bruto") or 0.35) * 100))
        def_gasto = int(round((sim_def.get("gasto_fijo_pct") or 0.60) * 100))
        def_crec = int(round((sim_def.get("crecimiento_anual") or 0.08) * 100))
        def_tick = int(round((sim_def.get("ticket_crecimiento") or 0.04) * 100))
        if cfg.sector:
            st.caption(f":material/tune: Defaults del sector **{cfg.sector}** "
                       f"(margen {def_margen}% · gasto fijo {def_gasto}% del ingreso)")

        col1, col2, col3 = st.columns(3)
        with col1:
            crec = _slider_int("sim_crecimiento", "Crecimiento de clientes (anual)",
                               -10, 50, def_crec,
                               1, ayuda="Variacion anual de la base de clientes.", formato="%d%%")
            churn_cfg = _slider_int("sim_churn", "Churn mensual", 0, 30,
                                    int(round(preset["churn_mensual"] * 100)),
                                    1, ayuda="Clientes que se pierden cada mes.", formato="%d%%")
        with col2:
            tick = _slider_int("sim_ticket", "Crecimiento del ticket (anual)",
                               -10, 30, def_tick,
                               1, formato="%d%%")
            nba = _slider_int("sim_nba", "Impacto Giro Recomienda (-% churn)",
                              0, 60, int(round(preset["efecto_giro_nba"] * 100)),
                               1, ayuda="Cuanto reduce el churn ejecutar las NBA.", formato="%d%%")
        with col3:
            margen = _slider_int("sim_margen", "Margen bruto", 5, 80,
                                 def_margen, 1, formato="%d%%")
            gasto_fijo_pct = _slider_int("sim_gasto_fijo",
                                         "Gasto fijo mensual (% del ingreso medio)",
                                         10, 120, def_gasto, 1, formato="%d%%")

        usar_ml = st.toggle(
            "Comparar con el modelo GIRO de ingresos (Gradient Boosting)",
            value=False, help="Superpone la salida del modelo predictivo entrenado "
                              "con tu historial.",
        )

    gasto_fijo = base["ingresos_12m"] / max(12, base["meses_muestra"] or 1) * (gasto_fijo_pct / 100)
    resultado = proyectar(
        df, meses=12,
        crecimiento_anual=crec / 100.0,
        ticket_crecimiento=tick / 100.0,
        churn_mensual=churn_cfg / 100.0,
        efecto_giro_nba=nba / 100.0,
        margen_bruto=margen / 100.0,
        gasto_fijo_mensual=gasto_fijo,
        ratios=ratios,
    )

    proy = resultado["proyeccion"]
    totales = resultado["totales"]

    # Serie historica real (ultimos 12 meses) para el contexto del grafico
    hist = df[df["fecha"] > df["fecha"].max() - pd.DateOffset(months=12)].copy()
    hist_serie = hist.groupby(hist["fecha"].dt.to_period("M"))["total"].sum().reset_index()
    hist_serie.columns = ["fecha", "ingresos"]
    hist_serie["fecha"] = hist_serie["fecha"].astype(str)
    hist_serie["tipo"] = "Real (12m)"

    proy_graf = proy[["fecha", "ingresos"]].copy()
    proy_graf.columns = ["fecha", "ingresos"]
    proy_graf["tipo"] = "Proyeccion"

    serie_graf = pd.concat([hist_serie, proy_graf], ignore_index=True)

    delta_ingresos = totales["ingresos"] - base["ingresos_12m"]
    delta_pct = (100 * delta_ingresos / base["ingresos_12m"]) if base["ingresos_12m"] > 0 else 0
    c.kpi_grid([
        ("Ingresos proyectados (12m)", c.moneda(totales["ingresos"], cfg.moneda),
         f"{delta_pct:+.0f}% vs 12m reales", None,
         "Facturacion total del escenario a 12 meses"),
        ("EBITDA proyectado", c.moneda(totales["ebitda"], cfg.moneda),
         f"margen {totales['margen_ebitda']*100:.0f}%", None,
         "Resultado operativo del escenario"),
        ("Clientes al final", c.miles(totales["clientes_finales"]),
         f"{totales['clientes_finales']-base['clientes_activos']:+.0f}", None,
         "Clientes estimados al mes 12"),
        ("Ticket al final", c.moneda(totales["ticket_final"], cfg.moneda), None, None,
         "Ticket promedio proyectado al mes 12"),
    ])

    col1, col2 = st.columns(2, vertical_alignment="center")
    with col1:
        with c.panel("Ingresos reales y proyectados", "Contexto de la ultima serie + escenario",
                     icono=":material/show_chart:"):
            fig = c.grafico_linea(
                serie_graf, "fecha", "ingresos", color="tipo",
                etiquetas={"fecha": "Mes", "ingresos": "Ingresos", "tipo": "Serie"})
            c.mostrar_grafico(fig)
    with col2:
        with c.panel("EBITDA mensual del escenario", "Ingresos - costos variables - gastos fijos",
                     icono=":material/trending_up:"):
            c.mostrar_grafico(c.grafico_barras(
                proy, "fecha", "ebitda",
                color_cont="Greens",
                etiquetas={"fecha": "Mes", "ebitda": "EBITDA"}),
                width="stretch", height="stretch")

    if usar_ml:
        try:
            ml = predictor.predecir_ingresos(meses_futuros=12)
            if not ml["predicciones"].empty:
                ml_serie = ml["predicciones"].copy()
                ml_serie.columns = ["fecha", "ingresos"]
                ml_serie["tipo"] = "Modelo GIRO (GB)"
                serie_ml = pd.concat([serie_graf, ml_serie], ignore_index=True)
                with c.panel("Comparacion con el modelo predictivo",
                             "Escenario bajo parametros vs modelo entrenado con tu historial",
                             icono=":material/compare_arrows:"):
                    c.mostrar_grafico(c.grafico_linea(
                        serie_ml, "fecha", "ingresos", color="tipo",
                        etiquetas={"fecha": "Mes", "ingresos": "Ingresos", "tipo": "Serie"}),
                        width="stretch", height="stretch")
                evaluacion = ml.get("evaluacion", {})
                if evaluacion.get("mape"):
                    st.caption(f":material/science: Modelo {ml['modelo']} · "
                               f"MAE {c.moneda(evaluacion.get('mae', 0), cfg.moneda)} · "
                               f"MAPE {evaluacion.get('mape', 0):.1f}% "
                               f"(fuente: {evaluacion.get('fuente', 'reentrenado')})")
        except Exception as e:  # noqa: BLE001
            st.warning(f"No se pudo comparar con el modelo: {e}")

    st.markdown("**Detalle de la proyeccion**")
    tabla = proy.copy()
    tabla["Ingresos"] = tabla["ingresos"].map(lambda v: c.moneda(v, cfg.moneda))
    tabla["EBITDA"] = tabla["ebitda"].map(lambda v: c.moneda(v, cfg.moneda))
    st.dataframe(tabla[["fecha", "clientes", "ticket", "Ingresos", "EBITDA"]],
                 width="stretch", height=300, column_config={
                     "clientes": st.column_config.NumberColumn("Clientes"),
                     "ticket": st.column_config.NumberColumn("Ticket", format="%.0f"),
                 })

    st.caption(f":material/lightbulb: Simulador sobre datos reales del workspace "
               f"**{cfg.clave}** — ETL + DuckDB. Ejecutar las alertas y NBA de GIRO "
               "es el camino para aterrizar un escenario agresivo.")


if __name__ == "__main__":
    principal()