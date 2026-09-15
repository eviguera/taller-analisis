"""Pagina: Predicciones (ingresos, demanda, churn e inventario)."""

import pandas as pd
import streamlit as st

from ui import components as c
from ui.context import obtener_estado


def principal():
    cfg, data, analyzer, predictor = obtener_estado()

    n_facturas = len(data.get("facturas", pd.DataFrame()))
    c.cabecera(
        "Predicciones",
        f"Modelos entrenados con {c.miles(n_facturas)} facturas",
        icono=":material/auto_graph:",
    )

    tab_ing, tab_dem, tab_churn, tab_inv = st.tabs(
        ["Ingresos", "Demanda de servicios", "Churn de clientes", "Reposicion"],
        key="tabs_predicciones", on_change="rerun",
    )

    with tab_ing:
        if tab_ing.open:
            c.titulo_seccion("Prediccion de ingresos mensuales",
                             "Gradient Boosting con rezagos de 1 a 3 meses",
                             icono=":material/trending_up:")
            meses = st.slider("Meses a predecir", 1, 12, 6, key="meses_ing")
            res = predictor.predecir_ingresos(meses_futuros=meses)

            if res.get("evaluacion"):
                ev = res["evaluacion"]
                c.kpi_grid([
                    ("MAE", c.moneda(ev.get("mae", 0), cfg.moneda), None, None,
                     "Error absoluto medio"),
                    ("RMSE", c.moneda(ev.get("rmse", 0), cfg.moneda), None, None,
                     "Raiz del error cuadratico medio"),
                    ("Error % (MAPE)", f"{ev.get('mape', 0):.1f}%", None, None,
                     "Error porcentual medio"),
                ])

            hist = res["historial"].rename(columns={"anio_mes": "Periodo", "ingresos": "Valor"}).assign(tipo="Historial")
            pred = res["predicciones"].rename(columns={"fecha": "Periodo", "ingresos_predichos": "Valor"}).assign(tipo="Prediccion")
            combinado = pd.concat([hist, pred])
            with c.panel("Ingresos historicos y proyeccion", "Historial real frente a proyeccion",
                         icono=":material/trending_up:"):
                st.plotly_chart(c.grafico_linea(
                    combinado, "Periodo", "Valor", color="tipo",
                    etiquetas={"Periodo": "Mes", "Valor": "Ingresos"},
                ), width="stretch", height="stretch")

            col1, col2 = st.columns(2, vertical_alignment="center")
            with col1:
                with c.panel("Proyeccion", "Ingresos estimados a futuro"):
                    st.dataframe(res["predicciones"], width="stretch", column_config={
                        "ingresos_predichos": st.column_config.NumberColumn("Ingresos", format="$#,##0"),
                    })
            with col2:
                with c.panel("Historico (ultimos 12)", "Ingresos observados recientes"):
                    st.dataframe(hist.tail(12), width="stretch", column_config={
                        "Valor": st.column_config.NumberColumn("Ingresos", format="$#,##0"),
                    })

    with tab_dem:
        if tab_dem.open:
            c.titulo_seccion("Demanda proyectada por servicio", "Regresion lineal por servicio",
                             icono=":material/query_stats:")
            dem = predictor.predecir_demanda(horizonte_meses=6)
            if dem["predicciones"].empty:
                c.vacio("Datos insuficientes para proyectar demanda.",
                        icono=":material/query_stats:")
            else:
                pred_df = dem["predicciones"]
                with c.panel("Proyeccion de demanda", "Demanda estimada por servicio y mes",
                             icono=":material/query_stats:"):
                    st.plotly_chart(c.grafico_linea(
                        pred_df, "fecha", "demanda_predicha", color="servicio",
                        etiquetas={"fecha": "Mes", "demanda_predicha": "Demanda estimada"},
                    ), width="stretch", height="stretch")
                st.markdown("**Tendencias detectadas**")
                st.dataframe(dem["tendencias"], width="stretch")
                with st.expander("Ver tabla completa de demanda", icon=":material/table_chart:"):
                    tabla = pred_df.pivot_table(index="fecha", columns="servicio",
                                                values="demanda_predicha", aggfunc="sum")
                    st.dataframe(tabla.style.format("{:.1f}"), width="stretch")

    with tab_churn:
        if tab_churn.open:
            c.titulo_seccion("Probabilidad de churn", "Clientes que podrian irse (Random Forest)",
                             icono=":material/person_off:")
            churn = predictor.predecir_churn()

            if churn.get("evaluacion"):
                ev = churn["evaluacion"]
                if ev.get("accuracy") is not None:
                    c.kpi_grid([
                        ("Precision (accuracy)", f"{ev['accuracy']:.2f}", None, None,
                         "Exactitud del modelo"),
                        ("Score F1", f"{ev['f1']:.2f}", None, None, "F1 balanceado"),
                        ("En riesgo (90d+)", f"{ev.get('num_churn_detectado', 0)}", None, None,
                         "Clientes detectados en riesgo"),
                        ("Tasa de churn", f"{ev.get('tasa_churn', 0):.1f}%", None, None,
                         "Proporcion de clientes en riesgo"),
                    ])
                elif ev.get("nota"):
                    st.info(ev["nota"], icon=":material/info:")

            resultados = churn["resultados"]
            con_prob = "prob_churn" in resultados.columns
            if con_prob:
                top = resultados.sort_values("prob_churn", ascending=False).head(15)
                with c.panel("Mayor probabilidad de churn", "Ranking de clientes en riesgo",
                             icono=":material/person_off:"):
                    st.plotly_chart(c.grafico_barras(
                        top, "nombre", "prob_churn", color="churn", color_cont="RdYlGn_r",
                        etiquetas={"nombre": "Cliente", "prob_churn": "Probabilidad"},
                    ), width="stretch", height="stretch")
                st.markdown("**Ranking completo**")
                st.dataframe(
                    resultados[["nombre", "recencia", "frecuencia", "monto", "churn", "prob_churn"]],
                    width="stretch", height=340,
                    column_config={
                        "prob_churn": st.column_config.ProgressColumn("Prob. churn", format="%.0f%%",
                                                                      min_value=0, max_value=1),
                        "monto": st.column_config.NumberColumn("Monto", format="$#,##0"),
                    },
                )
            else:
                st.dataframe(resultados, width="stretch")

    with tab_inv:
        if tab_inv.open:
            c.titulo_seccion("Reposicion sugerida de inventario",
                             "Reglas de rotacion y cobertura por producto",
                             icono=":material/inventory_2:")
            inv_pred = predictor.predecir_inventario()
            st.dataframe(
                inv_pred[["producto", "categoria", "stock_actual", "stock_minimo",
                          "tasa_rotacion_mensual", "meses_cobertura", "recomendacion",
                          "valor_stock", "margen_unitario"]],
                width="stretch", height=380,
                column_config={
                    "meses_cobertura": st.column_config.NumberColumn("Cobertura (meses)", format="%.1f"),
                    "tasa_rotacion_mensual": st.column_config.NumberColumn("Rotacion mensual", format="%.2f"),
                    "valor_stock": st.column_config.NumberColumn("Valor stock", format="$#,##0"),
                    "margen_unitario": st.column_config.NumberColumn("Margen unit.", format="$#,##0"),
                },
            )


if __name__ == "__main__":
    principal()