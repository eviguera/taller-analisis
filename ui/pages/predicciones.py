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
        f"Proyecciones calculadas con {c.miles(n_facturas)} facturas",
        icono=":material/auto_graph:",
    )

    hechos = analyzer.df
    n_meses = (hechos["fecha"].dt.to_period("M").nunique()
               if not hechos.empty and "fecha" in hechos.columns else 0)
    if n_meses == 0:
        c.vacio(
            "Aun no hay facturas para calcular predicciones.",
            icono=":material/auto_graph:",
            detalle="Importa tus facturas en 'Mis datos' y vuelve aqui.",
        )
        return

    tab_ing, tab_dem, tab_churn, tab_inv = st.tabs(
        ["Ingresos", "Demanda de servicios", "Churn de clientes", "Reposicion"],
        key="tabs_predicciones", on_change="rerun",
    )

    with tab_ing:
        if tab_ing.open:
            c.titulo_seccion("Prediccion de ingresos mensuales",
                             "Estima los ingresos de los proximos meses a partir de tu facturacion",
                             icono=":material/trending_up:")
            if n_meses < 5:
                c.vacio(
                    "Todavia no hay suficientes meses de facturas.",
                    icono=":material/trending_up:",
                    detalle="La proyeccion necesita al menos 5 meses de facturas. "
                            "Importa mas datos en 'Mis datos' y vuelve aqui.",
                )
            else:
                meses = st.slider("Meses a proyectar", 1, 12, 6, key="meses_ing")
                with st.spinner("Calculando la proyeccion de ingresos..."):
                    res = predictor.predecir_ingresos(meses_futuros=meses)

                if res.get("evaluacion"):
                    ev = res["evaluacion"]
                    c.kpi_grid([
                        ("Error promedio", c.moneda(ev.get("mae", 0), cfg.moneda), None, None,
                         "MAE: diferencia media entre lo proyectado y lo real, al mes"),
                        ("Error con picos", c.moneda(ev.get("rmse", 0), cfg.moneda), None, None,
                         "RMSE: como el Error promedio, pero penaliza los meses con mas error"),
                        ("Error en porcentaje", f"{ev.get('mape', 0):.1f}%", None, None,
                         "MAPE: error promedio de la proyeccion mensual, en porcentaje"),
                    ])

                hist = res["historial"].rename(columns={"anio_mes": "Periodo", "ingresos": "Valor"}).assign(tipo="Historial")
                pred = res["predicciones"].rename(columns={"fecha": "Periodo", "ingresos_predichos": "Valor"}).assign(tipo="Prediccion")
                combinado = pd.concat([hist, pred])
                with c.panel("Ingresos historicos y proyeccion", "Historial real frente a proyeccion",
                             icono=":material/trending_up:"):
                    fig = c.grafico_linea(
                        combinado, "Periodo", "Valor", color="tipo",
                        etiquetas={"Periodo": "Mes", "Valor": "Ingresos"},
                    )
                    # Linea separadora entre historico y prediccion
                    if not hist.empty and not pred.empty:
                        fig.add_vline(x=len(hist) - 0.5, line_dash="dash",
                                      line_color="gray", annotation_text="Prediccion")
                    c.mostrar_grafico(fig)

                col1, col2 = st.columns(2, vertical_alignment="center")
                with col1:
                    with c.panel("Proyeccion", "Ingresos estimados a futuro"):
                        st.dataframe(res["predicciones"], width="stretch", column_config={
                            "fecha": st.column_config.TextColumn("Mes"),
                            "ingresos_predichos": st.column_config.NumberColumn(
                                "Ingresos proyectados", format=c.formato_moneda(cfg.moneda)),
                            "ic_inferior": st.column_config.NumberColumn(
                                "Minimo probable", format=c.formato_moneda(cfg.moneda),
                                help="Limite inferior del rango probable (95 de cada 100 veces)"),
                            "ic_superior": st.column_config.NumberColumn(
                                "Maximo probable", format=c.formato_moneda(cfg.moneda),
                                help="Limite superior del rango probable (95 de cada 100 veces)"),
                        })
                with col2:
                    with c.panel("Historico (ultimos 12)", "Ingresos observados recientes"):
                        st.dataframe(hist[["Periodo", "Valor"]].tail(12), width="stretch",
                                     column_config={
                                         "Periodo": st.column_config.TextColumn("Mes"),
                                         "Valor": st.column_config.NumberColumn(
                                             "Ingresos", format=c.formato_moneda(cfg.moneda)),
                                     })

    with tab_dem:
        if tab_dem.open:
            c.titulo_seccion("Demanda proyectada por servicio",
                             "Cuanto se va a pedir de cada servicio en los proximos 6 meses",
                             icono=":material/query_stats:")
            with st.spinner("Calculando la demanda por servicio..."):
                dem = predictor.predecir_demanda(horizonte_meses=6)
            if dem["predicciones"].empty:
                c.vacio("Datos insuficientes para proyectar la demanda.",
                        icono=":material/query_stats:",
                        detalle="Se necesitan varios meses de facturas con servicios. "
                                "Importa mas datos en 'Mis datos'.")
            else:
                pred_df = dem["predicciones"]
                with c.panel("Proyeccion de demanda", "Demanda estimada por servicio y mes",
                             icono=":material/query_stats:"):
                    c.mostrar_grafico(c.grafico_linea(
                        pred_df, "fecha", "demanda_predicha", color="servicio",
                        etiquetas={"fecha": "Mes", "demanda_predicha": "Demanda estimada"},
                    ), width="stretch", height="stretch")
                c.titulo_seccion("Tendencias detectadas",
                                 "Cuanto sube o baja la demanda de cada servicio cada mes")
                st.dataframe(dem["tendencias"], width="stretch", column_config={
                    "servicio": st.column_config.TextColumn("Servicio"),
                    "tendencia": st.column_config.NumberColumn(
                        "Cambio al mes", format="%.1f",
                        help="Unidades de demanda que suben o bajan cada mes"),
                })
                with st.expander("Ver tabla completa de demanda", icon=":material/table_chart:"):
                    tabla = pred_df.pivot_table(index="fecha", columns="servicio",
                                                values="demanda_predicha", aggfunc="sum")
                    st.dataframe(tabla.style.format("{:.1f}"), width="stretch")

    with tab_churn:
        if tab_churn.open:
            c.titulo_seccion("Probabilidad de churn",
                             "Riesgo de que un cliente deje de comprar, segun su ultima visita",
                             icono=":material/person_off:")
            with st.spinner("Calculando el riesgo de cada cliente..."):
                churn = predictor.predecir_churn()

            if churn.get("evaluacion"):
                ev = churn["evaluacion"]
                if ev.get("accuracy") is not None:
                    c.kpi_grid([
                        ("Aciertos del modelo", f"{ev['accuracy'] * 100:.0f}%", None, None,
                         "Clientes bien clasificados sobre el total"),
                        ("Balance del modelo", f"{ev['f1'] * 100:.0f}%", None, None,
                         "Score F1: equilibrio entre aciertos y fallos"),
                        ("Clientes en riesgo", c.miles(ev.get("num_churn_detectado", 0)), None, None,
                         "Sin compra en mas de 90 dias"),
                        ("Proporcion en riesgo", f"{ev.get('tasa_churn', 0):.1f}%", None, None,
                         "Tasa de churn: clientes en riesgo sobre el total"),
                    ])
                elif ev.get("nota"):
                    c.vacio("Datos insuficientes para estimar el riesgo de churn.",
                            icono=":material/person_off:",
                            detalle="Con mas facturas de clientes el modelo separa mejor "
                                    "a los que estan en riesgo. Revisa 'Mis datos'.")

            resultados = churn["resultados"]
            config_clientes = {
                "cliente_id": st.column_config.NumberColumn("ID cliente"),
                "nombre": st.column_config.TextColumn("Cliente"),
                "recencia": st.column_config.NumberColumn(
                    "Dias desde la ultima compra", help="Recencia: dias sin comprar"),
                "frecuencia": st.column_config.NumberColumn("Visitas"),
                "monto": st.column_config.NumberColumn(
                    "Monto total", format=c.formato_moneda(cfg.moneda)),
                "primer_visita": st.column_config.DatetimeColumn("Primera visita",
                                                                 format="YYYY-MM-DD"),
                "ultima_visita": st.column_config.DatetimeColumn("Ultima visita",
                                                                 format="YYYY-MM-DD"),
                "usuario_activo_dias": st.column_config.NumberColumn("Dias desde la primera visita"),
                "promedio_gasto": st.column_config.NumberColumn(
                    "Gasto promedio", format=c.formato_moneda(cfg.moneda)),
                "churn": st.column_config.NumberColumn(
                    "En riesgo (1 = si)", help="1 = mas de 90 dias sin compra"),
                "prob_churn": st.column_config.ProgressColumn(
                    "Probabilidad de churn", format="percent", min_value=0, max_value=1),
            }
            if "prob_churn" in resultados.columns:
                top = resultados.sort_values("prob_churn", ascending=False).head(15).copy()
                top["riesgo"] = top["churn"].map({1: "En riesgo", 0: "Sin riesgo"}).fillna("Sin riesgo")
                with c.panel("Mayor probabilidad de churn", "Ranking de clientes en riesgo",
                             icono=":material/person_off:"):
                    c.mostrar_grafico(c.grafico_barras(
                        top, "nombre", "prob_churn", color="riesgo",
                        etiquetas={"nombre": "Cliente", "prob_churn": "Probabilidad de churn",
                                   "riesgo": "Riesgo"},
                    ), width="stretch", height="stretch")
                c.titulo_seccion("Ranking completo",
                                 f"{c.miles(len(resultados))} clientes ordenados por probabilidad")
                st.dataframe(
                    resultados[["nombre", "recencia", "frecuencia", "monto", "churn", "prob_churn"]],
                    width="stretch", height=340,
                    column_config=config_clientes,
                )
            else:
                st.dataframe(resultados, width="stretch", column_config=config_clientes)

    with tab_inv:
        if tab_inv.open:
            c.titulo_seccion("Reposicion sugerida de inventario",
                             "Cuanto stock te queda y cuando conviene pedir",
                             icono=":material/inventory_2:")
            with st.spinner("Calculando la reposicion sugerida..."):
                inv_pred = predictor.predecir_inventario()
            if inv_pred.empty:
                c.vacio("No hay inventario que reposicionar.",
                        icono=":material/inventory_2:",
                        detalle="Carga el dataset de inventario en 'Mis datos' "
                                "y el modelo calcula la reposicion sugerida.")
            else:
                st.dataframe(
                    inv_pred[["producto", "categoria", "stock_actual", "stock_minimo",
                              "demanda_mensual", "meses_cobertura", "cantidad_recomendada",
                              "recomendacion", "valor_stock", "margen_unitario"]],
                    width="stretch", height=380,
                    column_config={
                        "producto": st.column_config.TextColumn("Producto"),
                        "categoria": st.column_config.TextColumn("Categoria"),
                        "stock_actual": st.column_config.NumberColumn("Stock actual"),
                        "stock_minimo": st.column_config.NumberColumn("Stock minimo"),
                        "demanda_mensual": st.column_config.NumberColumn("Demanda (unid/mes)", format="%.1f"),
                        "meses_cobertura": st.column_config.NumberColumn("Cobertura (meses)", format="%.1f"),
                        "cantidad_recomendada": st.column_config.NumberColumn("Pedir (unid)"),
                        "recomendacion": st.column_config.TextColumn("Recomendacion"),
                        "valor_stock": st.column_config.NumberColumn("Valor stock", format=c.formato_moneda(cfg.moneda)),
                        "margen_unitario": st.column_config.NumberColumn("Margen unit.", format=c.formato_moneda(cfg.moneda)),
                    },
                )


if __name__ == "__main__":
    principal()