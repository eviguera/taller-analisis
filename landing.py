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
    :root {{ --p:{PRIM}; --s:{SEC}; --a:{ACA};
      --space-1: 4px;  --space-2: 8px;  --space-3: 12px;
      --space-4: 16px; --space-5: 24px; --space-6: 32px;
      --space-7: 48px; --space-8: 64px; --space-9: 96px;
    }}
    .block-container {{ padding-top: var(--space-6); max-width: 1100px; }}
    .skip-link {{ position: absolute; left: -9999px; top: 0; z-index: 60;
      background: #ffffff; color: #101828; font-weight: 700; text-decoration: none;
      padding: var(--space-3) var(--space-5); border-radius: 0 0 10px 0; }}
    .skip-link:focus {{ left: 0; outline: 3px solid var(--a); outline-offset: 2px; }}
    .hero {{
      background: linear-gradient(135deg, #101828 0%, #1e2a4a 60%, #0f1b2d 100%);
      border-radius: 24px; padding: var(--space-7); color: white; margin-bottom: var(--space-6);
    }}
    .hero .kicker {{ color: var(--s); text-transform: uppercase; letter-spacing: .18em;
                   font-size: .8rem; font-weight: 700; }}
    .hero h1, .hero h2 {{ font-size: 2.6rem; line-height: 1.15;
                       margin: var(--space-2) 0 var(--space-4) 0; }}
    .hero p {{ color: #C7CFDD; font-size: 1.1rem; max-width: 720px; }}
    .cta {{ display:inline-flex; align-items:center; box-sizing: border-box; min-height: 44px;
           background: var(--p); color: white !important;
           padding: var(--space-3) var(--space-5); border-radius: 999px; font-weight: 700;
           text-decoration: none; margin-top: var(--space-2); }}
    .cta.alt {{ background: transparent; border: 2px solid var(--s); color: var(--s) !important;
                margin-left: var(--space-2); }}
    .cta:hover {{ transform: translateY(-1px); box-shadow: 0 10px 22px -10px rgba(16,24,40,.55); }}
    .cta:active {{ transform: scale(.98); box-shadow: none; }}
    .cta:focus-visible {{ outline: 3px solid #ffffff; outline-offset: 3px; }}
    .feat {{ border: 1px solid rgba(16,24,40,.12); border-top: 4px solid var(--p);
            border-radius: 14px; padding: var(--space-4) var(--space-5); height: 100%; background: white; }}
    .feat h3 {{ margin: var(--space-2) 0; }}
    .feat p {{ color: #5A6274; font-size: .95rem; }}
    .feat .ico {{ font-size: 1.5rem; color: var(--p); }}
    .price {{
      border: 1px solid rgba(16,24,40,.14); border-radius: 16px; padding: var(--space-5);
      background: white; border-top: 5px solid var(--p); height: 100%;
    }}
    .price.dest {{ border-top-color: var(--a); box-shadow: 0 12px 30px -12px rgba(16,24,40,.25); }}
    .price h3 {{ margin: 0 0 var(--space-2) 0; }}
    .price .monto {{ font-size: 1.9rem; font-weight: 800; color: var(--p); }}
    .price ul {{ padding-left: var(--space-4); color: #5A6274; }}
    .price ul .grupo {{ list-style: none; margin-left: calc(-1 * var(--space-4));
                       margin-bottom: var(--space-1); font-weight: 700; font-size: .8rem;
                       letter-spacing: .06em; text-transform: uppercase; color: #101828; }}
    .section-title {{ font-size: 1.6rem; font-weight: 800; margin: var(--space-6) 0 var(--space-2) 0; }}
    .sub {{ color: #5A6274; }}
    .hero.cierre {{ margin-top: var(--space-7); text-align: center; }}
    .stButton > button {{ border-radius: 999px; }}
    @media (max-width: 680px) {{
      [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; }}
      [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{ flex: 1 1 100%; min-width: 100%; }}
      .hero {{ padding: var(--space-5); }}
      .hero h1, .hero h2 {{ font-size: 1.9rem; }}
    }}
    </style>
    """, unsafe_allow_html=True)

    # ----------------------------------------------------------------------
    # HERO
    # ----------------------------------------------------------------------
    st.markdown('<a class="skip-link" href="#contenido">Saltar al contenido</a>',
                unsafe_allow_html=True)
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
    # MODULOS
    # ----------------------------------------------------------------------
    st.markdown('<h2 class="section-title" id="contenido">Una plataforma, todo el ciclo</h2>'
                '<div class="sub">De conectar archivos hasta ejecutar la siguiente mejor acción.</div>',
                unsafe_allow_html=True)
    modulos = [
        (":material/cloud_upload:", "ETL inteligente",
         "Carga CSVs, Excel y .sav, clasifica archivos y normaliza tipos sin programar."),
        (":material/inventory_2:", "Almacen DuckDB",
         "Vistas SQL sobre millones de filas, en tu propia maquina."),
        (":material/query_stats:", "Hechos reales",
         "Cada venta queda con su detalle: demanda real de tu inventario, no reglas inventadas."),
        (":material/dashboard:", "Dashboards",
         "Resumen, clientes RFM, vehiculos, inventario, predicciones y estacionalidad."),
        (":material/task_alt:", "Giro Recomienda",
         "Siguiente mejor acción por cliente, con canal y mensaje; mantenimiento predictivo por activo."),
        (":material/auto_graph:", "Modelos persistentes",
         "Churn e ingresos: se reentrenan solos cuando toca y muestran sus métricas."),
        (":material/notifications_active:", "Alertas de negocio",
         "Stock, churn, caída de ingresos y cobranza. Reporte HTML y correo automático."),
        (":material/analytics:", "Interoperable",
         "Exporta a PSPP/SPSS (.sav/.por) para equipos que viven en estadistica."),
        (":material/apartment:", "Multiempresa",
         "Cada empresa (workspace) tiene sus datos y modelos aislados. Un solo servidor para todas."),
    ]
    cols = st.columns(3)
    for i, (ico, titulo, desc) in enumerate(modulos):
        with cols[i % 3]:
            st.markdown(f"""<div class="feat"><div class="ico">{ico}</div>
            <h3>{titulo}</h3><p>{desc}</p></div>""", unsafe_allow_html=True)

    # ----------------------------------------------------------------------
    # PRICING
    # ----------------------------------------------------------------------
    st.markdown('<h2 class="section-title">Planes</h2>'
                '<div class="sub">Precio mensual por empresa (workspace). '
                'Cada empresa se contrata por separado.</div>',
                unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    planes = [
        ("Core", "Por mediana empresa",
         [("Características", None),
          ("ETL + almacen DuckDB", True), ("9 dashboards", True),
          ("1 modelo (churn o ingresos)", True), ("Tema de marca", True),
          ("Export PSPP", False), ("Alertas automatizadas", False)],
         "CLP 150.000/mes", False),
        ("Pro", "Para mediana-grande",
         [("Características", None),
          ("Todo Core", True), ("Giro Recomienda (siguiente mejor acción)", True),
          ("Mantenimiento predictivo", True), ("Alertas + reporte/email", True),
          ("Modelos persistentes", True), ("Export PSPP completo", True)],
         "CLP 450.000/mes", True),
        ("Enterprise", "Grandes empresas / consultoras",
         [("Características", None),
          ("Todo Pro", True), ("Workspaces dedicados por depto", True),
          ("On-premise / reg data", True), ("API y CLI para automatizar", True),
          ("Soporte dedicado + SLA", True), ("White-label", True)],
         "Cotizacion", False),
    ]
    for col, (nombre, sub, filas, precio, dest) in zip((c1, c2, c3), planes):
        with col:
            cls = "price dest" if dest else "price"
            lis = "".join(
                f"<li>✅ {f[0]}</li>" if f[1] is True else
                f"<li class='grupo'>{f[0]}</li>" for f in filas if f[1] is None or f[1] is True
            )
            st.markdown(f"""<div class="{cls}"><h3>{nombre}</h3>
            <div class="sub">{sub}</div><div class="monto">{precio}</div><ul>{lis}</ul></div>""",
                        unsafe_allow_html=True)

    # ----------------------------------------------------------------------
    # CTA FINAL
    # ----------------------------------------------------------------------
    st.markdown(f"""
    <div class="hero cierre">
      <div class="kicker">Empieza hoy</div>
      <h2>Tu negocio ya genera los datos.<br>GIRO los convierte en decisiones.</h2>
      <a class="cta" href="{DEMO_URL}">Probar la demo ahora</a>
      <a class="cta alt" href="mailto:ventas@giroanalytics.com">ventas@giroanalytics.com</a>
    </div>
    """, unsafe_allow_html=True)

    st.caption("GIRO Analytics · stack 100% open source: Streamlit, DuckDB, scikit-learn, PSPP. "
               "Sin licencias ni infraestructura por empresa.")


if __name__ == "__main__":
    main()
