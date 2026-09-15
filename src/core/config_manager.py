"""Carga y validacion de la configuracion central (config/config.yaml)."""

import yaml
from pathlib import Path
from typing import Optional

from .config import AppConfig, DatasetConfig

ETIQUETAS_ESPERADAS = {
    "clientes": {"id", "nombre", "telefono", "email", "fecha_registro"},
    "vehiculos": {"id", "cliente_id", "marca", "modelo", "anio", "placa", "color", "kilometraje"},
    "servicios": {"id", "nombre", "precio_base", "tiempo_estimado_min"},
    "facturas": {"id", "cliente_id", "vehiculo_id", "fecha", "total", "descuento", "estado", "detalles"},
    "inventario": {"id", "producto", "categoria", "precio_costo", "precio_venta", "stock_actual", "stock_minimo"},
}


def cargar_config(ruta: Optional[Path] = None) -> AppConfig:
    ruta = Path(ruta) if ruta else Path(__file__).resolve().parent.parent.parent / "config" / "config.yaml"
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontro la configuracion en {ruta}")

    with open(ruta, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    base = Path(ruta).resolve().parent.parent

    negocio = (raw.get("negocio") or raw.get("taller") or {}) or {}

    cfg = AppConfig(
        negocio_nombre=negocio.get("nombre", "Mi Negocio"),
        sector=negocio.get("sector", ""),
        moneda=negocio.get("moneda", "MXN"),
        directorio_datos=base / raw.get("almacen", {}).get("directorio_datos", "data"),
        cache_dir=base / raw.get("almacen", {}).get("cache_dir", "data/cache"),
        usar_cache=raw.get("almacen", {}).get("usar_cache", True),
    )
    db = raw.get("almacen", {}).get("db", "data/almacen.duckdb")
    cfg.db_path = base / db

    fuentes = raw.get("fuentes", {}) or {}
    mapeos = raw.get("mapeo_columnas", {}) or {}

    for nombre, spec in fuentes.items():
        spec = spec or {}
        if isinstance(spec, str):
            spec = {"archivo": spec}
        cfg.datasets[nombre] = DatasetConfig(
            nombre=nombre,
            archivo=spec.get("archivo"),
            formato=spec.get("formato", "auto"),
            hoja=spec.get("hoja"),
            descripcion=spec.get("descripcion", ""),
            fuentes_alternativas=[str(a) for a in spec.get("fuentes_alternativas", [])],
            mapeo=dict(mapeos.get(nombre, {}) or {}),
        )

    # Si no hay config de fuentes, usar la estructura estandar del directorio de datos
    if not cfg.datasets:
        nombres = ["clientes", "vehiculos", "servicios", "facturas", "inventario"]
        for n in nombres:
            cfg.datasets[n] = DatasetConfig(nombre=n, archivo=f"{n}.csv", formato="auto")

    return cfg


def guardar_config(cfg: AppConfig, ruta: Optional[Path] = None) -> Path:
    ruta = Path(ruta) if ruta else Path(__file__).resolve().parent.parent.parent / "config" / "config.yaml"
    raw = {
        "negocio": {
            "nombre": cfg.negocio_nombre,
            "sector": cfg.sector or "",
            "moneda": cfg.moneda,
        },
        "almacen": {
            "directorio_datos": "data",
            "db": "data/almacen.duckdb",
            "cache_dir": "data/cache",
            "usar_cache": cfg.usar_cache,
        },
        "fuentes": {
            n: {
                "archivo": d.archivo,
                "formato": d.formato,
                "hoja": d.hoja,
                "descripcion": d.descripcion,
                "fuentes_alternativas": d.fuentes_alternativas,
            }
            for n, d in cfg.datasets.items() if d.archivo
        },
        "mapeo_columnas": {n: d.mapeo for n, d in cfg.datasets.items() if d.mapeo},
    }
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        yaml.safe_dump(raw, f, allow_unicode=True, sort_keys=False)
    return ruta