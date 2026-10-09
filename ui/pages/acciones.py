"""Pagina: Acciones (Giro Recomienda: next best action + mantenimiento predictivo + modelos)."""

import numpy as np
import pandas as pd
import streamlit as st

from ui import components as c
from ui.context import en_kiosco, exigir_escritura, obtener_estado
from src.recomendaciones import next_best_action, proximo_servicio

#: Nombre legible de cada tipo de modelo persistido.
NOMBRES_MODELO = {
    "ingresos": "Ingresos mensuales",
    "churn": "Clientes en riesgo",
}


def _resumen_metricas(evaluacion, moneda):
    """Metricas de un modelo como texto legible: etiqueta en espanol y unidad.

    La tabla de modelos mostraba ``str(dict)``, con cifras crudas sin unidad.
    Aqui cada clave conocida se traduce y se formatea; lo desconocido pasa
    tal cual para que el dato nunca se pierda.
    """
    claves = {
        "mae": ("Error medio", lambda v: c.moneda(v, moneda)),
        "rmse": ("Error con picos", lambda v: c.moneda(v, moneda)),
        "naive_mae": ("Error del promedio historico", lambda v: c.moneda(v, moneda)),
        "mape": ("Error en porcentaje", lambda v: f"{v:.1f}%"),
        "accuracy": ("Aciertos", lambda v: f"{v * 100:.0f}%"),
        "f1": ("Balance", lambda v: f"{v * 100:.0f}%"),
        "tasa_churn": ("En riesgo (% del total)", lambda v: f"{v:.1f}%"),
        "num_churn_detectado": ("Clientes en riesgo", lambda v: c.miles(v)),
        "nota": ("Nota", str),
    }
    partes = []
    for clave, valor in (evaluacion or {}).items():
        if clave in ("features_importantes", "fuente"):
            continue
        etiqueta, formatear = claves.get(clave, (clave, None))
        partes.append(f"{etiqueta}: {formatear(valor) if formatear else valor}")
    return " · ".join(partes) or "Sin metricas todavia"


