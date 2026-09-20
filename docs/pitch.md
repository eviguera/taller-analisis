# GIRO Analytics — Pitch (1 página)

**El GPS de tu negocio.** Analítica autogestionable, predicciones y motores de
decisión para medianas y grandes empresas. Todo el stack (ETL, almacén, ML,
alertas y multiempresa) está **construido y funcionando sobre software 100%
open source**, en una sola base de código.

---

## Problema (por qué ahora)
Las empresas media/grandes tienen datos descentralizados (Excel, ERP, facturas,
inventario) **y no tienen data team**. El BI tradicional (Power BI, consultoras)
visualiza el pasado a un costo alto y mensual; las decisiones siguen siendo
intuición. La IA de escritorio usa modelos opacos que no se atreven a operar.

## Solución (de dato a acción, en un click)
GIRO automatiza el ciclo completo:

1. **Ingesta**: ETL que conecta archivos, clasifica y normaliza (CSV, Excel, .sav).
2. **Almacén**: DuckDB multiempresa — esquema `core`/`analitica`, vistas SQL
   consumidas por los paneles, sin coste de infraestructura por tenant (~$0).
3. **Analítica**: 9 dashboards (resumen, RFM, inventario, estacionalidad…).
4. **Predicción**: churn, ingresos e inventario **con demanda real** derivada de
   la tabla de hechos (`factura_detalle`), no de reglas inventadas.
5. **Decisión**: *Giro Recomienda* — next best action por cliente (reactivar,
   recordar, upsell) con canal y mensaje, mantenimiento predictivo por activo,
   y alertas de stock/churn/ingresos/cobranza con reporte y email.
6. **Reporte**: *GIRO Reportes* — informes ejecutivos automatizados y
   white-label (5 tipos: resumen, ventas, clientes, inventario, predicciones)
   con lectura estratégica automática, listos para vender a pymes.

Diferenciadores técnicos que **ya existen en el repositorio**: hechos
relacionales, registry de modelos persistente (joblib), workspaces aislados por
empresa, modo presentación y exportación a PSPP/SPSS (.sav/.por).

## Mercado
Medianas y grandes de retail, taller/franchise, clínica, logística y
servicios. Cada vertical es una "plantilla" (`config.yaml` + `templates.py`)
que reduce el onboarding a una sesión. Mercado adyacente: consultoras y
agricultura de datos que revenden GIRO en white-label.

## Modelo de negocio
SaaS mensual por empresa/workspace — Core CLP 150k, Pro CLP 450k,
Enterprise cotización (on-premise para grandes con restricciones de datos).
COGS por tenant ≈ $2–10/mes → **margen bruto >90%**, conciencia de UM: ~25
clientes Pro (~$11M CLP MRR) sostiene la operación con 2 personas.

## Equipo y tracción
Producto construido de extremo a extremo (ETL, ML, alertas, multiempresa,
landing + demo en vivo en kiosco) sobre evidencia real de un taller mecánico
demo: 50 clientes, 88 unidades, 350 facturas → sentido de negocio por completo.
Roadmap en 4 fases: plantillas de vertical → conectores ERP/SQL → simulador
what-if y autoML por vertical → white-label y multi-DB (DuckDB→Postgres/Neon).

## Pedido
Buscamos **CLP 80–120M (≈ USD 85–130k)** semilla para 12 meses: 2 ing.
plataforma + 1 comercial, verticales (clínica/retail) y 3 pilotos pagos con
empresas medianas. Asks: sociedades comercial y técnica con experiencia en
ventas consultivas B2B SaaS.

---
*Contacto: ventas@giroanalytics.com · demo en vivo: `/log?kiosco=1` (modo presentación)*