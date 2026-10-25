"""Pagina de onboarding: flujo guiado para usuarios nuevos sin datos.

Se muestra solo cuando un workspace no tiene datos cargados. Guia al usuario
por tres pasos: configurar su negocio, cargar sus archivos y procesar el ETL.
Al finalizar, el dashboard queda listo para usar con sus propios datos.
"""

import streamlit as st

import pandas as pd

from ui import components as c
from ui.context import (
    obtener_config, obtener_workspace, cargar_datos, exigir_escritura,
)
from src.core.templates import lista_verticales


def _hay_datos() -> bool:
    """True si el workspace activo ya tiene al menos un dataset con filas."""
    cfg = obtener_config()
    try:
        data = cargar_datos(cfg)
    except Exception:  # noqa: BLE001 — si falla, tratamos como sin datos
        return False
    return bool(data) and any(
        isinstance(df, pd.DataFrame) and not df.empty
        for df in data.values()
    )


def _paso_configuracion() -> bool:
    """Paso 1: nombre, moneda y sector del negocio (preferencias de sesion)."""
    cfg = obtener_config()

    st.markdown("### Paso 1 de 3 — Configura tu negocio")
    st.caption("Esto se usa para personalizar tus reportes y dashboards.")

    c1, c2 = st.columns(2)
    with c1:
        nombre = st.text_input(
            "Nombre de tu negocio",
            value=cfg.negocio_nombre or "",
            placeholder="Ej: Taller Don Juan",
            key="onb_nombre",
        )
        moneda = st.selectbox(
            "Moneda",
            ["CLP", "MXN", "USD", "EUR", "COP"],
            index=["CLP", "MXN", "USD", "EUR", "COP"].index(cfg.moneda)
            if cfg.moneda in ["CLP", "MXN", "USD", "EUR", "COP"] else 0,
            key="onb_moneda",
        )
    with c2:
        sectores = ["general"] + [v for v in lista_verticales() if v != "general"]
        sector = st.selectbox(
            "Sector (plantilla inicial)",
            sectores,
            key="onb_sector",
            help="Cada sector trae sus propias metricas de referencia.",
        )

    st.markdown("---")
    if st.button("Guardar y continuar",
                 type="primary", icon=":material/arrow_forward:",
                 width="stretch", key="onb_btn_config"):
        if not nombre.strip():
            st.error("El nombre del negocio es obligatorio.")
            return False
        # Guardar en session_state (se aplican en obtener_config en cada rerun)
        st.session_state["negocio_nombre"] = nombre.strip()
        st.session_state["moneda"] = moneda
        st.session_state["sector"] = sector
        st.session_state["onb_paso"] = 2
        st.rerun()
    return True


def _paso_cargar_datos() -> bool:
    """Paso 2: subir archivos o generar datos de ejemplo."""
    st.markdown("### Paso 2 de 3 — Carga tus datos")
    st.caption(
        "Sube los archivos de tu negocio: facturas, clientes, servicios, "
        "vehiculos e inventario. Formatos aceptados: CSV, Excel (.xlsx/.xls) "
        "y PSPP/SPSS (.sav/.por)."
    )

    archivos = st.file_uploader(
        "Selecciona uno o mas archivos",
        type=["csv", "xlsx", "xls", "sav", "por"],
        accept_multiple_files=True,
        key="onb_archivos",
    )

    if archivos:
        st.info(f"{len(archivos)} archivo(s) seleccionado(s).")
        for a in archivos:
            st.caption(f"• {a.name} ({a.size:,} bytes)")

    st.markdown("---")

    # Opcion: datos de ejemplo (solo administradores pueden escribir)
    try:
        exigir_escritura()
        puede_ejemplo = True
    except Exception:  # noqa: BLE001
        puede_ejemplo = False

    c1, c2 = st.columns(2)
    with c1:
        if puede_ejemplo:
            if st.button("Usar datos de ejemplo",
                         icon=":material/auto_awesome:", width="stretch",
                         key="onb_btn_ejemplo"):
                from generate_data import main as generar_ejemplos
                try:
                    with st.spinner("Generando datos de ejemplo…"):
                        destino = generar_ejemplos(obtener_workspace())
                    st.success(
                        f"Datos de ejemplo generados en `{destino}`. "
                        "Procesa el ETL en el siguiente paso."
                    )
                    st.session_state["onb_tiene_ejemplo"] = True
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(f"No se pudo generar datos de ejemplo: {e}")
        else:
            st.button("Usar datos de ejemplo",
                      icon=":material/auto_awesome:", width="stretch",
                      disabled=True, key="onb_btn_ejemplo",
                      help="Solo los administradores pueden generar datos de ejemplo.")

    with c2:
        procesar = st.button(
            "Procesar ETL y continuar",
            type="primary", icon=":material/engine:",
            width="stretch", key="onb_btn_procesar",
            disabled=not archivos and not st.session_state.get("onb_tiene_ejemplo"),
        )

    if procesar:
        if archivos:
            st.warning(
                "La carga directa de archivos desde el onboarding se habilita "
                "en la pagina 'Mis datos'. Sube estos archivos alla y vuelve "
                "aqui para procesar el ETL."
            )
        st.session_state["onb_paso"] = 3
        st.rerun()
    return True


def _paso_finalizar() -> bool:
    """Paso 3: completar el onboarding."""
    st.markdown("### Paso 3 de 3 — Listo")
    st.markdown(
        "Tu negocio esta configurado en GIRO. Ahora puedes explorar el "
        "dashboard, ver KPIs, predicciones y alertas con tus propios datos."
    )

    hay = _hay_datos()
    if hay:
        st.success("Se detectaron datos en tu workspace.")
    else:
        st.info(
            "Aun no hay datos cargados. Ve a la pagina 'Mis datos' para "
            "subir tus archivos, o usa 'Generar datos de ejemplo' para probar."
        )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Ir al dashboard", type="primary",
                     icon=":material/dashboard:", width="stretch",
                     key="onb_btn_dashboard"):
            st.session_state["_onboarding_completado"] = True
            st.session_state["onb_paso"] = 4
            st.switch_page("ui/pages/resumen.py")
    with c2:
        if st.button("Configurar mas tarde",
                     icon=":material/settings:", width="stretch",
                     key="onb_btn_config_mas_tarde"):
            st.session_state["_onboarding_completado"] = True
            st.session_state["onb_paso"] = 4
            st.rerun()
    return True


def principal():
    """Renderiza el flujo de onboarding si no hay datos."""
    cfg = obtener_config()
    c.cabecera(
        "Bienvenido a GIRO",
        "Configuraremos tu negocio en 3 pasos rapidos.",
        icono=":material/rocket_launch:",
    )

    if "onb_paso" not in st.session_state:
        st.session_state["onb_paso"] = 1

    paso = st.session_state["onb_paso"]

    # Barra de progreso visual
    progreso = (paso - 1) / 3
    st.progress(progreso)

    if paso == 1:
        _paso_configuracion()
    elif paso == 2:
        _paso_cargar_datos()
    elif paso == 3:
        _paso_finalizar()
    elif paso >= 4:
        st.markdown("## :material/check_circle: Onboarding completado")
        st.markdown(
            "Ya puedes usar GIRO con tus datos. "
            "Usa el menu lateral para navegar entre las paginas."
        )
        if st.button("Ir al dashboard", type="primary",
                     icon=":material/dashboard:", width="stretch",
                     key="onb_btn_final"):
            st.switch_page("ui/pages/resumen.py")


if __name__ == "__main__":
    principal()