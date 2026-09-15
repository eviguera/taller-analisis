import base64
import io
import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from pathlib import Path

from .analyzer import Analyzer
from .predictions import Predictor

plt.rcParams["font.family"] = "DejaVu Sans"


def _miles(valor, decimales=0):
    """Formatea un numero con punto como separador de miles (es-CL)."""
    return f"{valor:,.{decimales}f}".replace(",", ".")


def _fig_a_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return f"data:image/png;base64,{encoded}"


class ReportGenerator:
    """Genera reportes HTML con analisis y predicciones."""

    def __init__(self, data):
        self.data = data
        self.analyzer = Analyzer(data)
        self.predictor = Predictor(data)
        self.output_dir = Path(__file__).parent.parent / "reports"

    def _kpi_html(self, kpis):
        items = {
            "Ingresos Totales": f"${_miles(kpis['total_ingresos'])}",
            "Facturas": f"{_miles(kpis['total_facturas'])}",
            "Ticket Promedio": f"${_miles(kpis['ticket_promedio'])}",
            "Clientes Activos": f"{kpis['clientes_activos']}",
            "Vehiculos": f"{kpis['vehiculos_atendidos']}",
            "Valor Cliente Prom.": f"${_miles(kpis['valor_cliente_promedio'])}",
        }
        cards = ""
        for label, value in items.items():
            cards += f"""
            <div class="kpi-card">
                <div class="kpi-value">{value}</div>
                <div class="kpi-label">{label}</div>
            </div>"""
        return cards

    def _grafico_ingresos(self):
        serie = self.analyzer.ingresos_por_mes()
        if serie.empty:
            return ""
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(serie["anio_mes"], serie["total"], marker="o", linewidth=2, color="#2563eb")
        ax.set_title("Ingresos Mensuales")
        ax.set_ylabel("Ingresos ($)")
        ax.grid(alpha=0.3)
        plt.xticks(rotation=45)
        return _fig_a_base64(fig)

    def _grafico_marcas(self):
        df = self.analyzer.ingresos_por_marca().head(8)
        if df.empty:
            return ""
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.barh(df["marca"][::-1], df["ingresos"][::-1], color="#10b981")
        ax.set_title("Ingresos por Marca")
        ax.set_xlabel("Ingresos ($)")
        ax.grid(alpha=0.3, axis="x")
        return _fig_a_base64(fig)

    def _grafico_servicios(self):
        df = self.analyzer.servicios_mas_solicitados().head(10)
        if df.empty:
            return ""
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar(df["servicio"], df["frecuencia"], color="#f59e0b")
        ax.set_title("Servicios Mas Solicitados")
        ax.set_ylabel("Frecuencia")
        plt.xticks(rotation=45, ha="right")
        ax.grid(alpha=0.3, axis="y")
        return _fig_a_base64(fig)

    def _grafico_estacionalidad(self):
        est = self.analyzer.estacionalidad()
        if est["por_mes"].empty:
            return ""
        df = est["por_mes"]
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        nombres_mes = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        axes[0].bar(nombres_mes, df["ingresos"], color="#8b5cf6")
        axes[0].set_title("Ingresos por Mes")
        axes[0].grid(alpha=0.3, axis="y")

        dias = {
            "Monday": "Lun", "Tuesday": "Mar", "Wednesday": "Mie",
            "Thursday": "Jue", "Friday": "Vie", "Saturday": "Sab", "Sunday": "Dom"
        }
        est["por_dia_semana"]["dia"] = est["por_dia_semana"]["dia_semana"].map(dias)
        axes[1].bar(est["por_dia_semana"]["dia"], est["por_dia_semana"]["ingresos"], color="#ec4899")
        axes[1].set_title("Ingresos por Dia")
        axes[1].grid(alpha=0.3, axis="y")
        return _fig_a_base64(fig)

    def _df_a_html(self, df, limit=15, table_class=""):
        df = df.head(limit).copy()
        return df.to_html(
            classes=f"data-table {table_class}".strip(),
            index=False,
            border=0,
            float_format=lambda x: _miles(float(x)),
        )

    def generar(self, base_filename=None):
        output_dir = self.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        fecha = datetime.now()
        filename = base_filename or f"reporte-{fecha.strftime('%Y%m%d-%H%M%S')}.html"
        ruta = output_dir / filename

        kpis = self.analyzer.kpis_globales()
        ingresos = self._grafico_ingresos()
        marcas = self._grafico_marcas()
        servicios = self._grafico_servicios()
        estacionalidad = self._grafico_estacionalidad()

        top_clientes = self.analyzer.clientes_top()
        rfm = self.analyzer.clientes_rfm()
        segmentos = rfm["segmento"].value_counts().to_dict() if not rfm.empty else {}

        # Predicciones
        pred_ingresos = self.predictor.predecir_ingresos()
        pred_demanda = self.predictor.predecir_demanda()
        prob_churn = self.predictor.predecir_churn()
        inv = self.predictor.predecir_inventario()

        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GIRO - Reporte de Inteligencia {fecha.strftime('%d/%m/%Y')}</title>
