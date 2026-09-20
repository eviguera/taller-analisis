"""Marca white-label de los reportes: identidad del cliente y del reventor.

Lee la seccion ``reportes:`` de la configuracion del workspace (branding,
contacto, logo) y la fusiona con el tema de marca (``tema:``) para resolver
los colores del documento. Asi una consultora puede entregar el reporte con
sus colores y datos de contacto, por cliente.
"""

import base64
from pathlib import Path

from .catalogo import TIPOS

COLOR_DEFECTO = "#7C4DFF"
COLOR_DEFECTO_SEC = "#00C2A8"
INK_DEFECTO = "#101828"


def _limpiar(valor):
    if valor is None:
        return None
    valor = valor.strip()
    return valor or None


def conf_reporte(cfg, clave="reportes") -> dict:
    """Devuelve la configuracion `reportes` del workspace (siempre dict)."""
    raw = getattr(cfg, clave, None)
    if raw is None:
        raw = {}
    return raw if isinstance(raw, dict) else {}


def marca(cfg) -> dict:
    """Resuelve la marca del reporte: colores, logo y datos del reventor."""
    rpt = conf_reporte(cfg)
    br = rpt.get("branding") or {}
    tema = getattr(cfg, "tema", None) or {}

    logo_data = None
    logo_ruta = _limpiar(br.get("logo") or "")
    if logo_ruta:
        ruta = Path(logo_ruta)
        if not ruta.is_absolute():
            ruta = Path(cfg.directorio_datos) / logo_ruta
        if ruta.exists():
            ext = ruta.suffix.lower()
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "svg": "image/svg+xml", "webp": "image/webp"}.get(ext.lstrip("."), "image/png")
            logo_data = f"data:{mime};base64,{base64.b64encode(ruta.read_bytes()).decode('utf-8')}"

    color_primario = _limpiar(br.get("color_primario")) or _limpiar(tema.get("color_primario")) or COLOR_DEFECTO
    color_secundario = _limpiar(br.get("color_secundario")) or _limpiar(tema.get("color_secundario")) or COLOR_DEFECTO_SEC
    color_acento = _limpiar(br.get("color_acento")) or _limpiar(tema.get("color_acento")) or color_primario

    return {
        # identidad del cliente (workspace)
        "negocio": cfg.negocio_nombre,
        "slogan": _limpiar(br.get("slogan")) or cfg.slogan or "",
        "moneda": getattr(cfg, "moneda", "CLP") or "CLP",
        "sector": getattr(cfg, "sector", "") or "",
        # identidad del reventor (quien entrega el reporte)
        "consultora": _limpiar(br.get("consultora")) or "GIRO Analytics",
        "contacto": _limpiar(br.get("contacto")) or "",
        "web": _limpiar(br.get("web")) or "",
        "pie": _limpiar(br.get("pie")) or "Reporte generado automaticamente con analitica de datos.",
        "logo": logo_data,
        # colores
        "color_primario": color_primario,
        "color_secundario": color_secundario,
        "color_acento": color_acento,
        "texto_logo": _limpiar(tema.get("texto_logo")) or "GIRO Analytics",
    }


def ocasion(cfg, por_defecto="Reporte ejecutivo") -> str:
    """Rotulo de la portada: que periodo cubre este reporte (ej. mensual)."""
    rpt = conf_reporte(cfg)
    return _limpiar(rpt.get("ocasion")) or por_defecto


def tipos_habilitados(cfg) -> list:
    """Tipos de reporte habilitados en la configuracion del workspace."""
    rpt = conf_reporte(cfg)
    tipos = rpt.get("tipos")
    if not isinstance(tipos, list) or not tipos:
        return list(TIPOS.keys())
    return [t for t in tipos if t in TIPOS] or list(TIPOS.keys())


def periodos_meses(cfg) -> list:
    rpt = conf_reporte(cfg)
    p = rpt.get("periodos_meses")
    if isinstance(p, list) and p:
        return [int(x) for x in p]
    return [3, 12]