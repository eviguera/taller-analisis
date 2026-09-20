"""Interfaz web de GIRO, inteligencia de negocio (Streamlit).

Router principal con st.navigation y barra lateral compartida: marca,
navegacion, controles de personalizacion (negocio y moneda) y pie de pagina.
"""

import streamlit as st

from ui import context
from ui import theme as tema_mod
from ui.context import obtener_config
from ui.pages import PAGINAS
from src import workspaces as ws
from src.core.templates import lista_verticales


def _kiosco_activo() -> bool:
    return str(st.query_params.get("kiosco", "0")) in ("1", "true", "verdadero")


def _selector_workspace():
    """Selectbox de empresa (workspace) + alta de nuevas empresas."""
    catalog = ws.listar_workspaces()
    opciones = ["principal"] + catalog
    actual = context.obtener_workspace()
    if actual not in opciones:
        opciones.append(actual)

    st.markdown("**Empresa (workspace)**")
    with st.container(border=True):
        clave = st.selectbox(
            "Workspace", opciones,
            index=opciones.index(actual) if actual in opciones else 0,
            key="sel_workspace", label_visibility="collapsed",
            help="Cada empresa tiene sus datos, almacen y modelos aislados.",
        )
        if clave != actual:
            st.session_state["workspace"] = clave
            st.cache_data.clear()
            st.cache_resource.clear()
            st.rerun()

        with st.expander("Crear empresa", icon=":material/add_business:"):
            nueva = st.text_input("Identificador (sin espacios)", key="ws_nueva",
                                  placeholder="ej: taller-don-juan")
            nom = st.text_input("Nombre comercial", key="ws_nombre",
                                placeholder="ej: Taller Don Juan")
            sector = st.selectbox(
                "Sector (plantilla)",
                ["taller"] + [v for v in lista_verticales() if v != "taller"],
                key="ws_sector", label_visibility="collapsed")
            mon = st.selectbox("Moneda", ["CLP", "MXN", "USD", "EUR", "COP"],
                               key="ws_moneda", label_visibility="collapsed")
            con_muestra = st.checkbox("Copiar datos de ejemplo", value=True,
                                      key="ws_muestra")
            if st.button("Crear", type="primary", icon=":material/add:",
                         disabled=not nueva.strip()):
                try:
                    cfg = context.crear_workspace_ui(
                        nueva.strip(), nom.strip(), mon, con_muestra, sector=sector)
                    st.success(f"Workspace **{cfg.negocio_nombre}** creado.")
                except Exception as e:  # noqa: BLE001
                    st.error(str(e))


def main():
    cfg_head = context.obtener_config()
    whitelabel = cfg_head.whitelabel or {}
    st.set_page_config(
        page_title=whitelabel.get("titulo") or "GIRO · Inteligencia de negocio",
        page_icon=":material/donut_large:",
        layout="wide",
        initial_sidebar_state="collapsed" if _kiosco_activo() else "expanded",
    )

    paginas = [
        st.Page(modulo, title=etiqueta, icon=icono, url_path=clave, default=principal)
        for etiqueta, clave, icono, modulo, principal in PAGINAS
    ]

    tema_mod.aplicar(cfg_head.tema)

    with st.sidebar:
        st.markdown(tema_mod.logo_html(
            (cfg_head.tema or {}).get("texto_logo", "GIRO Analytics"),
            cfg_head.slogan), unsafe_allow_html=True)

    pg = st.navigation(paginas, position="sidebar", expanded=not _kiosco_activo())

    kiosco = _kiosco_activo()
    with st.sidebar:
        if kiosco:
            st.space("small")
            if st.button("Salir del modo presentacion",
                         icon=":material/present_to_all:", width="stretch"):
                st.query_params.pop("kiosco", None)
                st.rerun()
        else:
            _selector_workspace()
            cfg = obtener_config()
            st.markdown("**Personalizar**")
            with st.container(border=True):
                nuevo_nombre = st.text_input(
                    "Nombre del negocio",
                    value=cfg.negocio_nombre,
                    key="inp_negocio_nombre",
                    help="Se guarda durante la sesion. Persistelo en config/config.yaml.",
                )
                nuevo_slogan = st.text_input(
                    "Eslogan",
                    value=cfg.slogan,
                    key="inp_slogan",
                    help="Aparece bajo la marca GIRO. Persistelo en config/config.yaml.",
                )
                nueva_moneda = st.selectbox(
                    "Moneda",
                    ["CLP", "MXN", "USD", "EUR", "COP"],
                    index=["CLP", "MXN", "USD", "EUR", "COP"].index(cfg.moneda)
                    if cfg.moneda in ["CLP", "MXN", "USD", "EUR", "COP"] else 0,
                    key="inp_moneda",
                    help="Formato de los importes en toda la app.",
                )
                c1, c2 = st.columns(2)
                with c1:
                    primario = st.color_picker(
                        "Color primario",
                        value=st.session_state.get("tema_primario") or
                        (cfg.tema or {}).get("color_primario", "#7C4DFF"),
                        key="inp_tema_primario",
                        help="Identidad de marca del workspace.",
                    )
                with c2:
                    acento = st.color_picker(
                        "Color acento",
                        value=st.session_state.get("tema_acento") or
                        (cfg.tema or {}).get("color_acento", "#FFB020"),
                        key="inp_tema_acento",
                    )
            st.session_state["negocio_nombre"] = (nuevo_nombre or "").strip() or "Mi Negocio"
            st.session_state["slogan"] = nuevo_slogan.strip()
            st.session_state["moneda"] = nueva_moneda
            st.session_state["tema_primario"] = primario
            st.session_state["tema_acento"] = acento
            if primario != (cfg.tema or {}).get("color_primario") or \
               acento != (cfg.tema or {}).get("color_acento"):
                st.cache_resource.clear()
                st.rerun()
            cfg = obtener_config()

            st.space("medium")
            if st.button("Modo presentacion (kiosco)",
                         icon=":material/present_to_all:",
                         help="Oculta paneles de configuracion para vender/demostrar."):
                st.query_params["kiosco"] = "1"
                st.rerun()

            st.markdown("**Sistema**")
            with st.container(border=True):
                st.markdown(
                    f":material/currency_exchange: Moneda **{cfg.moneda}**  \n"
                    f":material/factory: {cfg.negocio_nombre}  \n"
                    f":material/business: Workspace **{cfg.clave}**  \n"
                    f":material/database: DuckDB + parquet"
                )
            st.space("small")
            if st.button("Recargar datos", icon=":material/refresh:",
                         width="stretch", key="btn_recargar"):
                st.cache_data.clear()
                st.cache_resource.clear()
                st.rerun()
            st.space("large")
            st.caption("v1.7 · marca por empresa + kiosco + verticales")

    pg.run()

    if whitelabel.get("mostrar_footer", True):
        st.space("medium")
        pie = whitelabel.get("footer")
        if pie:
            st.caption(f":material/dataset: {pie}")
        else:
            st.caption(":material/dataset: Datos procesados con ETL y almacenados en "
                       "DuckDB. Analítica y predicciones de tu negocio.")


if __name__ == "__main__":
    main()