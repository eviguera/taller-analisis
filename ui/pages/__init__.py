"""Paginas de la interfaz web (definicion para st.navigation).

Cada tupla contiene: (titulo, clave url, icono Material, funcion principal, es_principal).
"""

from . import (resumen, negocio, acciones, alertas, clientes, servicios, vehiculos,
               inventario, predicciones, simulador, datos, reportes)

PAGINAS = [
    ("Resumen general", "resumen", ":material/dashboard:", resumen.principal, True),
    ("Negocio", "negocio", ":material/trending_up:", negocio.principal, False),
    ("Reportes", "reportes", ":material/description:", reportes.principal, False),
    ("Acciones", "acciones", ":material/task_alt:", acciones.principal, False),
    ("Alertas", "alertas", ":material/notifications_active:", alertas.principal, False),
    ("Clientes", "clientes", ":material/groups:", clientes.principal, False),
    ("Servicios", "servicios", ":material/build:", servicios.principal, False),
    ("Vehiculos", "vehiculos", ":material/directions_car:", vehiculos.principal, False),
    ("Inventario", "inventario", ":material/inventory_2:", inventario.principal, False),
    ("Predicciones", "predicciones", ":material/auto_graph:", predicciones.principal, False),
    ("Simulador", "simulador", ":material/science:", simulador.principal, False),
    ("Datos y configuracion", "datos", ":material/database:", datos.principal, False),
]

__all__ = ["PAGINAS"]