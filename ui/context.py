"""Estado compartido de la aplicacion: configuracion, datos, analisis y predicciones.

Se prioriza la simplicidad: la configuracion se cachea como recurso y la
velocidad de carga la da el cache parquet del pipeline; asi los datos nuevos
siempre se ven sin clicks extra.
"""

import streamlit as st

from src.core.config_manager import cargar_config
from src.core.pipeline import procesar_etl
from src.data_loader import load_all, get_data_summary, get_store
from src.analyzer import Analyzer
from src.predictions import Predictor


@st.cache_resource(show_spinner="Cargando configuracion...")
def _config_personalizada(nombre, moneda, slogan):
    """Configuracion base con las preferencias de la sesion aplicadas."""
    cfg = cargar_config()
    if nombre:
        cfg.negocio_nombre = nombre
    if moneda:
        cfg.moneda = moneda
    if slogan:
        cfg.slogan = slogan
    return cfg


def obtener_config():
    """Configuracion global, aplicadas las preferencias de la sesion.

    Los controles de la barra lateral guardan `negocio_nombre`, `moneda` y
    `slogan` en `st.session_state`; si no existen, se usa lo definido en
    `config.yaml`.
    """
    nombre = st.session_state.get("negocio_nombre") or st.session_state.get("taller_nombre") or None
    moneda = st.session_state.get("moneda") or None
    slogan = st.session_state.get("slogan") or None
    return _config_personalizada(nombre, moneda, slogan)


def cargar_datos(_cfg):
    """Carga los datasets en memoria (usa cache parquet del pipeline)."""
    return load_all(_cfg)


@st.cache_resource(show_spinner="Calculando analisis...")
def calcular_analista(data):
    return Analyzer(data)


@st.cache_resource(show_spinner="Entrenando modelos de prediccion...")
def calcular_predictor(data):
    return Predictor(data)


def obtener_estado():
    """Devuelve (cfg, data, analyzer, predictor) listos para renderizar una pagina."""
    cfg = obtener_config()
    try:
        data = cargar_datos(cfg)
        if len(data) < 3:
            st.warning("Se cargaron pocos datasets. Revisa la pagina de Datos para importar tus archivos.")
        analyzer = calcular_analista(data)
        predictor = calcular_predictor(data)
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudieron cargar los datos:\n\n`{e}`")
        st.info("Ve a la pagina **'Datos y configuracion'** despues de importar tus archivos.")
        st.stop()
    return cfg, data, analyzer, predictor


def resumen_calidad(data):
    return get_data_summary(data)


def ejecutar_etl_ui():
    """Ejecuta el ETL, actualiza DuckDB y limpia caches para ver los cambios."""
    cfg = obtener_config()
    resultado = procesar_etl(cfg)
    st.cache_data.clear()
    st.cache_resource.clear()
    return resultado


def consulta_sql(sql: str):
    """Registra las tablas actuales en DuckDB y ejecuta una consulta."""
    cfg = obtener_config()
    data = cargar_datos(cfg)
    store = get_store()
    try:
        if data:
            store.registrar_tablas(data)
        return store.consulta(sql)
    finally:
        store.cerrar()


def obtener_estructura():
    """Registra los datos en DuckDB, materializa core/analitica y devuelve
    el catalogo del almacen (tablas y vistas por esquema)."""
    cfg = obtener_config()
    data = cargar_datos(cfg)
    store = get_store()
    try:
        if data:
            store.registrar_tablas(data)
            store.construir_estructura(data)
        return store.info_estructura()
    finally:
        store.cerrar()


def consultar_vista(nombre: str):
    """Consulta una vista del esquema analitica (p. ej. 'ingresos_mensuales')."""
    cfg = obtener_config()
    data = cargar_datos(cfg)
    store = get_store()
    try:
        if data:
            store.registrar_tablas(data)
            store.construir_estructura(data)
        return store.consultar_vista(nombre)
    finally:
        store.cerrar()


VISTAS_PARA_EXPORTAR = [
    "ingresos_mensuales",
    "ingresos_por_marca",
    "ingresos_por_vehiculo",
    "rfm_clientes",
    "churn_clientes",
    "detalle_servicios",
    "demanda_servicios_mensual",
    "inventario_estado",
    "facturas_con_dimensiones",
]


def exportar_analitica_pspp(destino):
    """Exporta los datasets cargados y las vistas analiticas clave a .sav.

    Devuelve (exportados: list[str], errores: dict). Util para llevar la
    analitica completa a PSPP/SPSS desde la interfaz.
    """
    from pathlib import Path

    from src.loaders.pspp_loader import exportar_sav

    cfg = obtener_config()
    data = cargar_datos(cfg)
    store = get_store()
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)

    exportados: list = []
    errores: dict = {}
    try:
        if data:
            store.registrar_tablas(data)
            store.construir_estructura(data)

        for nombre, df in data.items():
            if df is None or df.empty:
                continue
            try:
                exportar_sav(df, destino / f"{nombre}.sav", label_archivo=f"{nombre} exportado")
                exportados.append(nombre)
            except Exception as e:  # noqa: BLE001
                errores[nombre] = str(e)

        for vista in VISTAS_PARA_EXPORTAR:
            try:
                df = store.consultar_vista(vista)
                exportar_sav(df, destino / f"analitica_{vista}.sav",
                             label_archivo=f"analitica_{vista}")
                exportados.append(f"analitica.{vista}")
            except Exception as e:  # noqa: BLE001
                errores[vista] = str(e)
        return exportados, errores
    finally:
        store.cerrar()