<style>
    :root {{
        --primary: #2563eb; --dark: #1e293b; --light: #f1f5f9; --accent: #f59e0b;
        --success: #10b981; --danger: #ef4444; --info: #8b5cf6;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background: var(--light); color: var(--dark); }}
    .header {{ background: linear-gradient(135deg, #1e3a8a, #2563eb); color: white; padding: 40px 30px; }}
    .header h1 {{ font-size: 28px; margin-bottom: 8px; }}
    .header p {{ opacity: 0.9; }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}
    .section {{ background: white; border-radius: 12px; padding: 25px; margin-bottom: 25px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    .section h2 {{ color: var(--primary); font-size: 20px; margin-bottom: 15px; border-bottom: 2px solid var(--light); padding-bottom: 10px; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 15px; margin-bottom: 25px; }}
    .kpi-card {{ background: white; border-radius: 10px; padding: 18px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-top: 4px solid var(--primary); }}
    .kpi-value {{ font-size: 22px; font-weight: 700; color: var(--dark); }}
    .kpi-label {{ font-size: 12px; color: #64748b; margin-top: 4px; }}
    .chart {{ text-align: center; margin: 15px 0; }}
    .chart img {{ max-width: 100%; border-radius: 8px; }}
    .data-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    .data-table th {{ background: var(--dark); color: white; padding: 10px; text-align: left; }}
    .data-table td {{ padding: 9px 10px; border-bottom: 1px solid #e2e8f0; }}
    .data-table tr:nth-child(even) {{ background: #f8fafc; }}
    .data-table tr:hover {{ background: #e0f2fe; }}
    .badge {{ display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; }}
    .badge-green {{ background: #d1fae5; color: #065f46; }}
    .badge-red {{ background: #fee2e2; color: #991b1b; }}
    .badge-yellow {{ background: #fef3c7; color: #92400e; }}
    .badge-blue {{ background: #dbeafe; color: #1e40af; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
    .footer {{ text-align: center; color: #64748b; padding: 20px; font-size: 12px; }}
    @media (max-width: 768px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
    table.data-table {{ font-size: 12px; }}
    th, td {{ text-align: left !important; }}
</style>
</head>
<body>
    <div class="header">
        <h1>GIRO - Inteligencia de negocio</h1>
        <p>Reporte generado el {fecha.strftime('%d de %B de %Y a las %H:%M')}</p>
    </div>

    <div class="container">
        <div class="kpi-grid">
            {self._kpi_html(kpis)}
        </div>

        <div class="section">
            <h2>Ingresos</h2>
            <div class="chart">{ingresos}</div>
        </div>

        <div class="section">
            <h2>Clientes</h2>
            <div class="grid-2">
                <div>
                    <h3 style="color:#334155; margin-bottom:10px; font-size:15px;">Top 10 Clientes por Valor</h3>
                    {self._df_a_html(top_clientes, limit=10)}
                </div>
                <div>
                    <h3 style="color:#334155; margin-bottom:10px; font-size:15px;">Segmentacion RFM</h3>
                    {self._df_a_html(rfm[["nombre", "recencia_dias", "frecuencia", "monto", "segmento"]].head(10), limit=10)}
                </div>
            </div>
        </div>

        <div class="section">
            <h2>Vehiculos y Marcas</h2>
            <div class="chart">{marcas}</div>
        </div>

        <div class="section">
            <h2>Servicios</h2>
            <div class="chart">{servicios}</div>
        </div>

        <div class="section">
            <h2>Estacionalidad</h2>
            <div class="chart">{estacionalidad}</div>
        </div>

        <div class="section">
            <h2>Prediccion de Ingresos</h2>
            <p style="margin-bottom:10px;">Modelo: <strong>Gradient Boosting</strong>
            {f'| MAE: ${_miles(pred_ingresos["evaluacion"]["mae"])} | RMSE: ${_miles(pred_ingresos["evaluacion"]["rmse"])}' if pred_ingresos.get("evaluacion") else ''}</p>
            {self._df_a_html(pred_ingresos["predicciones"], limit=6)}
        </div>

        <div class="section">
            <h2>Pronostico de Demanda por Servicio</h2>
            {self._df_a_html(pred_demanda["predicciones"].pivot_table(index='fecha', columns='servicio', values='demanda_predicha', aggfunc='sum').reset_index(), limit=6) if not pred_demanda["predicciones"].empty else "<p>Datos insuficientes.</p>"}
        </div>

        <div class="section">
            <h2>Clientes en Riesgo de Churn</h2>
            {f'<p>Accuracy: {prob_churn["evaluacion"].get("accuracy", "N/A")} | F1: {prob_churn["evaluacion"].get("f1", "N/A")} | Tasa churn: {prob_churn["evaluacion"].get("tasa_churn", "N/A")}%</p>' if prob_churn.get("evaluacion") else ''}
            {self._df_a_html(prob_churn["resultados"][["nombre", "recencia", "frecuencia", "monto", "churn", "prob_churn"]].head(15), limit=15)}
        </div>

        <div class="section">
            <h2>Inventario y Reposicion</h2>
            {self._df_a_html(inv[["producto", "stock_actual", "stock_minimo", "meses_cobertura", "recomendacion", "valor_stock"]].head(20), limit=20)}
        </div>

        <div class="section">
            <h2>Notas y Recomendaciones</h2>
            <ul style="line-height: 1.7; padding-left: 20px;">
                <li>Los meses de julio y agosto muestran picos de demanda. Considere tener personal adicional y stock elevado de repuestos de frenos y suspension en ese periodo.</li>
                <li>Los clientes del segmento "Campeones" representan la mayor parte de los ingresos. Implementar un programa de fidelidad.</li>
                <li>Para los clientes "En Riesgo" o "Perdido", enviar recordatorios de mantenimiento con ofertas especificas.</li>
                <li>Priorizar el reabastecimiento de productos marcados como "Reabastecer" en el inventario.</li>
            </ul>
        </div>

        <div class="footer">
            Generado por GIRO (inteligencia de negocio) - v1.4
        </div>
    </div>
</body>
</html>"""

        with open(ruta, "w", encoding="utf-8") as f:
            f.write(html)

        return str(ruta), {
            "kpis": kpis,
            "predicciones": {
                "ingresos": pred_ingresos,
                "demanda": pred_demanda,
                "churn": prob_churn,
                "inventario": inv
            }
        }