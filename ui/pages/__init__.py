"""Paginas de la interfaz web (definicion para st.navigation).

Cada tupla contiene: (titulo, clave url, icono Material, funcion principal, es_principal).
"""

from . import (resumen, negocio, acciones, alertas, clientes, servicios, vehiculos,
               inventario, predicciones, simulador, datos, reportes, decisiones,
               asesor_ia, onboarding, memoria, briefing, scheduler)

PAGINAS = [
    ("Resumen general", "resumen", ":material/dashboard:", resumen.principal, True),
    ("Decisiones", "decisiones", ":material/trending_up:", decisiones.principal, False),
    ("Asesor IA", "asesor-ia", ":material/psychology:", asesor_ia.principal, False),
    ("Predicciones", "predicciones", ":material/auto_graph:", predicciones.principal, False),
    ("Acciones", "acciones", ":material/task_alt:", acciones.principal, False),
    ("Alertas", "alertas", ":material/notifications_active:", alertas.principal, False),
    ("Briefing ejecutivo", "briefing", ":material/summarize:", briefing.principal, False),
    ("Memoria", "memoria", ":material/memory:", memoria.principal, False),
    ("Scheduler", "scheduler", ":material/schedule:", scheduler.principal, False),
    ("Onboarding", "onboarding", ":material/rocket_launch:", onboarding.principal, False),
    ("Mis datos", "datos", ":material/database:", datos.principal, False),
    ("Reportes", "reportes", ":material/description:", reportes.principal, False),
]

__all__ = ["PAGINAS"]