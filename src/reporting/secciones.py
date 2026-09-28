"""Renderers HTML de los bloques de un reporte: KPIs, graficos y tablas.

Cada funcion recibe datos ya calculados (analyzer/predictor) y devuelve un
fragmento HTML estilizado con las variables de marca en CSS vars. El motor
las une con la portada y el pie en un documento completo listo para imprimir.

Esta es la capa que produce HTML, asi que escapa todo valor que venga de los
datos del cliente (nombres, productos, segmentos, textos de insight). El
fragmento que ya es HTML y entra por parametro (``cuerpo``) se interpola tal
cual a proposito.
"""

from html import escape

from .formato import (miles, moneda, fig_a_base64, periodo_es,
                      MESES_ES_CORTO, DIAS_SEMANA)

# Tipos de insight admitidos. El valor va dentro de un atributo class, asi que
# se restringe a un conjunto cerrado en vez de confiar en la clave recibida.
_TIPOS_INSIGHT = ("positivo", "negativo", "apunte")


def seccion(titulo, cuerpo, subtitulo=""):
    """Envuelve un bloque con titulo, cuerpo y cabecera de marca.

    ``cuerpo`` es HTML ya construido y se inserta sin escapar.
    """
    stitulo = f'<p class="seccion-sub">{escape(subtitulo)}</p>' if subtitulo else ""
    return f"""
    <section class="seccion">
        <header class="seccion-hd">
            <div>
                <h2>{escape(titulo)}</h2>
                {stitulo}
            </div>
            <div class="seccion-tira"></div>
        </header>
        {cuerpo}
    </section>"""


def kpi_cards(kpis, moneda_cfg="CLP"):
    """Tarjetas de KPI para el bloque resumen."""
    items = [
        ("Ingresos totales", moneda(kpis.get("total_ingresos", 0), moneda_cfg), "Ingresos"),
        ("Facturas emitidas", miles(kpis.get("total_facturas", 0)), "Operacion"),
        ("Ticket promedio", moneda(kpis.get("ticket_promedio", 0), moneda_cfg), "Operacion"),
        ("Clientes activos", miles(kpis.get("clientes_activos", 0)), "Clientes"),
        ("Valor cliente prom.", moneda(kpis.get("valor_cliente_promedio", 0), moneda_cfg), "Clientes"),
        ("Descuentos otorgados", moneda(kpis.get("descuentos_total", 0), moneda_cfg), "Operacion"),
    ]
    cards = ""
    for etiqueta, valor, grupo in items:
        cards += (f'<div class="kpi-card"><span class="kpi-grupo">{escape(grupo)}</span>'
                  f'<span class="kpi-valor">{escape(valor)}</span>'
                  f'<span class="kpi-etiqueta">{escape(etiqueta)}</span></div>')
    return f'<div class="kpi-grid">{cards}</div>'


def insight_lista(insights):
    """Lista de insights estrategicos (positivo / negativo / apunte)."""
    if not insights:
        return '<p class="vacio">No hay observaciones automaticas para los datos actuales.</p>'
    html = ""
    for ins in insights:
        tipo = ins.get("tipo") if isinstance(ins, dict) else None
        if tipo not in _TIPOS_INSIGHT:
            tipo = "apunte"
        icono = {"positivo": "✔", "negativo": "!", "apunte": "i"}[tipo]
        html += (f'<div class="insight insight-{tipo}">'
                 f'<div class="insight-icono">{icono}</div>'
                 f'<div><strong>{escape(str(ins.get("titulo", "")))}</strong>'
                 f'<p>{escape(str(ins.get("texto", "")))}</p></div></div>')
    return html


def grafico_ingresos(analyzer, color):
    """Series de ingresos mensuales (linea + acumulado)."""
    serie = analyzer.ingresos_por_mes()
    if serie.empty:
        return ""
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=110)
    etiquetas = [periodo_es(x) for x in serie["anio_mes"]]
    barras = ax.bar(range(len(serie)), serie["total"], color=color, alpha=0.85, label="Ingresos")
    for i, v in enumerate(serie["total"]):
        if i == len(serie) - 1 or i == 0:
            ax.annotate(miles(v), (i, v), textcoords="offset points",
                        xytext=(0, 5), ha="center", fontsize=8, color="#475569")
    ax_twin = ax.twinx()
    ax_twin.plot(range(len(serie)), serie["acumulado"], color="#0F172A",
                 linewidth=2, marker="o", markersize=3, label="Acumulado")
    ax_twin.set_ylabel("Acumulado")
    ax.set_xticks(range(len(serie)))
    ax.set_xticklabels(etiquetas, rotation=40, ha="right", fontsize=8)
    ax.set_ylabel("Ingresos")
    ax.grid(alpha=0.25, axis="y")
    ax.spines["top"].set_visible(False)
    ax_twin.spines["top"].set_visible(False)
    fig.tight_layout()
    return fig_a_base64(fig)


