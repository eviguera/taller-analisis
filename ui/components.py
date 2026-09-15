"""Sistema de diseno compartido de la interfaz web.

Usa componentes nativos de Streamlit (st.metric, st.badge, st.title) y
graficos Plotly con una estetica sobria y tecnologica: paleta suave de
azul, gris y verde, tipografia Inter/Space Grotesk y adaptacion automatica
al modo claro/oscuro del tema.
"""

import io
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ------------------------------------------------------------------
#  Paleta suave: azul, gris y verde (sincronizada con config.toml)
# ------------------------------------------------------------------
PALETA = {
    "primario": "#2563eb",        # azul
    "azul_suave": "#60a5fa",
    "cielo": "#0ea5e9",
    "exito": "#059669",           # verde esmeralda
    "verde": "#16a34a",
    "esmeralda_suave": "#10b981",
    "alerta": "#d97706",
    "peligro": "#dc2626",
    "gris": "#64748b",
    "gris_suave": "#94a3b8",
    "pizarra": "#1e293b",
    "pizarra_claro": "#e2e8f0",
}

SECUENCIA_COLORES = [
    PALETA["primario"], PALETA["cielo"], PALETA["exito"], PALETA["verde"],
    PALETA["azul_suave"], PALETA["esmeralda_suave"], PALETA["gris"], PALETA["gris_suave"],
]

MESES_ES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

DIAS_ES = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo",
}


# ------------------------------------------------------------------
#  Utilidades de formato
# ------------------------------------------------------------------

def miles(valor, decimales=0):
    """Formatea un numero con punto como separador de miles (es-CL)."""
    return f"{valor:,.{decimales}f}".replace(",", ".")


def moneda(valor, moneda="MXN"):
    simbolos = {"MXN": "$", "USD": "$", "EUR": "€", "CLP": "$", "COP": "$"}
    s = simbolos.get(moneda, "$")
    return f"{s}{miles(valor)}"


def logo_png(ruta="ui/assets/GIRO.png", ancho=172):
    """Muestra la imagen del logo en la sidebar (SVG/PNG via base64).

    Usa `mix-blend-mode: multiply` para que el fondo blanco del PNG se funda
    con el fondo de la sidebar (claro u oscuro) sin caja blanca.
    """
    import base64
    from pathlib import Path

    p = Path(__file__).resolve().parent.parent / ruta
    if not p.exists():
        return None
    b64 = base64.b64encode(p.read_bytes()).decode()
    return (
        f'<img src="data:image/png;base64,{b64}" alt="GIRO" '
        f'style="width:{ancho}px;border-radius:10px;mix-blend-mode:multiply;'
        f'display:block;margin:0 auto;">'
    )


def _es_oscuro() -> bool:
    try:
        return st.context.theme.type == "dark"
    except Exception:  # noqa: BLE001
        return False


def _color_texto() -> str:
    return "#dbe4f1" if _es_oscuro() else "#1e293b"


# ------------------------------------------------------------------
#  Encabezados y jerarquia visual
# ------------------------------------------------------------------

def cabecera(titulo, subtitulo=None, icono=None, chips=None):
    """Encabezado de pagina: icono + titulo + subtitulo + chips opcionales."""
    st.title(titulo, icon=icono)
    if subtitulo:
        st.caption(subtitulo)
    if chips:
        with st.container(horizontal=True):
            for texto in chips:
                st.badge(texto, icon=":material/chevron_right:", color="gray")


def titulo_seccion(titulo, subtitulo=None, icono=None):
    st.markdown(f"### {icono + ' ' if icono else ''}{titulo}")
    if subtitulo:
        st.caption(subtitulo)


@contextmanager
def panel(titulo, subtitulo=None, icono=None, alto=None):
    """Tarjeta con borde y encabezado para agrupar un grafico/tabla."""
    kw = {"border": True}
    if alto:
        kw["height"] = alto
    with st.container(**kw):
        st.markdown(f"**{icono + ' ' if icono else ''}{titulo}**")
        if subtitulo:
            st.caption(subtitulo)
        yield


