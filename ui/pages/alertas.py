"""Pagina: Alertas y notificaciones (reglas de negocio evaluadas sobre los datos)."""

import pandas as pd
import streamlit as st

from ui import components as c
from ui.context import en_kiosco, exigir_escritura, obtener_estado
from src.alerts import generar_reporte_alertas, enviar_email
from src.alertas_avanzadas import (
    evaluar_alertas_avanzadas,
    resumen_alertas_avanzadas,
)
from src.memoria import (
    agregar_mute,
    eliminar_mute,
    inicializar_db,
    listar_mutes,
    ruta_db_por_workspace,
)

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
    c.html(
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
    )


def principal():
    _css_estructura()
    try:
        cfg, data, analyzer, predictor = obtener_estado()
    except Exception as e:  # nunca falle silenciosamente
        c.mensaje_error(
            "No se pudieron cargar los datos de alertas.",
            detalle=str(e) if str(e) else "Revisa que el almacén del workspace esté disponible.",
        )
        return

    c.cabecera(
        "Alertas",
        "Reglas de negocio monitorizadas: stock, churn, ingresos y cobranza",
        icono=":material/notifications_active:",
    )

    db_path = ruta_db_por_workspace(cfg.directorio_datos)
    try:
        inicializar_db(db_path)
    except Exception as e:  # noqa: BLE001
        c.mensaje_error(
            "No se pudo inicializar el ledger de alertas.",
            detalle=str(e) if str(e) else "",
        )
        return

    try:
        alertas = evaluar_alertas_avanzadas(cfg, data, analyzer=analyzer, predictor=predictor)
        res = resumen_alertas_avanzadas(alertas)
    except Exception as e:
        c.mensaje_error(
            "No se pudieron evaluar las reglas de alerta.",
            detalle=str(e) if str(e) else "Revisa que existan datos de inventario y facturación.",
        )
        return

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
            c.html(
                f"{c.badge(a['severidad'].upper(), COLOR.get(a['severidad'], 'info'))} "
                f"**{a['titulo']}**"
            )
            st.caption(a["detalle"])

    # ---- Mutes de alertas ----
    st.markdown("## Silenciar alertas (mutes)")
    st.caption(
        "Evita que una regla de alerta siga disparando para un tipo y entidad "
        "determinados durante un período."
    )

    try:
        mutes_activos = listar_mutes(db_path=db_path)
    except Exception as e:  # noqa: BLE001
        c.mensaje_error("No se pudieron leer los mutes.", detalle=str(e))
        mutes_activos = []

    col_m1, col_m2 = st.columns([3, 1])
    with col_m1:
        with st.form("form_mute_alerta", border=False):
            mute_tipo = st.text_input(
                "Tipo de alerta", key="inp_mute_tipo_alerta",
                placeholder="ej: stock_bajo, churn, caida_ingresos"
            )
            mute_entidad = st.text_input(
                "Entidad", key="inp_mute_entidad_alerta",
                placeholder="ej: producto X, cliente Y"
            )
            mute_hasta = st.date_input("Silenciar hasta", key="inp_mute_hasta_alerta")
            mute_motivo = st.text_input("Motivo", key="inp_mute_motivo_alerta")
            submitted_mute = st.form_submit_button("Agregar mute", type="primary")
        if submitted_mute and not en_kiosco():
            try:
                exigir_escritura()
                if not mute_tipo.strip() or not mute_entidad.strip():
                    c.mensaje_error("Tipo y entidad son obligatorios.")
                else:
                    hasta_iso = f"{mute_hasta.isoformat()}T23:59:59+00:00"
                    agregar_mute(
                        tipo=mute_tipo.strip(),
                        entidad=mute_entidad.strip(),
                        hasta_iso=hasta_iso,
                        motivo=mute_motivo.strip(),
                        db_path=db_path,
                    )
                    c.confirmacion_exito("Mute agregado.")
                    st.rerun()
            except Exception as exc:  # noqa: BLE001
                c.mensaje_error("No se pudo agregar el mute.", detalle=str(exc))

    if mutes_activos:
        st.markdown("### Mutes activos")
        for m in mutes_activos:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.markdown(f"**{m.tipo}** · {m.entidad}")
                    st.caption(f"Hasta: {m.hasta[:16]} · Motivo: {m.motivo or '—'}")
                with col2:
                    st.caption(f"Creado: {m.creada_en[:16]}")
                with col3:
                    if not en_kiosco():
                        if st.button("Eliminar", key=f"delmute_{m.id}", width="stretch"):
                            try:
                                exigir_escritura()
                                if eliminar_mute(m.id, db_path=db_path):
                                    c.confirmacion_exito("Mute eliminado.")
                                    st.rerun()
                                else:
                                    c.mensaje_error("No se encontró el mute.")
                            except Exception as exc:  # noqa: BLE001
                                c.mensaje_error("No se pudo eliminar el mute.", detalle=str(exc))
                    else:
                        st.caption("Solo lectura")
    else:
        c.vacio("Sin mutes activos.", icono=":material/volume_off:")

    st.markdown("### Reporte y notificacion")
    col1, col2 = st.columns(2, vertical_alignment="center")
    with col1:
        # Unica accion primaria de la pantalla: generar el reporte.
        if st.button("Generar reporte HTML", type="primary",
                     icon=":material/description:", disabled=en_kiosco()):
            with st.status("Generando reporte…", expanded=False) as estado:
                try:
                    ruta = generar_reporte_alertas(cfg, data, alertas)
                except Exception as e:
                    estado.update(label="Error generando reporte", state="error", expanded=False)
                    c.mensaje_error(
                        "No se pudo generar el reporte HTML.",
                        detalle=str(e) if str(e) else "Revisa que exista el directorio de reportes del workspace.",
                    )
                    ruta = None
            if ruta is not None:
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
        else:
            if st.button(
                "Enviarme resumen por email",
                type="primary",
                icon=":material/send:",
                disabled=en_kiosco(),
                width="stretch",
            ):
                # En modo unico negocio cualquier usuario puede enviar;
                # en modo multiempresa solo administrador.
                if not context.es_modo_unico():
                    exigir_escritura("Solo un administrador puede enviar alertas por email.")
                with st.spinner("Enviando alertas por email…"):
                    try:
                        envio = enviar_email(
                            cfg,
                            f"[GIRO] Alertas de {cfg.negocio_nombre}",
                            _html_alerta(alertas, cfg),
                        )
                    except Exception as e:
                        envio = False
                        c.mensaje_error(
                            "No se pudo enviar el email de alertas.",
                            detalle=str(e) if str(e) else "Revisa la configuración SMTP en alertas.smtp del workspace.",
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