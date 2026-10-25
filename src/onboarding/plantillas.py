"""Plantillas de configuración por sector vertical para el onboarding.

Cada plantilla define valores por defecto para: alertas, mantenimiento,
simulador, conectores, tema y suscripción. Son valores razonables para cada
vertical, pensados como punto de partida que el dueño del negocio ajusta.
"""

from __future__ import annotations

from typing import Any, Optional

# ---------------------------------------------------------------------------
# Plantillas por sector
# ---------------------------------------------------------------------------

_PLANTILLAS: dict[str, dict[str, Any]] = {
    "taller": {
        "sector": "taller_mecanico",
        "moneda": "MXN",
        "negocio_nombre": "Mi Taller",
        "slogan": "Gira tus datos en resultados",
        "alertas": {
            "stock_bajo": True,
            "churn": True,
            "churn_riesgo_umbral": 0.60,
            "caida_ingresos": True,
            "caida_ingresos_mom": -0.20,
            "facturas_pendientes": True,
            "facturas_pendientes_dias": 60,
            "max_stock_alertas": 10,
            "max_facturas_pendientes": 20,
        },
        "mantenimiento": {
            "intervalos_meses": {
                "cambio de aceite": 6,
                "revision de frenos": 12,
                "alineación y balanceo": 6,
                "cambio de filtros": 6,
                "revision de suspension": 12,
            },
            "pendientes_considerar": 3,
        },
        "simulador": {
            "margen_bruto": 0.42,
            "gasto_fijo_mensual": 45000,
            "crecimiento_anual": 0.08,
        },
        "suscripcion": {
            "planes": {"Core": 150000, "Pro": 450000, "Enterprise": None},
            "costo_tenant_mensual": 3000,
            "gasto_fijo_mensual": 7000000,
            "tasa_recuperacion_riesgo": 0.30,
        },
        "tema": {
            "color_primario": "#1e40af",
            "color_acento": "#2563eb",
            "fuente": "Inter",
        },
    },
    "clinica": {
        "sector": "clinica",
        "moneda": "MXN",
        "negocio_nombre": "Mi Clínica",
        "slogan": "Salud y bienestar, datos al servicio del paciente",
        "alertas": {
            "stock_bajo": True,
            "churn": True,
            "churn_riesgo_umbral": 0.50,
            "caida_ingresos": True,
            "caida_ingresos_mom": -0.15,
            "facturas_pendientes": True,
            "facturas_pendientes_dias": 30,
            "max_stock_alertas": 10,
            "max_facturas_pendientes": 20,
        },
        "mantenimiento": {},
        "simulador": {
            "margen_bruto": 0.60,
            "gasto_fijo_mensual": 80000,
            "crecimiento_anual": 0.10,
        },
        "suscripcion": {
            "planes": {"Core": 200000, "Pro": 600000, "Enterprise": None},
            "costo_tenant_mensual": 4000,
            "gasto_fijo_mensual": 9000000,
            "tasa_recuperacion_riesgo": 0.25,
        },
        "tema": {
            "color_primario": "#0f766e",
            "color_acento": "#14b8a6",
            "fuente": "Inter",
        },
    },
    "retail": {
        "sector": "retail",
        "moneda": "MXN",
        "negocio_nombre": "Mi Tienda",
        "slogan": "Cada venta cuenta, cada cliente importa",
        "alertas": {
            "stock_bajo": True,
            "churn": True,
            "churn_riesgo_umbral": 0.55,
            "caida_ingresos": True,
            "caida_ingresos_mom": -0.15,
            "facturas_pendientes": True,
            "facturas_pendientes_dias": 45,
            "max_stock_alertas": 15,
            "max_facturas_pendientes": 30,
        },
        "mantenimiento": {},
        "simulador": {
            "margen_bruto": 0.30,
            "gasto_fijo_mensual": 60000,
            "crecimiento_anual": 0.12,
        },
        "suscripcion": {
            "planes": {"Core": 120000, "Pro": 350000, "Enterprise": None},
            "costo_tenant_mensual": 2500,
            "gasto_fijo_mensual": 6000000,
            "tasa_recuperacion_riesgo": 0.35,
        },
        "tema": {
            "color_primario": "#7c3aed",
            "color_acento": "#a855f7",
            "fuente": "Inter",
        },
    },
    "logistica": {
        "sector": "logistica",
        "moneda": "MXN",
        "negocio_nombre": "Mi Logística",
        "slogan": "Movemos tu negocio con precisión",
        "alertas": {
            "stock_bajo": False,
            "churn": True,
            "churn_riesgo_umbral": 0.65,
            "caida_ingresos": True,
            "caida_ingresos_mom": -0.20,
            "facturas_pendientes": True,
            "facturas_pendientes_dias": 30,
            "max_stock_alertas": 5,
            "max_facturas_pendientes": 20,
        },
        "mantenimiento": {},
        "simulador": {
            "margen_bruto": 0.25,
            "gasto_fijo_mensual": 100000,
            "crecimiento_anual": 0.15,
        },
        "suscripcion": {
            "planes": {"Core": 180000, "Pro": 500000, "Enterprise": None},
            "costo_tenant_mensual": 3500,
            "gasto_fijo_mensual": 8000000,
            "tasa_recuperacion_riesgo": 0.30,
        },
        "tema": {
            "color_primario": "#0891b2",
            "color_acento": "#06b6d4",
            "fuente": "Inter",
        },
    },
    "farmacia": {
        "sector": "farmacia",
        "moneda": "MXN",
        "negocio_nombre": "Mi Farmacia",
        "slogan": "Tu salud es nuestra prioridad",
        "alertas": {
            "stock_bajo": True,
            "churn": True,
            "churn_riesgo_umbral": 0.50,
            "caida_ingresos": True,
            "caida_ingresos_mom": -0.10,
            "facturas_pendientes": True,
            "facturas_pendientes_dias": 15,
            "max_stock_alertas": 20,
            "max_facturas_pendientes": 30,
        },
        "mantenimiento": {},
        "simulador": {
            "margen_bruto": 0.45,
            "gasto_fijo_mensual": 50000,
            "crecimiento_anual": 0.09,
        },
        "suscripcion": {
            "planes": {"Core": 140000, "Pro": 420000, "Enterprise": None},
            "costo_tenant_mensual": 3000,
            "gasto_fijo_mensual": 6500000,
            "tasa_recuperacion_riesgo": 0.28,
        },
        "tema": {
            "color_primario": "#dc2626",
            "color_acento": "#ef4444",
            "fuente": "Inter",
        },
    },
    "restoran": {
        "sector": "restoran",
        "moneda": "MXN",
        "negocio_nombre": "Mi Restaurante",
        "slogan": "Sabor que se mide, servicio que se mejora",
        "alertas": {
            "stock_bajo": True,
            "churn": True,
            "churn_riesgo_umbral": 0.55,
            "caida_ingresos": True,
            "caida_ingresos_mom": -0.15,
            "facturas_pendientes": True,
            "facturas_pendientes_dias": 7,
            "max_stock_alertas": 15,
            "max_facturas_pendientes": 25,
        },
        "mantenimiento": {},
        "simulador": {
            "margen_bruto": 0.35,
            "gasto_fijo_mensual": 70000,
            "crecimiento_anual": 0.11,
        },
        "suscripcion": {
            "planes": {"Core": 110000, "Pro": 330000, "Enterprise": None},
            "costo_tenant_mensual": 2000,
            "gasto_fijo_mensual": 5500000,
            "tasa_recuperacion_riesgo": 0.33,
        },
        "tema": {
            "color_primario": "#ca8a04",
            "color_acento": "#eab308",
            "fuente": "Inter",
        },
    },
    "constructora": {
        "sector": "constructora",
        "moneda": "MXN",
        "negocio_nombre": "Mi Constructora",
        "slogan": "Construimos proyectos, no solo obras",
        "alertas": {
            "stock_bajo": True,
            "churn": True,
            "churn_riesgo_umbral": 0.70,
            "caida_ingresos": True,
            "caida_ingresos_mom": -0.25,
            "facturas_pendientes": True,
            "facturas_pendientes_dias": 90,
            "max_stock_alertas": 10,
            "max_facturas_pendientes": 15,
        },
        "mantenimiento": {},
        "simulador": {
            "margen_bruto": 0.20,
            "gasto_fijo_mensual": 150000,
            "crecimiento_anual": 0.07,
        },
        "suscripcion": {
            "planes": {"Core": 250000, "Pro": 700000, "Enterprise": None},
            "costo_tenant_mensual": 5000,
            "gasto_fijo_mensual": 10000000,
            "tasa_recuperacion_riesgo": 0.20,
        },
        "tema": {
            "color_primario": "#374151",
            "color_acento": "#6b7280",
            "fuente": "Inter",
        },
    },
}

