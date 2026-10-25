"""Pagina: Memoria operativa (ledger de decisiones, iniciativas y acciones).

Muestra lo que el sistema ha decidido, lo que esta en curso y las acciones
programadas del workspace. Permite editar resultados de decisiones, gestionar
mutes de alertas y ver el historial de ejecuciones del scheduler.
"""

import streamlit as st

from ui import components as c
from ui.context import en_kiosco, obtener_estado, exigir_escritura
from src.memoria import (
    inicializar_db,
    listar_decisiones,
    actualizar_resultado_decision,
    listar_iniciativas,
    obtener_todas_iniciativas,
    eliminar_iniciativa,
    registrar_iniciativa,
    listar_consejos,
    obtener_acciones_pendientes,
    obtener_todas_acciones,
    programar_accion,
    marcar_accion_hecha,
    marcar_accion_fallida,
    ruta_db_por_workspace,
    agregar_mute,
    listar_mutes,
    eliminar_mute,
    matches_mute,
    HistorialEjecucion,
)


def _severidad_color(sev: str) -> str:
    return {"critica": "rojo", "media": "amarillo", "baja": "azul"}.get(sev, "info")


def principal():
    c.cabecera(
        "Memoria operativa",
        "Decisiones, iniciativas, acciones y mutes del workspace",
        icono=":material/memory:",
    )

    try:
        cfg, _data, _analyzer, _predictor = obtener_estado()
    except Exception as e:
        c.mensaje_error(
            "No se pudieron cargar los datos del workspace.",
            detalle=str(e) if str(e) else "Revisa que el almacén del workspace esté disponible.",
        )
        return

    db_path = ruta_db_por_workspace(cfg.directorio_datos)
    try:
        inicializar_db(db_path)
    except Exception as e:  # noqa: BLE001 — no bloquee la vista por la memoria
        c.mensaje_error(
            "No se pudo inicializar el ledger de memoria.",
            detalle=str(e) if str(e) else "",
        )
        return

    # ---- Decisiones recientes ----
    st.markdown("## Decisiones recientes")
    try:
        decisiones = listar_decisiones(db_path=db_path)
    except Exception as e:  # noqa: BLE001
        c.mensaje_error("No se pudieron leer las decisiones.", detalle=str(e))
        decisiones = []

    if not decisiones:
        c.vacio(
            "Sin decisiones registradas aún.",
            icono=":material/assignment:",
            detalle="Las alertas evaluadas y las acciones del scheduler se registran aquí automáticamente.",
        )
    else:
        for d in decisiones[:30]:
            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"**{d.resumen}**")
                    st.caption(
                        f"{d.timestamp[:16]} · dominio: {d.dominio} · sesión: {d.sesion_id or '—'}"
                    )
                    if d.justificacion:
                        st.caption(f"Justificación: {d.justificacion}")
                with col2:
                    c.badge((d.sesion_id or "sistema").upper(), "info")
                if d.resultado:
                    st.markdown(
                        f":material/check_circle: **Resultado:** {d.resultado}"
                    )
                else:
                    # Permitir editar el resultado (solo admin / escritura)
                    clave_res = f"res_{d.id}"
                    nuevo = st.text_input(
                        "Resultado real (p. ej. 'cliente reactivado')",
                        key=clave_res,
                        placeholder="¿Qué pasó realmente?",
                    )
                    col_s, col_x = st.columns([1, 4])
                    with col_s:
                        if st.button(
                            "Guardar",
                            key=f"save_{d.id}",
                            disabled=en_kiosco(),
                            width="stretch",
                        ):
                        # El on_click se gestiona con el rerun del botón; acá usamos
                        # session_state para persistir tras el rerun.
                            st.session_state[f"_guardar_res_{d.id}"] = nuevo
                    if st.session_state.get(f"_guardar_res_{d.id}") and not en_kiosco():
                        try:
                            exigir_escritura()
                            valor = st.session_state.pop(f"_guardar_res_{d.id}")
                            if actualizar_resultado_decision(d.id, valor, db_path=db_path):
                                c.confirmacion_exito("Resultado guardado.")
                                st.rerun()
                            else:
                                c.mensaje_error("No se encontró la decisión para actualizar.")
                        except Exception as exc:  # noqa: BLE001
                            c.mensaje_error("No se pudo guardar el resultado.", detalle=str(exc))

    # ---- Iniciativas ----
    st.markdown("## Iniciativas")
    col_i1, col_i2 = st.columns([3, 1])
    with col_i1:
        st.markdown("### Activar / crear iniciativa")
        with st.form("form_iniciativa", border=False):
            nuevo_titulo = st.text_input("Título", key="inp_iniciativa_titulo")
            nuevo_estado = st.selectbox(
                "Estado",
                ["activa", "en curso", "pausada", "completada"],
                key="inp_iniciativa_estado",
            )
            nuevo_resumen = st.text_area("Resumen", key="inp_iniciativa_resumen")
            submitted = st.form_submit_button("Guardar iniciativa", type="primary")
        if submitted and not en_kiosco():
            try:
                exigir_escritura()
                if not nuevo_titulo.strip():
                    c.mensaje_error("El título es obligatorio.")
                else:
                    registrar_iniciativa(
                        titulo=nuevo_titulo.strip(),
                        estado=nuevo_estado,
                        resumen=nuevo_resumen.strip(),
                        db_path=db_path,
                    )
                    c.confirmacion_exito("Iniciativa guardada.")
                    st.rerun()
            except Exception as exc:  # noqa: BLE001
                c.mensaje_error("No se pudo guardar la iniciativa.", detalle=str(exc))

    try:
        iniciativas = obtener_todas_iniciativas(db_path=db_path)
    except Exception as e:  # noqa: BLE001
        c.mensaje_error("No se pudieron leer las iniciativas.", detalle=str(e))
        iniciativas = []

    if iniciativas:
        st.markdown("### Listado")
        for i in iniciativas[:30]:
            with st.container(border=True):
                col1, col2, col3 = st.columns([4, 1, 1])
                with col1:
                    c.html(f"**{i.titulo}**  {c.badge(i.estado.upper(), 'azul')}")
                    if i.resumen:
                        st.caption(i.resumen)
                with col2:
                    st.caption(f"Actualizada: {i.actualizada_en[:16]}")
                with col3:
                    if i.estado != "completada" and not en_kiosco():
                        if st.button(
                            "Completar",
                            key=f"comp_{i.id}",
                            width="stretch",
                        ):
                            try:
                                exigir_escritura()
                                registrar_iniciativa(
                                    titulo=i.titulo,
                                    estado="completada",
                                    resumen=i.resumen or "",
                                    db_path=db_path,
                                )
                                c.confirmacion_exito("Iniciativa completada.")
                                st.rerun()
                            except Exception as exc:  # noqa: BLE001
                                c.mensaje_error("No se pudo completar.", detalle=str(exc))
                    if en_kiosco():
                        st.caption("Solo lectura")

    # ---- Consejos ----
    st.markdown("## Consejos del sistema")
    try:
        consejos = listar_consejos(db_path=db_path)
    except Exception as e:  # noqa: BLE001
        c.mensaje_error("No se pudieron leer los consejos.", detalle=str(e))
        consejos = []

    if not consejos:
        c.vacio(
            "Sin consejos registrados aún.",
            icono=":material/lightbulb:",
            detalle="Los agentes de estrategia registran sus consejos aquí.",
        )
    else:
        for cn in consejos[:20]:
            with st.container(border=True):
                st.markdown(f"**{cn.dominio}**: {cn.resumen_consejo[:200]}")
                st.caption(f"Consulta: {cn.resumen_consulta[:120]} · {cn.timestamp[:16]}")

    # ---- Mutes de alertas ----
    st.markdown("## Mutes de alertas")
    st.caption(
        "Silencia alertas de un tipo y entidad durante un período. Útil para evitar "
        "ruido de una regla que ya conoces y no quieres que vuelva a disparar."
    )

    col_m1, col_m2 = st.columns([3, 1])
    with col_m1:
        with st.form("form_mute", border=False):
            mute_tipo = st.text_input("Tipo de alerta", key="inp_mute_tipo",
                                      placeholder="ej: stock_bajo, churn, caida_ingresos")
            mute_entidad = st.text_input("Entidad", key="inp_mute_entidad",
                                         placeholder="ej: producto X, cliente Y")
            mute_hasta = st.date_input("Silenciar hasta", key="inp_mute_hasta")
            mute_motivo = st.text_input("Motivo", key="inp_mute_motivo")
            submitted_mute = st.form_submit_button("Agregar mute", type="primary")
        if submitted_mute and not en_kiosco():
            try:
                exigir_escritura()
                if not mute_tipo.strip() or not mute_entidad.strip():
                    c.mensaje_error("Tipo y entidad son obligatorios.")
                else:
                    hasta_iso = f"{mute_hasta.isoformat()}T23:59:59+00:00"
                    agregar_mute(
                        tipo=mute_tipo.strip(),
                        entidad=mute_entidad.strip(),
                        hasta_iso=hasta_iso,
                        motivo=mute_motivo.strip(),
                        db_path=db_path,
                    )
                    c.confirmacion_exito("Mute agregado.")
                    st.rerun()
            except Exception as exc:  # noqa: BLE001
                c.mensaje_error("No se pudo agregar el mute.", detalle=str(exc))

    try:
        mutes = listar_mutes(db_path=db_path)
    except Exception as e:  # noqa: BLE001
        c.mensaje_error("No se pudieron leer los mutes.", detalle=str(e))
        mutes = []

    if mutes:
        st.markdown("### Mutes activos")
        for m in mutes:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.markdown(f"**{m.tipo}** · {m.entidad}")
                    st.caption(f"Hasta: {m.hasta[:16]} · Motivo: {m.motivo or '—'}")
                with col2:
                    st.caption(f"Creado: {m.creada_en[:16]}")
                with col3:
                    if not en_kiosco():
                        if st.button("Eliminar", key=f"delmute_{m.id}", width="stretch"):
                            try:
                                exigir_escritura()
                                if eliminar_mute(m.id, db_path=db_path):
                                    c.confirmacion_exito("Mute eliminado.")
                                    st.rerun()
                                else:
                                    c.mensaje_error("No se encontró el mute.")
                            except Exception as exc:  # noqa: BLE001
                                c.mensaje_error("No se pudo eliminar el mute.", detalle=str(exc))
                    else:
                        st.caption("Solo lectura")
    else:
        c.vacio("Sin mutes activos.", icono=":material/volume_off:")

    # ---- Acciones programadas ----
    st.markdown("## Acciones programadas")
    try:
        acciones = obtener_todas_acciones(db_path=db_path)
    except Exception as e:  # noqa: BLE001
        c.mensaje_error("No se pudieron leer las acciones.", detalle=str(e))
        acciones = []

    if not acciones:
        c.vacio(
            "Sin acciones programadas.",
            icono=":material/schedule:",
            detalle="El scheduler las crea y ejecuta según su hora programada.",
        )
    else:
        for a in acciones[:30]:
            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(
                        f"**{a.tipo}** — {a.texto_intencion[:120]}{'…' if len(a.texto_intencion) > 120 else ''}"
                    )
                    st.caption(
                        f"Ejecutar en: {a.ejecutar_en[:16]} · canal: {a.canal} "
                        f"· intentos: {a.intentos} · estado: {a.estado}"
                    )
                    if a.ultimo_error:
                        c.badge("FALLO", "rojo")
                        st.caption(a.ultimo_error)
                with col2:
                    if a.estado == "pendiente" and not en_kiosco():
                        if st.button("Marcar hecha", key=f"done_{a.id}", width="stretch"):
                            try:
                                exigir_escritura()
                                if marcar_accion_hecha(a.id, db_path=db_path):
                                    c.confirmacion_exito("Marcada como hecha.")
                                    st.rerun()
                                else:
                                    c.mensaje_error("No se encontró la acción.")
                            except Exception as exc:  # noqa: BLE001
                                c.mensaje_error("No se pudo marcar.", detalle=str(exc))
                    elif a.estado == "pendiente":
                        st.caption("Solo lectura")

    if en_kiosco():
        st.info("Modo presentación: la memoria es de solo lectura.")


if __name__ == "__main__":
    principal()
