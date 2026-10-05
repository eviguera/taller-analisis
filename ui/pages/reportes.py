"""Pagina: Reportes ejecutivos (producto reventa, white-label).

Genera PDF/HTML automaticos por tipo, con la marca de la consultora que
entrega y el analisis estrategico del workspace activo. Es la cara visible
de GIRO Reportes para el reventor: configurar marca, generar y descargar.
"""

from datetime import datetime
from pathlib import Path

import streamlit as st

from src.reporting import catalogo, por_clave
from src.reporting import branding as br_mod
from src.reporting.engine import GeneradorReportes, listar_generados

from ui import components as c
from ui.context import en_kiosco, exigir_escritura, obtener_estado


def _ruta_config(cfg) -> Path:
    """Ruta al config.yaml del workspace activo (para persistir marca)."""
    base = Path(__file__).resolve().parent.parent.parent
    if (cfg.clave or "principal") == "principal":
        return base / "config" / "config.yaml"
    return base / "workspaces" / cfg.clave / "config" / "config.yaml"


def _guardar_branding(cfg, cambios: dict):
    """Persiste los campos de branding del reporte en el config del workspace."""
    import yaml
    ruta = _ruta_config(cfg)
    raw = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    reportes = dict(raw.get("reportes") or {})
    branding = dict(reportes.get("branding") or {})
    branding.update({k: v for k, v in cambios.items() if v is not None and v != ""})
    reportes["branding"] = branding
    raw["reportes"] = reportes
    ruta.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")


def _generar(cfg, data, tipo: str, ocasion_label: str) -> list:
    """Genera el/los reportes y devuelve las rutas creadas."""
    gen = GeneradorReportes(cfg, data)
    if tipo == catalogo.TODOS:
        metas = gen.generar_todos(ocasion_label=ocasion_label)
    else:
        metas = [gen.generar(tipo, ocasion_label=ocasion_label)[1]]
    return [m["archivo"] for m in metas]


def _componente_html(ruta_html: str, alto: int = 780):
    try:
        st.iframe(srcdoc=Path(ruta_html).read_text(encoding="utf-8"),
                  height=int(alto), scrolling=True)
    except Exception as e:  # noqa: BLE001
        st.warning(f"No se pudo previsualizar el reporte: {e}")


def _boton_descarga(ruta_html: str):
    import platform
    import subprocess
    ruta = Path(ruta_html)
    contenido = ruta.read_bytes()
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "Descargar HTML", contenido, file_name=ruta.name,
            mime="text/html", icon=":material/download:", width="stretch",
        )
    with c2:
        # `open` solo existe en macOS; el boton se oculta en servidor o en
        # Linux donde seria un no-op silencioso. Lista sin shell: la ruta
        # nunca se interpreta como comando.
        if platform.system() == "Darwin":
            if st.button("Abrir en el navegador", icon=":material/open_in_new:",
                         width="stretch", key="rpt_abrir"):
                try:
                    subprocess.run(["open", str(ruta)], check=False,
                                   capture_output=True, timeout=10)
                    st.toast("Reporte abierto en el navegador.")
                except Exception as e:  # noqa: BLE001
                    c.mensaje_error("No se pudo abrir el reporte.",
                                    detalle=f"{type(e).__name__}: {e}")
        else:
            st.caption("Descarga el HTML y ábrelo en tu navegador.")