# ------------------------------------------------------------------
#  KPIs
# ------------------------------------------------------------------

def kpi_grid(items):
    """Renderiza una fila de KPIs como st.metric nativos con tarjeta (border).

    items: lista de tuplas
        (etiqueta, valor[, delta[, tendencia[, ayuda]]])
      - delta: string de variacion (p. ej. "+12%")
      - tendencia: secuencia de numeros para el mini-grafico (sparkline)
      - ayuda: texto informativo
    """
    with st.container(horizontal=True):
        for item in items:
            etiqueta, valor = item[0], item[1]
            delta = item[2] if len(item) > 2 else None
            tendencia = item[3] if len(item) > 3 else None
            ayuda = item[4] if len(item) > 4 else None
            st.metric(
                etiqueta, valor, delta=delta, help=ayuda, border=True,
                chart_data=tendencia, chart_type="line",
            )


def vacio(mensaje, icono=":material/info:", detalle=None):
    """Estado vacio con tono informativo ligero."""
    with st.container(border=True):
        st.markdown(f"**{icono} {mensaje}**")
        if detalle:
            st.caption(detalle)


# ------------------------------------------------------------------
#  Formato / badges
# ------------------------------------------------------------------

def formato_archivo(fmt):
    """Chip de color para mostrar el formato de un archivo en una tabla."""
    color = {
        "csv": "#2563eb", "excel": "#059669", "sav": "#7c3aed",
        "zsav": "#7c3aed", "por": "#0ea5e9", "parquet": "#64748b",
    }.get(fmt, "#64748b")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:10px;font-size:11px;">{fmt.upper()}</span>'


def badge(texto, tipo="info"):
    """Badge en markdown usando el sistema nativo de Streamlit (sin CSS)."""
    estilo = {
        "verde": "green", "rojo": "red", "amarillo": "orange",
        "azul": "blue", "info": "violet",
    }.get(tipo, "gray")
    return f":{estilo}-badge[{texto}]"


# ------------------------------------------------------------------
#  Utilidades de descarga
# ------------------------------------------------------------------

def descargar(df: pd.DataFrame, nombre_base: str, etiquetas_valores=None):
    """Genera botones de descarga en CSV, Excel y PSPP (.sav) para `df`."""
    opciones = ["CSV", "Excel"]
    try:
        import pyreadstat  # noqa: F401
        opciones.append("PSPP (.sav)")
    except ImportError:
        pass

    fmt = st.segmented_control(
        "Formato de descarga", opciones, key=f"dl_{nombre_base}",
        default="CSV", label_visibility="collapsed", width="stretch",
    )
    fmt = fmt or "CSV"
    nombre = f"{nombre_base}.{'csv' if fmt == 'CSV' else ('xlsx' if fmt == 'Excel' else 'sav')}"

    if fmt == "CSV":
        st.download_button(
            "Descargar", df.to_csv(index=False).encode("utf-8-sig"),
            file_name=nombre, mime="text/csv", icon=":material/download:",
        )
    elif fmt == "Excel":
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False)
        st.download_button(
            "Descargar", buf.getvalue(), file_name=nombre,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            icon=":material/download:",
        )
    else:
        from src.loaders.pspp_loader import exportar_sav
        with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
            exportar_sav(df, Path(tmp.name), variable_value_labels=etiquetas_valores or {})
            tmp.seek(0)
            contenido = tmp.read()
        st.download_button(
            "Descargar", contenido, file_name=nombre,
            mime="application/octet-stream", icon=":material/download:",
        )


# ------------------------------------------------------------------
#  Graficos reutilizables (estetica sobria y consistente)
# ------------------------------------------------------------------

