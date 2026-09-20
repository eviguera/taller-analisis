"""Plantillas de vertical para crear workspaces listos para cada sector.

Cada vertical define los parametros que diferencian negocio, inventario,
mantenimiento predictivo y alertas. Se usan como base al crear un workspace
con ``workspace crear <clave> --sector clinica`` (o desde la UI).
"""

VERTICALES = {
    "taller": {
        "sector": "taller mecanico",
        "slogan": "Gira tus datos en resultados",
        "tema": {
            "texto_logo": "GIRO Analytics",
            "color_primario": "#7C4DFF",
        },
        "inventario": {
            "mapeo_servicio_categoria": {
                "aceite": "Aceites", "freno": "Frenos", "filtro": "Filtros",
                "bujia": "Motor", "correa": "Motor", "suspension": "Suspension",
                "bateria": "Electrico", "llanta": "Llantas", "climatizacion": "Climatizacion",
                "transmision": "Transmision", "refrigerante": "Climatizacion",
            },
        },
        "mantenimiento": {
            "intervalos_meses": {
                "cambio de aceite": 3, "alineacion y balance": 6,
                "cambio de frenos": 12, "cambio de llantas": 18,
                "cambio de bujias": 12, "cambio de bateria": 24,
                "cambio de filtro de aire": 6, "diagnostico computarizado": 6,
            },
        },
    },
    "clinica": {
        "sector": "clinica medica",
        "slogan": "Pacientes sanos, decisiones informadas",
        "tema": {"texto_logo": "GIRO Salud", "color_primario": "#0E9F6E"},
        "inventario": {
            "mapeo_servicio_categoria": {
                "consulta": "Consultas", "ecografia": "Imagenes",
                "laboratorio": "Laboratorio", "urgencia": "Urgencia",
                "cirugia": "Procedimientos", "control": "Consultas",
            },
        },
        "mantenimiento": {
            "intervalos_meses": {
                "control": 6, "ecografia": 12, "laboratorio": 3,
                "urgencia": 12, "consulta": 12,
            },
        },
        "alertas": {"max_facturas_pendientes": 40},
    },
    "retail": {
        "sector": "retail",
        "slogan": "Tu rotacion manda",
        "tema": {"texto_logo": "GIRO Retail", "color_primario": "#EE7C0D"},
        "inventario": {
            "mapeo_servicio_categoria": {
                "panaderia": "Panaderia", "bebida": "Bebidas",
                "congelado": "Congelados", "limpieza": "Aseo",
                "lacteo": "Lacteos", "fruta": "Frutas y verduras",
            },
        },
        "mantenimiento": {
            "intervalos_meses": {"reposicion": 1, "inventario": 1, "auditoria": 3},
        },
        "alertas": {"max_stock_alertas": 25},
    },
    "logistica": {
        "sector": "logistica y transporte",
        "slogan": "Cada km, medido y optimizado",
        "tema": {"texto_logo": "GIRO Logistica", "color_primario": "#2563EB"},
        "inventario": {
            "mapeo_servicio_categoria": {
                "combustible": "Combustible", "neumatico": "Neumaticos",
                "filtro": "Filtros", "freno": "Frenos", "aceite": "Lubricantes",
            },
        },
        "mantenimiento": {
            "intervalos_meses": {
                "cambio de aceite": 2, "rotacion neumaticos": 6,
                "frenos": 6, "filtro de aire": 4, "revision tecnica": 6,
            },
        },
    },
    "farmacia": {
        "sector": "farmacia",
        "slogan": "Salud con rotacion y stock al dia",
        "tema": {"texto_logo": "GIRO Farma", "color_primario": "#0E7490"},
        "inventario": {
            "mapeo_servicio_categoria": {
                "analgesico": "Analgesicos", "antigripal": "Respiratorio",
                "antibiotico": "Antibioticos", "dermocosmetico": "Dermocosmetica",
                "pediatria": "Pediatria", "vitamina": "Vitaminas y suplementos",
                "gastro": "Digestivo", "cronico": "Cronicos",
            },
        },
        "mantenimiento": {
            "intervalos_meses": {"reposicion": 1, "vigencia_lotes": 1, "auditoria": 3},
        },
        "alertas": {"max_stock_alertas": 30, "lotes_por_vencer_dias": 60},
    },
    "restoran": {
        "sector": "restoranes",
        "slogan": "Del pedido al ticket, sin perder nada",
        "tema": {"texto_logo": "GIRO Sabor", "color_primario": "#D94841"},
        "inventario": {
            "mapeo_servicio_categoria": {
                "entrada": "Entradas", "fondo": "Platos de fondo",
                "bebida": "Bebidas", "postre": "Postres", "mermas": "Mermas",
                "insumo": "Insumos de cocina", "caja": "Otros",
            },
        },
        "mantenimiento": {
            "intervalos_meses": {"revision_cocina": 1, "mantencion_extractor": 6,
                                "calibracion_equipos_frio": 3},
        },
        "alertas": {"max_stock_alertas": 25, "merma_alerta_pct": 0.05},
    },
    "constructora": {
        "sector": "constructora",
        "slogan": "Obras en mandato y costos bajo control",
        "tema": {"texto_logo": "GIRO Obra", "color_primario": "#B45309"},
        "inventario": {
            "mapeo_servicio_categoria": {
                "obra gruesa": "Obra gruesa", "terminaciones": "Terminaciones",
                "maquinaria": "Maquinaria", "seguridad": "Seguridad",
                "electricidad": "Electricidad", "sanitaria": "Sanitaria",
            },
        },
        "mantenimiento": {
            "intervalos_meses": {"maquinaria_menor": 3, "maquinaria_pesada": 6,
                                "grua": 12, "vehiculos": 4},
        },
        "alertas": {"max_facturas_pendientes": 15, "caida_ingresos_mom": -0.15},
    },
}

