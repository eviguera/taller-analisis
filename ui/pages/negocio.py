"""Pagina: Negocio (panorama para inversionistas).

Cuantifica en la moneda del workspace el valor que GIRO genera sobre los
datos reales (retention de cartera, ARPU, churn, valor recuperable y ROI de
la suscripcion) y la unidad economica de la plataforma (COGS por tenant,
margen bruto, MRR y break-even).
"""

import pandas as pd
import streamlit as st

from src.negocio import (escenarios_proyeccion, planes_activos,
                         roi_suscripcion, salud_cartera, serie_mensual,
                         tasa_recuperacion_riesgo, unidad_economica,
                         valor_recuperable)

from ui import components as c
from ui.context import obtener_estado


def principal():
    cfg, data, analyzer, predictor = obtener_estado()

    c.cabecera(
        "Panorama de negocio",
        "Valor que GIRO genera sobre tus datos y unidad económica de la plataforma",
        icono=":material/trending_up:",
    )

    salud = salud_cartera(analyzer)
    if not salud:
        c.vacio("Aún no hay facturas suficientes para calcular las métricas de negocio.",
                icono=":material/trending_up:",
                detalle="Importa tus facturas en 'Mis datos' y procesa el ETL para habilitar este panel.")
        return

    # ------------------------------------------------------------------
    #  KPIs de cartera (sobre los datos reales del workspace)
    # ------------------------------------------------------------------
    serie = serie_mensual(analyzer)
    tend = lambda k: serie.get(k) or None
    st.header("1 · Salud de la cartera (datos reales)",
              icon=":material/account_balance_wallet:")
    st.caption("Retención, ARPU y cartera en riesgo del negocio")
    c.kpi_grid([
        ("Clientes activos (12m)", c.miles(salud["clientes_activos"]), None,
         tend("clientes"), "Clientes distintos en los últimos 12 meses"),
        ("Ingresos 12m", c.moneda(salud["ingresos_12m"], cfg.moneda), None,
         tend("ingresos"), "Facturación de los últimos 12 meses"),
        ("ARPU mensual", c.moneda(salud["arpu_mensual"], cfg.moneda), None,
         tend("arpu"), "Ingreso promedio por cliente activo al mes"),
        ("LTV bruto", c.moneda(salud["ltv_gross"], cfg.moneda), None,
         None, "Valor de por vida estimado de un cliente sin GIRO (1 ÷ churn mensual)"),
        ("Churn mensual", f"{salud['churn_mensual']*100:.0f}%/mes", None, None,
         "Pérdida de clientes implícita en la serie"),
        ("Retención mensual", f"{salud['retencion_mensual']*100:.0f}%", None,
         None, "Clientes que se mantienen mes a mes"),
    ])
    st.space("medium")

    # ------------------------------------------------------------------
    #  Cartera en riesgo y valor recuperable
    # ------------------------------------------------------------------
    col1, col2 = st.columns(2, vertical_alignment="center")
    with col1:
        with c.panel("Cartera en riesgo",
                     "Clientes en los segmentos En riesgo y Perdido (análisis RFM)",
                     icono=":material/warning:", alto="stretch"):
            st.metric("Clientes en riesgo", c.miles(salud["clientes_en_riesgo"]))
            st.metric("Cartera en riesgo",
                      c.moneda(salud["monto_en_riesgo"], cfg.moneda))
            st.metric("Peso sobre la cartera",
                      f"{salud['pct_cartera_en_riesgo']*100:.0f}%")
    with col2:
        with c.panel("Valor que GIRO puede recuperar",
                     f"Recupera el {tasa_recuperacion_riesgo(cfg)*100:.0f}% de la cartera "
                     "en riesgo con Giro Recomienda",
                     icono=":material/volunteer_activism:", alto="stretch"):
            recup = valor_recuperable(analyzer, cfg)
            st.metric("Valor recuperable",
                      c.moneda(recup, cfg.moneda),
                      delta=f"{tasa_recuperacion_riesgo(cfg)*100:.0f}% de la cartera en riesgo")
            st.caption("Ejecutar las acciones de reactivación y recordatorio "
                       "es lo que reduce la pérdida de clientes.")
    st.space("medium")

    # ------------------------------------------------------------------
    #  ROI de la suscripcion
    # ------------------------------------------------------------------
    st.header("2 · ROI de la suscripción", icon=":material/donut_large:")
    st.caption("Lo que GIRO protege o recupera frente al costo del plan")
    eventos = escenarios_proyeccion(analyzer, cfg)
    roi = roi_suscripcion(analyzer, cfg)
    if eventos and roi:
        col1, col2 = st.columns(2, vertical_alignment="center")
        with col1:
            with c.panel("12 meses: no hacer nada vs ejecutar GIRO",
                         "Simulador sobre datos reales (Conservador frente a Agresivo "
                         "con Giro Recomienda)",
                         icono=":material/science:", alto="stretch"):
                c.kpi_grid([
                    ("Ingresos sin GIRO", c.moneda(eventos["conservador"]["ingresos"], cfg.moneda),
                     None, None, "Escenario conservador con el churn histórico"),
                    ("Ingresos con GIRO", c.moneda(eventos["agresivo"]["ingresos"], cfg.moneda),
                     f"+{100*eventos['delta_ingresos']/max(eventos['conservador']['ingresos'],1):.0f}%",
                     None, "Escenario agresivo ejecutando las acciones de Giro Recomienda"),
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
        c.vacio("No hay datos suficientes para calcular los escenarios.",
                icono=":material/science:",
                detalle="Importa tus facturas en 'Mis datos' y procesa el ETL.")

    # ------------------------------------------------------------------
    #  Unidad economica de la plataforma (para inversionistas)
    # ------------------------------------------------------------------
    st.space("medium")
    st.header("3 · Unidad económica de GIRO (plataforma)",
              icon=":material/account_balance:")
    st.caption("Costo de servicio (COGS) por workspace, margen bruto, "
               "ingreso recurrente (MRR) y punto de equilibrio")
    ue = unidad_economica(cfg)
    c.kpi_grid([
        ("COGS por workspace", c.moneda(ue["costo_tenant"], cfg.moneda), None, None,
         "Infraestructura por empresa al mes (DuckDB + parquet + código abierto)."),
        ("Margen bruto", f"{ue['margen_bruto']*100:.0f}%", None, None,
         "Precio ponderado menos COGS, sobre el precio."),
        ("Punto de equilibrio", f"~{c.miles(ue['breakeven_clientes'])} clientes Pro",
         None, None,
         "Clientes Pro necesarios para cubrir el gasto fijo mensual."),
    ])

    st.subheader("Ingreso recurrente mensual (MRR) por tamaño de cartera")
    st.caption("Composición del mix: Core 40% / Pro 60%")
    tabla = ue["tabla"].copy()
    for col in ("MRR bruto", "COGS (infra)", "Gasto fijo", "MRR neto"):
        tabla[col] = tabla[col].map(lambda v: c.moneda(v, cfg.moneda))
    tabla["Margen bruto"] = tabla["Margen bruto"].map(lambda v: f"{v*100:.0f}%")
    st.dataframe(tabla, width="stretch", height=220, column_config={
        "Clientes": st.column_config.NumberColumn("Clientes"),
    })
    st.caption(f":material/tune: Parámetros editables en el config `suscripcion:` "
               f"(planes, costo_tenant, gasto_fijo, tasa_recuperacion_riesgo).")

    # Detalle de planes configurados
    planes = planes_activos(cfg)
    st.subheader(f"Planes vigentes ({cfg.moneda}/mes)")
    c.kpi_grid([
        (nombre, c.moneda(precio, cfg.moneda), None, None, "Precio mensual del plan")
        for nombre, precio in planes.items()
    ])


if __name__ == "__main__":
    principal()