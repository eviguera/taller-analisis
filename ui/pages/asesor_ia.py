"""Página: Asesor IA - Diagnóstico automático grounded a datos del workspace."""
import streamlit as st

from src.aplicacion import asesor_negocio
from ui import components
from ui.context import cargar_datos, obtener_config


def principal():
    cfg = obtener_config()
    data = cargar_datos(cfg)

    st.title("🧠 Asesor IA")
    st.caption(
        "Diagnóstico accionable basado en los datos reales de tu workspace. "
        "Respuestas ancladas a agregados."
    )

    disponible = asesor_negocio.asesor_ia_disponible()
    if not disponible:
        st.warning(
            "El Asesor IA necesita una clave de OpenRouter para generar respuestas. "
            "La generación está deshabilitada hasta que configures "
            "`GIRO_IA_API_KEY` o `OPENROUTER_API_KEY` en el entorno del proceso."
        )
        st.code(
            'export GIRO_IA_API_KEY="tu-clave"\n'
            ".venv/bin/streamlit run dashboard.py",
            language="bash",
        )
        st.caption(
            "La clave se lee solo de variables de entorno; no se guarda en el "
            "repositorio ni en la configuración. Reinicia el dashboard después "
            "de definirla."
        )

    tab_diag, tab_chat = st.tabs(["Diagnóstico", "Preguntar"])

    with tab_diag:
        st.markdown("### Diagnóstico automático")
        st.info(
            "Genera un diagnóstico con hallazgos, acciones priorizadas y "
            "riesgos usando solo agregados de tu negocio."
        )
        if st.button("Generar diagnóstico", type="primary", disabled=not disponible):
            with st.spinner("Analizando datos y generando diagnóstico..."):
                try:
                    resp = asesor_negocio.generar_diagnostico_automatico(cfg, data)
                    st.session_state["asesor_diag"] = resp
                except Exception as e:
                    st.error(f"Error al generar diagnóstico: {e}")
        resp = st.session_state.get("asesor_diag")
        if resp is not None:
            if getattr(resp, "resumen_ejecutivo", ""):
                with components.panel("Resumen ejecutivo"):
                    st.markdown(resp.resumen_ejecutivo)
            if getattr(resp, "hallazgos", None):
                st.markdown("#### Hallazgos clave")
                for h in resp.hallazgos:
                    sev = (h.severidad or "").lower()
                    badge_map = {
                        "critica": "rojo",
                        "alta": "naranja",
                        "media": "amarillo",
                        "baja": "azul",
                        "ok": "verde",
                    }
                    tipo_badge = badge_map.get(sev, "info")
                    components.panel(h.titulo, h.descripcion)
                    components.html(
                        f"Severidad: {components.badge(sev or 'media', tipo_badge)}"
                    )
                    if h.evidencia:
                        with st.expander("Evidencia"):
                            for ev in h.evidencia:
                                st.write(f"- {ev}")
            if getattr(resp, "acciones", None):
                st.markdown("#### Acciones priorizadas")
                for i, a in enumerate(resp.acciones, 1):
                    with components.panel(f"{i}. {a.titulo}", a.descripcion):
                        cols = st.columns(4)
                        cols[0].markdown(f"**Prioridad:** {a.prioridad}")
                        cols[1].markdown(f"**Esfuerzo:** {a.esfuerzo}")
                        cols[2].markdown(f"**Impacto:** {a.impacto}")
                        cols[3].markdown(f"**Plazo:** {a.plazo}")
                        st.caption(f"Categoría: {a.categoria}")
            if getattr(resp, "riesgos", None):
                st.markdown("#### Riesgos")
                for r in resp.riesgos:
                    with components.panel(r.titulo, r.descripcion):
                        st.caption(
                            f"Probabilidad: {r.probabilidad} | Impacto: {r.impacto}"
                        )
                        if r.mitigacion:
                            st.info(f"Mitigación: {r.mitigacion}")
            if getattr(resp, "preguntas_para_aclarar", None) and resp.preguntas_para_aclarar:
                st.markdown("#### Preguntas para aclarar")
                for p in resp.preguntas_para_aclarar:
                    st.write(f"- {p}")
            if getattr(resp, "fuentes_usadas", None) and resp.fuentes_usadas:
                st.caption(f"Fuentes usadas: {', '.join(resp.fuentes_usadas)}")
            if getattr(resp, "modelo", ""):
                st.caption(f"Modelo: {resp.proveedor}/{resp.modelo}")

    with tab_chat:
        st.markdown("### Pregúntale a GIRO")
        pregunta = st.text_input(
            "Pregunta sobre tus datos",
            placeholder="¿Dónde pierdo margen? ¿Qué clientes me dejaron de comprar?",
            disabled=not disponible,
        )
        if st.button("Preguntar", disabled=not disponible):
            if not pregunta.strip():
                st.warning("Escribe una pregunta")
            else:
                with st.spinner("Consultando con el asesor..."):
                    try:
                        resp = asesor_negocio.preguntar_al_asesor(
                            cfg, data, pregunta.strip()
                        )
                        st.session_state["asesor_chat"] = resp
                    except Exception as e:
                        st.error(f"Error: {e}")
        resp_c = st.session_state.get("asesor_chat")
        if resp_c is not None:
            if getattr(resp_c, "resumen_ejecutivo", ""):
                with components.panel("Respuesta"):
                    st.markdown(resp_c.resumen_ejecutivo)
            if getattr(resp_c, "acciones", None):
                st.markdown("#### Acciones sugeridas")
                for a in resp_c.acciones:
                    st.write(
                        f"- **{a.titulo}** "
                        f"({a.prioridad}/{a.esfuerzo}/{a.plazo}): {a.descripcion}"
                    )
            if getattr(resp_c, "preguntas_para_aclarar", None) and resp_c.preguntas_para_aclarar:
                with st.expander("Necesito aclaraciones"):
                    for p in resp_c.preguntas_para_aclarar:
                        st.write(f"- {p}")
            if getattr(resp_c, "fuentes_usadas", None) and resp_c.fuentes_usadas:
                st.caption(f"Fuentes usadas: {', '.join(resp_c.fuentes_usadas)}")