DEFAULT_SECTOR = "taller"

# Benchmarks economicos por vertical: defaults del simulador what-if.
# El simulador los usa como punto de partida cuando se crea el workspace.
BENCHMARKS = {
    "taller": dict(margen_bruto=0.42, gasto_fijo_pct=0.60, crecimiento_anual=0.08,
                   ticket_crecimiento=0.04),
    "clinica": dict(margen_bruto=0.45, gasto_fijo_pct=0.62, crecimiento_anual=0.12,
                    ticket_crecimiento=0.05),
    "retail": dict(margen_bruto=0.28, gasto_fijo_pct=0.48, crecimiento_anual=0.10,
                   ticket_crecimiento=0.03),
    "logistica": dict(margen_bruto=0.22, gasto_fijo_pct=0.55, crecimiento_anual=0.15,
                      ticket_crecimiento=0.02),
    "farmacia": dict(margen_bruto=0.30, gasto_fijo_pct=0.45, crecimiento_anual=0.09,
                     ticket_crecimiento=0.02),
    "restoran": dict(margen_bruto=0.62, gasto_fijo_pct=0.55, crecimiento_anual=0.06,
                     ticket_crecimiento=0.03),
    "constructora": dict(margen_bruto=0.18, gasto_fijo_pct=0.42, crecimiento_anual=0.07,
                         ticket_crecimiento=0.03),
}


def lista_verticales() -> list:
    return list(VERTICALES.keys())


def aplicar_vertical(vertical: str) -> dict:
    """Devuelve los parametros base de una vertical (dict plano para merge)."""
    if isinstance(vertical, dict):
        vertical = vertical.get("sector", "")
    clave = (vertical or DEFAULT_SECTOR).strip().lower().replace(" ", "")
    plantilla = VERTICALES.get(clave) or VERTICALES.get(DEFAULT_SECTOR)
    salida = {
        "negocio": {"sector": plantilla["sector"], "slogan": plantilla["slogan"]},
        "inventario": {"mapeo_servicio_categoria": plantilla.get("inventario", {})
                       .get("mapeo_servicio_categoria", {})},
        "mantenimiento": {"intervalos_meses": plantilla.get("mantenimiento", {})
                          .get("intervalos_meses", {})},
        "tema": plantilla.get("tema", {}),
        "simulador": dict(BENCHMARKS.get(clave, {})),
    }
    if "alertas" in plantilla:
        salida["alertas"] = plantilla["alertas"]
    salida["_clave"] = clave
    return salida