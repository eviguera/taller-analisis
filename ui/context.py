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

import streamlit as st

from src import aplicacion
from src.core import auth
from src.core.pipeline import procesar_etl
from src.data_loader import load_all
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


def cargar_datos(_cfg, workspace: str | None = None):
    """Carga los datasets del workspace en memoria.

    Usa el cache parquet del pipeline y, encima, ``st.cache_data`` con la
    clave ``(workspace, firma_de_fuentes)``: sin esto, cada rerun de cada
    pagina volvia a escanear el directorio y a deserializar los parquet, y
    los conectores externos se re-consultaban por red tambien. Cambiar un
    fichero (o el mapeo) cambia la firma y refresca; ``sincronizar_conectores``
    y el ETL llaman a ``st.cache_data.clear()`` para forzar la relectura.

    El ``ttl`` acota lo que la firma no alcanza a ver: la BD externa de un
    conector cambia sin tocar ningun fichero local, y solo la UI limpia la
    cache al sincronizar (el ETL por CLI corre en otro proceso y no puede).
    El ``max_entries`` evita que cada firma antigua retenga su copia de los
    datasets para siempre.
    """
    ws = workspace or obtener_workspace()
    return _cargar_datos_cacheado(ws, _firma_fuentes(_cfg), _cfg)


@st.cache_data(show_spinner=False, ttl=600, max_entries=32)
def _cargar_datos_cacheado(workspace: str, firma: str, cfg) -> dict:
    """Cache de ``load_all``. ``workspace`` y ``firma`` van en la clave (regla 1)."""
    return load_all(cfg)


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
    return aplicacion.resumen_calidad(data)


def ejecutar_etl_ui():
    """Ejecuta el ETL, actualiza DuckDB y limpia caches para ver los cambios."""
    cfg = obtener_config()
    resultado = procesar_etl(cfg)
    st.cache_data.clear()
    st.cache_resource.clear()
    return resultado


def consulta_sql(sql: str):
    """Sincroniza el workspace y ejecuta una consulta de solo lectura.

    Solo admin. Es la unica via de SQL arbitrario de la app, asi que el
    permiso se comprueba aqui y no en el boton que la dispara: ocultar el
    widget no protege nada si la funcion sigue siendo alcanzable. La
    validacion de la consulta ya no vive aqui: es parte del caso de uso.
    """
    exigir(auth.PERMISO_CONSOLA_SQL,
           "La consola SQL es una funcion de administracion.")
    cfg = obtener_config()
    return aplicacion.consulta_sql(cfg, cargar_datos(cfg), sql)


def _validar_sql_solo_lectura(sql: str) -> None:
    """Delegado al caso de uso: una sola implementacion compartida."""
    aplicacion.validar_sql_solo_lectura(sql)


def _firma_fuentes(cfg) -> str:
    """Firma de los originales del workspace. Va en la clave del cache."""
    return aplicacion.firma_fuentes(cfg)


def _firma_datos(cfg, data) -> str:
    """Firma de los datos ya cargados: fuentes + forma de cada dataset."""
    return aplicacion.firma_datos(cfg, data)


def _sincronizar_almacen(store, cfg, data, materializar: bool = False) -> bool:
    """Registra los datos en el almacen solo si cambiaron desde la ultima carga."""
    return aplicacion.sincronizar_almacen(store, cfg, data, materializar=materializar)


def obtener_estructura():
    """Sincroniza el almacen, materializa core/analitica y devuelve el catalogo."""
    cfg = obtener_config()
    return aplicacion.estructura(cfg, cargar_datos(cfg))


def consultar_vista(nombre: str):
    """Consulta una vista del esquema analitica (p. ej. 'ingresos_mensuales')."""
    cfg = obtener_config()
    return aplicacion.vista(cfg, cargar_datos(cfg), nombre)


#: Vistas que salen en la exportacion analitica (el listado vive en el caso de uso).
VISTAS_PARA_EXPORTAR = aplicacion.VISTAS_PARA_EXPORTAR


def exportar_analitica_pspp(destino):
    """Exporta los datasets cargados y las vistas analiticas clave a .sav.

    Devuelve (exportados: list[str], errores: dict). Util para llevar la
    analitica completa a PSPP/SPSS desde la interfaz.
    """
    cfg = obtener_config()
    return aplicacion.exportar_analitica_pspp(cfg, cargar_datos(cfg), destino)


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