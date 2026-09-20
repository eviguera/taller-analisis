"""Estilos CSS de los reportes: documento A4 imprimible a PDF desde el navegador.

Se inyectan variables de marca (colores del cliente/reventor) para que cada
workspace imprima su identidad. Diseñado para ``@media print`` (margenes A4)
y para vista en pantalla.
"""

css_reporte = """<style>
:root {{
    --p: {primario};
    --p-soft: color-mix(in srgb, {primario} 8%, white);
    --s: {secundario};
    --a: {acento};
    --ink: #0F172A;
    --muted: #64748B;
    --line: #E2E8F0;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ background: #EEF2F7; }}
body {{
    font-family: 'Helvetica Neue', 'Segoe UI', Arial, sans-serif;
    color: var(--ink); line-height: 1.5; font-size: 14px;
}}
.documento {{ max-width: 860px; margin: 0 auto; padding: 24px; }}
.sector-tope {{ color: var(--muted); font-size: 11px; letter-spacing: .18em;
    text-transform: uppercase; font-weight: 700; }}

/* ---------- portada ---------- */
.portada {{ background: var(--p-soft); border: 1px solid var(--line);
    border-radius: 18px; padding: 40px 36px; margin-bottom: 28px; }}
.portada .logo {{ max-height: 64px; max-width: 220px; margin-bottom: 18px; }}
.portada h1 {{ font-size: 30px; color: var(--ink); line-height: 1.15; }}
.portada .ocasion {{
    display: inline-block; background: var(--p); color: #fff; font-weight: 700;
    padding: 6px 14px; border-radius: 999px; font-size: 12px; margin-top: 12px;
    letter-spacing: .04em; }}
.portada .datos {{ margin-top: 26px; padding-top: 18px; border-top: 1px solid var(--line);
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; }}
.portada .dato b {{ display: block; font-size: 11px; color: var(--muted);
    text-transform: uppercase; letter-spacing: .08em; }}
.portada .dato span {{ font-size: 14px; font-weight: 600; }}
.portada .dato.reversa {{ text-align: right; }}

/* ---------- secciones ---------- */
.seccion {{ background: #fff; border: 1px solid var(--line); border-radius: 14px;
    padding: 24px; margin-bottom: 22px; }}
.seccion-hd {{ display: flex; align-items: center; gap: 14px; margin-bottom: 16px; }}
.seccion-hd h2 {{ font-size: 17px; color: var(--ink); }}
.seccion-sub {{ font-size: 11px; color: var(--muted); }}
.seccion-tira {{ flex: 1; height: 3px; border-radius: 99px;
    background: linear-gradient(90deg, var(--p), var(--s)); opacity: .5; }}
.seccion-sin-titulo .seccion-hd {{ display: none; }}

/* ---------- KPIs ---------- */
.kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px; }}
.kpi-card {{ background: var(--p-soft); border: 1px solid color-mix(in srgb, {primario} 22%, transparent);
    border-left: 3px solid var(--p); border-radius: 12px; padding: 14px; }}
.kpi-grupo {{ display: block; font-size: 10px; color: var(--muted); text-transform: uppercase;
    letter-spacing: .1em; }}
.kpi-valor {{ display: block; font-size: 20px; font-weight: 800; margin: 2px 0; }}
.kpi-etiqueta {{ display: block; font-size: 11px; color: var(--muted); }}

/* ---------- insights ---------- */
.insight {{ display: flex; gap: 12px; border: 1px solid var(--line); border-left: 4px solid var(--muted);
    background: #F8FAFC; border-radius: 10px; padding: 12px 14px; margin-bottom: 10px; }}
.insight-positivo {{ border-left-color: #10B981; }}
.insight-negativo {{ border-left-color: #EF4444; }}
.insight-apunte {{ border-left-color: var(--a); }}
.insight-icono {{ width: 26px; height: 26px; border-radius: 50%; flex: none;
    display: grid; place-items: center; font-weight: 900; font-size: 13px;
    background: var(--line); color: var(--ink); }}
.insight-positivo .insight-icono {{ background: #D1FAE5; color: #065F46; }}
.insight-negativo .insight-icono {{ background: #FEE2E2; color: #991B1B; }}
.insight-apunte .insight-icono {{ background: #FEF3C7; color: #92400E; }}
.insight strong {{ font-size: 13px; }}
.insight p {{ font-size: 12.5px; color: #475569; margin-top: 2px; }}

/* ---------- graficos y tablas ---------- */
.chart {{ text-align: center; margin: 12px 0 4px; }}
.chart img {{ max-width: 100%; border-radius: 10px; border: 1px solid var(--line); }}
.tabla-scroll {{ overflow-x: auto; }}
.tabla {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
.tabla th {{ background: var(--ink); color: #fff; padding: 9px 10px; text-align: left;
    font-size: 11px; text-transform: uppercase; letter-spacing: .06em; }}
.tabla td {{ padding: 8px 10px; border-bottom: 1px solid var(--line); }}
.tabla tr:nth-child(even) td {{ background: #F8FAFC; }}
.cell-alta {{ font-weight: 800; color: #B91C1C; }}

/* ---------- badges de segmentos ---------- */
.seg-badges {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }}
.seg-badge {{ display: flex; flex-direction: column; align-items: center; min-width: 84px;
    background: #F8FAFC; border: 1px solid var(--line); border-radius: 10px; padding: 8px 10px; }}
.seg-badge strong {{ font-size: 18px; }}
.seg-badge span {{ font-size: 10px; color: var(--muted); text-transform: uppercase;
    letter-spacing: .05em; }}
.seg-campeon {{ border-top: 3px solid #10B981; }}
.seg-riesgo, .seg-perdido {{ border-top: 3px solid #EF4444; }}
.seg-alto {{ border-top: 3px solid #8B5CF6; }}

/* ---------- varios ---------- */
.nota {{ font-size: 10.5px; color: var(--muted); margin-top: 8px; }}
.vacio {{ color: var(--muted); font-size: 12.5px; font-style: italic; }}
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
.pie {{ color: var(--muted); font-size: 11px; text-align: center; padding: 18px 0 6px; }}
.pie b {{ color: var(--p); }}

@page {{ size: A4; margin: 12mm; }}
@media print {{
    html, body {{ background: #fff; }}
    .documento {{ padding: 0; }}
    .seccion, .portada {{ break-inside: avoid; }}
}}
@media (max-width: 680px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}
</style>"""


def css(primario="#7C4DFF", secundario="#00C2A8", acento="#FFB020") -> str:
    return css_reporte.format(primario=primario, secundario=secundario, acento=acento)