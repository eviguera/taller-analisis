"""Tema de marca por workspace: colores, logo y CSS inyectado.

Cada empresa (workspace) puede llevar sus colores de marca en
``config.yaml`` bajo ``tema:``. La app inyecta un overlay de CSS por sesion
sobre el tema base de Streamlit, manteniendo la identidad del cliente en
demo, piloto y despliegue.
"""

import streamlit as st

DEFAULT_TEMA = {
    "color_primario": "#7C4DFF",
    "color_secundario": "#00C2A8",
    "color_acento": "#FFB020",
    "texto_logo": "GIRO Analytics",
}


def tema_config(tema: dict) -> dict:
    """Fusiona el tema de la configuracion con los valores por defecto."""
    salida = dict(DEFAULT_TEMA)
    if isinstance(tema, dict):
        salida.update({k: v for k, v in tema.items() if v})
    return salida


def css(tema: dict) -> str:
    """CSS inyectable con las variables de marca del workspace.

    Deliberadamente NO sobreescribe los colores globales de la app: el tema
    base vive en ``.streamlit/config.toml``. Solo expone las variables de marca
    para usos puntuales (marca en la barra lateral).
    """
    t = tema_config(tema)
    primario = t["color_primario"]
    secundario = t["color_secundario"]
    acento = t["color_acento"]
    return f"""
    <style>
    :root {{
        --giro-primario: {primario};
        --giro-secundario: {secundario};
        --giro-acento: {acento};
    }}
    .giro-brand {{ font-size: 1.2rem; font-weight: 700; }}
    .giro-brand small {{ font-size: 0.7rem; opacity: 0.75; font-weight: 400; }}
    </style>
    """


def logo_html(texto_logo: str, slogan: str = "") -> str:
    """Cabecera de marca para el sidebar."""
    return (
        '<div class="giro-brand">'
        f"{texto_logo}"
        + (f"<br><small>{slogan}</small>" if slogan else "")
        + "</div>"
    )


def aplicar(tema: dict) -> None:
    """Inyecta el CSS del tema del workspace en la pagina."""
    st.markdown(css(tema), unsafe_allow_html=True)