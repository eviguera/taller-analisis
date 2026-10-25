"""Casos de uso del almacen analitico.

Este modulo es el corazon del refactor hexagonal: toda la orquestacion del
almacen (firmas, sincronizacion, consultas de vistas, exportacion) vivia en
`ui/context.py`, es decir escrita en un modulo de Streamlit. Asi era
inrecuperable para cualquier otro adaptador: un proceso que no fuera el
dashboard no podia consultar una vista ni exportar sin arrastrar Streamlit.

Aqui **no** hay `import streamlit`. El cacheo (`st.cache_data`) y los
permisos de renderizado siguen siendo cosa de la UI; el nucleo recibe los
datos ya cargados y opera sobre `PuertoAlmacen`, sin conocer el motor.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

import pandas as pd

from ..core import conector_sql
from ..core.metadatos import EJEMPLOS_SQL, VISTAS_PARA_EXPORTAR
from ..puertos import PuertoAlmacen
from .carga import derivados_almacen

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..core.config import AppConfig

#: Registro de fabricas de almacen. Permite romper la dependencia directa
#: de src.aplicacion hacia src.data_loader: cualquier adaptador puede
#: registrar su propia fabrica y abrir_almacen la usara sin importar el
#: motor concreto.
_ALMACEN_FABRICA: Optional[Callable[["AppConfig"], PuertoAlmacen]] = None


def registrar_fabrica_almacen(fabrica: Callable[["AppConfig"], PuertoAlmacen]) -> None:
    """Registra una fabrica de almacen.

    Cualquier adaptador (DuckDB, Postgres, etc.) puede registrar su propia
    fabrica para que abrir_almacen la use sin importar el motor concreto.
    """
    global _ALMACEN_FABRICA
    _ALMACEN_FABRICA = fabrica

#: Vistas que salen en la exportacion analitica a PSPP/SPSS y ejemplos de
#: consultas SQL se definen en src.core.metadatos y se importan arriba.
#: Se mantienen aqui como reexport para compatibilidad con codigo existente
#: que las importe desde src.aplicacion.almacen.
VISTAS_PARA_EXPORTAR = VISTAS_PARA_EXPORTAR  # noqa: F811
EJEMPLOS_SQL = EJEMPLOS_SQL  # noqa: F811


# ------------------------------------------------------------------
#  Firmas: deciden si hay que volver a escribir en el almacen
# ------------------------------------------------------------------

def firma_fuentes(cfg: "AppConfig") -> str:
    """Firma barata de los originales del workspace: mtimes/tamaños y mapeo.

    No recorre los valores (eso costaria como la carga misma): basta con que
    cambie un fichero o el mapeo para que la firma cambie. Se separa de la
    firma completa para poder cachear la carga sin haber cargado nada todavia.
    """
    partes = []
    # El mapeo de columnas tambien define la estructura: si cambia sin tocar
    # los ficheros, la firma debe cambiar igualmente.
    try:
        for nombre, dcfg in sorted((getattr(cfg, "datasets", None) or {}).items()):
            partes.append(f"map:{nombre}:{sorted((dcfg.mapeo or {}).items())}")
    except (AttributeError, TypeError) as exc:  # noqa: BLE001 — nunca se traga
        log.warning(
            "No se pudo leer el mapeo de columnas para la firma de fuentes: %s", exc,
        )
    try:
        base = Path(cfg.directorio_datos)
        # El propio almacen vive aqui (almacen.duckdb y su .wal): cada
        # escritura en la BD cambiaria su mtime y la firma se invalidaria
        # a si misma en bucle, registrando siempre.
        excluidos = derivados_almacen(cfg)
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
    except OSError as exc:  # noqa: BLE001 — nunca se traga en silencio
        log.warning(
            "No se pudo leer el directorio de datos para la firma de fuentes: %s", exc,
        )
    return "|".join(partes)


def firma_datos(cfg: "AppConfig", data: dict[str, pd.DataFrame]) -> str:
    """Firma de los datos ya cargados: fuentes + forma de cada dataset."""
    import hashlib

    partes = [firma_fuentes(cfg)]
    for nombre in sorted(data):
        df = data[nombre]
        if isinstance(df, pd.DataFrame):
            partes.append(f"{nombre}:{df.shape[0]}x{df.shape[1]}:{len(df.columns)}")
    return hashlib.sha1("|".join(partes).encode("utf-8")).hexdigest()


def sincronizar_almacen(store: PuertoAlmacen, cfg: "AppConfig",
                        data: dict[str, pd.DataFrame],
                        materializar: bool = False) -> bool:
    """Registra los datos en el almacen solo si cambiaron desde la ultima carga.

    Antes, leer UNA vista (o abrir la pestana Esquema) volvia a hacer
    DROP+CREATE de cada tabla y a reconstruir core/analitica entero en cada
    rerun. La firma vive en ``giro_meta`` dentro del propio almacen, asi que
    si se recrea la BD la firma desaparece con ella.
    """
    if not data:
        return False
    firma = firma_datos(cfg, data)
    registrados = store.firma_carga("datos") == firma
    if not registrados:
        store.registrar_tablas(data)
        store.guardar_firma(firma, "datos")
    if materializar:
        if store.firma_carga("estructura") != firma:
            store.construir_estructura(data)
            store.guardar_firma(firma, "estructura")
    return not registrados


# ------------------------------------------------------------------
#  Validacion de SQL
# ------------------------------------------------------------------

def validar_sql_solo_lectura(sql: str) -> None:
    """La consola SQL aplica la MISMA regla que los conectores.

    Antes habia una lista propia de sentencias en la UI, paralela a la de
    ``conector_sql``: dos listas con palabras distintas significa que una
    pantalla puede relajarse sin que la otra se entere. Hay una sola
    implementacion compartida y solo queda la llamada.
    """
    conector_sql.validar_solo_lectura(sql, "La consulta")


# ------------------------------------------------------------------
#  Casos de uso
# ------------------------------------------------------------------

def abrir_almacen(cfg: "AppConfig") -> PuertoAlmacen:
    """Almacen del workspace, listo para usar. El llamador lo cierra.

    Si se registro una fabrica de almacen (ver registrar_fabrica_almacen),
    la usa. De lo contrario, recurre al import perezoso de get_store como
    fallback para retrocompatibilidad.
    """
    global _ALMACEN_FABRICA
    if _ALMACEN_FABRICA is not None:
        return _ALMACEN_FABRICA(cfg)
    from ..data_loader import get_store  # noqa: PLC0415 — fallback por retrocompatibilidad

    return get_store(cfg)


def consulta_sql(cfg: "AppConfig", data: dict[str, pd.DataFrame],
                 sql: str) -> pd.DataFrame:
    """Sincroniza el almacen y ejecuta una consulta de solo lectura.

    Solo admin: el permiso lo impone el llamador (la UI lo hace en
    renderizado, la API en el middleware) porque la autorizacion depende de
    quien pide, no de lo que se pide. La validacion de la consulta, en
    cambio, va aqui: es una propiedad de la operacion, no del adaptador.
    """
    validar_sql_solo_lectura(sql)
    store = abrir_almacen(cfg)
    try:
        sincronizar_almacen(store, cfg, data)
        return store.consulta(sql)
    finally:
        store.cerrar()


def estructura(cfg: "AppConfig", data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Sincroniza, materializa core/analitica y devuelve el catalogo."""
    store = abrir_almacen(cfg)
    try:
        sincronizar_almacen(store, cfg, data, materializar=True)
        return store.info_estructura()
    finally:
        store.cerrar()