def _layout(fig, titulo="", leyenda=True):
    """Aplica una estetica consistente a cualquier figura Plotly."""
    fig.update_layout(
        template="plotly_dark" if _es_oscuro() else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color=_color_texto(), size=13),
        title=dict(
            text=titulo or None,
            font=dict(family="Space Grotesk", size=16, color=_color_texto()),
        ),
        legend=dict(title_text="", orientation="h", yanchor="bottom",
                    y=1.02, xanchor="left", x=0) if leyenda else dict(visible=False),
        margin=dict(l=10, r=10, t=52 if titulo else 24, b=10),
        hovermode="x unified",
        bargap=0.35,
    )
    grid = "rgba(148,163,184,0.12)" if _es_oscuro() else "rgba(148,163,184,0.20)"
    fig.update_xaxes(gridcolor=grid, zeroline=False)
    fig.update_yaxes(gridcolor=grid, zeroline=False)
    return fig


def grafico_linea(df, x, y, titulo="", color=None, etiquetas=None):
    fig = px.line(df, x=x, y=y, markers=True, color=color,
                  labels=etiquetas or {},
                  color_discrete_sequence=SECUENCIA_COLORES)
    _layout(fig, titulo)
    if color:
        fig.update_traces(line_width=2.5)
    else:
        fig.update_traces(line_width=2.5, line_color=PALETA["primario"])
    return fig


def grafico_barras(df, x, y, titulo="", color=None, vertical=True, etiquetas=None, color_cont=None):
    if vertical:
        fig = px.bar(df, x=x, y=y, color=color, labels=etiquetas or {},
                     color_discrete_sequence=SECUENCIA_COLORES,
                     color_continuous_scale=color_cont or "Blues")
    else:
        fig = px.bar(df, y=x, x=y, color=color, labels=etiquetas or {},
                     color_discrete_sequence=SECUENCIA_COLORES,
                     color_continuous_scale=color_cont or "Blues")
    _layout(fig, titulo)
    if not color and not color_cont:
        fig.update_traces(marker_color=PALETA["primario"])
    if not vertical:
        fig.update_layout(margin=dict(l=120, r=10, t=52 if titulo else 24, b=10))
    return fig


def grafico_pastel(df, nombres, valores, titulo=""):
    fig = px.pie(df, names=nombres, values=valores, hole=0.42,
                 color_discrete_sequence=SECUENCIA_COLORES)
    text_color = "#e2e8f0" if _es_oscuro() else "#0f172a"
    fig.update_traces(textposition="inside", textinfo="label+percent",
                      textfont=dict(color=text_color, size=12),
                      marker=dict(line=dict(color="rgba(0,0,0,0)", width=0)))
    _layout(fig, titulo, leyenda=False)
    return fig


def grafico_dispersion(df, x, y, titulo="", color=None, hover=None, log_y=False, size=None):
    fig = px.scatter(df, x=x, y=y, color=color, size=size, hover_data=hover,
                     log_y=log_y,
                     color_discrete_sequence=SECUENCIA_COLORES)
    _layout(fig, titulo)
    fig.update_traces(marker=dict(opacity=0.75, line=dict(width=1, color="rgba(255,255,255,0.8)")))
    return fig


def grafico_hist(df, x, nbins=20, titulo="", xlabel=None):
    fig = px.histogram(df, x=x, nbins=nbins,
                       labels={x: xlabel or x},
                       color_discrete_sequence=[PALETA["primario"]])
    _layout(fig, titulo)
    fig.update_traces(marker_color=PALETA["primario"], marker_line_width=0)
    return fig


def grafico_area(df, x, y, titulo=""):
    """Grafico de area (ideal para acumulados)."""
    fig = px.area(df, x=x, y=y, color_discrete_sequence=[PALETA["exito"]])
    _layout(fig, titulo)
    fig.update_traces(line_width=0, fillcolor="rgba(5,150,105,0.18)")
    return fig


def progreso(valor, formato="%.0f%%"):
    """Muestra una barra de progreso con etiqueta, ideal para probabilidades."""
    st.progress(min(max(valor, 0), 1), text=formato % valor)