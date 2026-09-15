"""Interfaz web del Sistema de Analisis del Taller Mecanico (Streamlit).

Router principal con st.navigation y barra lateral compartida: marca,
navegacion, controles globales y pie de pagina.
"""

import streamlit as st

from ui.context import obtener_config
from ui.pages import PAGINAS


def main():
    st.set_page_config(
        page_title="Analitica del Taller Mecanico",
        page_icon=":material/build:",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    paginas = [
        st.Page(modulo, title=etiqueta, icon=icono, url_path=clave, default=principal)
        for etiqueta, clave, icono, modulo, principal in PAGINAS
    ]

    with st.sidebar:
        st.markdown("#### :material/build_circle: Taller · Analitica")
        st.caption("Sistema de inteligencia de negocio")

    pg = st.navigation(paginas, position="sidebar", expanded=True)

    with st.sidebar:
        cfg = obtener_config()
        st.space("medium")
        st.markdown("**Sistema**")
        with st.container(border=True):
            st.markdown(
                f":material/currency_exchange: Moneda **{cfg.moneda}**  \n"
                f":material/factory: {cfg.taller_nombre}  \n"
                f":material/database: DuckDB + parquet"
            )
        st.space("small")
        if st.button("Recargar datos", icon=":material/refresh:",
                     width="stretch", key="btn_recargar"):
            st.cache_data.clear()
            st.cache_resource.clear()
            st.rerun()
        st.space("large")
        st.caption("v1.2 · ETL + DuckDB + ML")

    pg.run()

    st.space("medium")
    st.caption(":material/dataset: Datos procesados con ETL y almacenados en DuckDB. "
               "Analitica y predicciones del taller mecanico.")


if __name__ == "__main__":
    main()