SECTORES = sorted(_PLANTILLAS)


def validar_sector(sector: str) -> str:
    """Valida que el sector sea uno de los soportados y lo devuelve normalizado."""
    sector = (sector or "").strip().lower()
    if sector not in _PLANTILLAS:
        raise ValueError(
            f"Sector no soportado: {sector!r}. Sectores disponibles: {SECTORES}"
        )
    return sector


def configuracion_por_sector(
    sector: str,
    clave: str,
    nombre: Optional[str] = None,
    moneda: Optional[str] = None,
) -> dict[str, Any]:
    """Genera el diccionario de config.yaml para un sector y workspace dados.

    No escribe nada en disco: solo devuelve el dict listo para serializar a
    YAML. El llamador (CLI o UI) se encarga de escribir el archivo.
    """
    sector = validar_sector(sector)
    plantilla = dict(_PLANTILLAS[sector])  # copia para no mutar la plantilla
    plantilla["clave"] = clave
    if nombre:
        plantilla["negocio_nombre"] = nombre
    if moneda:
        plantilla["moneda"] = moneda
    return plantilla


def aplicar_plantilla(
    sector: str,
    clave: str,
    nombre: Optional[str] = None,
    moneda: Optional[str] = None,
    ruta_salida=None,
) -> dict[str, Any]:
    """Genera la configuración y, opcionalmente, la escribe como YAML.

    Si `ruta_salida` se proporciona, escribe el fichero YAML allí y devuelve
    el mismo dict. Si no, solo devuelve el dict.
    """
    import yaml

    cfg = configuracion_por_sector(sector, clave, nombre=nombre, moneda=moneda)
    if ruta_salida is not None:
        from pathlib import Path

        ruta_salida = Path(ruta_salida)
        ruta_salida.parent.mkdir(parents=True, exist_ok=True)
        ruta_salida.write_text(
            yaml.dump(cfg, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    return cfg
