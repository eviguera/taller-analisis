"""Estado compartido de la aplicacion: sesion, configuracion, datos, analisis y predicciones.

Se prioriza la simplicidad: la configuracion se cachea como recurso y la
velocidad de carga la da el cache parquet del pipeline; asi los datos nuevos
siempre se ven sin clicks extra. Soporta multiplicidad de workspaces
(multiempresa) seleccionables desde la barra lateral.

El ambito de empresa se impone aqui, en el servidor: ``obtener_workspace``
pasa siempre por ``auth.workspace_permitido``, de modo que un cliente sin
permisos sobre una empresa no puede llegar a su datos aunque manipule
``st.session_state``.
"""

import hashlib

import streamlit as st

from src.core import auth, conector_sql
from src.core.config_manager import cargar_config
from src.core.pipeline import procesar_etl
from src.data_loader import load_all, get_data_summary, get_store
from src.analyzer import Analyzer
from src.predictions import Predictor
from src import workspaces


def _kiosco() -> bool:
    return str(st.query_params.get("kiosco", "0")) in ("1", "true", "verdadero")


def en_kiosco() -> bool:
    """True si la pagina se sirve en modo presentacion (``?kiosco=1``).

    Las paginas lo consultan para ocultar las acciones que escriben. El
    kiosco promete solo lectura y esa promesa tiene que valer tambien para
    un admin que entra con su sesion abierta, no solo para el visitante.
    """
    return _kiosco()


def _token() -> str:
    """Token de sesion: estado de sesion y, si se pidio, query string."""
    token = st.session_state.get("auth_token") or ""
    if not token and auth.PERSISTIR_URL:
        token = str(st.query_params.get(auth.PARAM_URL, "") or "")
    return token


def sesion() -> auth.Sesion:
    """Sesion de la peticion actual (identidad, rol y alcance)."""
    return auth.inicio_de_sesion(_token(), modo_kiosco=_kiosco())


def iniciar_sesion(usuario: auth.Usuario) -> None:
    """Guarda el token tras un login correcto."""
    st.session_state["auth_token"] = auth.emitir_cookie(usuario)
    if auth.PERSISTIR_URL:
        st.query_params[auth.PARAM_URL] = st.session_state["auth_token"]
    st.cache_data.clear()
    st.cache_resource.clear()


def cerrar_sesion() -> None:
    """Cierra la sesion, limpia caches y recarga."""
    st.session_state.pop("auth_token", None)
    st.query_params.pop(auth.PARAM_URL, None)
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()


def exigir(permiso: str, mensaje: str = "") -> None:
    """Frena la renderizacion si la sesion no tiene el permiso."""
    s = sesion()
    if s.puede(permiso):
        return
    st.error(mensaje or "No tienes permiso para esta seccion.")
    st.caption("Pide a un administrador que te otorgue acceso.")
    st.stop()


def exigir_escritura(mensaje: str = "") -> None:
    """Comprueba el permiso EN la accion que escribe, no en el widget.

    Ocultar o deshabilitar un boton no es autorizacion: la pagina se puede
    abrir por URL y el widget se puede reactivar. Toda accion que persiste
    config, modelos o dispara un envio tiene que pasar por aqui.
    """
    exigir(auth.PERMISO_GESTIONAR_EMPRESAS,
           mensaje or "Solo un administrador puede realizar esta accion.")


@st.cache_resource(show_spinner="Cargando configuracion...")
def _config_personalizada(workspace, nombre, moneda, slogan, primario=None, acento=None):
    """Configuracion del workspace activo con las preferencias de la sesion."""
    cfg = workspaces.config_actual(selector=lambda: workspace)
    if nombre:
        cfg.negocio_nombre = nombre
    if moneda:
        cfg.moneda = moneda
    if slogan:
        cfg.slogan = slogan
    if primario or acento:
        cfg.tema = dict(cfg.tema or {})
        if primario:
            cfg.tema["color_primario"] = primario
        if acento:
            cfg.tema["color_acento"] = acento
    return cfg


