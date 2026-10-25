"""Pagina: Scheduler de trabajos recurrentes.

Muestra los jobs registrados, permite ejecutar uno bajo demanda, y muestra
el historial de ejecuciones. El scheduler se ejecuta como proceso aparte
(entrypoint.sh o `python main.py scheduler run`); esta pagina solo consulta
y dispara acciones.
"""

import pandas as pd
import streamlit as st

from ui import components as c
from ui.context import en_kiosco, obtener_estado, exigir_escritura
from src.memoria import (
    inicializar_db,
    obtener_acciones_pendientes,
    obtener_todas_acciones,
    marcar_accion_hecha,
    marcar_accion_fallida,
    ruta_db_por_workspace,
)
from src.scheduler import Scheduler, listar_jobs, registrar_job


def principal():
    c.cabecera(
        "Scheduler de trabajos",
        "Jobs recurrentes y acciones programadas del workspace",
        icono=":material/schedule:",
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
    except Exception as e:  # noqa: BLE001
        c.mensaje_error(
            "No se pudo inicializar el ledger de memoria.",
            detalle=str(e) if str(e) else "",
        )
        return

    # ---- Jobs registrados y ejecución bajo demanda ----
    st.markdown("## Jobs disponibles")
    jobs = listar_jobs()
    if not jobs:
        c.vacio(
            "Sin jobs registrados.",
            icono=":material/playlist_add:",
            detalle="Registra jobs desde el modulo de scheduler o desde la CLI.",
        )
    else:
        c.dataframe(
            pd.DataFrame({"job": jobs, "estado": ["registrado"] * len(jobs)}),
            etiquetas={"job": "Nombre del job", "estado": "Estado"},
            indice_visible=False,
        )

    st.markdown("### Ejecutar un job ahora")
    col_j1, col_j2 = st.columns([3, 1])
    with col_j1:
        job_ejecutar = st.selectbox(
            "Selecciona el job",
            jobs,
            key="sel_job_ejecutar",
            disabled=not jobs or en_kiosco(),
        )
    with col_j2:
        if st.button(
            "Ejecutar ahora",
            type="primary",
            disabled=not jobs or en_kiosco(),
            width="stretch",
        ):
            try:
                exigir_escritura()
                sched = Scheduler(cfg.directorio_datos, db_path=db_path)
                # Importar jobs predeterminados para asegurar registro
                from src.scheduler.jobs_predeterminados import _job_evaluar_alertas  # noqa: F401
                sched.ejecutar_job_ahora(job_ejecutar)
                c.confirmacion_exito(f"Job '{job_ejecutar}' ejecutado.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                c.mensaje_error("No se pudo ejecutar el job.", detalle=str(exc))

    # ---- Historial de ejecuciones ----
    st.markdown("## Historial de ejecuciones")
    sched = Scheduler(cfg.directorio_datos, db_path=db_path)
    try:
        historial = sched.obtener_historial()
    except Exception as e:  # noqa: BLE001
        c.mensaje_error("No se pudo leer el historial.", detalle=str(e))
        historial = []

    if not historial:
        c.vacio(
            "Sin ejecuciones registradas aún.",
            icono=":material/history:",
            detalle="Cada vez que el scheduler ejecuta un job, se registra aquí el resultado.",
        )
    else:
        for h in historial[:30]:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    icono_estado = ":material/check_circle:" if h.estado == "ok" else ":material/error:"
                    st.markdown(
                        f"{icono_estado} **{h.job}** — {h.estado}"
                    )
                    if h.error:
                        st.caption(f"Error: {h.error[:200]}")
                with col2:
                    st.caption(f"Ejecutado: {h.ejecutada_en[:16]}")
                with col3:
                    st.caption(f"Filas: {h.filas_afectadas}")

    # ---- Acciones pendientes ----
    st.markdown("## Acciones pendientes de ejecución")
    try:
        acciones = obtener_acciones_pendientes(db_path=db_path)
    except Exception as e:  # noqa: BLE001
        c.mensaje_error("No se pudieron leer las acciones.", detalle=str(e))
        acciones = []

    if not acciones:
        c.vacio(
            "Sin acciones pendientes.",
            icono=":material/check_circle:",
            detalle="El scheduler las ejecuta según su hora programada.",
        )
    else:
        for a in acciones:
            with st.container(border=True):
                st.markdown(f"**{a.tipo}** — {a.texto_intencion[:100]}")
                st.caption(
                    f"Ejecutar en: {a.ejecutar_en[:16]} · "
                    f"tipo: {a.tipo} · estado: {a.estado}"
                )

    # ---- Todas las acciones (historial) ----
    st.markdown("## Todas las acciones programadas")
    try:
        todas = obtener_todas_acciones(db_path=db_path)
    except Exception as e:  # noqa: BLE001
        c.mensaje_error("No se pudieron leer las acciones.", detalle=str(e))
        todas = []

    if todas:
        for a in todas[:30]:
            with st.container(border=True):
                c.html(
                    f"**{a.tipo}** — {a.texto_intencion[:100]}  "
                    f"{c.badge(a.estado.upper(), 'azul' if a.estado == 'hecha' else 'rojo')}"
                )
                st.caption(
                    f"Programada: {a.creada_en[:16]} · Ejecutar: {a.ejecutar_en[:16]} · "
                    f"estado: {a.estado}"
                )
                if a.ultimo_error:
                    st.caption(f"Último error: {a.ultimo_error}")
    else:
        c.vacio("Sin acciones registradas.", icono=":material/schedule:")

    st.caption(
        "Para arrancar el scheduler como proceso aparte: "
        "`python main.py scheduler run` (o añádelo al entrypoint.sh del contenedor)."
    )

    if en_kiosco():
        st.info("Modo presentación: solo lectura.")


if __name__ == "__main__":
    principal()
