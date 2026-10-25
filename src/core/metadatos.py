"""Metadatos del almacén analítico.

Contiene definiciones compartidas de vistas analíticas, ejemplos de consultas
SQL y otros metadatos que son usados por múltiples módulos (aplicacion, UI,
API, etc.) sin pertenecer a un caso de uso específico.
"""

from __future__ import annotations

#: Vistas que salen en la exportación analítica a PSPP/SPSS.
VISTAS_PARA_EXPORTAR = [
    "ingresos_mensuales",
    "ingresos_por_marca",
    "ingresos_por_vehiculo",
    "rfm_clientes",
    "churn_clientes",
    "detalle_servicios",
    "demanda_servicios_mensual",
    "ingresos_por_servicio_mensual",
    "factura_detalle_desnormalizado",
    "inventario_estado",
    "facturas_con_dimensiones",
]

#: Ejemplos de consultas SQL para la consola SQL y la documentación.
EJEMPLOS_SQL = {
    "Facturas recientes": "SELECT * FROM facturas LIMIT 10",
    "Top clientes por gasto": "SELECT nombre, SUM(total) AS gasto FROM facturas GROUP BY nombre ORDER BY gasto DESC LIMIT 10",
    "Vehículos por marca": "SELECT marca, COUNT(*) AS vehiculos FROM vehiculos GROUP BY marca ORDER BY vehiculos DESC",
    "Facturas por estado": "SELECT estado, SUM(total) AS monto, COUNT(*) AS facturas FROM facturas GROUP BY estado",
}
