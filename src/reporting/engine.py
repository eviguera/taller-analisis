"""Motor de generacion de reportes: arma el documento HTML white-label.

Flujo: datos -> Analyzer/Predictor -> secciones segun el tipo de reporte ->
un HTML completo lista para imprimir a PDF (A4) en ``reports/<clave>/<tipo>/``.
Opcionalmente convierte a PDF si WeasyPrint esta instalado y envia por email
si el SMTP del workspace esta configurado (automatizable via cron).
"""

from __future__ import annotations

import os
from datetime import datetime
from html import escape
from pathlib import Path
from typing import List, Optional

import matplotlib
matplotlib.use("Agg")

from . import catalogo
from . import secciones as S
from .branding import marca, ocasion, tipos_habilitados, periodos_meses
from .estilos import css as css_reporte
from .formato import (miles, moneda, fecha_es, periodo_es)
from .insights import generar_insights
from src.core.config import umbral_churn


def _base_reports() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "reports"


class GeneradorReportes:
    """Genera reportes ejecutivos para un workspace determinados datos."""

    def __init__(self, cfg, data, base_dir: Optional[Path] = None):
        self.cfg = cfg
        self.data = data
        self.base_dir = Path(base_dir) if base_dir else _base_reports()
        self.output_dir = self.base_dir / (cfg.clave or "principal")
        self.marca = marca(cfg)
        self.mon = self.marca["moneda"] or "CLP"

    # ------------------------------------------------------------------
    #  Estructura del documento
    # ------------------------------------------------------------------
    def _portada(self, meta: dict) -> str:
        m = self.marca
        # Todo lo que sale de m viene de config/config.yaml: son texto de marca
        # capturado por el usuario (nombre, eslogan, consultora, contacto), y
        # el documento se sirve para descarga y se pinta en un iframe. Escapa.
        # Los colores no se escapan: branding.marca ya los valida como hex.
        logo = (f'<img class="logo" src="{escape(m["logo"] or "")}" alt=""/>'
                if m.get("logo") else "")
        slogan = (f'<p style="color:#64748B;margin-top:4px;">{escape(m["slogan"])}</p>'
                  if m.get("slogan") else "")
        sector_tope = (f'<div class="sector-tope">{escape(m["sector"])}</div>'
                       if m.get("sector") else "")
        contacto = " · ".join([x for x in [m["contacto"], m["web"]] if x])
        return f"""
        <div class="portada">
            {logo}{sector_tope}
            <h1>{escape(meta["titulo"])}</h1>{slogan}
            <div><span class="ocasion">{escape(meta["ocasion"])}</span></div>
            <div class="datos">
                <div class="dato"><b>Empresa</b><span>{escape(m["negocio"])}</span></div>
                <div class="dato"><b>Periodo analizado</b><span>{escape(meta["periodo"])}</span></div>
                <div class="dato"><b>Generado el</b><span>{escape(meta["fecha"])}</span></div>
                <div class="dato reversa"><b>Entregado por</b>
                    <span>{escape(m["consultora"])}</span>
                    {f'<br><small style="color:#94A3B8;">{escape(contacto)}</small>'
                     if contacto else ''}
                </div>
            </div>
        </div>"""

    def _contenido(self, tipo: str, ctx: dict) -> str:
        """Renderiza las secciones del tipo de reporte en orden."""
        renderers = {
            "kpis": self._sec_kpis,
            "insights": self._sec_insights,
            "ventas": self._sec_ventas,
            "estacionalidad": self._sec_estacionalidad,
            "servicios": self._sec_servicios,
            "clientes": self._sec_clientes,
            "clientes_top": self._sec_clientes_top,
            "churn": self._sec_churn,
            "inventario": self._sec_inventario,
            "predicciones": self._sec_predicciones,
            "recomendaciones": self._sec_recomendaciones,
            "metodologia": self._sec_metodologia,
        }
        partes = []
        for secc in catalogo.TIPOS[tipo]["secciones"]:
            fn = renderers.get(secc)
            if fn is None:
                continue
            html = fn(ctx)
            if html:
                partes.append(html)
        return "\n".join(partes)

    # ------------------------------------------------------------------
    #  Portada por tipo
    # ------------------------------------------------------------------
    def _meta(self, tipo: str, ocasion_label: str) -> dict:
        periodos = periodos_meses(self.cfg)
        alcance = f"Ultimos {max(periodos)} meses de operacion"
        return {
            "titulo": catalogo.TIPOS[tipo]["titulo"],
            "ocasion": ocasion_label or ocasion(self.cfg),
            "periodo": alcance,
            "fecha": fecha_es(datetime.now(), con_hora=True),
        }

    # ------------------------------------------------------------------
    #  Renderers de seccion
    # ------------------------------------------------------------------
    def _sec_kpis(self, ctx):
        kpis = ctx["kpis"]
        return S.seccion("Indicadores clave", S.kpi_cards(kpis, self.mon),
                         "KPIs del periodo analizado")

    def _sec_insights(self, ctx):
        insights = ctx["insights"]
        return S.seccion("Lectura estrategica",
                         S.insight_lista(insights),
                         "Observaciones automaticas para la direccion")

    def _sec_ventas(self, ctx):
        analyzer = ctx["analyzer"]
        serie = analyzer.ingresos_por_mes()
        grafico = S.grafico_ingresos(analyzer, self.marca["color_primario"])
        tabla = S.tabla(serie, columnas=["anio_mes", "total", "acumulado"],
                        titulos={"anio_mes": "Periodo", "total": "Ingresos",
                                 "acumulado": "Acumulado"},
                        moneda_cols={"total": self.mon, "acumulado": self.mon})
        cuerpo = (f'<div class="chart">{grafico}</div>' if grafico else "") + tabla
        return S.seccion("Ingresos y tendencia", cuerpo,
                         "Serie mensual de facturacion")

    def _sec_estacionalidad(self, ctx):
        analyzer = ctx["analyzer"]
        est = analyzer.estacionalidad()
        grafico = S.grafico_estacionalidad(analyzer, self.marca["color_secundario"])
        por_mes = est["por_mes"].rename(columns={"mes": "Mes"})
        tabla = S.tabla(por_mes, moneda_cols={"ingresos": self.mon})
        cuerpo = (f'<div class="chart">{grafico}</div>' if grafico else "") + tabla
        return S.seccion("Estacionalidad", cuerpo,
                         "Cuando se concentra la demanda")

    def _sec_servicios(self, ctx):
        from . import secciones as S2
        analyzer = ctx["analyzer"]
        df = analyzer.servicios_mas_solicitados()
        if df.empty:
            return ""
        import matplotlib.pyplot as plt
        from .formato import fig_a_base64
        fig, ax = plt.subplots(figsize=(8, 3.6), dpi=110)
        top = df.head(10)
        ax.barh(top["servicio"][::-1], top["frecuencia"][::-1],
                color=self.marca["color_acento"], alpha=0.9)
        ax.set_xlabel("Solicitudes")
        ax.grid(alpha=0.25, axis="x")
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        grafico = fig_a_base64(fig)
        tabla = S2.tabla(df, columnas=["servicio", "frecuencia"],
                         titulos={"servicio": "Servicio", "frecuencia": "Solicitudes"})
        return S.seccion("Servicios mas demandados",
                         f'<div class="chart">{grafico}</div>' + tabla,
                         "Que servicios mueven la operacion")

    def _sec_clientes(self, ctx):
        analyzer = ctx["analyzer"]
        rfm = analyzer.clientes_rfm()
        badges = S.badges_segmentos(rfm)
        tabla = S.tabla(rfm, columnas=["nombre", "segmento", "recencia_dias",
                                       "frecuencia", "monto"],
                        titulos={"nombre": "Cliente", "segmento": "Segmento",
                                 "recencia_dias": "Recencia (dias)",
                                 "frecuencia": "Frecuencia", "monto": "Valor"},
                        limit=14, moneda_cols={"monto": self.mon})
        return S.seccion("Segmentacion RFM", badges + tabla,
                         "Clientes agrupados por valor, frecuencia y recencia")

    def _sec_clientes_top(self, ctx):
        analyzer = ctx["analyzer"]
        top = analyzer.clientes_top()
        tabla = S.tabla(top, columnas=["nombre", "facturas", "total_gastado",
                                       "ultima_visita"],
                        titulos={"nombre": "Cliente", "facturas": "Facturas",
                                 "total_gastado": "Total", "ultima_visita": "Ultima visita"},
                        moneda_cols={"total_gastado": self.mon})
        return S.seccion("Top clientes por valor", tabla,
                         "Donde se concentra el ingreso")

    def _sec_churn(self, ctx):
        pred = ctx["predictor"].predecir_churn()
        resultados = pred.get("resultados")
        if resultados is None or resultados.empty:
            return ""
        umbral = umbral_churn(self.cfg.alertas)
        tabla = S.tabla(resultados,
                        columnas=["nombre", "recencia", "frecuencia", "monto",
                                  "churn", "prob_churn"],
                        titulos={"nombre": "Cliente", "recencia": "Recencia",
                                 "frecuencia": "Frecuencia", "monto": "Valor",
                                 "churn": "Estado", "prob_churn": "Prob. abandono"},
                        limit=15, moneda_cols={"monto": self.mon},
                        pct_cols={"prob_churn": "percent"})
        riesgo = resultados[resultados["prob_churn"] >= umbral]
        aviso = (f'<p style="font-size:12.5px;color:#475569;margin-bottom:10px;">'
                 f"{len(riesgo)} cliente(s) superan el umbral de riesgo "
                 f"({umbral:.0%}) y requieren accion de retencion.</p>")
        return S.seccion("Riesgo de churn", aviso + tabla,
                         "Clientes con probabilidad de abandonar")

    def _sec_inventario(self, ctx):
        predictor = ctx["predictor"]
        inv = predictor.predecir_inventario()
        if inv is None or inv.empty:
            return ""
        criticos = inv[inv["recomendacion"] == "Reabastecer"]
        resumen = (f'<p style="font-size:13px;color:#0F172A;margin-bottom:10px;">'
                   f"<b>{len(criticos)}</b> productos requieren reposicion de "
                   f"<b>{len(inv)}</b> del catalogo.</p>")
        tabla = S.tabla(inv, columnas=["producto", "stock_actual", "stock_minimo",
                                       "meses_cobertura", "recomendacion",
                                       "valor_stock"],
                        titulos={"producto": "Producto", "stock_actual": "Stock",
                                 "stock_minimo": "Minimo",
                                 "meses_cobertura": "Cobertura (meses)",
                                 "recomendacion": "Accion",
                                 "valor_stock": "Valor stock"},
                        limit=18, moneda_cols={"valor_stock": self.mon})
        return S.seccion("Inventario y reposicion", resumen + tabla,
                         "Cobertura y stock bajo el minimo")

    def _sec_predicciones(self, ctx):
        predictor = ctx["predictor"]
        mon = self.mon
        piezas = []

        ingresos = predictor.predecir_ingresos()
        if ingresos.get("predicciones") is not None and not ingresos["predicciones"].empty:
            blk = S.tabla(ingresos["predicciones"], limit=8,
                          columnas=["fecha", "ingresos_predichos"],
                          titulos={"fecha": "Periodo",
                                   "ingresos_predichos": "Ingresos proyectados"},
                          moneda_cols={"ingresos_predichos": mon})
            mejor = ""
            eva = ingresos.get("evaluacion") or {}
            if eva.get("mae") is not None:
                mejor = (f'<p class="nota">Error medio absoluto '
                         f'{moneda(eva["mae"], mon)}.</p>')
            piezas.append(S.seccion("Ingresos proyectados", blk + mejor,
                                    "Modelo de series con lags"))

        demanda = predictor.predecir_demanda()
        if demanda.get("predicciones") is not None and not demanda["predicciones"].empty:
            piezas.append(S.seccion("Demanda por servicio",
                                    S.tabla(demanda["predicciones"], limit=10),
                                    "Volumen esperado de servicios"))

        churn = predictor.predecir_churn()
        resultados = churn.get("resultados")
        if resultados is not None and not resultados.empty:
            piezas.append(S.seccion("Clientes en riesgo",
                                    S.tabla(resultados, limit=10),
                                    "Probabilidad de abandono por cliente"))

        inventario = predictor.predecir_inventario()
        if inventario is not None and not inventario.empty:
            piezas.append(S.seccion("Stock proyectado",
                                    S.tabla(inventario, limit=12),
                                    "Cobertura y reposicion estimada"))

        return "\n".join(piezas) if piezas else ""

    def _sec_recomendaciones(self, ctx):
        from src.recomendaciones import next_best_action
        acciones = next_best_action(self.data, self.cfg, n=20)
        if acciones.empty:
            return ""
        cols = [c for c in ["nombre", "accion", "canal", "mensaje", "prioridad",
                            "prob_churn"] if c in acciones.columns]
        tabla = S.tabla(acciones, columnas=cols, limit=18,
                        titulos={"nombre": "Cliente", "accion": "Accion",
                                 "canal": "Canal", "mensaje": "Mensaje",
                                 "prioridad": "Prioridad",
                                 "prob_churn": "Prob. abandono"},
                        pct_cols={"prob_churn": "percent"})
        return S.seccion("Proximas acciones recomendadas", tabla,
                         "Next best action por cliente")

    def _sec_metodologia(self, ctx):
        return S.seccion(
            "Metodologia",
            f'<ul style="padding-left:18px;font-size:12.5px;color:#475569;'
             f'line-height:1.8;"><li>Datos procesados con pipeline ETL y almacen '
             f'duckDB.</li><li>KPIs, estacionalidad y segmentacion RFM calculados '
             f'sobre los datos de {escape(self.marca["negocio"])}.</li><li>Predicciones '
             f'con modelos de machine learning (sklearn) retenidos por workspace.'
             f'</li><li>Las cifras usan los valores expresados en {escape(self.mon)}.</li>'
             f'</ul>',
            "Como se construyo este reporte")

    # ------------------------------------------------------------------
    #  Ensamble y escritura
    # ------------------------------------------------------------------
    def _documento(self, tipo: str, ocasion_label: str = "") -> tuple:
        ctx = self._contexto(tipo)
        meta = self._meta(tipo, ocasion_label)
        portada = self._portada(meta)
        contenido = self._contenido(tipo, ctx)
        pie = (f'<div class="pie"><b>{escape(self.marca["consultora"])}</b> · '
               f'{escape(self.marca["pie"])}</div>')
        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(meta["titulo"])} · {escape(self.marca["negocio"])}</title>
{css_reporte(self.marca["color_primario"], self.marca["color_secundario"], self.marca["color_acento"])}
</head>
<body>
<div class="documento">
    {portada}
    {contenido}
    {pie}