def principal():
    cfg, data, analyzer, predictor = obtener_estado()

    c.cabecera(
        "Acciones recomendadas",
        "Que hacer, con que cliente y por que canal, ordenado por prioridad",
        icono=":material/task_alt:",
    )

    tab_aba, tab_mant, tab_modelos = st.tabs(
        ["Acciones por cliente", "Proximo mantenimiento", "Modelos"],
        key="tabs_acciones", on_change="rerun",
    )

    with tab_aba:
        if tab_aba.open:
            acciones = next_best_action(data, cfg, predictor=predictor)
            if acciones.empty:
                c.vacio("Sin facturas suficientes para calcular acciones.",
                        icono=":material/task_alt:",
                        detalle="Se necesitan facturas y clientes con historial. "
                                "Importa tus datos en 'Mis datos'.")
            else:
                criticas = acciones["accion"].isin(["Reactivar", "Recordatorio preventivo"]).sum()
                c.kpi_grid([
                    ("Acciones sugeridas", c.miles(len(acciones)), None, None,
                     "Clientes priorizados con accion concreta"),
                    ("Para reactivar o recordar", c.miles(criticas), None, None,
                     "Acciones de retencion y mantenimiento preventivo"),
                    ("Riesgo promedio", f"{acciones['prob_churn'].mean():.0%}", None, None,
                     "Probabilidad media de perder a estos clientes"),
                ])

                with c.panel("Cola de acciones priorizada",
                             "Se ordena por riesgo de perder al cliente (55%), valor (30%) "
                             "e inactividad (15%)",
                             icono=":material/task_alt:"):
                    st.dataframe(
                        acciones[["nombre", "accion", "canal", "mensaje", "prioridad",
                                  "prob_churn", "monto", "recencia_dias", "servicio_sugerido"]],
                        width="stretch", height=420,
                        column_config={
                            "nombre": st.column_config.TextColumn("Cliente"),
                            "accion": st.column_config.TextColumn("Accion"),
                            "canal": st.column_config.TextColumn("Canal"),
                            "mensaje": st.column_config.TextColumn("Mensaje"),
                            "servicio_sugerido": st.column_config.TextColumn("Servicio sugerido"),
                            "prob_churn": st.column_config.ProgressColumn(
                                "Riesgo de churn", format="percent", min_value=0, max_value=1),
                            "monto": st.column_config.NumberColumn("Monto", format=c.formato_moneda(cfg.moneda)),
                            "prioridad": st.column_config.NumberColumn("Prioridad", format="%.2f"),
                            "recencia_dias": st.column_config.NumberColumn(
                                "Dias desde la ultima visita"),
                        },
                    )
                top6 = acciones.head(6)
                colores = np.where(top6["accion"] == "Reactivar", "rojo",
                          np.where(top6["accion"] == "Recordatorio preventivo", "amarillo", "azul"))
                etiquetas = top6["accion"] + " → " + top6["nombre"]
                c.titulo_seccion("Acciones mas urgentes",
                                 "Las 6 primeras de la cola, listas para enviar")
                lineas = [f"- {c.badge(et, col)} — {canal}: _{msj}_"
                          for et, col, canal, msj in zip(etiquetas, colores, top6["canal"], top6["mensaje"])]
                st.markdown("\n".join(lineas))
                c.descargar(acciones, "next_best_action")

    with tab_mant:
        if tab_mant.open:
            progs = proximo_servicio(data, cfg)
            if progs.empty:
                c.vacio("Sin vehiculos o sin facturas para proyectar el mantenimiento.",
                        icono=":material/directions_car:",
                        detalle="Importa tus vehiculos y facturas en 'Mis datos' "
                                "y vuelve aqui.")
            else:
                urgentes = int((progs["prioridad"] >= 4).sum())
                c.kpi_grid([
                    ("Vehiculos evaluados", c.miles(len(progs)), None, None,
                     "Vehiculos con mantenimiento proyectado"),
                    ("Servicios urgentes", c.miles(urgentes), None, None,
                     "Mantenimientos con prioridad alta"),
                    ("Mas dias sin visita",
                     f"{c.miles(progs['dias_sin_visita'].max())} dias", None, None,
                     "Vehiculo que mas tiempo lleva sin volver"),
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
                            "cliente": st.column_config.TextColumn("Cliente"),
                            "marca": st.column_config.TextColumn("Marca"),
                            "modelo": st.column_config.TextColumn("Modelo"),
                            "placa": st.column_config.TextColumn("Placa"),
                            "anio": st.column_config.NumberColumn("Anio"),
                            "kilometraje": st.column_config.NumberColumn("Kilometraje (km)", format="%d"),
                            "dias_sin_visita": st.column_config.NumberColumn("Dias sin visita"),
                            "servicio_sugerido": st.column_config.TextColumn("Servicio sugerido"),
                            "nota": st.column_config.TextColumn("Estado"),
                            "meses_estimados": st.column_config.NumberColumn(
                                "Meses desde el ultimo servicio", format="%.1f"),
                            "intervalo_meses": st.column_config.NumberColumn(
                                "Cada cuantos meses", format="%.0f"),
                            "prioridad": st.column_config.NumberColumn("Prioridad", format="%.0f"),
                        },
                    )
                c.descargar(progs, "mantenimiento_predictivo")

    with tab_modelos:
        if tab_modelos.open:
            c.titulo_seccion("Registro de modelos",
                             "Se guardan y se usan en cada visita sin volver a entrenar",
                             icono=":material/model_training:")
            modelos = predictor.registro_modelos()
            if modelos:
                filas = []
                for m in modelos:
                    n_muestras = m.get("n_muestras")
                    filas.append({
                        "Modelo": NOMBRES_MODELO.get(m.get("tipo"), m.get("tipo") or "?"),
                        "Entrenado": m.get("fecha_entrenamiento", ""),
                        "Muestras": (c.miles(n_muestras)
                                     if isinstance(n_muestras, (int, float))
                                     else str(n_muestras or "")),
                        "Metricas": _resumen_metricas(m.get("evaluacion"), cfg.moneda),
                        "Guardado": bool(m.get("existe_modelo", False)),
                    })
                st.dataframe(
                    pd.DataFrame(filas),
                    width="stretch",
                    column_config={"Guardado": st.column_config.CheckboxColumn("Guardado")},
                )
            else:
                c.vacio("Aun no hay modelos guardados.",
                        icono=":material/model_training:",
                        detalle="Entrena los modelos en la pagina de Predicciones "
                                "y se guardaran automaticamente.")

            if en_kiosco():
                st.caption("Modo presentacion: los modelos se reentrenan fuera del kiosco.")
            if st.button("Reentrenar todos los modelos", icon=":material/restart_alt:",
                         disabled=en_kiosco()):
                exigir_escritura("Solo un administrador puede reentrenar los modelos.")
                with st.spinner("Preparando el reentrenamiento..."):
                    for tipo in ("churn", "ingresos"):
                        predictor.reentrenar(tipo)
                st.cache_resource.clear()
                st.session_state["reentrenamiento_listo"] = True
                st.rerun()
            if st.session_state.pop("reentrenamiento_listo", False):
                c.confirmacion_exito(
                    "Modelos reentrenados.",
                    "Se actualizan solos en la proxima visita a la pagina de Predicciones.")


if __name__ == "__main__":
    principal()