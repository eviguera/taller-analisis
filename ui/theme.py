"""Tema de marca por workspace: colores, logo y CSS inyectado.

Cada empresa (workspace) puede llevar sus colores de marca en
``config.yaml`` bajo ``tema:``. La app inyecta un overlay de CSS por sesion
sobre el tema base de Streamlit, manteniendo la identidad del cliente en
demo, piloto y despliegue.
"""

import html

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


def _css_premium(oscuridad: bool) -> str:
    """Overlay CSS opcional (pedido por el usuario) con look SaaS.

    Eleva tarjetas de metricas, paneles con borde y botones primarios con
    sombras suaves y radios consistentes, adaptandose al modo claro/oscuro.
    """
    if oscuridad:
        fondo_tarjeta = "#0f1c33"
        borde_tarjeta = "#2a3a5a"
        sombra_tarjeta = "0 1px 2px rgba(0,0,0,0.35), 0 6px 16px rgba(0,0,0,0.28)"
        sombra_panel = "0 1px 2px rgba(0,0,0,0.30), 0 3px 10px rgba(0,0,0,0.25)"
    else:
        fondo_tarjeta = "#ffffff"
        borde_tarjeta = "#e2e8f0"
        sombra_tarjeta = "0 1px 2px rgba(30,41,59,0.04), 0 6px 16px rgba(30,41,59,0.06)"
        sombra_panel = "0 1px 2px rgba(30,41,59,0.04), 0 3px 10px rgba(30,41,59,0.05)"

    return f"""
    <style>
    [data-testid="stMetric"] {{
        background: {fondo_tarjeta};
        border: 1px solid {borde_tarjeta};
        border-radius: 14px;
        padding: 0.9rem 1rem;
        box-shadow: {sombra_tarjeta};
    }}
    [data-testid="stMetricLabel"] p {{
        font-size: 0.82rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        opacity: 0.75;
    }}
    /* metricValueFontSize = 2.5rem fijo desborda cuando una fila de
       kpi_grid tiene muchas tarjetas (o el valor es largo). Aqui baja
       con el ancho disponible pero sin pasar de 2.5rem, y el valor se
       parte en vez de salirse de la tarjeta. */
    [data-testid="stMetricValue"] {{
        font-size: clamp(1.35rem, 1.1rem + 1vw, 2.5rem);
        line-height: 1.15;
        overflow-wrap: anywhere;
    }}
    [data-testid="stVerticalBlockBorderWrapper"] {{
        box-shadow: {sombra_panel};
    }}
    [data-testid="stBaseButton-primary"] {{
        box-shadow: {sombra_panel};
    }}
    [data-testid="stBadge"] {{
        border-radius: 999px;
    }}
    .giro-brand {{ letter-spacing: 0.01em; }}
    .giro-brand::after {{
        content: "";
        display: block;
        width: 2.2rem;
        height: 3px;
        border-radius: 2px;
        margin-top: 0.4rem;
        background: linear-gradient(90deg, var(--giro-primario), var(--giro-secundario));
    }}
    </style>
    """


def logo_html(texto_logo: str, slogan: str = "") -> str:
    """Cabecera de marca para el sidebar.

    El texto viene del config del workspace (editable por el tenant), asi que
    se escapa: sin esto un ``texto_logo`` con ``<img onerror=...>`` se ejecuta
    en el navegador de todos los usuarios de esa empresa.
    """
    texto = html.escape(str(texto_logo or ""))
    sub = html.escape(str(slogan or ""))
    return (
        '<div class="giro-brand">'
        f"{texto}"
        + (f"<br><small>{sub}</small>" if sub else "")
        + "</div>"
    )


def aplicar(tema: dict) -> None:
    """Inyecta el CSS del tema del workspace + overlay premium en la pagina."""
    oscuro = False
    try:
        oscuro = st.context.theme.type == "dark"
    except Exception:  # noqa: BLE001  (st.context fuera de runtime: se asume claro)
        oscuro = False
    st.markdown(css(tema) + _css_premium(oscuro), unsafe_allow_html=True)