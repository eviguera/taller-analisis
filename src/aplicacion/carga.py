"""Casos de uso de carga: subir, detectar, resumir y exportar archivos.

Subir ficheros al directorio de datos, clasificar los origenes, resumir
los ``.sav``, publicar conectores y exportar datasets a PSPP eran bucles
repartidos por ``ui/pages/datos.py``: logica de disco (cuotas,
deduplicacion, confinamiento de rutas, lecturas de ficheros) escrita
dentro de un adaptador Streamlit y solo recuperable arrancando la UI.

Aqui **no** hay ``import streamlit``. Las subidas llegan como
``(nombre, tamano, contenido)`` y cada adaptador hace su propia
traduccion: el ``file_uploader`` de la interfaz, un request de la API o
un fichero que deje el CLI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from ..core import catalog

#: Cuota por archivo en la subida: corta un fichero gigante. Va de la mano
#: con server.maxUploadSize (200 MB por defecto), asi que por si sola no
#: frena nada que el servidor no rechace ya.
LIMITE_SUBIDA_BYTES = 200 * 1024 * 1024
#: Cuota acumulada del workspace: sin ella, N ficheros pequenos o subidas
#: repetidas llenarian el disco del contenedor, que todos los tenants
#: comparten. Es la que de verdad protege el disco compartido.
CUOTA_WORKSPACE_BYTES = 1024 * 1024 * 1024

#: Formatos PSPP/SPSS que resume la pestana de integracion.
FORMATOS_PSPP = ("sav", "zsav", "por")


def derivados_almacen(cfg) -> set:
    """Nombres de los ficheros derivados del almacen: no se suben ni cuentan.

    El almacen DuckDB, su WAL y su temporal son derivados, no subidos:
    comerian la cuota del tenant sin motivo. Tambien son los que hay que
    excluir de la firma de originales (``firma_fuentes``), porque cada
    escritura en la BD cambiaria su mtime y la firma se invalidaria a si
    misma en bucle.
    """
    db = Path(cfg.db_path).name
    return {db, f"{db}.wal", f"{db}.tmp"}


def mismo_contenido(ruta: Path, contenido) -> bool:
    """True si el fichero en disco ya es byte a byte el contenido subido.

    Se compara por bloques: cargar un fichero de 200 MB entero en RAM solo
    para descartar una reescritura seria mas caro que el propio guardado.
    """
    bloque = 1 << 20
    with open(ruta, "rb") as f:
        for inicio in range(0, len(contenido), bloque):
            if f.read(bloque) != bytes(contenido[inicio:inicio + bloque]):
                return False
        return f.read(1) == b""


def guardar_subidas(subidas, destino_dir, excluidos=frozenset(),
                    limite_bytes: int = LIMITE_SUBIDA_BYTES,
                    cuota_bytes: int = CUOTA_WORKSPACE_BYTES):
    """Guarda las subidas en el workspace, solo si su contenido cambio.

    ``subidas`` es una secuencia de ``(nombre, tamano, contenido)`` donde
    ``contenido`` es bytes o memoryview: el caso de uso no conoce el
    ``file_uploader`` de Streamlit.

    El bloque que envuelve el ``file_uploader`` se re-ejecuta en cada
    rerun: reescribir los ficheros a ciegas movia el mtime de los
    originales, la firma de ``firma_fuentes`` cambiaba siempre y la cache
    se invalidaba a si misma en bucle, recargando todo justo en la
    pantalla de importacion.

    Devuelve ``(guardados, sin_cambios, por_archivo, por_cuota)``.
    ``por_archivo`` corta un fichero mayor que ``limite_bytes``;
    ``por_cuota`` frena el acumulado del directorio de datos del
    workspace contra ``cuota_bytes``. Los nombres en ``excluidos`` (ver
    ``derivados_almacen``) no cuentan en la cuota: son derivados, no los
    sube nadie, y comerian la cuota del tenant sin motivo.
    """
    destino_dir = Path(destino_dir)
    destino_dir.mkdir(parents=True, exist_ok=True)
    guardados = sin_cambios = por_archivo = por_cuota = 0
    ocupado = sum(f.stat().st_size for f in destino_dir.iterdir()
                  if f.is_file() and f.name not in excluidos)
    for nombre, tamano, contenido in subidas:
        tam = tamano or 0
        if tam > limite_bytes:
            por_archivo += 1
            continue
        if ocupado + tam > cuota_bytes:
            por_cuota += 1
            continue
        # Path(nombre).name descarta cualquier ruta que traiga el nombre
        # subido ("../../x"): el archivo tiene que caer dentro del
        # directorio del workspace y de ningun otro sitio.
        destino = destino_dir / Path(nombre).name
        if (destino.exists() and destino.stat().st_size == tam
                and mismo_contenido(destino, contenido)):
            sin_cambios += 1
            continue
        destino.write_bytes(contenido)
        ocupado += tam
        guardados += 1
    return guardados, sin_cambios, por_archivo, por_cuota


def directorio_datos_permitido(cfg, ruta) -> bool:
    """True si ``ruta`` (resuelta) cae dentro del directorio de datos.

    La interfaz deja escribir cualquier texto en el cuadro del directorio;
    resolverlo contra el del workspace es lo que impide que un valor tipo
    ``../../otro_taller`` saque la lectura (y las subidas) del
    aislamiento por empresa (regla 1).
    """
    base = Path(cfg.directorio_datos).resolve()
    return Path(ruta).resolve().is_relative_to(base)


def filas_detectadas(archivos) -> List[Dict]:
    """Filas de la tabla de archivos detectados, clasificadas por dataset.

    Devuelve valores crudos (formato sin etiquetar, confianza como tanto
    por uno): el pintado de la tabla es cosa de la UI. Un archivo ya
    clasificado por el catalogo no se vuelve a puntuar.
    """
    filas: List[Dict] = []
    for a in archivos:
        dataset, confianza = (catalog.clasificar_archivo(a.ruta, a.formato)
                              if a.dataset_estimado is None
                              else (a.dataset_estimado, None))
        filas.append({
            "archivo": a.nombre,
            "formato": a.formato,
            "tamano_kb": a.tamaño_kb,
            "dataset": dataset,
            "confianza": confianza,
        })
    return filas


def filas_conectores(cfg) -> List[Dict]:
    """Filas de la tabla de conectores: que fuente tiene cada uno y si existe.

    Para una fuente remota (URL o DSN) no hay nada que comprobar en
    disco: la presencia se da por buena si el conector trae ``fuente``.
    """
    from ..core.conector_sql import parsear_conectores  # noqa: PLC0415 — core, sin adaptadores

    filas: List[Dict] = []
    for x in parsear_conectores(cfg):
        fuente = x.fuente
        if fuente and "://" not in str(fuente):
            existe = (Path(cfg.directorio_datos) / str(fuente)).exists()
        else:
            existe = bool(fuente)
        filas.append({
            "nombre": x.nombre,
            "motor": x.motor,
            "dataset": x.dataset,
            "fuente": str(fuente or "(consulta)"),
            "forzar": x.forzar,
            "existe": existe,
        })
    return filas


def exportar_datasets_sav(data, destino) -> Tuple[List[str], Dict[str, str]]:
    """Exporta cada dataset cargado a ``destino/nombre.sav``.

    Devuelve ``(exportados, fallos)``: los datasets vacios se saltan y un
    dataset que pyreadstat no sabe escribir no tumba los demas, que es
    como lo espera la UI (un aviso por fallo y el resto exportado).
    """
    from ..loaders.pspp_loader import exportar_sav  # noqa: PLC0415 — adaptador, import perezoso

    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    exportados: List[str] = []
    fallos: Dict[str, str] = {}
    for nombre, df in data.items():
        if df is None or df.empty:
            continue
        try:
            exportar_sav(df, destino / f"{nombre}.sav",
                         label_archivo=f"{nombre} exportado")
            exportados.append(nombre)
        except Exception as e:  # noqa: BLE001 — un dataset malo no tumba la exportacion
            fallos[nombre] = str(e)
    return exportados, fallos


def leer_archivos_pspp(directorio) -> List[Dict]:
    """Lee los ``.sav``/``.zsav``/``.por`` de un directorio y resume cada uno.

    Devuelve una entrada por fichero con ``nombre``, ``formato``,
    ``datos``, ``etiquetas`` (mapa variable -> {valor: texto}) y
    ``error``. Un fichero ilegible no tumbar la pantalla: se lista con su
    error para que la UI lo avise junto al resto.
    """
    from ..loaders import get_loader  # noqa: PLC0415 — adaptador, import perezoso

    resumenes: List[Dict] = []
    for a in catalog.escanear_directorio(Path(directorio)):
        if a.formato not in FORMATOS_PSPP:
            continue
        try:
            res = get_loader(a.ruta).cargar(a.ruta)
            resumenes.append({
                "nombre": a.nombre,
                "formato": a.formato,
                "datos": res.datos,
                "etiquetas": res.metadatos.get("etiquetas_valores", {}) or {},
                "error": None,
            })
        except Exception as e:  # noqa: BLE001 — un .sav ilegible no tumbar la pestana
            resumenes.append({
                "nombre": a.nombre,
                "formato": a.formato,
                "datos": None,
                "etiquetas": {},
                "error": str(e),
            })
    return resumenes


def ejecutar_etl(cfg):
    """Ejecuta el pipeline ETL del workspace y devuelve su resultado.

    Caso de uso compartido por los adaptadores de entrada (UI, API, CLI):
    la apertura del almacen ya pasa por el punto unico de decision de
    motor dentro de ``procesar_etl``. Las caches de Streamlit las limpia
    el llamador, que es el unico que las conoce.
    """
    from ..core.pipeline import procesar_etl  # noqa: PLC0415 — data_loader importa este modulo arriba

    return procesar_etl(cfg)


__all__ = [
    "LIMITE_SUBIDA_BYTES",
    "CUOTA_WORKSPACE_BYTES",
    "FORMATOS_PSPP",
    "derivados_almacen",
    "mismo_contenido",
    "guardar_subidas",
    "directorio_datos_permitido",
    "filas_detectadas",
    "filas_conectores",
    "exportar_datasets_sav",
    "leer_archivos_pspp",
    "ejecutar_etl",
]
