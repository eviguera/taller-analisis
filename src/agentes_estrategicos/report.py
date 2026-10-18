"""Report Agent.

Genera un reporte ejecutivo HTML white-label a partir del análisis, el dossier
de decisión y la validación de gobernanza.

El reporte incluye:
* Portada con nombre del negocio y fecha.
* Resumen ejecutivo con los indicadores clave.
* Sección de alertas críticas.
* Tabla de decisiones con acciones recomendadas.
* Escenarios 12 meses (conservador vs agresivo).
* Pie de página con branding del workspace.

El HTML es autocontenido y listo para imprimir a PDF en A4 o enviar por email.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import jinja2

from src.formatos import moneda, miles


def generar_reporte_ejecutivo(
    analisis: Dict[str, Any],
    dossier: Dict[str, Any],
    validacion: Dict[str, Any],
    cfg: Any,
) -> Dict[str, Any]:
    """Genera un reporte ejecutivo HTML.

    Argumentos:
        analisis: resultado del Analyst Agent.
        dossier: resultado del Strategy Agent.
        validacion: resultado del Governance Agent.
        cfg: configuración del workspace (AppConfig).

    Devuelve un diccionario con:
        - ruta: ruta al archivo HTML generado.
        - contenido: contenido HTML como string.
        - titulo: título del reporte.
    """
    cfg = cfg or {}

    # Construir contexto para la plantilla Jinja2.
    contexto = _construir_contexto_reporte(
        analisis=analisis,
        dossier=dossier,
        validacion=validacion,
        cfg=cfg,
    )

    # Renderizar plantilla HTML.
    html_contenido = _renderizar_plantilla(contexto)

    # Guardar archivo.
    ruta_archivo = _guardar_reporte(html_contenido, cfg=cfg)

    return {
        "ruta": str(ruta_archivo),
        "contenido": html_contenido,
        "titulo": contexto.get("negocio_nombre", "Reporte Ejecutivo"),
        "fecha_generacion": datetime.now().isoformat(),
    }


def _construir_contexto_reporte(
    analisis: Dict[str, Any],
    dossier: Dict[str, Any],
    validacion: Dict[str, Any],
    cfg: Any,
) -> Dict[str, Any]:
    """Construye el contexto de datos para la plantilla Jinja2."""
    kpis = analisis.get("kpis", {})
    salud = analisis.get("salud_cartera", {}) or {}
    alertas = analisis.get("alertas", [])
    decisiones = dossier.get("decisiones_validadas", dossier.get("decisiones", []))

    # Negocio.
    negocio_nombre = getattr(cfg, "negocio_nombre", "Mi Negocio") if cfg else "Mi Negocio"
    negocio_sector = getattr(cfg, "sector", "") if cfg else ""
    moneda = getattr(cfg, "moneda", "CLP") if cfg else "CLP"
    clave_workspace = getattr(cfg, "clave", "principal") if cfg else "principal"

    # Alertas críticas y medias.
    alertas_criticas = [a for a in alertas if a.get("severidad") == "critica"]
    alertas_medias = [a for a in alertas if a.get("severidad") == "media"]

    # Decisiones válidas.
    decisiones_validas = [d for d in decisiones if d.get("valido", True)]
    decisiones_actuar = [d for d in decisiones_validas if d.get("accion") == "actuar"]
    decisiones_revisar = [d for d in decisiones_validas if d.get("accion") == "revisar"]

    # Escenarios.
    escenario_conservador = dossier.get("escenario_conservador", {})
    escenario_agresivo = dossier.get("escenario_agresivo", {})
    delta_ingresos = float(dossier.get("delta_ingresos", 0))
    delta_ebitda = float(dossier.get("delta_ebitda", 0))

    # Fecha actual.
    ahora = datetime.now()

    return {
        "negocio_nombre": negocio_nombre,
        "negocio_sector": negocio_sector,
        "moneda": moneda,
        "clave_workspace": clave_workspace,
        "fecha_generacion": ahora.strftime("%d/%m/%Y"),
        "fecha_generacion_completa": ahora.strftime("%d de %B de %Y a las %H:%M"),
        # KPIs.
        "total_ingresos": kpis.get("total_ingresos", 0),
        "total_facturas": kpis.get("total_facturas", 0),
        "ticket_promedio": kpis.get("ticket_promedio", 0),
        "clientes_activos": kpis.get("clientes_activos", 0),
        "descuentos_total": kpis.get("descuentos_total", 0),
        "valor_cliente_promedio": kpis.get("valor_cliente_promedio", 0),
        # Salud de cartera.
        "arpu_mensual": salud.get("arpu_mensual", 0),
        "arpu_anual": salud.get("arpu_anual", 0),
        "churn_mensual": salud.get("churn_mensual", 0),
        "retencion_mensual": salud.get("retencion_mensual", 0),
        "ltv_gross": salud.get("ltv_gross", 0),
        "valor_total_cartera": salud.get("valor_total_cartera", 0),
        "monto_en_riesgo": salud.get("monto_en_riesgo", 0),
        "clientes_en_riesgo": salud.get("clientes_en_riesgo", 0),
        # Alertas.
        "n_alertas_criticas": len(alertas_criticas),
        "n_alertas_medias": len(alertas_medias),
        "alertas_criticas": alertas_criticas[:10],
        "alertas_medias": alertas_medias[:10],
        # Decisiones.
        "decisiones": decisiones_validas,
        "n_decisiones_actuar": len(decisiones_actuar),
        "n_decisiones_revisar": len(decisiones_revisar),
        "decisiones_actuar": decisiones_actuar[:5],
        "decisiones_revisar": decisiones_revisar[:5],
        # Escenarios.
        "ingresos_conservador": escenario_conservador.get("ingresos", 0),
        "ebitda_conservador": escenario_conservador.get("ebitda", 0),
        "ingresos_agresivo": escenario_agresivo.get("ingresos", 0),
        "ebitda_agresivo": escenario_agresivo.get("ebitda", 0),
        "delta_ingresos": delta_ingresos,
        "delta_ebitda": delta_ebitda,
        "margen_ebitda_conservador": escenario_conservador.get("margen_ebitda", 0),
        "margen_ebitda_agresivo": escenario_agresivo.get("margen_ebitda", 0),
        # Recomendación principal.
        "recomendacion_principal": dossier.get("recomendacion_principal", {}),
        # Configuración.
        "cfg": cfg,
    }


def _renderizar_plantilla(contexto: Dict[str, Any]) -> str:
    """Renderiza la plantilla HTML del reporte ejecutivo."""
    plantilla_html = _obtener_plantilla_html()
    entorno = jinja2.Environment(loader=jinja2.BaseLoader())
    # Registrar filtros personalizados para usar en la plantilla.
    entorno.filters['moneda'] = lambda v, m="CLP": moneda(v, m)
    plantilla = entorno.from_string(plantilla_html)
    return plantilla.render(**contexto)


def _obtener_plantilla_html() -> str:
    """Devuelve la plantilla HTML del reporte ejecutivo."""
    return """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <title>{{ negocio_nombre }} - Reporte Ejecutivo</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            color: #1e293b;
            line-height: 1.6;
            background: #f8fafc;
        }
        .container {
            max-width: 1000px;
            margin: 0 auto;
            padding: 40px;
            background: #ffffff;
        }
        header {
            background: linear-gradient(135deg, #0F7666 0%, #0d9488 100%);
            color: white;
            padding: 40px 30px;
            border-radius: 12px 12px 0 0;
            margin-bottom: 30px;
        }
        header h1 {
            font-size: 28px;
            margin-bottom: 8px;
            font-weight: 700;
        }
        header .subtitulo {
            font-size: 16px;
            opacity: 0.9;
        }
        header .meta {
            margin-top: 12px;
            font-size: 13px;
            opacity: 0.8;
        }
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .kpi-card {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 24px;
            text-align: center;
        }
        .kpi-card .valor {
            font-size: 32px;
            font-weight: 700;
            color: #0F7666;
            margin-bottom: 8px;
        }
        .kpi-card .etiqueta {
            font-size: 14px;
            color: #64748b;
            font-weight: 500;
        }
        .kpi-card .delta {
            font-size: 13px;
            margin-top: 6px;
        }
        .delta.positivo { color: #059669; }
        .delta.negativo { color: #dc2626; }
        .delta.neutral { color: #64748b; }
        .seccion {
            margin-bottom: 30px;
        }
        .seccion h2 {
            font-size: 20px;
            margin-bottom: 16px;
            color: #1e293b;
            border-bottom: 2px solid #0F7666;
            padding-bottom: 8px;
        }
        .panel {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
        }
        .panel h3 {
            font-size: 16px;
            margin-bottom: 12px;
            color: #1e293b;
        }
        .alerta {
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 12px;
            border-left: 4px solid;
        }
        .alerta.critica { background: #fef2f2; border-color: #dc2626; color: #7f1d1d; }
        .alerta.media { background: #fefce8; border-color: #d97706; color: #78350f; }
        .alerta.ok { background: #f0fdf4; border-color: #059669; color: #14532d; }
        .decision {
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 12px;
            border: 1px solid #e2e8f0;
            background: #ffffff;
        }
        .decision h4 {
            font-size: 16px;
            margin-bottom: 6px;
            color: #1e293b;
        }
        .decision .motivo {
            font-size: 14px;
            color: #475569;
            margin-bottom: 10px;
        }
        .decision .impacto {
            font-size: 14px;
            font-weight: 700;
            color: #0F7666;
        }
        .escenarios {
            display: flex;
            gap: 16px;
            margin-top: 12px;
        }
        .escenario {
            flex: 1;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }
        .escenario .valor {
            font-size: 20px;
            font-weight: 700;
            color: #1e293b;
        }
        .escenario .etiqueta {
            font-size: 12px;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .recomendacion-principal {
            background: linear-gradient(135deg, #0F7666 0%, #0d9488 100%);
            color: white;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 30px;
        }
        .recomendacion-principal h2 {
            color: white;
            margin-bottom: 12px;
        }
        .recomendacion-principal p {
            font-size: 16px;
            line-height: 1.6;
            opacity: 0.95;
        }
        footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #e2e8f0;
            color: #64748b;
            font-size: 12px;
            text-align: center;
        }
        @media print {
            body { background: #ffffff; }
            .container { box-shadow: none; border: none; }
            .panel, .alerta, .decision { break-inside: avoid; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>{{ negocio_nombre }}</h1>
            {% if negocio_sector %}<div class="subtitulo">{{ negocio_sector }}</div>{% endif %}
            <div class="meta">
                Reporte Ejecutivo · {{ fecha_generacion_completa }}<br>
                Workspace: {{ clave_workspace }} · Moneda: {{ moneda }}
            </div>
        </header>

        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="valor">{{ total_ingresos | moneda(moneda) }}</div>
                <div class="etiqueta">Ingresos del mes</div>
            </div>
            <div class="kpi-card">
                <div class="valor">{{ total_facturas }}</div>
                <div class="etiqueta">Facturas emitidas</div>
            </div>
            <div class="kpi-card">
                <div class="valor">{{ ticket_promedio | moneda(moneda) }}</div>
                <div class="etiqueta">Ticket promedio</div>
            </div>
            <div class="kpi-card">
                <div class="valor">{{ clientes_activos }}</div>
                <div class="etiqueta">Clientes activos</div>
            </div>
        </div>

        <div class="seccion">
            <h2>Resumen Ejecutivo</h2>
            <div class="panel">
                <p>{{ resumen_texto }}</p>
            </div>
        </div>

        {% if alertas_criticas or alertas_medias %}
        <div class="seccion">
            <h2>Alertas de Negocio</h2>
            {% for alerta in alertas_criticas %}
            <div class="alerta critica">
                <strong>{{ alerta.titulo }}</strong><br>
                {{ alerta.detalle }}
            </div>
            {% endfor %}
            {% for alerta in alertas_medias %}
            <div class="alerta media">
                <strong>{{ alerta.titulo }}</strong><br>
                {{ alerta.detalle }}
            </div>
            {% endfor %}
        </div>
        {% endif %}

        <div class="seccion">
            <h2>Decisiones Recomendadas</h2>
            {% for decision in decisiones %}
            <div class="decision">
                <h4>{{ decision.titulo }}</h4>
                <div class="motivo">{{ decision.motivo }}</div>
                {% if decision.impacto_esperado != 0 %}
                <div class="impacto">Impacto esperado: {{ decision.impacto_esperado | moneda(moneda) }}</div>
                {% endif %}
                <div style="font-size: 12px; color: #64748b; margin-top: 8px;">
                    Confianza: {{ decision.confianza }} | Acción: {{ decision.accion }}
                </div>
            </div>
            {% endfor %}
        </div>

        <div class="seccion">
            <h2>Escenarios a 12 Meses</h2>
            <div class="panel">
                <div class="escenarios">
                    <div class="escenario">
                        <div class="etiqueta">Conservador</div>
                        <div class="valor">{{ ingresos_conservador | moneda(moneda) }}</div>
                        <div class="etiqueta">Ingresos</div>
                        <div class="etiqueta" style="font-size: 11px;">{{ ebitda_conservador | moneda(moneda) }} EBITDA</div>
                    </div>
                    <div class="escenario">
                        <div class="etiqueta">Agresivo (con Giro Recomienda)</div>
                        <div class="valor">{{ ingresos_agresivo | moneda(moneda) }}</div>
                        <div class="etiqueta">Ingresos</div>
                        <div class="etiqueta" style="font-size: 11px;">{{ ebitda_agresivo | moneda(moneda) }} EBITDA</div>
                    </div>
                    <div class="escenario">
                        <div class="etiqueta">Delta Ingresos</div>
                        <div class="valor" style="color: {% if delta_ingresos > 0 %}#059669{% else %}#dc2626{% endif %};">
                            {{ delta_ingresos | moneda(moneda) }}
                        </div>
                        <div class="etiqueta" style="font-size: 11px;">{{ delta_ebitda | moneda(moneda) }} EBITDA</div>
                    </div>
                </div>
            </div>
        </div>

        {% if recomendacion_principal %}
        <div class="recomendacion-principal">
            <h2>Recomendación Principal</h2>
            <p>
                <strong>{{ recomendacion_principal.area }}:</strong>
                {{ recomendacion_principal.motivo }}
            </p>
            {% if recomendacion_principal.impacto_esperado != 0 %}
            <p><strong>Impacto esperado:</strong> {{ recomendacion_principal.impacto_esperado | moneda(moneda) }}</p>
            {% endif %}
        </div>
        {% endif %}

        <footer>
            Reporte generado automáticamente con GIRO Analytics.<br>
            Los datos y predicciones pertenecen a tu empresa.
        </footer>
    </div>
</body>
</html>"""


def _guardar_reporte(html_contenido: str, cfg: Any) -> Path:
    """Guarda el reporte HTML en disco y devuelve la ruta."""
    from src.reporting.engine import listar_generados
    from pathlib import Path as PathLib

    # Directorio de reportes del workspace.
    directorio_reportes = PathLib("reports") / getattr(cfg, "clave", "principal")
    directorio_reportes.mkdir(parents=True, exist_ok=True)

    ahora = datetime.now()
    nombre_archivo = f"reporte_ejecutivo_{ahora.strftime('%Y%m%d_%H%M%S')}.html"
    ruta = directorio_reportes / nombre_archivo

    ruta.write_text(html_contenido, encoding="utf-8")

    return ruta


__all__ = ["generar_reporte_ejecutivo"]