</div>
</body>
</html>"""
        return html, ctx

    def _contexto(self, tipo: str) -> dict:
        """Calcula solo lo que necesita cada tipo de reporte."""
        from src.analyzer import Analyzer
        from src.predictions import Predictor

        analyzer = Analyzer(self.data)
        predictor = Predictor(self.data, cfg=self.cfg)
        kpis = analyzer.kpis_globales()
        inventario_data = analyzer.inventario_data() if "inventario" in self.data else None
        criticos = int((inventario_data["estado_stock"] == "Bajo").sum()) \
            if inventario_data is not None and "estado_stock" in inventario_data else 0
        insights = generar_insights(analyzer, kpis, moneda=self.mon,
                                    inventario_critico=criticos)
        return {"cfg": self.cfg, "data": self.data, "analyzer": analyzer,
                "predictor": predictor, "kpis": kpis, "insights": insights}

    def generar(self, tipo: str = "resumen", ocasion_label: str = "",
                base_filename: Optional[str] = None,
                escribir: bool = True) -> tuple:
        """Genera un reporte del tipo indicado y devuelve (ruta, metadatos)."""
        if tipo not in catalogo.TIPOS:
            raise ValueError(
                f"Tipo de reporte desconocido: {tipo}. Usa {catalogo.tipos_hint()}.")
        html, ctx = self._documento(tipo, ocasion_label)

        if not escribir:
            return "", {"tipo": tipo, "html": html}

        dir_tipo = self.output_dir / tipo
        dir_tipo.mkdir(parents=True, exist_ok=True)
        fecha = datetime.now()
        nombre = base_filename or f"reporte-{tipo}-{fecha.strftime('%Y%m%d-%H%M%S')}.html"
        ruta = dir_tipo / nombre
        ruta.write_text(html, encoding="utf-8")

        meta = {"tipo": tipo, "archivo": str(ruta), "ruta_html": str(ruta),
                "titulo": catalogo.TIPOS[tipo]["titulo"],
                "num_insights": len(ctx["insights"]),
                "kpis": ctx["kpis"], "fecha": fecha}
        return str(ruta), meta

    def generar_todos(self, tipos: Optional[List[str]] = None,
                      ocasion_label: str = "") -> List[dict]:
        """Genera todos los tipos habilitados (o los indicados) en lote."""
        tipos = [t for t in (tipos or tipos_habilitados(self.cfg)) if t in catalogo.TIPOS]
        resultados = []
        for tipo in tipos:
            ruta, meta = self.generar(tipo, ocasion_label=ocasion_label)
            resultados.append(meta)
        return resultados

    # ------------------------------------------------------------------
    #  Extras: PDF opcional y envio por email
    # ------------------------------------------------------------------
    def a_pdf(self, ruta_html: str) -> Optional[str]:
        """Convierte el HTML a PDF si weasyprint esta instalado (opcional)."""
        try:
            from weasyprint import HTML
            ruta_pdf = str(Path(ruta_html).with_suffix(".pdf"))
            HTML(ruta_html).write_pdf(ruta_pdf)
            return ruta_pdf
        except Exception:  # noqa: BLE001
            return None

    def enviar_email(self, asunto: str, cuerpo_html: str) -> bool:
        """Envia el reporte por SMTP si el workspace lo tiene configurado."""
        try:
            from src.alerts import enviar_email
            return enviar_email(self.cfg, asunto, cuerpo_html)
        except Exception:  # noqa: BLE001
            return False


def listar_generados(cfg, base_dir: Optional[Path] = None) -> List[dict]:
    """Lista los reportes ya generados de un workspace (por tipo)."""
    raiz = Path(base_dir) if base_dir else _base_reports()
    carpeta = raiz / (cfg.clave or "principal")
    resultados = []
    if not carpeta.exists():
        return resultados
    for dir_tipo in sorted(carpeta.iterdir()):
        if not dir_tipo.is_dir():
            continue
        archivos = sorted(dir_tipo.glob("reporte-*.html"), reverse=True)
        for archivo in archivos:
            resultados.append({
                "tipo": dir_tipo.name,
                "archivo": str(archivo),
                "nombre": archivo.name,
                "fecha": archivo.stat().st_mtime,
            })
    return resultados