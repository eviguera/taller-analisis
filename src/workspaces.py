"""Workspaces multiempresa (tenancy ligera sobre archivos).

Cada workspace es una carpeta autocontenida::

    workspaces/<clave>/
    ├── config/config.yaml        # su propia configuracion
    └── data/                     # sus datasets, DuckDB y modelos

``cargar_config`` resuelve las rutas relativas a la carpeta del workspace,
por lo que cada empresa tiene su almacen, su cache y sus modelos aislados.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import List, Optional

import yaml

from .core.config import AppConfig
from .core.config_manager import cargar_config, guardar_config

RAIZ_WORKSPACES = Path(__file__).resolve().parent.parent / "workspaces"

CLAVE_PRINCIPAL = "principal"

# La clave se usa como nombre de carpeta y se concatena con rutas del sistema de
# archivos, asi que se restringe a un alfabeto seguro: sin separadores, sin "..",
# sin bytes de control ni caracteres exoticos del sistema de archivos.
PATRON_CLAVE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def normalizar_clave(clave: str) -> str:
    """Normaliza una clave a su forma canonica: minusculas y guiones.

    Solo sustituye espacios por guiones. NO translitera caracteres peligrosos
    (``/``, ``.``, ``\\``, nul): esos se dejan intactos para que
    ``validar_clave`` los rechace de forma explicita en vez de crear en
    silencio una carpeta con otro nombre.
    """
    texto = (clave or "").strip().lower().replace(" ", "-").replace("\t", "-")
    while "--" in texto:
        texto = texto.replace("--", "-")
    return texto.strip("-")


def validar_clave(clave: str) -> str:
    """Valida una clave de workspace y la devuelve ya normalizada.

    Lanza ``ValueError`` si no cumple ``PATRON_CLAVE``. Es la unica puerta de
    entrada antes de construir rutas con la clave, de modo que ``..``,
    ``/`` y rutas absolutas nunca lleguen al sistema de archivos.
    """
    clave = normalizar_clave(clave)
    if not clave:
        raise ValueError("La clave del workspace no puede estar vacia")
    if not PATRON_CLAVE.match(clave):
        raise ValueError(
            "Clave de workspace invalida: usa solo minusculas, digitos, guion "
            "(-) y guion bajo (_), empezando por letra o digito (max. 64). "
            "No se admiten rutas, barras ni puntos."
        )
    return clave


def listar_workspaces() -> List[str]:
    """Claves de los workspaces configurados en ``workspaces/``."""
    if not RAIZ_WORKSPACES.exists():
        return []
    ordenadas = sorted(
        d.name for d in RAIZ_WORKSPACES.iterdir()
        if d.is_dir() and (d / "config" / "config.yaml").exists()
    )
    return ordenadas


def ruta_workspace(clave: str) -> Path:
    """Ruta absoluta del workspace. Valida la clave antes de construirla."""
    return RAIZ_WORKSPACES / validar_clave(clave)


def existe(clave: str) -> bool:
    return (ruta_workspace(clave) / "config" / "config.yaml").exists()


def config_workspace(clave: str) -> AppConfig:
    """Configuracion de un workspace (lee su propio config.yaml)."""
    ruta_cfg = ruta_workspace(clave) / "config" / "config.yaml"
    if not ruta_cfg.exists():
        raise FileNotFoundError(f"No existe el workspace '{clave}' ({ruta_cfg})")
    return cargar_config(ruta_cfg)


def crear_workspace(clave: str, nombre: Optional[str] = None,
                    moneda: Optional[str] = None,
                    slogan: Optional[str] = None,
                    con_datos_muestra: bool = False,
                    sector: Optional[str] = None,
                    base_config: Optional[Path] = None) -> AppConfig:
    """Crea un workspace nuevo a partir de la plantilla de configuracion.

    ``con_datos_muestra`` copia los archivos CSV de ejemplo del directorio de
    datos principal para que el workspace arranque con datos. ``sector`` aplica
    una plantilla de vertical (taller, clinica, retail, ...) con sus valores de
    inventario, mantenimiento, alertas y tema de marca.
    """
    clave = validar_clave(clave)
    if clave == CLAVE_PRINCIPAL:
        raise ValueError("'principal' es el workspace raiz y no puede recrearse")

    destino = ruta_workspace(clave)
    if existe(clave):
        return config_workspace(clave)

    # Plantilla: config actual del proyecto (+ vertical si se pide)
    plantilla = base_config or (Path(__file__).resolve().parent.parent / "config" / "config.yaml")
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "config").mkdir(parents=True, exist_ok=True)
    (destino / "data").mkdir(parents=True, exist_ok=True)

    raw = yaml.safe_load(plantilla.read_text(encoding="utf-8")) or {}
    vertical = {}
    if sector:
        from .core.templates import aplicar_vertical
        vertical = aplicar_vertical(sector)

    negocio = dict(raw.get("negocio") or {})
    if nombre:
        negocio["nombre"] = nombre
    if moneda:
        negocio["moneda"] = moneda
    if slogan:
        negocio["slogan"] = slogan
    negocio["clave"] = clave  # type: ignore[assignment]
    if vertical.get("negocio"):
        negocio["sector"] = vertical["negocio"].get("sector", negocio.get("sector", ""))
        negocio.setdefault("slogan", vertical["negocio"].get("slogan"))

    almacen = dict(raw.get("almacen") or {})
    almacen.update({
        "directorio_datos": "data",
        "db": "data/almacen.duckdb",
        "cache_dir": "data/cache",
    })

    tema = dict(raw.get("tema") or {})
    if vertical.get("tema"):
        tema.update(vertical["tema"])

    salida = {
        "negocio": negocio,
        "tema": tema,
        "almacen": almacen,
        "fuentes": raw.get("fuentes") or {},
        "mapeo_columnas": raw.get("mapeo_columnas") or {},
        "inventario": dict(raw.get("inventario") or {}),
        "mantenimiento": dict(raw.get("mantenimiento") or {}),
        "alertas": dict(raw.get("alertas") or {}),
        "simulador": dict(raw.get("simulador") or {}),
        "whitelabel": dict(raw.get("whitelabel") or {}),
        "reportes": dict(raw.get("reportes") or {}),
    }
    if vertical.get("inventario"):
        salida["inventario"].update(vertical["inventario"])
    if vertical.get("mantenimiento"):
        salida["mantenimiento"].update(vertical["mantenimiento"])
    if vertical.get("alertas"):
        salida["alertas"].update(vertical["alertas"])
    if vertical.get("simulador"):
        salida["simulador"].update(vertical["simulador"])

    ruta_cfg = destino / "config" / "config.yaml"
    ruta_cfg.write_text(yaml.safe_dump(salida, allow_unicode=True, sort_keys=False),
                        encoding="utf-8")

    if con_datos_muestra:
        origen = Path(__file__).resolve().parent.parent / "data"
        copiados = 0
        for ext in (".csv", ".xlsx"):
            for archivo in origen.glob(f"*{ext}"):
                if archivo.name in ("almacen.duckdb",):
                    continue
                if archivo.name.lower().startswith((".",)):
                    continue
                shutil.copy2(archivo, destino / "data" / archivo.name)
                copiados += 1
        if copiados == 0:
            print("  (nota: no habia archivos de muestra para copiar)")

    return config_workspace(clave)


def workspace_activo(selector=None) -> str:
    """Workspace activo: env GIRO_WORKSPACE > selector (callable) > 'principal'.

    La clave se valida siempre. Un valor invalido (env mal configurado o
    selector manipulado) lanza ``ValueError`` en vez de caer silenciosamente en
    'principal', para no mostrar los datos de otra empresa por accidente.
    """
    import os
    desde_env = os.environ.get("GIRO_WORKSPACE", "")
    if desde_env:
        return validar_clave(desde_env)
    if callable(selector):
        sel = selector()
        if sel:
            return validar_clave(str(sel))
    return CLAVE_PRINCIPAL


def config_actual(selector=None) -> AppConfig:
    """Configuracion del workspace activo (principal lee la config raiz)."""
    clave = workspace_activo(selector)
    if clave in (CLAVE_PRINCIPAL, "", None):
        return cargar_config()
    return config_workspace(clave)