def obtener_workspace() -> str:
    """Workspace efectivo, ya acotado a los permisos de la sesion."""
    s = sesion()
    return auth.workspace_permitido(s, st.session_state.get("workspace") or "")


def workspaces_visibles() -> list:
    """Empresas que la sesion puede seleccionar."""
    return auth.workspaces_visibles(sesion())


def obtener_config():
    """Configuracion global del workspace, aplicadas las preferencias de la sesion."""
    ws = obtener_workspace()
    nombre = st.session_state.get("negocio_nombre") or st.session_state.get("taller_nombre") or None
    moneda = st.session_state.get("moneda") or None
    slogan = st.session_state.get("slogan") or None
    primario = st.session_state.get("tema_primario") or None
    acento = st.session_state.get("tema_acento") or None
    return _config_personalizada(ws, nombre, moneda, slogan, primario, acento)


def cargar_datos(_cfg):
    """Carga los datasets del workspace en memoria (usa cache parquet del pipeline)."""
    return load_all(_cfg)


@st.cache_resource(show_spinner="Calculando analisis...")
def calcular_analista(data, workspace: str):
    return Analyzer(data)


@st.cache_resource(show_spinner="Entrenando modelos de prediccion...")
def calcular_predictor(data, cfg, workspace: str):
    return Predictor(data, cfg=cfg)


def obtener_estado():
    """Devuelve (cfg, data, analyzer, predictor) listos para renderizar una pagina."""
    cfg = obtener_config()
    ws = obtener_workspace()
    try:
        data = cargar_datos(cfg)
        if len(data) < 3:
            st.warning("Se cargaron pocos datasets. Revisa la pagina de Datos para importar tus archivos.")
        analyzer = calcular_analista(data, ws)
        predictor = calcular_predictor(data, cfg, ws)
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudieron cargar los datos:\n\n`{e}`")
        st.info("Ve a la pagina **'Mis datos'** despues de importar tus archivos.")
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
    """Registra las tablas del workspace en DuckDB y ejecuta una consulta.

    Solo admin. Es la unica via de SQL arbitrario de la app, asi que el
    permiso se comprueba aqui y no en el boton que la dispara: ocultar el
    widget no protege nada si la funcion sigue siendo alcanzable.
    """
    exigir(auth.PERMISO_CONSOLA_SQL,
           "La consola SQL es una funcion de administracion.")
    _validar_sql_solo_lectura(sql)
    cfg = obtener_config()
    store = get_store(cfg)
    try:
        data = cargar_datos(cfg)
        _sincronizar_almacen(store, cfg, data)
        return store.consulta(sql)
    finally:
        store.cerrar()


def _validar_sql_solo_lectura(sql: str) -> None:
    """La consola SQL aplica la MISMA regla que los conectores.

    Antes habia aqui una lista propia de sentencias, paralela a la de
    ``conector_sql``: dos listas con palabras distintas significa que una
    pantalla puede relajarse sin que la otra se entere. Ahora hay una sola
    implementacion compartida y aqui solo queda la llamada.
    """
    conector_sql.validar_solo_lectura(sql, "La consulta")


def _firma_fuentes(cfg) -> str:
    """Firma barata de los originales del workspace: mtimes/tamaños y mapeo.

    No recorre los valores (eso costaria como la carga misma): basta con que
    cambie un fichero o el mapeo para que la firma cambie. Se separa de la
    firma completa para poder cachear ``cargar_datos`` sin haber cargado
    nada todavia.
    """
    from pathlib import Path

    partes = []
    # El mapeo de columnas tambien define la estructura: si cambia sin tocar
    # los ficheros, la firma debe cambiar igualmente.
    try:
        for nombre, dcfg in sorted((getattr(cfg, "datasets", None) or {}).items()):
            partes.append(f"map:{nombre}:{sorted((dcfg.mapeo or {}).items())}")
    except (AttributeError, TypeError):
        pass
    try:
        base = Path(cfg.directorio_datos)
        # El propio almacen vive aqui (almacen.duckdb y su .wal): cada
        # escritura en la BD cambiaria su mtime y la firma se invalidaria a
        # si misma en bucle, registrando siempre.
        db = Path(cfg.db_path).name
        excluidos = {db, f"{db}.wal", f"{db}.tmp"}
        for ruta in sorted(base.iterdir()):
            # Solo ficheros originales: los directorios (p. ej. data/cache,
            # que esta DENTRO de directorio_datos) cambian de mtime al
            # escribir la propia cache y la firma se invalidaria sin motivo.
            if not ruta.is_file() or ruta.name in excluidos:
                continue
            try:
                s = ruta.stat()
            except OSError:
                continue
            partes.append(f"{ruta.name}:{s.st_mtime_ns}:{s.st_size}")
    except OSError:
        pass
    return "|".join(partes)


