"""Tema de marca por workspace: colores, logo y CSS inyectado.

Cada empresa (workspace) puede llevar sus colores de marca en
``config.yaml`` bajo ``tema:``. La app inyecta un overlay de CSS por sesion
sobre el tema base de Streamlit, manteniendo la identidad del cliente en
demo, piloto y despliegue.

Diseño minimalista inspirado en Plausible + Stripe + Linear:
- Casi monocromático; color solo para significado (estado/accion).
- Bordes tenues, sin sombras genericas en todo.
- Tipografía Inter/Space Grotesk ya definida en .streamlit/config.toml.
"""
import html

import streamlit as st

DEFAULT_TEMA = {
    # Paleta casi monocromática. El color se reserva para significado,
    # nunca para decoración.
    "color_primario": "#0F766E",      # verde-teca: acción principal / OK
    "color_secundario": "#B45309",    # ámbar: advertencia
    "color_acento": "#DC2626",        # rojo: crítica / peligro
    "texto_logo": "GIRO Analytics",
    # Tokens de estructura (inyectados vía CSS).
    "fondo_panel": "#0B1120",         # azul noche profundo (modo oscuro)
    "borde_sutil": "#E2E8F0",         # borde tenue (modo claro)
    "texto_suave": "#64748B",         # texto secundario, etiquetas
    "fondo_suave": "#F8FAFC",         # fondo muy suave para secciones
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
    base vive en .streamlit/config.toml. Solo expone las variables de marca
    para usos puntuales.
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


def _css_premium(oscuridad: bool) -> str:
    """Overlay CSS minimalista.

    Sustituye las sombras genericas y los radios uniformes por bordes
    tenues y jerarquía tipográfica. Color solo para significado.
    """
    if oscuridad:
        fondo_tarjeta = "#0B1120"
        borde_tarjeta = "#1F2A44"
        texto_suave = "#94A3B8"
    else:
        fondo_tarjeta = "#FFFFFF"
        borde_tarjeta = "#E2E8F0"
        texto_suave = "#64748B"

    return f"""
    <style>
    /* Paneles: borde tenue, sin sombra generica (ni kit de tarjetas SaaS). */
    [data-testid="stContainer"] > div[data-testid="stElementContainer"] {{
        box-shadow: none !important;
    }}
    /* Tablas: filas limpias, numeros a la derecha, grid tenue. */
    .stDataFrame {{ border: 1px solid {borde_tarjeta}; }}
    .stDataFrame [role="row"] {{ border-bottom: 1px solid {borde_tarjeta}; }}
    /* Botones primarios: sin sombra pesada, color solo para accion. */
    .stButton > button[kind="primary"] {{
        box-shadow: none !important;
        background: {primario} !important;
        border: none !important;
    }}
    .stButton > button[kind="primary"]:hover {{
        opacity: 0.9;
    }}
    .giro-brand {{ letter-spacing: 0.01em; }}
    .giro-brand::after {{
        content: "";
        display: block;
        width: 2.2rem;
        height: 2px;
        border-radius: 1px;
        margin-top: 0.4rem;
        background: {primario};
    }}
    </style>
    """


def _css_accesibilidad(oscuridad: bool) -> str:
    """CSS global de accesibilidad: foco visible, targets 44px, skip-to-content."""
    contorno = "#60a5fa" if oscuridad else "#2563eb"
    return f"""
    <style>
    .stButton > button:focus-visible,
    .stDownloadButton > button:focus-visible,
    .stFormSubmitButton > button:focus-visible,
    .stLinkButton > a:focus-visible,
    [data-testid="stTabs"] [role="tab"]:focus-visible,
    .stTextInput input:focus-visible,
    .stSelectbox button:focus-visible {{
        outline: 3px solid {contorno};
        outline-offset: 2px;
    }}
    [data-testid="stButton"] > button,
    .stDownloadButton > button,
    .stFormSubmitButton > button {{
        min-height: 44px;
    }}
    .skip-link {{
        position: absolute;
        left: -9999px;
        top: 0;
        z-index: 999;
        background: #101828;
        color: #ffffff;
        font-weight: 700;
        text-decoration: none;
        padding: 12px 24px;
        border-radius: 0 0 10px 0;
    }}
    .skip-link:focus {{
        left: 0;
        outline: 3px solid {contorno};
        outline-offset: 2px;
    }}
    </style>
    """


def logo_html(texto_logo: str, slogan: str = "") -> str:
    """Cabecera de marca para el sidebar."""
    texto = html.escape(str(texto_logo or ""))
    sub = html.escape(str(slogan or ""))
    return (
        '<div class="giro-brand">'
        f"{texto}"
        + (f"<br><small>{sub}</small>" if sub else "")
        + "</div>"
    )


def aplicar(tema: dict) -> None:
    """Inyecta el CSS del tema del workspace + overlays de accesibilidad."""
    oscuro = False
    try:
        oscuro = st.context.theme.type == "dark"
    except Exception:
        oscuro = False
    st.markdown(css(tema) + _css_premium(oscuro) + _css_accesibilidad(oscuro),
               unsafe_allow_html=True)