def vista(cfg: "AppConfig", data: dict[str, pd.DataFrame],
          nombre: str) -> pd.DataFrame:
    """Consulta una vista del esquema analitica (p. ej. 'ingresos_mensuales')."""
    store = abrir_almacen(cfg)
    try:
        sincronizar_almacen(store, cfg, data, materializar=True)
        return store.consultar_vista(nombre)
    finally:
        store.cerrar()


def exportar_analitica_pspp(cfg: "AppConfig",
                            data: dict[str, pd.DataFrame],
                            destino: Path | str) -> Tuple[List[str], Dict[str, str]]:
    """Exporta los datasets cargados y las vistas analiticas clave a .sav.

    Devuelve ``(exportados, errores)``. Util para llevar la analitica
    completa a PSPP/SPSS.
    """
    from ..loaders.pspp_loader import exportar_sav

    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    store = abrir_almacen(cfg)

    exportados: List[str] = []
    errores: Dict[str, str] = {}
    try:
        if data:
            sincronizar_almacen(store, cfg, data, materializar=True)

        for nombre, df in data.items():
            if df is None or df.empty:
                continue
            try:
                exportar_sav(df, destino / f"{nombre}.sav", label_archivo=f"{nombre} exportado")
                exportados.append(nombre)
            except Exception as e:  # noqa: BLE001
                errores[nombre] = str(e)

        for nombre_vista in VISTAS_PARA_EXPORTAR:
            try:
                df = store.consultar_vista(nombre_vista)
                exportar_sav(df, destino / f"analitica_{nombre_vista}.sav",
                             label_archivo=f"analitica_{nombre_vista}")
                exportados.append(f"analitica.{nombre_vista}")
            except Exception as e:  # noqa: BLE001
                errores[nombre_vista] = str(e)
        return exportados, errores
    finally:
        store.cerrar()


def resumen_calidad(data: dict[str, pd.DataFrame]) -> dict:
    """Resumen de calidad de los datasets cargados."""
    from ..data_loader import get_data_summary

    return get_data_summary(data)


def resumen_reglas(calidad: pd.DataFrame) -> Tuple[dict, pd.DataFrame]:
    """Conteo de reglas por estado y subconjunto que no las cumple.

    Devuelve ``(resumen, fallas)``: la UI pinta el resumen y la tabla de
    las reglas que no pasan, pero el conteo y el filtro son del nucleo
    para que la pantalla, la CLI y la API reporten exactamente lo mismo.
    Un ``calidad`` vacio (o ``None``) devuelve ceros y tabla vacia.
    """
    from ..core.calidad import resumen  # noqa: PLC0415 — core, sin adaptadores

    if calidad is None or calidad.empty:
        return resumen(calidad), pd.DataFrame()
    return resumen(calidad), calidad[calidad["estado"] != "OK"]


__all__ = [
    "VISTAS_PARA_EXPORTAR",
    "EJEMPLOS_SQL",
    "firma_fuentes",
    "firma_datos",
    "sincronizar_almacen",
    "validar_sql_solo_lectura",
    "abrir_almacen",
    "consulta_sql",
    "estructura",
    "vista",
    "exportar_analitica_pspp",
    "resumen_calidad",
    "resumen_reglas",
]
