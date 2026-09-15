"""Paginas de la interfaz web (definicion para st.navigation).

Cada tupla contiene: (titulo, clave url, icono Material, funcion principal, es_principal).
"""

from . import resumen, clientes, servicios, vehiculos, inventario, predicciones, datos

PAGINAS = [
    ("Resumen general", "resumen", ":material/dashboard:", resumen.principal, True),
    ("Clientes", "clientes", ":material/groups:", clientes.principal, False),
    ("Servicios", "servicios", ":material/build:", servicios.principal, False),
    ("Vehiculos", "vehiculos", ":material/directions_car:", vehiculos.principal, False),
    ("Inventario", "inventario", ":material/inventory_2:", inventario.principal, False),
    ("Predicciones", "predicciones", ":material/auto_graph:", predicciones.principal, False),
    ("Datos y configuracion", "datos", ":material/database:", datos.principal, False),
]

__all__ = ["PAGINAS"]