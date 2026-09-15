"""Catalogo de datos: deteccion de archivos y clasificacion automatica de datasets."""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .config import AppConfig, DatasetConfig

FORMATOS_EXT = {
    ".csv": "csv",
    ".tsv": "csv",
    ".xlsx": "excel",
    ".xls": "excel",
    ".sav": "sav",
    ".zsav": "zsav",
    ".por": "por",
    ".parquet": "parquet",
}

IDENTIFICADORES = {
    "clientes": {"cliente", "nombre", "telefono", "email", "cliente_id"},
    "vehiculos": {"vehiculo", "placa", "marca", "modelo", "kilometraje", "cliente_id"},
    "servicios": {"servicio", "precio_base", "tiempo_estimado", "precio"},
    "facturas": {"factura", "factu", "fecha", "total", "descuento", "detalles", "cliente_id"},
    "inventario": {"inventario", "producto", "stock", "precio_costo", "categoria"},
}


@dataclass
class ArchivoDetectado:
    ruta: Path
    nombre: str
    formato: str
    tamaño_kb: float
    dataset_estimado: Optional[str] = None
    coincidencia: Optional[str] = None
    n_columnas: int = 0


def formato_de(archivo: Path) -> Optional[str]:
    if archivo.suffix.lower() not in FORMATOS_EXT:
        return None
    ext = archivo.suffix.lower()
    if ext == ".tsv":
        return "csv"
    return FORMATOS_EXT[ext]


def escanear_directorio(directorio: Path) -> List[ArchivoDetectado]:
    """Detecta archivos de datos soportados en un directorio."""
    if not directorio.exists():
        return []
    resultados = []
    for archivo in sorted(directorio.iterdir()):
        if not archivo.is_file():
            continue
        fmt = formato_de(archivo)
        if fmt is None or archivo.name.startswith("."):
            continue
        resultados.append(ArchivoDetectado(
            ruta=archivo,
            nombre=archivo.name,
            formato=fmt,
            tamaño_kb=round(archivo.stat().st_size / 1024, 1),
        ))
    return resultados


def _leer_columnas_ligero(ruta: Path, formato: str) -> Optional[List[str]]:
    """Lee solo los nombres de columna sin cargar todos los datos."""
    try:
        if ruta.suffix.lower() in (".sav", ".zsav", ".por"):
            import pyreadstat
            _, meta = pyreadstat.read_sav(str(ruta)) if ruta.suffix.lower() != ".por" else pyreadstat.read_por(str(ruta))
            return list(meta.column_names)
        if ruta.suffix.lower() == ".parquet":
            import pandas as pd
            return list(pd.read_parquet(ruta).columns[:50])
        df = _leer_cabecera(ruta, formato, n=3)
        return list(df.columns)
    except Exception:
        return None


def _leer_cabecera(ruta: Path, formato: str, n: int = 3):
    import pandas as pd
    try:
        sep = "\t" if ruta.suffix.lower() == ".tsv" else ","
        return pd.read_csv(ruta, sep=sep, nrows=n, encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(ruta, sep=sep, nrows=n, encoding="latin-1")


def clasificar_dataset(columnas: List[str]) -> Dict[str, float]:
    """Puntua la probabilidad de que unas columnas correspondan a cada dataset canonico."""
    cols_set = {c.strip().lower() for c in columnas}
    puntajes = {}
    for nombre, marcadores in IDENTIFICADORES.items():
        matches = marcadores & cols_set
        if not matches:
            puntajes[nombre] = 0.0
            continue
        puntaje = len(matches) / max(1, len(marcadores))
        # Reforzar con hitos distintivos
        if nombre == "clientes" and "nombre" in cols_set:
            puntaje += 0.2
        if nombre == "facturas" and "fecha" in cols_set and "total" in cols_set:
            puntaje += 0.2
        if nombre == "vehiculos" and "placa" in cols_set:
            puntaje += 0.2
        if nombre == "inventario" and "stock" in cols_set:
            puntaje += 0.2
        puntajes[nombre] = round(min(1.0, puntaje), 2)
    return puntajes


def clasificar_archivo(ruta: Path, formato: str) -> (Optional[str], float):
    columnas = _leer_columnas_ligero(ruta, formato)
    if not columnas:
        return None, 0.0
    puntajes = clasificar_dataset(columnas)
    mejor = max(puntajes, key=puntajes.get)
    if puntajes[mejor] >= 0.45:
        return mejor, puntajes[mejor]
    return None, 0.0


def vincular_archivos_a_datasets(archivos: List[ArchivoDetectado],
                                 cfg: AppConfig) -> Dict[str, Path]:
    """Determina, para cada dataset configurado, que archivo le corresponde."""
    asignacion: Dict[str, Path] = {}
    usados = set()

    # 1. Coincidencia explicita por nombre de archivo en config
    for nombre, dcfg in cfg.datasets.items():
        if dcfg.archivo:
            candidato = cfg.directorio_datos / dcfg.archivo
            if candidato.exists():
                asignacion[nombre] = candidato
                usados.add(candidato)
                continue
            for alt in dcfg.fuentes_alternativas:
                alt_path = cfg.directorio_datos / alt
                if alt_path.exists():
                    asignacion[nombre] = alt_path
                    usados.add(alt_path)
                    break

    # 2. Deteccion por contenido para archivos sin asignar
    archivos_pendientes = [a for a in archivos if a.ruta not in usados]
    for archivo in archivos_pendientes:
        dataset, score = clasificar_archivo(archivo.ruta, archivo.formato)
        archivo.dataset_estimado = dataset
        archivo.coincidencia = f"{score:.0%}"
        archivo.n_columnas = len(_leer_columnas_ligero(archivo.ruta, archivo.formato) or [])
        if dataset and dataset not in asignacion:
            asignacion[dataset] = archivo.ruta
            usados.add(archivo.ruta)

    return asignacion