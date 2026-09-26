"""Pagina: Negocio (panorama para inversionistas).

Cuantifica en CLP el valor que GIRO genera sobre los datos reales del
workspace (retention de cartera, ARPU, churn, valor recuperable y ROI de la
suscripcion) y la unidad economica de la plataforma (COGS por tenant, margen
bruto, MRR y break-even).
"""

import pandas as pd
import streamlit as st

from src.negocio import (escenarios_proyeccion, planes_activos,
                         roi_suscripcion, salud_cartera, serie_mensual,
                         unidad_economica, valor_recuperable)

from ui import components as c
from ui.context import obtener_estado


def principal():
    cfg, data, analyzer, predictor = obtener_estado()

    c.cabecera(
        "Panorama de negocio",
        "Valor que GIRO genera sobre tus datos + unidad economica de la plataforma",
        icono=":material/trending_up:",
    )

    salud = salud_cartera(analyzer)
    if not salud:
        c.vacio("Sin facturas suficientes para calcular metricas de negocio.",
                icono=":material/trending_up:",
                detalle="Importa tus facturas y procesa el ETL para habilitar este panel.")
        return

    # ------------------------------------------------------------------
    #  KPIs de cartera (sobre los datos reales del workspace)
    # ------------------------------------------------------------------
    serie = serie_mensual(analyzer)
    tend = lambda k: serie.get(k) or None
    c.titulo_seccion("1 · Salud de la cartera (datos reales)",
                     "Retencion, ARPU y cartera en riesgo del negocio",
                     icono=":material/account_balance_wallet:")
    c.kpi_grid([
        ("Clientes activos (12m)", c.miles(salud["clientes_activos"]), None,
         tend("clientes"), "Clientes distintos en los ultimos 12 meses"),
        ("Ingresos 12m", c.moneda(salud["ingresos_12m"], cfg.moneda), None,
         tend("ingresos"), "Facturacion de los ultimos 12 meses"),
        ("ARPU mensual", c.moneda(salud["arpu_mensual"], cfg.moneda), None,
         tend("arpu"), "Ingreso promedio por cliente activo al mes"),
        ("LTV bruto (1/churn)", c.moneda(salud["ltv_gross"], cfg.moneda), None,
         None, "Valor de por vida estimado de un cliente sin GIRO"),
        ("Churn mensual", f"{salud['churn_mensual']*100:.0f}%/mes", None, None,
         "Perdida de clientes implicita en la serie"),
        ("Retencion mensual", f"{salud['retencion_mensual']*100:.0f}%", None,
         None, "Clientes que se mantienen mes a mes"),
    ])
    st.space("medium")

    # ------------------------------------------------------------------
    #  Cartera en riesgo y valor recuperable
    # ------------------------------------------------------------------
    col1, col2 = st.columns(2, vertical_alignment="center")
    with col1:
        with c.panel("Cartera en riesgo",
                     "Clientes en segmentos En Riesgo / Perdido (RFM)",
                     icono=":material/warning:", alto="stretch"):
            st.metric("Clientes en riesgo", c.miles(salud["clientes_en_riesgo"]))
            st.metric("Cartera en riesgo",
                      c.moneda(salud["monto_en_riesgo"], cfg.moneda))
            st.metric("Peso sobre la cartera",
                      f"{salud['pct_cartera_en_riesgo']*100:.0f}%")
    with col2:
        with c.panel("Valor que GIRO puede recuperar",
                     f"Recupera el {tasa_recuperacion(cfg)*100:.0f}% de la cartera "
                     "en riesgo con Giro Recomienda (NBA)",
                     icono=":material/volunteer_activism:", alto="stretch"):
            recup = valor_recuperable(analyzer, cfg)
            st.metric("Valor recuperable",
                      c.moneda(recup, cfg.moneda),
                      delta=f"{tasa_recuperacion(cfg)*100:.0f}% de la cartera en riesgo")
            st.caption("Ejecutar las next-best-actions de reactivacion y "
                       "recordatorio es lo que reduce el churn.")
    st.space("medium")

    # ------------------------------------------------------------------
    #  ROI de la suscripcion
    # ------------------------------------------------------------------
    c.titulo_seccion("2 · ROI de la suscripcion",
                     "Lo que GIRO protege/recupera vs lo que cuesta el plan",
                     icono=":material/donut_large:")
    eventos = escenarios_proyeccion(analyzer, cfg)
    roi = roi_suscripcion(analyzer, cfg)
    if eventos and roi:
        col1, col2 = st.columns(2, vertical_alignment="center")
        with col1:
            with c.panel("12 meses: no hacer nada vs ejecutar GIRO",
                         "Simulador sobre datos reales (Conservador vs Agresivo + NBA)",
                         icono=":material/science:", alto="stretch"):
                c.kpi_grid([
                    ("Ingresos sin GIRO", c.moneda(eventos["conservador"]["ingresos"], cfg.moneda),
                     None, None, "Escenario conservador (churn historico)"),
                    ("Ingresos con GIRO", c.moneda(eventos["agresivo"]["ingresos"], cfg.moneda),
                     f"+{100*eventos['delta_ingresos']/max(eventos['conservador']['ingresos'],1):.0f}%",
                     None, "Escenario agresivo ejecutando las NBA"),
                    ("EBITDA extra 12m", c.moneda(eventos["delta_ebitda"], cfg.moneda),
                     None, None, "Diferencia de EBITDA entre ambos escenarios"),
                ])
        with col2:
            with c.panel("ROI por plan (12 meses)",
                         "Valor recuperado + ingresos extra vs costo anual",
                         icono=":material/timeline:", alto="stretch"):
                df_roi = pd.DataFrame(roi)
                df_roi["plan"] = df_roi["plan"].str.upper()
                for col in ("costo_anual", "valor_recuperable", "delta_ingresos", "valor_total"):
                    df_roi[col] = df_roi[col].map(lambda v: c.moneda(v, cfg.moneda))
                st.dataframe(
                    df_roi.rename(columns={
                        "plan": "Plan", "costo_anual": "Costo anual",
                        "valor_recuperable": "Recuperable",
                        "delta_ingresos": "Ingresos extra",
                        "valor_total": "Valor total GIRO", "roi": "ROI",
                    }),
                    width="stretch", column_config={
                        "ROI": st.column_config.NumberColumn("ROI", format="%.1fx"),
                    },
                )
                st.caption("ROI = (valor recuperable + ingresos extra) / costo anual.")
    else:
        st.info("No hay datos suficientes para calcular los escenarios.")

    # ------------------------------------------------------------------
    #  Unidad economica de la plataforma (para inversionistas)
    # ------------------------------------------------------------------
    st.space("medium")
    c.titulo_seccion("3 · Unidad economica de GIRO (plataforma)",
                     "COGS por tenant, margen bruto, MRR y break-even",
                     icono=":material/account_balance:")
    ue = unidad_economica(cfg)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("COGS por tenant", c.moneda(ue["costo_tenant"], cfg.moneda), border=True,
                  help="Infraestructura por empresa/mes (DuckDB + parquet + open source).")
    with col2:
        st.metric("Margen bruto", f"{ue['margen_bruto']*100:.0f}%", border=True,
                  help="Precio ponderado menos COGS, sobre el precio.")
    with col3:
        st.metric("Break-even", f"~{c.miles(ue['breakeven_clientes'])} clientes Pro", border=True,
                  help="Clientes Pro necesarios para cubrir el gasto fijo mensual.")

    st.markdown("**MRR por tamano de cartera (mix Core 40% / Pro 60%)**")
    tabla = ue["tabla"].copy()
    for col in ("MRR bruto", "COGS (infra)", "Gasto fijo", "MRR neto"):
        tabla[col] = tabla[col].map(lambda v: c.moneda(v, cfg.moneda))
    tabla["Margen bruto"] = tabla["Margen bruto"].map(lambda v: f"{v*100:.0f}%")
    st.dataframe(tabla, width="stretch", height=220, column_config={
        "Clientes": st.column_config.NumberColumn("Clientes"),
    })
    st.caption(f":material/tune: Parametros editables en config `suscripcion:` "
               f"(planes, costo_tenant, gasto_fijo, tasa_recuperacion_riesgo).")

    # Detalle de planes configurados
    planes = planes_activos(cfg)
    st.markdown("**Planes vigentes (CLP/mes)**")
    cols = st.columns(len(planes))
    for i, (nombre, precio) in enumerate(planes.items()):
        with cols[i]:
            st.metric(nombre, c.moneda(precio, cfg.moneda), border=True)


def tasa_recuperacion(cfg):
    from src.negocio import tasa_recuperacion_riesgo
    return tasa_recuperacion_riesgo(cfg)


if __name__ == "__main__":
    principal()