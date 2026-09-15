"""Interfaz web de GIRO, inteligencia de negocio (Streamlit).

Router principal con st.navigation y barra lateral compartida: marca,
navegacion, controles de personalizacion (negocio y moneda) y pie de pagina.
"""

import streamlit as st

from ui.context import obtener_config
from ui.pages import PAGINAS


def main():
    st.set_page_config(
        page_title="GIRO · Inteligencia de negocio",
        page_icon=":material/donut_large:",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    paginas = [
        st.Page(modulo, title=etiqueta, icon=icono, url_path=clave, default=principal)
        for etiqueta, clave, icono, modulo, principal in PAGINAS
    ]

    with st.sidebar:
        st.markdown("#### :material/donut_large: GIRO")
        st.caption("Inteligencia de negocio")

    pg = st.navigation(paginas, position="sidebar", expanded=True)

    with st.sidebar:
        cfg = obtener_config()
        st.markdown("**Personalizar**")
        with st.container(border=True):
            nuevo_nombre = st.text_input(
                "Nombre del negocio",
                value=cfg.negocio_nombre,
                key="inp_negocio_nombre",
                help="Se guarda durante la sesion. Persistelo en config/config.yaml.",
            )
            nueva_moneda = st.selectbox(
                "Moneda",
                ["CLP", "MXN", "USD", "EUR", "COP"],
                index=["CLP", "MXN", "USD", "EUR", "COP"].index(cfg.moneda)
                if cfg.moneda in ["CLP", "MXN", "USD", "EUR", "COP"] else 0,
                key="inp_moneda",
                help="Formato de los importes en toda la app.",
            )
        st.session_state["negocio_nombre"] = (nuevo_nombre or "").strip() or "Mi Negocio"
        st.session_state["moneda"] = nueva_moneda
        cfg = obtener_config()

        st.space("medium")
        st.markdown("**Sistema**")
        with st.container(border=True):
            st.markdown(
                f":material/currency_exchange: Moneda **{cfg.moneda}**  \n"
                f":material/factory: {cfg.negocio_nombre}  \n"
                f":material/database: DuckDB + parquet"
            )
        st.space("small")
        if st.button("Recargar datos", icon=":material/refresh:",
                     width="stretch", key="btn_recargar"):
            st.cache_data.clear()
            st.cache_resource.clear()
            st.rerun()
        st.space("large")
        st.caption("v1.4 · ETL + DuckDB + ML")

    pg.run()

    st.space("medium")
    st.caption(":material/dataset: Datos procesados con ETL y almacenados en DuckDB. "
               "Analitica y predicciones de tu negocio.")


if __name__ == "__main__":
    main()