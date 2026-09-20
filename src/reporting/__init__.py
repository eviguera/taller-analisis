"""GIRO Reportes: motor de reportes ejecutivos automatizados (producto reventa).

Genera reportes HTML white-label (listos para imprimir a PDF) por cliente
(workspace) con la marca de la consultora que entrega y el analisis
estrategico de sus datos: resumen, ventas, clientes, inventario y
predicciones. Se orquesta por CLI (automatizable via cron) o desde la UI.

Modulos:
    catalogo   - tipos de reporte disponibles y sus secciones.
    branding   - marca white-label del cliente/reventor para la portada.
    insights   - lectura estrategica automatica (reglas sobre los datos).
    secciones  - renderers HTML: KPIs, graficos, tablas, portada.
    engine     - GeneradorReportes: arma el HTML y opcionalmente PDF/email.
"""

from .catalogo import REPORTES, TIPOS, por_clave
from .engine import GeneradorReportes

__all__ = ["REPORTES", "TIPOS", "por_clave", "GeneradorReportes"]