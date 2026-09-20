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
    "fondo_sidenav": "#101828",
    "texto_logo": "GIRO Analytics",
}


def tema_config(tema: dict) -> dict:
    """Fusiona el tema de la configuracion con los valores por defecto."""
    salida = dict(DEFAULT_TEMA)
    if isinstance(tema, dict):
        salida.update({k: v for k, v in tema.items() if v})
    return salida


def css(tema: dict) -> str:
    """CSS inyectable con las variables de marca del workspace."""
    t = tema_config(tema)
    primario, secundario, acento = t["color_primario"], t["color_secundario"], t["color_acento"]
    fondo = t["fondo_sidenav"]
    return f"""
    <style>
    :root {{
        --giro-primario: {primario};
        --giro-secundario: {secundario};
        --giro-acento: {acento};
        --giro-fondo: {fondo};
    }}
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, var(--giro-fondo) 0%, var(--giro-fondo) 100%);
    }}
    [data-testid="stSidebar"] *:not(svg):not(input) {{ color: #E6EAF2; }}
    [data-testid="stSidebar"] .stButton button[kind="primary"] {{
        background-color: var(--giro-primario);
        border: none;
        color: #FFFFFF;
    }}
    [data-testid="stSidebar"] .stButton button {{ color: #E6EAF2; }}
    .stApp a {{ color: var(--giro-primario); }}
    [data-testid="stMetric"] {{
        background: color-mix(in srgb, var(--giro-primario) 6%, white);
        border: 1px solid color-mix(in srgb, var(--giro-primario) 25%, transparent);
        border-left: 4px solid var(--giro-primario);
        border-radius: 12px;
        padding: 12px 16px;
    }}
    .giro-badge {{
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.02em;
    }}
    .giro-brand {{ font-size: 1.2rem; font-weight: 700; color: white; }}
    .giro-brand span {{ color: var(--giro-primario); }}
    .giro-brand small {{ font-size: 0.7rem; opacity: 0.75; font-weight: 400; color: #C7CFDD; }}
    [data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,0.08) !important; }}
    </style>
    """


def logo_html(texto_logo: str, slogan: str = "") -> str:
    """Cabecera de marca para el sidebar."""
    return (
        '<div class="giro-brand">'
        '<img src="https://placehold.co/24x24/7C4DFF/FFFFFF?text=G" '
        'style="border-radius:6px;vertical-align:-4px;">&nbsp;<span>'
        f"{texto_logo}"
        "</span>"
        + (f"<br><small>{slogan}</small>" if slogan else "")
        + "</div>"
    )


def aplicar(tema: dict) -> None:
    """Inyecta el CSS del tema del workspace en la pagina."""
    st.markdown(css(tema), unsafe_allow_html=True)