def grafico_estacionalidad(analyzer, color):
    """Barras de ingresos por mes del anio y por dia de la semana."""
    est = analyzer.estacionalidad()
    por_mes = est["por_mes"]
    por_dia = est["por_dia_semana"]
    if por_mes.empty:
        return ""
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), dpi=110)
    axes[0].bar(MESES_ES_CORTO, por_mes["ingresos"], color=color, alpha=0.9)
    axes[0].set_title("Ingresos por mes del anio", fontsize=10)
    axes[0].grid(alpha=0.25, axis="y")
    axes[0].tick_params(labelsize=8)
    ejes = [DIAS_SEMANA.get(str(d), str(d)) for d in por_dia["dia_semana"]]
    axes[1].bar(ejes, por_dia["ingresos"], color="#0F172A", alpha=0.85)
    axes[1].set_title("Ingresos por dia de la semana", fontsize=10)
    axes[1].grid(alpha=0.25, axis="y")
    axes[1].tick_params(labelsize=8)
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig_a_base64(fig)


def tabla(df, columnas=None, titulos=None, limit=12, moneda_cols=None,
          pct_cols=None, resaltar=None):
    """Tabla HTML con formateo es-CL, sin valores index.
    
    `moneda_cols` / `pct_cols`: diccionarios columna -> (valor, moneda) o
    columna -> forma; `resaltar`: dict columna -> lista de celdas a marcar.
    """
    if df is None or df.empty:
        return '<p class="vacio">Sin datos suficientes para esta seccion.</p>'

    columnas = [_c for _c in (columnas or list(df.columns)) if _c in df.columns]
    if not columnas:
        return '<p class="vacio">Sin columnas disponibles.</p>'
    df = df[columnas].head(limit)
    titulos = titulos or {c: c for c in columnas}
    resaltar = resaltar or {}

    # Construir celdas vectorizadas por columna
    cell_data = {}
    for col in columnas:
        serie = df[col]
        if moneda_cols and col in moneda_cols:
            texto = serie.apply(lambda v: moneda(v, moneda_cols[col] or "CLP") if isinstance(v, (int, float)) else str(v))
        elif pct_cols and col in pct_cols:
            texto = serie.apply(lambda v: f"{float(v) * 100:.0f}%" if isinstance(v, (int, float)) else str(v))
        else:
            texto = serie.apply(lambda v: miles(v) if isinstance(v, (int, float)) else str(v))
        # El texto de la celda viene de los datos del cliente (nombres,
        # productos, servicios): va escapado siempre.
        texto = texto.apply(escape)
        if col in resaltar:
            mask = serie.isin(resaltar[col])
            td_parts = [f"<td class='{'cell-alta' if m else ''}'>{val}</td>" for val, m in zip(texto, mask)]
            cell_data[col] = td_parts
        else:
            cell_data[col] = [f"<td>{v}</td>" for v in texto]

    # Combinar en filas HTML
    filas = ""
    for i in range(len(df)):
        celdas = "".join(cell_data[col][i] for col in columnas)
        filas += f"<tr>{celdas}</tr>"

    cab = "".join(f"<th>{escape(str(titulos.get(c, c)))}</th>" for c in columnas)
    return (f'<div class="tabla-scroll"><table class="tabla">'
            f"<thead><tr>{cab}</tr></thead><tbody>{filas}</tbody></table></div>")


def badges_segmentos(rfm):
    """Resumen de segmentos RFM como badges contables."""
    if rfm is None or rfm.empty:
        return ""
    conteo = rfm["segmento"].value_counts()
    clases = {"Campeones": "seg-campeon", "Alto Valor": "seg-alto",
              "Cliente Leal": "seg-leal", "Activo": "seg-activo",
              "Promedio": "seg-promedio", "En Riesgo": "seg-riesgo",
              "Perdido": "seg-perdido"}
    piezas = ""
    for segmento, n in conteo.items():
        # "clases.get(...)" ya cae en un valor conocido si el segmento es
        # inesperado, asi que la clase es segura; el nombre del segmento no.
        piezas += (f'<div class="seg-badge {clases.get(segmento, "seg-promedio")}">'
                   f'<strong>{int(n)}</strong>'
                   f'<span>{escape(str(segmento))}</span></div>')
    return f'<div class="seg-badges">{piezas}</div>'


def notas_tabla(columnas, moneda_cfg="CLP"):
    """Leyenda pequena de unidades para pie de tablas numericas."""
    return (f'<p class="nota">Valores en {escape(str(moneda_cfg))}. '
            "Cifras generadas con ETL y almacen DuckDB.</p>")