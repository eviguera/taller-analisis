"""Metricas de negocio de GIRO: valor por cliente y unidad economica.

Calcula, sobre los datos reales de un workspace, lo que GIRO significa para
su cliente (retencion de cartera, ARPU, cartera en riesgo y valor recuperable)
y lo que significa para el inversionista (unidad economica: costo por tenant,
margen bruto, MRR por escenario y retorno de la suscripcion).

Los numeros de la plataforma (precio de planes, costo por tenant) viven en
``config/config.yaml`` bajo ``suscripcion:``; si no estan configurados se usan
los defaults del pitch.
"""

from __future__ import annotations

import pandas as pd

from .simulador import aplicar_preset, base_datos, proyectar

# Defaults de la plataforma para el pitch/landing (CLP por mes, por tenant).
PLANES_DEFAULT = {"Core": 150_000, "Pro": 450_000, "Enterprise": None}
# Mix de cartera asumido para el MRR de plataforma (40% Core / 60% Pro).
MIX_PLANES = {"Core": 0.40, "Pro": 0.60}
# Gasto fijo mensual estimado de operacion de la plataforma (2 ingenieros
# plataforma + 1 comercial + herramientas), para calcular el break-even.
GASTO_FIJO_MENSUAL_DEFAULT = 7_000_000
# COGS por tenant: DuckDB + parquet + open source (~USD 3/mes).
COSTO_TENANT_MENSUAL_DEFAULT = 3_000


def _suscripcion(cfg) -> dict:
    return dict(getattr(cfg, "suscripcion", None) or {})


def planes_activos(cfg) -> dict:
    """Precios mensuales por plan (CLP)."""
    planes = dict(_suscripcion(cfg).get("planes", {}) or {})
    if not planes:
        planes = dict(PLANES_DEFAULT)
    for clave in list(planes):
        if planes[clave] is None:
            planes.pop(clave)
    return planes


def costo_tenant_mensual(cfg) -> float:
    return float(_suscripcion(cfg).get("costo_tenant_mensual", COSTO_TENANT_MENSUAL_DEFAULT))


def tasa_recuperacion_riesgo(cfg) -> float:
    """Fraccion de la cartera en riesgo que Giro Recomienda ayuda a recuperar."""
    return float(_suscripcion(cfg).get("tasa_recuperacion_riesgo", 0.30))


def gasto_fijo_plataforma(cfg) -> float:
    return float(_suscripcion(cfg).get("gasto_fijo_mensual", GASTO_FIJO_MENSUAL_DEFAULT))


def _base(analyzer) -> dict:
    return base_datos(analyzer.df) or {}


def salud_cartera(analyzer) -> dict:
    """KPIs de salud de la cartera: ARPU, churn implicito y cartera en riesgo."""
    base = _base(analyzer)
    if not base:
        return {}

    rfm = analyzer.clientes_rfm() if not analyzer.df.empty else pd.DataFrame()
    segmentos_riesgo = {"En Riesgo", "Perdido"}
    monto_riesgo = 0.0
    n_riesgo = 0
    monto_total_rfm = 0.0
    if not rfm.empty and "segmento" in rfm.columns:
        riesgo = rfm[rfm["segmento"].isin(segmentos_riesgo)]
        monto_riesgo = float(riesgo["monto"].sum())
        n_riesgo = int(riesgo["cliente_id"].nunique())
        monto_total_rfm = float(rfm["monto"].sum())

    clientes = max(int(base.get("clientes_activos", 0)), 1)
    ingresos_12m = float(base.get("ingresos_12m", 0.0))
    churn = float(base.get("churn_mensual_historico", 0.0))
    arpu_mensual = ingresos_12m / 12.0 / clientes
    ltv_gross = (arpu_mensual / churn) if churn > 0 else 0.0

    return {
        "clientes_activos": int(base.get("clientes_activos", 0)),
        "ingresos_12m": ingresos_12m,
        "arpu_mensual": arpu_mensual,
        "arpu_anual": arpu_mensual * 12.0,
        "churn_mensual": churn,
        "retencion_mensual": max(0.0, 1.0 - churn),
        "ltv_gross": ltv_gross,
        "valor_total_cartera": monto_total_rfm or ingresos_12m,
        "monto_en_riesgo": monto_riesgo,
        "clientes_en_riesgo": n_riesgo,
        "pct_cartera_en_riesgo": (monto_riesgo / monto_total_rfm) if monto_total_rfm > 0 else 0.0,
    }


def serie_mensual(analyzer) -> dict:
    """Series mensuales (ultimos 12 meses) para sparklines de la cartera.

    Devuelve listas alineadas por mes de ingresos, clientes activos y ARPU,
    listas para alimentar el mini-grafico de cada KPI.
    """
    d = getattr(analyzer, "df", None)
    if d is None or d.empty or "fecha" not in d.columns or "total" not in d.columns:
        return {}
    d = d[d["estado"] != "Cancelada"] if "estado" in d.columns else d
    d = d.copy()
    d["fecha"] = pd.to_datetime(d["fecha"], errors="coerce")
    d = d.dropna(subset=["fecha"])
    if d.empty:
        return {}
    fecha_max = d["fecha"].max()
    hist = d[d["fecha"] > fecha_max - pd.DateOffset(months=12)]
    if hist.empty:
        hist = d

    mes = hist["fecha"].dt.to_period("M").astype(str)
    ingresos = hist.groupby(mes)["total"].sum()
    if "cliente_id" in hist:
        clientes = hist.groupby(mes)["cliente_id"].nunique()
    else:
        clientes = hist.groupby(mes).size()
    g = pd.concat([ingresos, clientes], axis=1).sort_index()

    arpu = [
        round(float(ing) / float(cli), 2) if cli else 0.0
        for ing, cli in zip(g.iloc[:, 0], g.iloc[:, 1])
    ]
    return {
        "meses": g.index.tolist(),
        "ingresos": [round(float(v), 2) for v in g.iloc[:, 0]],
        "clientes": [int(v) for v in g.iloc[:, 1]],
        "arpu": arpu,
    }


