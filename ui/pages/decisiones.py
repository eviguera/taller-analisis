"""Página: Decisiones del negocio.

Entrega al dueño de la pyme los indicadores que necesita para decidir hoy,
con una recomendación de acción clara en cada uno.

Incluye indicadores predictivos: cuánto se facturará el mes que viene
(modelo Gradient Boosting) y el escenario 12 meses (simulador what-if).

Diseño minimalista: un número principal, tablas simples, color solo para
significado (rojo = actuar, ámbar = revisar, verde = todo bien).
"""
import pandas as pd
import streamlit as st

from ui import components as c
from ui.context import obtener_estado
from src.agentes_estrategicos import ejecutar_pipeline_de_decisiones


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

    # Ejecutar el pipeline completo de agentes de decisión.
    try:
        resultado = ejecutar_pipeline_de_decisiones(data, cfg=cfg)
    except Exception as e:
        c.mensaje_error(
            "No se pudieron calcular las decisiones de negocio.",
            detalle=str(e) if str(e) else "Revisa que los datos estén completos.",
        )
        return

    resumen = resultado.get("resumen_ejecutivo", {})
    analisis = resultado.get("analisis", {})
    dossier = resultado.get("dossier", {})
    validacion = resultado.get("validacion", {})

    c.cabecera(
        "Decisiones de tu negocio",
        "Indicadores para decidir hoy, sin complicaciones",
        icono=":material/trending_up:",
    )

    # ---- Resumen ejecutivo ----
    c.kpi_grid([
        ("Estado general", resumen.get("mensaje_principal", "Sin datos"),
         None, None, "Resumen de lo que requiere tu atención"),
    ])

    # ---- Indicadores individuales ----
    for indicador in resumen.get("indicadores", []):
        color = _color_accion(indicador.get("accion", "info"))
        icono_accion = {
            "actuar": ":material/priority_high:",
            "revisar": ":material/notifications:",
            "ok": ":material/check_circle:",
        }.get(indicador.get("accion", "info"), ":material/info:")

        with c.panel(
            f"{indicador.get('nombre', 'Indicador')}  {c.badge(indicador.get('accion', 'info').upper(), color)}",
            subtitulo=indicador.get("detalle", ""),
            icono=icono_accion,
        ):
            c.kpi_grid([
                ("Valor", indicador.get('valor', '-'), None, None,
                 indicador.get('detalle', '')),
            ])

    # ---- Recomendación de acción ----
    n_actuar = resumen.get("n_decisiones_actuar", 0)
    n_revisar = resumen.get("n_decisiones_revisar", 0)

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

    # ---- Predicción de ingresos (modelo ML) ----
    st.divider()
    st.markdown("### 📈 Ingresos esperados (próximo mes)")
    ingreso_predicho = None
    for d in dossier.get("decisiones", []):
        if d.get("area") == "ingresos":
            with c.panel(
                f"{d.get('decision', 'Ingresos')}  {c.badge(d.get('confianza', 'info').upper(), 'azul')}",
                subtitulo=d.get("motivo", ""),
                icono=":material/trending_up:",
            ):
                c.kpi_grid([
                    ("Impacto esperado",
                     f"{d.get('impacto_esperado', 0):+,.0f}",
                     None, None, "vs mes anterior"),
                ])
                st.caption(
                    f"Confianza: {d.get('confianza', 'N/A')} | "
                    f"Escenarios: conservador ${d.get('escenarios', {}).get('conservador', 0):,.0f} | "
                    f"base ${d.get('escenarios', {}).get('base', 0):,.0f} | "
                    f"agresivo ${d.get('escenarios', {}).get('agresivo', 0):,.0f}"
                )
            ingreso_predicho = d

    # ---- Escenario 12 meses ----
    st.divider()
    st.markdown("### 📊 Escenario a 12 meses")
    if not dossier.get("escenarios_disponibles", True):
        c.vacio(
            "Sin escenarios proyectados",
            icono=":material/query_stats:",
            detalle=(
                dossier.get("motivo_sin_escenarios")
                or "Importa facturas para proyectar escenarios con datos reales."
            ),
        )
    else:
        escenario_conservador = dossier.get("escenario_conservador", {})
        escenario_agresivo = dossier.get("escenario_agresivo", {})
        delta_ingresos = dossier.get("delta_ingresos", 0)
        delta_ebitda = dossier.get("delta_ebitda", 0)

        col1, col2, col3 = st.columns(3)
        with col1:
            c.kpi_grid([
                ("Conservador",
                 f"{escenario_conservador.get('ingresos', 0):,.0f}",
                 None, None,
                 f"Ingresos 12m · EBITDA {escenario_conservador.get('ebitda', 0):,.0f}"),
            ])
        with col2:
            c.kpi_grid([
                ("Agresivo (con acciones)",
                 f"{escenario_agresivo.get('ingresos', 0):,.0f}",
                 None, None,
                 f"Ingresos 12m · EBITDA {escenario_agresivo.get('ebitda', 0):,.0f}"),
            ])
        with col3:
            signo = "+" if delta_ingresos > 0 else ""
            c.kpi_grid([
                ("Delta ingresos",
                 f"{signo}{delta_ingresos:,.0f}",
                 None, None,
                 f"vs conservador · Δ EBITDA {signo}{delta_ebitda:,.0f}"),
            ])

    # ---- Recomendación principal ----
    st.divider()
    st.markdown("### 🎯 Recomendación principal")
    recomendacion = dossier.get("recomendacion_principal", {})
    if recomendacion and recomendacion.get("decision"):
        with c.panel(
            recomendacion.get("decision", "Decisión principal"),
            subtitulo=recomendacion.get("motivo", ""),
            icono=":material/lightbulb:",
        ):
            c.kpi_grid([
                ("Impacto esperado",
                 f"{recomendacion.get('impacto_esperado', 0):+,.0f}",
                 None, None,
                 recomendacion.get('motivo', '')),
            ])
            st.caption(
                f"Confianza: {recomendacion.get('confianza', 'N/A')} | Área: {recomendacion.get('area', 'general')}"
            )
    else:
        c.vacio(
            "No hay recomendación principal disponible.",
            icono=":material/info:",
            detalle="Importa más datos en 'Mis datos' para obtener recomendaciones más precisas.",
        )

    # ---- Alertas críticas ----
    alertas = analisis.get("alertas", [])
    alertas_criticas = [a for a in alertas if a.get("severidad") == "critica"]
    if alertas_criticas:
        st.divider()
        st.markdown("### 🚨 Alertas críticas")
        for alerta in alertas_criticas[:5]:
            with c.panel(
                f"{c.badge('CRÍTICA', 'rojo')} {alerta.get('titulo', 'Alerta')}",
                subtitulo=alerta.get("detalle", ""),
                icono=":material/error:",
            ):
                pass

    # ---- Advertencias de gobernanza ----
    advertencias = validacion.get("advertencias", [])
    if advertencias:
        st.divider()
        st.markdown("### ⚠️ Avisos de gobernanza")
        for adv in advertencias:
            st.warning(
                f"**{adv.get('area', 'General')}**: {adv.get('motivo', '')}"
            )

    # ---- Botón de reporte ----
    st.divider()
    st.markdown("### 📄 Reporte ejecutivo")
    st.caption("Genera un documento HTML completo con todo el análisis para compartir con tu equipo o inversores.")
    col_r1, col_r2 = st.columns([3, 1])
    with col_r1:
        st.info(
            "El reporte incluye portada, KPIs, alertas, decisiones, escenarios y recomendación principal."
        )
    with col_r2:
        if st.button("Generar reporte HTML", type="primary", icon=":material/description:", width="stretch"):
            with st.spinner("Generando reporte ejecutivo..."):
                try:
                    reporte = resultado.get("reporte", {})
                    if reporte and reporte.get("ruta"):
                        st.success(f"Reporte generado: {reporte['ruta']}")
                        with open(reporte["ruta"], "rb") as fh:
                            st.download_button(
                                "Descargar reporte HTML",
                                fh.read(),
                                file_name=reporte["ruta"].split("/")[-1],
                                mime="text/html",
                                icon=":material/download:",
                                width="stretch",
                            )
                    else:
                        st.error("No se pudo generar el reporte.")
                except Exception as e:
                    st.error(f"No se pudo generar el reporte: {e}")


if __name__ == "__main__":
    principal()
