"""Catalogo de reportes ejecutivos disponibles para cada cliente.

Cada tipo de reporte es una pieza autonoma white-label con un objetivo de
decision. El orden logico va de lo panoramico (resumen) a lo especifico
(ventas, clientes, inventario, predicciones). ``SECCIONES`` indica que
bloques se renderizan para cada tipo (claves resueltas por el motor).
"""

TIPOS = {
    "resumen": {
        "titulo": "Resumen ejecutivo",
        "descripcion": "Panorama del negocio: KPIs, tendencia de ingresos, "
                       "estacionalidad y lectura estrategica para la direccion.",
        "icono": "chart-pie",
        "secciones": ["kpis", "insights", "ventas", "estacionalidad", "recomendaciones", "metodologia"],
    },
    "ventas": {
        "titulo": "Analisis de ventas",
        "descripcion": "Ingresos por periodo, estacionalidad, demanda por "
                       "servicio y productos que mas mueven el negocio.",
        "icono": "trending-up",
        "secciones": ["insights", "ventas", "estacionalidad", "servicios"],
    },
    "clientes": {
        "titulo": "Gestion de clientes",
        "descripcion": "Segmentacion RFM, valor por cliente, riesgos de churn "
                       "y proximas acciones comerciales recomendadas.",
        "icono": "users",
        "secciones": ["insights", "clientes", "clientes_top", "churn", "recomendaciones"],
    },
    "inventario": {
        "titulo": "Inventario y reposicion",
        "descripcion": "Valor de stock, cobertura, productos criticos y "
                       "cantidad sugerida de reposicion.",
        "icono": "box",
        "secciones": ["insights", "inventario", "servicios"],
    },
    "predicciones": {
        "titulo": "Predicciones y proyecciones",
        "descripcion": "Ingresos, demanda, churn e inventario proyectados con "
                       "modelos para anticipar los proximos meses.",
        "icono": "sparkles",
        "secciones": ["insights", "predicciones"],
    },
}

REPORTES = [
    {"clave": clave, **meta}
    for clave, meta in TIPOS.items()
]

# Con este nombre (o perfil) el CLI genera todos los tipos de una vez.
TODOS = "todos"


def por_clave(clave: str) -> dict:
    """Devuelve la metadata de un tipo de reporte (o None si no existe)."""
    return TIPOS.get(clave)


def tipos_hint() -> str:
    return "resumen|ventas|clientes|inventario|predicciones|todos"