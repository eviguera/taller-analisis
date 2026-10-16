"""Sistema de diseno compartido de la interfaz web.

Estetica minimalista inspirada en Plausible + Stripe + Linear:
- Casi monocromático; color solo para significado.
- Bordes tenues, sin sombras genericas ni tarjetas idénticas.
- Tablas como interfaz principal; un chart hero por vista.
"""
import io
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.formatos import (
    formato_archivo as _f_formato_archivo,
    formato_moneda as _f_formato_moneda,
    miles as _f_miles,
    moneda as _f_moneda,
)

# ------------------------------------------------------------------
#  Paleta casi monocromática. Color solo para significado.
# ------------------------------------------------------------------
PALETA = {
    "primario": "#0F766E",        # verde-teca: acción principal / OK
    "primario_suave": "#34D399",
    "secundario": "#B45309",      # ámbar: advertencia
    "acento": "#DC2626",          # rojo: crítica
    "fondo_panel": "#0B1120",
    "borde_sutil": "#E2E8F0",     # borde tenue (claro)
    "texto_suave": "#64748B",
    "fondo_suave": "#F8FAFC",
    "peligro": "#DC2626",
    "gris": "#64748b",
    "gris_suave": "#94a3b8",
}

SECUENCIA_COLORES = [
    PALETA["primario"], PALETA["primario_suave"], PALETA["secundario"],
    PALETA["acento"], PALETA["peligro"], PALETA["gris"], PALETA["gris_suave"],
]

MESES_ES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
            "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

DIAS_ES = {
    "Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles",
    "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo",
}


def miles(valor, decimales=0):
    return _f_miles(valor, decimales)


def moneda(valor, moneda="MXN"):
    return _f_moneda(valor, moneda)


def formato_moneda(moneda="CLP"):
    return _f_formato_moneda(moneda)


def _es_oscuro() -> bool:
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def _color_texto() -> str:
    return "#dbe4f1" if _es_oscuro() else "#1e293b"


# ------------------------------------------------------------------
#  Encabezados y jerarquia visual
# ------------------------------------------------------------------

def cabecera(titulo, subtitulo=None, icono=None, chips=None):
    st.title(titulo, icon=icono)
    if subtitulo:
        st.caption(subtitulo)
    if chips:
        with st.container(horizontal=True):
            for texto in chips:
                st.badge(texto, icon=":material/chevron_right:", color="gray")


def titulo_seccion(titulo, subtitulo=None, icono=None):
    st.markdown(f"## {icono + ' ' if icono else ''}{titulo}")
    if subtitulo:
        st.caption(subtitulo)


# ------------------------------------------------------------------
#  Paneles: borde tenue, sin sombra generica.
# ------------------------------------------------------------------

@contextmanager
def panel(titulo, subtitulo=None, icono=None, alto=None):
    """Panel con borde tenue para agrupar un grafico o tabla."""
    kw = {"border": True}
    if alto:
        kw["height"] = alto
    with st.container(**kw):
        st.markdown(
            f"<div style='color:{PALETA['texto_suave']};font-size:0.75rem;"
            f"text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.5rem;'"
            f" border-bottom:1px solid {PALETA['borde_sutil']};"
            f"padding-bottom:0.35rem;'>{icono + ' ' if icono else ''}{titulo}</div>",
            unsafe_allow_html=True,
        )
        if subtitulo:
            st.caption(subtitulo)
        yield


# ------------------------------------------------------------------
#  KPIs: una aguja principal + lecturas secundarias discretas.
# ------------------------------------------------------------------

def kpi_grid(items):
    """Renderiza una fila de KPIs como lecturas de aguja.

    items: lista de tuplas
        (etiqueta, valor[, delta[, tendencia[, ayuda]]])

    El primer ítem es la aguja principal: valor más grande, color primario.
    El resto son lecturas secundarias, discretas.
    """
    with st.container(horizontal=True):
        for i, item in enumerate(items):
            etiqueta, valor = item[0], item[1]
            delta = item[2] if len(item) > 2 else None
            ayuda = item[4] if len(item) > 4 else None
            es_primario = i == 0
            with st.container(border=True):
                if es_primario:
                    st.markdown(
                        f"<div style='color:{PALETA['texto_suave']};font-size:0.85rem;"
                        f"text-transform:uppercase;letter-spacing:0.08em;'>{etiqueta}</div>"
                        f"<div style='color:{PALETA['primario']};font-size:2.1rem;"
                        f"font-weight:700;'>{valor}</div>"
                        f"{f'<div style=\"color:{PALETA['primario_suave']};font-size:0.8rem;\" '
                        f'>{delta}</div>' if delta else ''}"
                        f"{f'<div style=\"color:{PALETA['texto_suave']};font-size:0.8rem;\" '
                        f'>{ayuda}</div>' if ayuda else ''}",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f"<div style='color:{PALETA['texto_suave']};font-size:0.85rem;"
                        f"text-transform:uppercase;letter-spacing:0.05em;'>{etiqueta}</div>"
                        f"<div style='color:{PALETA['primario_suave']};font-size:1.4rem;"
                        f"font-weight:600;'>{valor}</div>"
                        f"{f'<div style=\"color:{PALETA['texto_suave']};font-size:0.8rem;\" '
                        f'>{delta}</div>' if delta else ''}"
                        f"{f'<div style=\"color:{PALETA['texto_suave']};font-size:0.8rem;\" '
                        f'>{ayuda}</div>' if ayuda else ''}",
                        unsafe_allow_html=True,
                    )


