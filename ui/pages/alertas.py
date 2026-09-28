"""Pagina: Alertas y notificaciones (reglas de negocio evaluadas sobre los datos)."""

import pandas as pd
import streamlit as st

from ui import components as c
from ui.context import obtener_estado
from src.alerts import evaluar_alertas, resumen_alertas, generar_reporte_alertas, enviar_email

COLOR = {"critica": "rojo", "media": "amarillo", "baja": "azul"}


def principal():
    cfg, data, analyzer, predictor = obtener_estado()

    c.cabecera(
        "Alertas",
        "Reglas de negocio monitorizadas: stock, churn, ingresos y cobranza",
        icono=":material/notifications_active:",
    )

    alertas = evaluar_alertas(cfg, data)
    res = resumen_alertas(alertas)

    c.kpi_grid([
        ("Alertas activas", f"{res['total']}", None, None, "Reglas que se dispararon"),
        ("Criticas", f"{res['critica']}", None, None, "Requieren accion inmediata"),
        ("Medias", f"{res['media']}", None, None, "Requieren seguimiento"),
        ("Tipos distintos", f"{len(res['por_tipo'])}", None, None,
         "Reglas con al menos una alerta"),
    ])
    if res["por_tipo"]:
        tipo_df = pd.DataFrame(list(res["por_tipo"].items()),
                               columns=["Regla", "Alertas"])
        col1, col2 = st.columns([1, 2], vertical_alignment="center")
        with col1:
            with c.panel("Alertas por regla", "Que se esta disparando"):
                st.plotly_chart(c.grafico_barras(
                    tipo_df, "Regla", "Alertas", color_cont="Reds",
                    etiquetas={"Regla": "Regla", "Alertas": "Alertas"},
                ), width="stretch", height="stretch")

    st.markdown("## Detalle de alertas")
    if not alertas:
        st.success("Sin alertas activas en este momento.", icon=":material/verified:")
    for a in alertas:
        with st.container(border=True):
            st.markdown(
                f"{c.badge(a['severidad'].upper(), COLOR.get(a['severidad'], 'info'))} "
                f"**{a['titulo']}**"
            )
            st.caption(a["detalle"])

    st.markdown("### Reporte y notificacion")
    col1, col2 = st.columns(2, vertical_alignment="center")
    with col1:
        if st.button("Generar reporte HTML", icon=":material/description:"):
            ruta = generar_reporte_alertas(cfg, data, alertas)
            st.success(f"Reporte generado en `{ruta.name}`")
            with open(ruta, "rb") as fh:
                st.download_button(
                    "Descargar reporte", fh.read(),
                    file_name=ruta.name, mime="text/html",
                    icon=":material/download:",
                )
    with col2:
        if st.button("Enviar por email", icon=":material/send:"):
            envio = enviar_email(
                cfg,
                f"[GIRO] Alertas de {cfg.negocio_nombre}",
                _html_alerta(alertas, cfg),
            )
            if envio:
                st.success("Alertas enviadas por email.")
            else:
                st.info("SMTP no configurado: revisa `alertas.smtp` y la variable de entorno.")


def _html_alerta(alertas, cfg):
    tarjetas = "".join(
        f"<li><b>{a['titulo']}</b><br><small>{a['detalle']}</small></li>"
        for a in alertas
    ) or "<li>Sin alertas activas.</li>"
    return f"<h3>Alertas {cfg.negocio_nombre}</h3><ul>{tarjetas}</ul>"


if __name__ == "__main__":
    principal()