def principal():
    cfg, data, _, _ = obtener_estado()

    c.cabecera(
        "Reportes ejecutivos",
        f"{cfg.negocio_nombre} · GIRO Reportes genera documentos autoanalizados "
        "con la marca de tu consultora (white-label)",
        icono=":material/description:",
    )

    if len(data) < 3:
        c.vacio(
            "Faltan datasets para generar reportes.",
            icono=":material/database_off:",
            detalle="Importa tus datos en 'Mis datos' antes de generar.",
        )
        return

    # ------------------------------------------------------------------
    #  Marca white-label del reporte (reventa)
    # ------------------------------------------------------------------
    marca = br_mod.marca(cfg)
    st.markdown("**Marca del reporte (white-label)**")
    with st.container(border=True):
        col_b1, col_b2 = st.columns([2, 1])
        with col_b1:
            consultora = st.text_input("Consultora / reventor", value=marca["consultora"],
                                       key="rpt_consultora",
                                       help="Quien entrega el reporte.")
            contacto = st.text_input("Contacto", value=marca["contacto"] or "",
                                     key="rpt_contacto",
                                     placeholder="ventas@consultora.cl · +56 9 1234 5678")
            web = st.text_input("Web", value=marca["web"] or "", key="rpt_web",
                                placeholder="https://consultora.cl")
        with col_b2:
            color = st.color_picker("Color de marca", value=marca["color_primario"],
                                    key="rpt_color")
            ocasion_def = st.text_input("Rotulo de portada", value=br_mod.ocasion(cfg),
                                        key="rpt_ocasion",
                                        placeholder="Reporte mensual")
        if en_kiosco():
            st.caption("Modo presentacion: la marca se edita fuera del kiosco.")
        guardar = st.button("Guardar marca", icon=":material/save:",
                            type="primary", key="rpt_guardar",
                            disabled=en_kiosco())
        if guardar:
            exigir_escritura("Solo un administrador puede guardar la marca.")
            try:
                _guardar_branding(cfg, {
                    "consultora": consultora.strip(),
                    "contacto": contacto.strip(),
                    "web": web.strip(),
                    "color_primario": color,
                })
                st.success("Marca guardada en el config del workspace.")
                st.cache_resource.clear()
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"No se pudo guardar: {e}")

    st.markdown("**Generar reporte**")
    with st.container(border=True):
        tipos = [catalogo.TODOS] + [r["clave"] for r in catalogo.REPORTES]
        col_g1, col_g2, col_g3 = st.columns([2, 2, 1])
        with col_g1:
            tipo = st.selectbox(
                "Tipo de reporte", tipos,
                format_func=lambda t: "Todos los reportes" if t == catalogo.TODOS
                else por_clave(t)["titulo"],
                key="rpt_tipo", help="'Todos' genera los 5 reportes del catalogo.",
            )
        with col_g2:
            ocasion = st.text_input("Ocasion (portada)", value=ocasion_def,
                                    key="rpt_ocasion_gen",
                                    placeholder="Reporte mensual",
                                    help="Etiqueta impresa en la portada.")
        with col_g3:
            st.space("small")
            generar = st.button("Generar reporte", type="primary",
                                icon=":material/auto_awesome:", width="stretch",
                                key="rpt_generar", disabled=en_kiosco())

        if tipo == catalogo.TODOS:
            st.caption("Se generan: " + ", ".join(
                r["titulo"] for r in catalogo.REPORTES) + ".")
        else:
            st.caption(por_clave(tipo)["descripcion"])

        if generar:
            with st.spinner("Calculando analisis, predicciones y armando el documento..."):
                try:
                    rutas = _generar(cfg, data, tipo, ocasion.strip())
                except Exception as e:  # noqa: BLE001
                    st.error(f"Fallo la generacion: {e}")
                    rutas = []
            if rutas:
                st.success(f"Reporte(s) generado(s): {len(rutas)}")
                st.session_state["ultimo_reporte"] = rutas[-1]

    # ------------------------------------------------------------------
    #  Vista previa del ultimo generado + descarga
    # ------------------------------------------------------------------
    ruta_ultimo = st.session_state.get("ultimo_reporte")
    if ruta_ultimo and Path(ruta_ultimo).exists():
        with c.panel("Vista previa", "Imprime a PDF desde el navegador o descarga el HTML",
                     icono=":material/visibility:"):
            _boton_descarga(ruta_ultimo)
            _componente_html(ruta_ultimo)

    # ------------------------------------------------------------------
    #  Historial de reportes generados en este workspace
    # ------------------------------------------------------------------
    st.markdown("**Reportes generados**")
    generados = listar_generados(cfg)
    if not generados:
        c.vacio("Aun no hay reportes de este workspace.",
                icono=":material/history:",
                detalle="Genera el primero con el boton de arriba o via CLI: "
                        "`python main.py reporte generar --tipo todos`.")
        return

    por_tipo: dict = {}
    for g in generados:
        por_tipo.setdefault(g["tipo"], []).append(g)

    for tipo_key, lista in por_tipo.items():
        meta = por_clave(tipo_key)
        with st.expander(f":material/{meta['icono']}: {meta['titulo']} "
                         f"({len(lista)})", expanded=tipo_key == "resumen"):
            for g in lista[:8]:
                fecha = datetime.fromtimestamp(g["fecha"]).strftime("%d/%m/%Y %H:%M")
                col_h1, col_h2 = st.columns([4, 1])
                with col_h1:
                    st.caption(f"`{g['nombre']}` · generado {fecha}")
                with col_h2:
                    if st.button("Mostrar", key=f"ver_{tipo_key}_{g['nombre']}",
                                 width="stretch", icon=":material/visibility:"):
                        st.session_state["ultimo_reporte"] = g["archivo"]
                        st.rerun()
                st.divider()
    st.caption(":material/lightbulb: Automatiza con el CLI: "
               "`python main.py reporte generar --tipo todos --periodo 'Reporte mensual'` "
               "y un cron/`crontab` para entregar reportes periodicos.")


if __name__ == "__main__":
    principal()