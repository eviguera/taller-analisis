"""Página: Decisiones del negocio.

Entrega al dueño de la pyme los indicadores que necesita para decidir hoy,
con una recomendación de acción clara en cada uno.

Diseño minimalista: un número principal, tablas simples, color solo para
significado (rojo = actuar, ámbar = revisar, verde = todo bien).
"""
import pandas as pd
import streamlit as st

from ui import components as c
from ui.context import obtener_estado
from src.aplicacion import decisiones


def _color_accion(accion: str) -> str:
    """Devuelve el color del badge según la acción requerida."""
    return {
        "actuar": "rojo",
        "revisar": "amarillo",
        "ok": "verde",
    }.get(accion, "info")


def principal():
    try:
        cfg, data, analyzer, predictor = obtener_estado()
    except Exception as e:  # nunca falle silenciosamente
        c.mensaje_error(
            "No se pudieron cargar los datos para decisiones.",
            detalle=str(e) if str(e) else "Revisa que el almacén del workspace esté disponible.",
        )
        return

    resumen = decisiones.indicadores_decision(data)

    c.cabecera(
        "Decisiones de tu negocio",
        "Indicadores para decidir hoy, sin complicaciones",
        icono=":material/trending_up:",
    )

    # ---- Resumen ejecutivo ----
    c.kpi_grid([
        ("Estado general", resumen.resumen_texto[:60] + ("…" if len(resumen.resumen_texto) > 60 else ""),
         None, None, "Resumen de lo que requiere tu atención"),
    ])

    # ---- Indicadores individuales ----
    for indicador in resumen.indicadores:
        color = _color_accion(indicador.accion)
        icono_accion = {
            "actuar": ":material/priority_high:",
            "revisar": ":material/notifications:",
            "ok": ":material/check_circle:",
        }.get(indicador.accion, ":material/info:")

        with c.panel(
            f"{indicador.nombre}  {c.badge(indicador.accion.upper(), color)}",
            subtitulo=indicador.detalle,
            icono=icono_accion,
        ):
            st.markdown(
                f"<div style='font-size:2rem;font-weight:700;color:{c.PALETA['primario'] if indicador.accion == 'ok' else c.PALETA['peligro'] if indicador.accion == 'actuar' else c.PALETA['secundario']};'>{indicador.valor}</div>",
                unsafe_allow_html=True,
            )

    # ---- Recomendación de acción ----
    n_actuar = sum(1 for i in resumen.indicadores if i.accion == "actuar")
    n_revisar = sum(1 for i in resumen.indicadores if i.accion == "revisar")

    st.divider()
    if n_actuar > 0:
        c.mensaje_error(
            f"Tienes {n_actuar} área{'s' if n_actuar != 1 else ''} que requiere{'n' if n_actuar != 1 else ''} atención inmediata.",
            detalle="Empieza por lo que está en rojo. Los indicadores en ámbar pueden esperar unos días.",
        )
    elif n_revisar > 0:
        st.info(
            f"Todo va bien, pero hay {n_revisar} área{'s' if n_revisar != 1 else ''} que vale la pena revisar esta semana.",
            icon=":material/notifications:",
        )
    else:
        c.confirmacion_exito(
            "Todo va bien.",
            "Sigue monitoreando tus indicadores semanalmente.",
        )


if __name__ == "__main__":
    principal()