def vacio(mensaje, icono=":material/info:", detalle=None, cta=None):
    with st.container(border=True):
        st.markdown(f"**{icono} {mensaje}**")
        if detalle:
            st.caption(detalle)
        if cta:
            st.caption(f"→ {cta}")


# ------------------------------------------------------------------
#  Mensajes y notificaciones
# ------------------------------------------------------------------

def mensaje_error(msg, detalle=None):
    texto = f"**{msg}**"
    if detalle:
        texto += f"\n\n{detalle}"
    st.error(texto, icon=":material/error:")


def confirmacion_exito(msg, detalle=None):
    texto = f"**{msg}**"
    if detalle:
        texto += f"\n\n{detalle}"
    st.success(texto, icon=":material/check_circle:")


def vacio_con_cta(mensaje, cta, icono=":material/info:", on_click=None,
                  clave=None, cta_secundario=None, on_click_secundario=None):
    with st.container(border=True):
        st.markdown(f"**{icono} {mensaje}**")
        col1, col2 = st.columns([2, 1] if cta_secundario else [1])
        with col1:
            if st.button(cta, type="primary", use_container_width=True,
                         key=clave, on_click=on_click):
                st.rerun()
        if cta_secundario:
            with col2:
                if st.button(cta_secundario, use_container_width=True,
                             key=f"{clave}_sec" if clave else None,
                             on_click=on_click_secundario):
                    st.rerun()


# ------------------------------------------------------------------
#  Badges: sin estilo píldora, color solo para significado.
# ------------------------------------------------------------------

def badge(texto, tipo="info"):
    color = {
        "verde": PALETA["primario"],
        "rojo": PALETA["peligro"],
        "amarillo": PALETA["secundario"],
        "azul": PALETA["primario"],
        "info": PALETA["texto_suave"],
        "acento": PALETA["acento"],
    }.get(tipo, PALETA["texto_suave"])
    return (
        f"<span style='background:{color};color:#ffffff;padding:2px 8px;"
        f"border-radius:4px;font-size:0.75rem;font-weight:600;"
        f"text-transform:uppercase;letter-spacing:0.05em;'>{texto}</span>"
    )


# ------------------------------------------------------------------
#  Tablas reutilizables: números a la derecha, filas limpias.
# ------------------------------------------------------------------

def dataframe(df, etiquetas=None, column_config=None, alto=None,
              indice_visible=False, **kwargs):
    config = dict(column_config or {})
    for columna, titulo in (etiquetas or {}).items():
        config.setdefault(columna, titulo)
    opciones = dict(width="stretch", hide_index=not indice_visible,
                    column_config=config or None, **kwargs)
    if alto is not None:
        opciones["height"] = alto
    st.dataframe(df, **opciones)


# ------------------------------------------------------------------
#  Formato de archivo
# ------------------------------------------------------------------

def formato_archivo(fmt):
    """Etiqueta de formato para una celda de tabla (texto plano)."""
    return _f_formato_archivo(fmt)


# ------------------------------------------------------------------
#  Descargas
# ------------------------------------------------------------------

def descargar(df: pd.DataFrame, nombre_base: str, etiquetas_valores=None):
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
        from src.aplicacion import exportar_datasets_sav
        with tempfile.TemporaryDirectory() as tmp:
            exportar_datasets_sav({nombre_base: df}, tmp,
                                  etiquetas={nombre_base: etiquetas_valores or {}})
            contenido = (Path(tmp) / f"{nombre_base}.sav").read_bytes()
        st.download_button(
            "Descargar", contenido, file_name=nombre,
            mime="application/octet-stream", icon=":material/download:",
        )


# ------------------------------------------------------------------
#  Graficos: un chart hero por vista, colores de la paleta.
# ------------------------------------------------------------------

def _layout(fig, titulo="", leyenda=True):
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
        bargap=0.4,
    )
    grid = "rgba(31,42,68,0.35)" if _es_oscuro() else "rgba(31,42,68,0.15)"
    fig.update_xaxes(gridcolor=grid, zeroline=False)
    fig.update_yaxes(gridcolor=grid, zeroline=False)
    return fig


def mostrar_grafico(fig, clave=None, **kwargs):
    kwargs.setdefault("width", "stretch")
    kwargs.setdefault("height", "stretch")
    kwargs.setdefault("config", {"displaylogo": False})
    st.plotly_chart(fig, key=clave, **kwargs)


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
    fig = px.area(df, x=x, y=y, color_discrete_sequence=[PALETA["exito"]])
    _layout(fig, titulo)
    fig.update_traces(line_width=0, fillcolor="rgba(5,150,105,0.18)")
    return fig


def progreso(valor, formato="%.0f%%"):
    st.progress(min(max(valor, 0), 1), text=formato % valor)
