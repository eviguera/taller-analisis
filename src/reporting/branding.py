"""Marca white-label de los reportes: identidad del cliente y del reventor.

Lee la seccion ``reportes:`` de la configuracion del workspace (branding,
contacto, logo) y la fusiona con el tema de marca (``tema:``) para resolver
los colores del documento. Asi una consultora puede entregar el reporte con
sus colores y datos de contacto, por cliente.

Este modulo resuelve *datos*, no HTML: el escapado ocurre en la capa que
renderiza (``secciones`` y ``engine``). Aqui si hace falta, lo que se valida
son los colores, porque acaban interpolados dentro de un bloque CSS.
"""

import base64
import re
from pathlib import Path

from .catalogo import TIPOS

COLOR_DEFECTO = "#7C4DFF"
COLOR_DEFECTO_SEC = "#00C2A8"
INK_DEFECTO = "#101828"

# Solo hex de 3 o 6 digitos. Los colores van dentro de un bloque CSS del
# documento, asi que un valor como "red;} body{display:none" inyectaria reglas.
_COLOR_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _limpiar(valor):
    if valor is None:
        return None
    valor = valor.strip()
    return valor or None


def _color(valor, defecto: str) -> str:
    """Un color o el defecto. Rechaza cualquier cosa que no sea hex."""
    candidato = _limpiar(valor)
    if candidato and _COLOR_HEX.match(candidato):
        return candidato
    return defecto


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

    color_primario = _color(br.get("color_primario"), _color(tema.get("color_primario"), COLOR_DEFECTO))
    color_secundario = _color(br.get("color_secundario"), _color(tema.get("color_secundario"), COLOR_DEFECTO_SEC))
    color_acento = _color(br.get("color_acento"), _color(tema.get("color_acento"), color_primario))

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


# Campos que se pueden persistir desde fuera. La lista es cerrada a proposito:
# lo que se escribe aqui acaba en el config.yaml del tenant, y que cualquier
# llamador meta claves arbitrarias en esa seccion es una puerta de entrada,
# no una comodidad.
CAMPOS_BRANDING = ("consultora", "contacto", "web", "slogan", "pie")
COLORES_BRANDING = ("color_primario", "color_secundario", "color_acento")


def guardar_branding(cfg, cambios: dict) -> dict:
    """Persiste la marca white-label en el ``config.yaml`` del workspace.

    Es la cara escritora de :func:`marca` y :func:`ocasion`: antes vivia en
    la pagina de reportes, junto con su propia copia de la ruta del fichero,
    de modo que el nucleo no podia guardar marca y otra pantalla podria
    discrepar sobre donde vive el config. La ruta sale de
    ``conector_sql.ruta_config_workspace``, que es la unica implementacion.

    Los colores se validan **aqui**, no solo al leer: lo que se guarda en
    disco es lo que despues acara interpolado dentro de un bloque CSS del
    documento. Un valor no-hex se rechaza en vez de corromper el config.
    """
    import yaml

    from ..core.conector_sql import ruta_config_workspace

    desconocidos = [k for k in cambios
                    if k not in CAMPOS_BRANDING and k not in COLORES_BRANDING]
    if desconocidos:
        raise ValueError(
            "Campos de marca no reconocidos: " + ", ".join(sorted(desconocidos)))

    ruta = ruta_config_workspace(cfg)
    raw = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    reportes = dict(raw.get("reportes") or {})
    branding = dict(reportes.get("branding") or {})

    for campo in CAMPOS_BRANDING:
        if campo in cambios:
            valor = _limpiar(cambios[campo])
            if valor is not None:
                branding[campo] = valor

    for color in COLORES_BRANDING:
        if color in cambios:
            candidato = _limpiar(cambios[color])
            if candidato is None:
                continue
            if not _COLOR_HEX.match(candidato):
                raise ValueError(
                    f"Color de marca no valido: {candidato!r}. "
                    "Usa el formato #RGB o #RRGGBB.")
            branding[color] = candidato

    reportes["branding"] = branding
    raw["reportes"] = reportes
    ruta.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8")
    return branding