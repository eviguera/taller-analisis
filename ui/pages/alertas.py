"""Pagina: Alertas y notificaciones (reglas de negocio evaluadas sobre los datos)."""

import pandas as pd
import streamlit as st

from ui import components as c
from ui.context import en_kiosco, exigir_escritura, obtener_estado
from src.alerts import evaluar_alertas, resumen_alertas, generar_reporte_alertas, enviar_email

COLOR = {"critica": "rojo", "media": "amarillo", "baja": "azul"}


def _css_estructura() -> None:
    """Reparaciones estructurales de accesibilidad de la pagina.

    Foco visible explicito, targets de accion de 44px y prosa ancha a 65ch
    (los detalles de cada alerta son frases largas). Va en CSS porque
    Streamlit no expone esos ajustes como widgets; el salto al contenido
    (skip-link) depende del shell de la app, no de esta pantalla.
    """
    try:
        oscuro = st.context.theme.type == "dark"
    except Exception:  # noqa: BLE001 (st.context fuera de runtime: se asume claro)
        oscuro = False
    contorno = "#60a5fa" if oscuro else "#2563eb"
    st.markdown(
        f"""
<style>
/* Foco visible explicito en todo lo interactivo (AA). */
a:focus-visible, button:focus-visible, input:focus-visible,
textarea:focus-visible, select:focus-visible, [role="tab"]:focus-visible {{
    outline: 3px solid {contorno};
    outline-offset: 2px;
}}
/* Targets de accion >= 44px: botones y descargas. */
[data-testid="stButton"] button,
[data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button {{
    min-height: 44px;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}}
[data-testid="stButton"] button:hover:not(:disabled),
[data-testid="stDownloadButton"] button:hover,
[data-testid="stFormSubmitButton"] button:hover {{
    transform: translateY(-1px);
    box-shadow: 0 4px 10px rgba(15, 23, 42, 0.18);
}}
/* Prosa larga a 65ch; los graficos van a todo el ancho. */
[data-testid="stMarkdownContainer"] p {{
    max-width: 65ch;
}}
</style>
""",
        unsafe_allow_html=True,
    )


def principal():
    _css_estructura()
    cfg, data, analyzer, predictor = obtener_estado()

    c.cabecera(
        "Alertas",
        "Reglas de negocio monitorizadas: stock, churn, ingresos y cobranza",
        icono=":material/notifications_active:",
    )

    alertas = evaluar_alertas(cfg, data, analyzer=analyzer, predictor=predictor)
    res = resumen_alertas(alertas)

    c.kpi_grid([
        ("Alertas activas", c.miles(res['total']), None, None, "Reglas que se dispararon"),
        ("Criticas", c.miles(res['critica']), None, None, "Requieren accion inmediata"),
        ("Medias", c.miles(res['media']), None, None, "Requieren seguimiento"),
        ("Tipos distintos", c.miles(len(res['por_tipo'])), None, None,
         "Reglas con al menos una alerta"),
    ])
    if res["por_tipo"]:
        tipo_df = pd.DataFrame(list(res["por_tipo"].items()),
                               columns=["Regla", "Alertas"])
        # Sin columns: el panel era la unica columna y col2 quedaba en blanco.
        with c.panel("Alertas por regla", "Que se esta disparando"):
            c.mostrar_grafico(c.grafico_barras(
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
        # Unica accion primaria de la pantalla: generar el reporte.
        if st.button("Generar reporte HTML", type="primary",
                     icon=":material/description:", disabled=en_kiosco()):
            with st.status("Generando reporte…", expanded=False) as estado:
                ruta = generar_reporte_alertas(cfg, data, alertas)
            estado.update(label="Reporte listo", state="complete", expanded=False)
            st.success(f"Reporte generado: `{ruta.name}`. Descárgalo abajo.")
            with open(ruta, "rb") as fh:
                st.download_button(
                    "Descargar reporte", fh.read(),
                    file_name=ruta.name, mime="text/html",
                    icon=":material/download:",
                )
    with col2:
        if en_kiosco():
            st.caption("Modo presentacion: el envio se hace fuera del kiosco.")
        if st.button("Enviar por email", icon=":material/send:", disabled=en_kiosco()):
            exigir_escritura("Solo un administrador puede enviar alertas por email.")
            with st.spinner("Enviando alertas por email…"):
                envio = enviar_email(
                    cfg,
                    f"[GIRO] Alertas de {cfg.negocio_nombre}",
                    _html_alerta(alertas, cfg),
                )
            if envio:
                st.success("Alertas enviadas por email.")
            else:
                st.error(
                    "No se pudo enviar el email. Revisa la configuración "
                    "`alertas.smtp` y las credenciales SMTP del entorno."
                )


def _html_alerta(alertas, cfg):
    tarjetas = "".join(
        f"<li><b>{a['titulo']}</b><br><small>{a['detalle']}</small></li>"
        for a in alertas
    ) or "<li>Sin alertas activas.</li>"
    return f"<h3>Alertas {cfg.negocio_nombre}</h3><ul>{tarjetas}</ul>"


if __name__ == "__main__":
    principal()