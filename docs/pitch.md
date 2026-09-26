# GIRO Analytics — Pitch de inversion (1 pagina)

**El GPS de tu negocio.** Analítica autogestionable, predicciones y motores de
decisión para pymes medias. Todo el stack (ETL, almacén, ML, alertas,
multiempresa y reportes white-label) está **construido y funcionando sobre
software 100% open source**, en una sola base de código.

---

## Problema
Las pymes medias tienen datos descentralizados (Excel, ERP, facturas,
inventario) **y no tienen data team**. El BI tradicional (Power BI,
consultoras) visualiza el pasado a alto costo mensual; las decisiones siguen
siendo intuición. Los modelos de IA de escritorio son opacos y no se atreven
a operar. Resultado: **cartera que se fuga, stock que se vence y clientes
que llegan tarde**.

## Solucion (de dato a accion, en un click)
GIRO automatiza el ciclo completo, ya funcional en el repositorio:

1. **Ingesta**: ETL que conecta archivos, clasifica y normaliza (CSV, Excel, .sav, ERP/SQL).
2. **Almacen**: DuckDB multiempresa — esquema `core`/`analitica`, vistas SQL
   listas para BI, costo de infraestructura por tenant ≈ **$0**.
3. **Analitica**: 9 paneles (resumen, RFM, inventario, estacionalidad…).
4. **Prediccion**: churn, ingresos, demanda e inventario **con demanda real**
   derivada de la tabla de hechos (`factura_detalle`), no de reglas inventadas.
5. **Decision**: *Giro Recomienda* — next best action por cliente (reactivar,
   recordar, upsell) con canal y mensaje, mantenimiento predictivo por activo,
   y alertas de stock/churn/ingresos/cobranza con reporte y email.
6. **Reporte**: *GIRO Reportes* — informes ejecutivos automatizados y
   white-label (5 tipos) con lectura estratégica automática, listos para
   revender a pymes (producto reventa).

## Traccion (evidencia real de un taller mecanico demo)
Datos de ejemplo ya analizados en la app (ver página **Negocio**):

| Metrica (12m) | Valor | Lectura |
|---|---|---|
| Ingresos | $1.332.424 CLP | base real de facturacion |
| Clientes activos | 48 | cartera operando |
| ARPU mensual | $2.313 | valor por cliente activo |
| Churn mensual implicito | ~12% | fugas medibles y actuables |
| Cartera en riesgo (RFM) | $783.429 (30%) | 17 clientes En Riesgo/Perdidos |
| Valor recuperable (NBA) | ~$235.029 | 30% de la cartera en riesgo |

**Con GIRO**: simular el escenario agresivo sobre esos datos arroja **$1,76M
de ingresos extra + $739K de EBITDA extra** en 12 meses vs no hacer nada
(detalle en la página Negocio → "ROI de la suscripcion").

## Unidad economica (pagina Negocio → "Unidad economica de GIRO")
Lo que la plataforma cuesta servir y lo que escala:

| Metrica | Valor |
|---|---|
| COGS por tenant | ~$3.000 CLP/mes (DuckDB + parquet + open source) |
| Margen bruto | **>99%** |
| ARPU ponderado (Core 40% / Pro 60%) | ~$330.000 CLP/mes |
| Gasto fijo mensual (2 ing. + 1 comercial) | $7.000.000 CLP |
| **Break-even** | ~22 clientes Pro / ~$8,3M MRR |
| MRR @ 25 clientes | $8,25M (neto positivo) |
| MRR @ 50 clientes | $16,5M (MRR neto $9,35M) |

## Mercado
Pymes medias de retail, taller/franchise, clínica, logística, farmacia,
restoranes y construcción. Cada vertical es una "plantilla"
(`templates.py`) que reduce el onboarding a una sesión; hay **7 plantillas
listas**. Mercado adyacente: consultoras que revenden GIRO en white-label
(reportes automatizados).

## Modelo de negocio
SaaS mensual por empresa (workspace): **Core CLP 150k · Pro CLP 450k ·
Enterprise cotización** (on-premise para grandes). La unidad económica esta
medida y vive en la app, no en una proyeccion hoja suelta. **Margen bruto
>99%, break-even en ~22 clientes.**

## Roadmap (4 fases, ~estado actual)
1. ✅ Plantillas de vertical (7) + workspaces multiempresa
2. ✅ Conectores ERP/SQL + warehouse multi-DB (DuckDB → Postgres/Neon/MySQL)
3. ✅ Simulador what-if y autoML por vertical + reportes white-label
4. 🔜 3 pilotos pagos en verticales clinica/retail + on-premise Enterprise

## Equipo
Producto construido de extremo a extremo (ETL, ML, alertas, reportes,
multiempresa, landing + demo en vivo en kiosco) sobre evidencia real.

## Pedido
Buscamos **CLP 80–120M (≈ USD 85–130k)** semilla para 12 meses: 2 ingenieros
de plataforma + 1 comercial, profundizar verticales (clínica/retail) y **3
pilotos pagos** con pymes medias. Asks: sociedades comercial y técnica con
experiencia en venta consultiva B2B SaaS. **Unidad económica ya medida en la
app: solo falta el canal.**

---
*Contacto: ventas@giroanalytics.com · demo en vivo: `/?kiosco=1` (modo presentación) · pagina Negocio en la app: unidad economica y ROI en vivo.*