def _firma_datos(cfg, data) -> str:
    """Firma de los datos ya cargados: fuentes + forma de cada dataset."""
    import pandas as pd

    partes = [_firma_fuentes(cfg)]
    for nombre in sorted(data):
        df = data[nombre]
        if isinstance(df, pd.DataFrame):
            partes.append(f"{nombre}:{df.shape[0]}x{df.shape[1]}:{len(df.columns)}")
    return hashlib.sha1("|".join(partes).encode("utf-8")).hexdigest()


def _sincronizar_almacen(store, cfg, data, materializar: bool = False) -> bool:
    """Registra los datos en DuckDB solo si cambiaron desde la ultima carga.

    Antes, leer UNA vista (o abrir la pestaña Esquema) volvía a hacer
    DROP+CREATE de cada tabla y a reconstruir core/analitica entero en cada
    rerun. La firma vive en ``giro_meta`` dentro del propio fichero DuckDB,
    asi que si se recrea la DB la firma desaparece con ella.
    """
    if not data:
        return False
    firma = _firma_datos(cfg, data)
    registrados = store.firma_carga("datos") == firma
    if not registrados:
        store.registrar_tablas(data)
        store.guardar_firma(firma, "datos")
    if materializar:
        if store.firma_carga("estructura") != firma:
            store.construir_estructura(data)
            store.guardar_firma(firma, "estructura")
    return not registrados


def obtener_estructura():
    """Registra los datos en DuckDB, materializa core/analitica y devuelve
    el catalogo de objetos del almacen del workspace."""
    cfg = obtener_config()
    store = get_store(cfg)
    try:
        data = cargar_datos(cfg)
        _sincronizar_almacen(store, cfg, data, materializar=True)
        return store.info_estructura()
    finally:
        store.cerrar()


def consultar_vista(nombre: str):
    """Consulta una vista del esquema analitica (p. ej. 'ingresos_mensuales')."""
    cfg = obtener_config()
    store = get_store(cfg)
    try:
        data = cargar_datos(cfg)
        _sincronizar_almacen(store, cfg, data, materializar=True)
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
    "ingresos_por_servicio_mensual",
    "factura_detalle_desnormalizado",
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
    store = get_store(cfg)
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)

    exportados: list = []
    errores: dict = {}
    try:
        data = cargar_datos(cfg)
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


# ------------------------------------------------------------------
#  Workspaces (multiempresa)
# ------------------------------------------------------------------

def crear_workspace_ui(clave: str, nombre: str, moneda: str, con_muestra: bool,
                       sector: str = None):
    """Crea un workspace desde la UI, lo selecciona y limpia caches.

    Solo admin. ``src.workspaces.crear_workspace`` valida la clave antes de
    construir rutas, pero el permiso se comprueba aqui para que un cliente no
    pueda siquiera crear su propia carpeta.
    """
    exigir(auth.PERMISO_GESTIONAR_EMPRESAS,
           "Crear empresas es una funcion de administracion.")
    from src.core.templates import lista_verticales
    cfg = workspaces.crear_workspace(
        clave, nombre=nombre or None, moneda=moneda or None,
        sector=sector or None, con_datos_muestra=con_muestra)
    st.session_state["workspace"] = cfg.clave
    st.cache_data.clear()
    st.cache_resource.clear()
    return cfg