def valor_recuperable(analyzer, cfg) -> float:
    """Monto anual que GIRO puede ayudar a retener/recuperar (CLP)."""
    salud = salud_cartera(analyzer)
    if not salud:
        return 0.0
    return salud["monto_en_riesgo"] * tasa_recuperacion_riesgo(cfg)


def escenarios_proyeccion(analyzer, cfg) -> dict:
    """Delta 12m entre no hacer nada (Conservador) y ejecutar Giro Recomienda.

    Compara el escenario Conservador (churn historico, sin NBA) con el
    Agresivo (+ Giro Recomienda) usando el simulador sobre los datos reales.
    """
    if analyzer.df.empty:
        return {}
    base = _base(analyzer)
    if not base:
        return {}
    from .simulador import ratios_estacionales
    ratios = ratios_estacionales(analyzer.df)
    sim = cfg.simulador or {}
    margen = float(sim.get("margen_bruto", 0.42))

    def _proyectar(nombre_preset):
        p = aplicar_preset(base["churn_mensual_historico"], nombre_preset)
        return proyectar(
            analyzer.df, meses=12,
            crecimiento_anual=p["crecimiento_anual"],
            ticket_crecimiento=p["ticket_crecimiento"],
            churn_mensual=p["churn_mensual"],
            efecto_giro_nba=p["efecto_giro_nba"],
            margen_bruto=margen,
            ratios=ratios,
        )

    conservador = _proyectar("Conservador")
    agresivo = _proyectar("Agresivo (+ Giro Recomienda)")
    if not conservador or not agresivo:
        return {}

    t_con = conservador["totales"]
    t_agr = agresivo["totales"]
    delta_ingresos = float(t_agr["ingresos"] - t_con["ingresos"])
    delta_ebitda = float(t_agr["ebitda"] - t_con["ebitda"])

    return {
        "conservador": t_con,
        "agresivo": t_agr,
        "delta_ingresos": delta_ingresos,
        "delta_ebitda": delta_ebitda,
        "serie_conservador": conservador["proyeccion"],
        "serie_agresivo": agresivo["proyeccion"],
    }


def roi_suscripcion(analyzer, cfg) -> list:
    """ROI de la suscripcion frente al valor recuperable y al delta 12m.

    Devuelve una lista de dicts, uno por plan con precio fijo, comparando el
    valor que GIRO genera (recuperacion de cartera + delta de ingresos) con el
    costo anual de la suscripcion.
    """
    eventos = escenarios_proyeccion(analyzer, cfg) or {}
    delta_ingresos = float(eventos.get("delta_ingresos", 0.0))
    recuperable = valor_recuperable(analyzer, cfg)
    valor_total = delta_ingresos + recuperable
    filas = []
    for nombre, precio_mensual in planes_activos(cfg).items():
        costo_anual = float(precio_mensual) * 12.0
        filas.append({
            "plan": nombre,
            "precio_mensual": float(precio_mensual),
            "costo_anual": costo_anual,
            "valor_recuperable": recuperable,
            "delta_ingresos": delta_ingresos,
            "valor_total": valor_total,
            "roi": (valor_total / costo_anual) if costo_anual > 0 else 0.0,
        })
    return filas


def unidad_economica(cfg, escenarios=(5, 10, 25, 50, 100)) -> dict:
    """MRR, margen bruto y break-even de la plataforma por tamano de cartera.

    Escenarios de clientes (workspaces pagos) con un mix Core/Pro; se calcula
    MRR bruto, costos de infraestructura (COGS) y MRR neto. La fila break-even
    marca cuantos clientes Pro se necesitan para cubrir el gasto fijo mensual.

    Devuelve un dict con los supuestos (``precio_ponderado``, ``costo_tenant``,
    ``gasto_fijo``, ``margen_bruto``, ``breakeven_clientes``) y la tabla de
    escenarios en ``tabla``.
    """
    planes = planes_activos(cfg)
    precio_ponderado = sum(
        planes.get(nombre, 0) * peso for nombre, peso in MIX_PLANES.items())
    costo = costo_tenant_mensual(cfg)
    gasto_fijo = gasto_fijo_plataforma(cfg)
    margen_bruto = (precio_ponderado - costo) / precio_ponderado if precio_ponderado else 0.0
    breakeven = int(gasto_fijo / precio_ponderado) + 1 if precio_ponderado else None

    filas = []
    for n in escenarios:
        mrr = precio_ponderado * n
        costo_total = costo * n
        filas.append({
            "Clientes": n,
            "MRR bruto": mrr,
            "COGS (infra)": costo_total,
            "Margen bruto": margen_bruto,
            "Gasto fijo": gasto_fijo,
            "MRR neto": mrr - costo_total - gasto_fijo,
        })
    df = pd.DataFrame(filas)
    return {
        "precio_ponderado": precio_ponderado,
        "costo_tenant": costo,
        "gasto_fijo": gasto_fijo,
        "margen_bruto": margen_bruto,
        "breakeven_clientes": breakeven,
        "tabla": df,
    }