"""Paginas de la interfaz web (definicion para st.navigation).

Cada tupla contiene: (titulo, clave url, icono Material, funcion principal, es_principal).
"""

from . import (resumen, negocio, acciones, alertas, clientes, servicios, vehiculos,
               inventario, predicciones, simulador, datos, reportes)

PAGINAS = [
    ("Resumen general", "resumen", ":material/dashboard:", resumen.principal, True),
    ("Predicciones", "predicciones", ":material/auto_graph:", predicciones.principal, False),
    ("Acciones", "acciones", ":material/task_alt:", acciones.principal, False),
    ("Alertas", "alertas", ":material/notifications_active:", alertas.principal, False),
    ("Mis datos", "datos", ":material/database:", datos.principal, False),
    ("Reportes", "reportes", ":material/description:", reportes.principal, False),
]

__all__ = ["PAGINAS"]