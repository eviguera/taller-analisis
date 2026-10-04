"""Pagina: Acciones (Giro Recomienda: next best action + mantenimiento predictivo + modelos)."""

import numpy as np
import pandas as pd
import streamlit as st

from ui import components as c
from ui.context import obtener_estado
from src.recomendaciones import next_best_action, proximo_servicio


def principal():
    cfg, data, analyzer, predictor = obtener_estado()

    c.cabecera(
        "Acciones recomendadas",
        "De la analitica a la accion: que hacer y con quien (next best action)",
        icono=":material/task_alt:",
    )

    tab_aba, tab_mant, tab_modelos = st.tabs(
        ["Next best action", "Mantenimiento predictivo", "Modelos"],
        key="tabs_acciones", on_change="rerun",
    )

    with tab_aba:
        if tab_aba.open:
            acciones = next_best_action(data, cfg)
            if acciones.empty:
                c.vacio("Sin facturas suficientes para calcular acciones.",
                        icono=":material/task_alt:")
            else:
                criticas = acciones["accion"].isin(["Reactivar", "Recordatorio preventivo"]).sum()
                c.kpi_grid([
                    ("Acciones sugeridas", f"{len(acciones)}", None, None,
                     "Clientes priorizados con accion concreta"),
                    ("Reactivar / recordar", f"{criticas}", None, None,
                     "Acciones de retencion y preventivo"),
                    ("Prob. churn media", f"{acciones['prob_churn'].mean():.0%}", None, None,
                     "Riesgo promedio de la cola priorizada"),
                ])

                with c.panel("Cola de acciones priorizada",
                             "Prioridad = riesgo churn (55%) + valor (30%) + inactividad (15%)",
                             icono=":material/task_alt:"):
                    st.dataframe(
                        acciones[["nombre", "accion", "canal", "mensaje", "prioridad",
                                  "prob_churn", "monto", "recencia_dias", "servicio_sugerido"]],
                        width="stretch", height=420,
                        column_config={
                            "prob_churn": st.column_config.ProgressColumn(
                                "Riesgo", format="percent", min_value=0, max_value=1),
                            "monto": st.column_config.NumberColumn("Monto", format=c.formato_moneda(cfg.moneda)),
                            "prioridad": st.column_config.NumberColumn("Prioridad", format="%.2f"),
                            "recencia_dias": st.column_config.NumberColumn("Recencia (dias)"),
                        },
                    )
                top6 = acciones.head(6)
                colores = np.where(top6["accion"] == "Reactivar", "rojo",
                          np.where(top6["accion"] == "Recordatorio preventivo", "amarillo", "azul"))
                etiquetas = top6["accion"] + " → " + top6["nombre"]
                lineas = [f"- {c.badge(et, col)} — {canal}: _{msj}_"
                          for et, col, canal, msj in zip(etiquetas, colores, top6["canal"], top6["mensaje"])]
                st.markdown("\n".join(lineas))
                c.descargar(acciones, "next_best_action")

    with tab_mant:
        if tab_mant.open:
            progs = proximo_servicio(data, cfg)
            if progs.empty:
                c.vacio("Sin vehiculos o sin catalogo de mantenimiento configurado.",
                        icono=":material/directions_car:")
            else:
                urgentes = int((progs["prioridad"] >= 4).sum())
                c.kpi_grid([
                    ("Vehiculos evaluados", f"{len(progs)}", None, None,
                     "Vehiculos con mantenimiento proyectado"),
                    ("Servicios urgentes", f"{urgentes}", None, None,
                     "Urgencia alta (vence pronto)"),
                    ("Sin visita", f"{int(progs['dias_sin_visita'].max())} dias max",
                     None, None, "Dias sin visita del vehiculo mas inactivo"),
                ])
                with c.panel("Proximo servicio por vehiculo",
                             "Segun intervalo de mantenimiento y ultimo servicio realizado",
                             icono=":material/build:"):
                    st.dataframe(
                        progs[["cliente", "marca", "modelo", "placa", "anio", "kilometraje",
                               "dias_sin_visita", "servicio_sugerido", "nota",
                               "meses_estimados", "intervalo_meses", "prioridad"]],
                        width="stretch", height=400,
                        column_config={
                            "kilometraje": st.column_config.NumberColumn("Km", format="%d"),
                            "dias_sin_visita": st.column_config.NumberColumn("Dias sin visita"),
                            "meses_estimados": st.column_config.NumberColumn("Desde ultimo (meses)", format="%.1f"),
                            "intervalo_meses": st.column_config.NumberColumn("Intervalo", format="%.0f"),
                            "prioridad": st.column_config.NumberColumn("Prioridad", format="%.0f"),
                        },
                    )
                c.descargar(progs, "mantenimiento_predictivo")

    with tab_modelos:
        if tab_modelos.open:
            c.titulo_seccion("Registry de modelos",
                             "Modelos persistentes: no se re-entrenan en cada sesion",
                             icono=":material/model_training:")
            modelos = predictor.registro_modelos()
            if modelos:
                st.dataframe(
                    pd.DataFrame([
                        {
                            "Modelo": m.get("tipo"),
                            "Entrenado": m.get("fecha_entrenamiento", ""),
                            "Muestras": m.get("n_muestras", ""),
                            "Metricas": str({k: v for k, v in (m.get("evaluacion") or {}).items()
                                             if k != "features_importantes"}),
                            "Modelo guardado": m.get("existe_modelo", False),
                        }
                        for m in modelos
                    ]),
                    width="stretch",
                    column_config={"Modelo guardado": st.column_config.CheckboxColumn("Guardado")},
                )
            else:
                st.info("Aun no hay modelos persistidos. Entrena en la pagina de Predicciones "
                        "y se guardaran automaticamente.")

            if st.button("Reentrenar todos los modelos", icon=":material/restart_alt:"):
                for tipo in ("churn", "ingresos"):
                    predictor.reentrenar(tipo)
                st.cache_resource.clear()
                st.rerun()


if __name__ == "__main__":
    principal()