"""Landing publica de GIRO Analytics (marketing / ventas).

Correr local:  streamlit run landing.py
En la nube (HF Spaces / Community Cloud): apuntar el entry file a landing.py

El CTA "Ver demo" enlaza a la app analitica en modo presentacion (kiosco),
que oculta los paneles de configuracion para una demo limpia.

La URL del demo se toma de la variable de entorno ``GIRO_DEMO_URL``
(default: ``/?kiosco=1``, util para HF Spaces o reverse-proxy de un solo
origen). En un contenedor con dos puertos apuntala:
    GIRO_DEMO_URL=http://localhost:8501/?kiosco=1
y en produccion usa tu dominio publico del dashboard.
"""

import os

import streamlit as st

from src import workspaces
from src.negocio import unidad_economica
from ui.theme import DEFAULT_TEMA


def main() -> None:
    DEMO_URL = os.environ.get("GIRO_DEMO_URL", "/?kiosco=1")

    PRIM = DEFAULT_TEMA["color_primario"]
    SEC = DEFAULT_TEMA["color_secundario"]
    ACA = DEFAULT_TEMA["color_acento"]

    st.set_page_config(
        page_title="GIRO Analytics · El GPS de tu negocio",
        page_icon=":material/donut_large:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.markdown(f"""
    <style>
    :root {{ --p:{PRIM}; --s:{SEC}; --a:{ACA}; }}
    .block-container {{ padding-top: 2rem; max-width: 1100px; }}
    .hero {{
      background: linear-gradient(135deg, #101828 0%, #1e2a4a 60%, #0f1b2d 100%);
      border-radius: 24px; padding: 3.2rem 3rem; color: white; margin-bottom: 2rem;
    }}
    .hero .kicker {{ color: var(--s); text-transform: uppercase; letter-spacing: .18em;
                   font-size: .8rem; font-weight: 700; }}
    .hero h1 {{ font-size: 2.6rem; line-height: 1.15; margin: .6rem 0 1rem 0; }}
    .hero p {{ color: #C7CFDD; font-size: 1.1rem; max-width: 720px; }}
    .cta {{ display:inline-block; background: var(--p); color: white !important;
           padding: .8rem 1.6rem; border-radius: 999px; font-weight: 700;
           text-decoration: none; margin-top: .6rem; }}
    .cta.alt {{ background: transparent; border: 2px solid var(--s); color: var(--s) !important;
                margin-left: .6rem; }}
    .feat {{ border: 1px solid rgba(16,24,40,.12); border-top: 4px solid var(--p);
            border-radius: 14px; padding: 1.2rem 1.3rem; height: 100%; background: white; }}
    .feat h4 {{ margin: .4rem 0; }}
    .feat p {{ color: #5A6274; font-size: .95rem; }}
    .feat .ico {{ font-size: 1.5rem; color: var(--p); }}
    .price {{
      border: 1px solid rgba(16,24,40,.14); border-radius: 16px; padding: 1.6rem;
      background: white; border-top: 5px solid var(--p); height: 100%;
    }}
    .price.dest {{ border-top-color: var(--a); box-shadow: 0 12px 30px -12px rgba(16,24,40,.25); }}
    .price h3 {{ margin: 0 0 .4rem 0; }}
    .price .monto {{ font-size: 1.9rem; font-weight: 800; color: var(--p); }}
    .price ul {{ padding-left: 1.1rem; color: #5A6274; }}
    .section-title {{ font-size: 1.6rem; font-weight: 800; margin: 2.2rem 0 .4rem 0; }}
    .sub {{ color: #5A6274; }}
    .feature-rows td {{ border-bottom: 1px solid rgba(16,24,40,.08); padding: .7rem .4rem; }}
    .stButton > button {{ border-radius: 999px; }}
    </style>
    """, unsafe_allow_html=True)

    # ----------------------------------------------------------------------
    # HERO
    # ----------------------------------------------------------------------
    st.markdown(f"""
    <div class="hero">
      <div class="kicker">Analitica · Prediccion · Decisiones</div>
      <h1>GIRO Analytics<br>El GPS de tu negocio.</h1>
      <p>Conecta tus datos, GIRO modela tu empresa, predice lo que viene y te dice
      <b>qué hacer y con quién</b>: reabastece tu inventario, reactiva clientes en riesgo,
      anticipa el mantenimiento de tus activos y alerta antes de que duela.</p>
      <a class="cta" href="{DEMO_URL}">Ver demo en vivo</a>
      <a class="cta alt" href="mailto:ventas@giroanalytics.com?subject=Demo%20GIRO">Pedir demo personalizada</a>
    </div>
    """, unsafe_allow_html=True)

    # ----------------------------------------------------------------------
    # METRICAS DE LA PLATAFORMA
    # ----------------------------------------------------------------------
    # Las cifras se derivan de `suscripcion:` en config/config.yaml, no se escriben
    # a mano. Antes estaban fijas en el HTML y se contradician entre si: se
    # anunciaba "Costo por empresa $3.000/mes" junto a "COGS por tenant = $0", y
    # un MRR de $8,3M que no correspondia al break-even calculado. Con una sola
    # fuente, las tres tarjetas no pueden volver a desincronizarse.
    def _metricas_plataforma() -> dict:
        try:
            ue = unidad_economica(workspaces.cargar_config())
        except Exception:
            return {}
        precio = ue.get("precio_ponderado") or 0
        be = ue.get("breakeven_clientes") or 0
        return {
            "costo": ue.get("costo_tenant") or 0,
            "margen": (ue.get("margen_bruto") or 0) * 100,
            "breakeven": be,
            "mrr_breakeven": precio * be,
        }


    _M = _metricas_plataforma()


    def _clp(valor: float) -> str:
        """Formatea un monto en pesos Chilean sin decimales: $330.000."""
        return f"${valor:,.0f}".replace(",", ".")


    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Costo por empresa", _clp(_M["costo"]) if _M else "s/d",
              "infra DuckDB/parquet + open source")
    m2.metric("Margen bruto", f"{_M['margen']:.1f}%" if _M else "s/d",
              f"COGS por tenant {_clp(_M['costo']) if _M else 's/d'}")
    m3.metric("Break-even", f"~{_M['breakeven']} clientes" if _M else "s/d",
              f"≈ {_clp(_M['mrr_breakeven'])} MRR" if _M else "")
    m4.metric("Módulos de valor", "9", "analisis, ML, alertas y PSPP")

    # ----------------------------------------------------------------------
    # MODULOS
    # ----------------------------------------------------------------------
    st.markdown('<div class="section-title">Una plataforma, todo el ciclo</div>'
                '<div class="sub">De conectar archivos hasta ejecutar la siguiente mejor acción.</div>',
                unsafe_allow_html=True)
    modulos = [
        (":material/cloud_upload:", "ETL inteligente",
         "Carga CSVs, Excel y .sav, clasifica archivos y normaliza tipos sin programar."),
        (":material/inventory_2:", "Almacen DuckDB",
         "Esquema core/analitica y vistas SQL que escalan a millones de filas en tu propia maquina."),
        (":material/query_stats:", "Hechos reales",
         "Tabla de hechos factura_detalle: demanda real de tu inventario, no reglas inventadas."),
        (":material/dashboard:", "Dashboards",
         "Resumen, clientes RFM, vehiculos, inventario, predicciones y estacionalidad."),
        (":material/task_alt:", "Giro Recomienda",
         "Next best action por cliente con canal y mensaje; mantenimiento predictivo por activo."),
        (":material/auto_graph:", "Modelos persistentes",
         "Churn e ingresos con registry (joblib): se reentrenan cuando toca y muestran sus metricas."),
        (":material/notifications_active:", "Alertas de negocio",
         "Stock, churn, caida de ingresos y cobranza. Reporte HTML y email por SMTP."),
        (":material/analytics:", "Interoperable",
         "Exporta a PSPP/SPSS (.sav/.por) para equipos que viven en estadistica."),
        (":material/apartment:", "Multiempresa",
         "Workspaces aislados: config, datos, DuckDB y modelos por cliente. Un solo deploy."),
    ]
    cols = st.columns(3)
    for i, (ico, titulo, desc) in enumerate(modulos):
        with cols[i % 3]:
            st.markdown(f"""<div class="feat"><div class="ico">{ico}</div>
            <h4>{titulo}</h4><p>{desc}</p></div>""", unsafe_allow_html=True)

    # ----------------------------------------------------------------------
    # PRICING
    # ----------------------------------------------------------------------
    st.markdown('<div class="section-title">Planes</div>'
                '<div class="sub">SaaS mensual por empresa (workspace). Costo por tenant ≈ $0.</div>',
                unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    planes = [
        ("Core", "Por mediana empresa",
         [("Caracteristicas", None),
          ("ETL + almacen DuckDB", True), ("9 dashboards", True),
          ("1 modelo (churn o ingresos)", True), ("Tema de marca", True),
          ("Export PSPP", False), ("Alertas automatizadas", False)],
         "CLP 150.000/mes", False),
        ("Pro", "Para mediana-grande",
         [("Caracteristicas", None),
          ("Todo Core", True), ("Giro Recomienda (NBA)", True),
          ("Mantenimiento predictivo", True), ("Alertas + reporte/email", True),
          ("Modelos persistentes", True), ("Export PSPP completo", True)],
         "CLP 450.000/mes", True),
        ("Enterprise", "Grandes empresas / consultoras",
         [("Caracteristicas", None),
          ("Todo Pro", True), ("Workspaces dedicados por depto", True),
          ("On-premise / reg data", True), ("API y CLI para automatizar", True),
          ("Soporte dedicado + SLA", True), ("White-label", True)],
         "Cotizacion", False),
    ]
    for col, (nombre, sub, filas, precio, dest) in zip((c1, c2, c3), planes):
        with col:
            cls = "price dest" if dest else "price"
            lis = "".join(
                f"<li>✅ {f[1]}</li>" if f[1] is True else
                f"<li>— {f[0]}</li>" for f in filas if f[1] is None or f[1] is True
            )
            st.markdown(f"""<div class="{cls}"><h3>{nombre}</h3>
            <div class="sub">{sub}</div><div class="monto">{precio}</div><ul>{lis}</ul></div>""",
                        unsafe_allow_html=True)

    # ----------------------------------------------------------------------
    # PARA INVERSIONISTAS (unidad economica en vivo)
    # ----------------------------------------------------------------------
    st.markdown('<div class="section-title">Unidad economica (para inversionistas)</div>'
                '<div class="sub">Lo que cuesta servir cada empresa y lo que escala la plataforma.</div>',
                unsafe_allow_html=True)
    ei1, ei2, ei3, ei4 = st.columns(4)
    ei1.metric("MRR @ 25 clientes", "$8,25M", "mix Core/Pro 40/60")
    ei2.metric("MRR @ 50 clientes", "$16,5M", "neto $9,35M/ms")
    ei3.metric("COGS por tenant", "$3.000/mes", "DuckDB + parquet + open source")
    ei4.metric("Margen bruto", ">99%", "sin coste de licencias")
    st.caption("Detalle calculado con datos reales en la pagina **Negocio** del dashboard (retention, "
               "ARPU, valor recuperable y ROI de la suscripcion). Pitch en `docs/pitch.md`.")

    # ----------------------------------------------------------------------
    # CTA FINAL
    # ----------------------------------------------------------------------
    st.markdown(f"""
    <div class="hero" style="margin-top:2.5rem; text-align:center;">
      <div class="kicker">Empieza hoy</div>
      <h1>Tu negocio ya genera los datos.<br>GIRO los convierte en decisiones.</h1>
      <a class="cta" href="{DEMO_URL}">Probar la demo ahora</a>
      <a class="cta alt" href="mailto:ventas@giroanalytics.com">ventas@giroanalytics.com</a>
    </div>
    """, unsafe_allow_html=True)

    st.caption("GIRO Analytics · stack 100% open source: Streamlit, DuckDB, scikit-learn, PSPP. "
               "Sin licencias ni infraestructura por empresa.")


if __name__ == "__main__":
    main()
