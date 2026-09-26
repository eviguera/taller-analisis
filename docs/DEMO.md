# Guion de demo de GIRO para inversores

Duracion estimada: ~8 min. Todas las cifras son las reales del dashboard.
(La demo usa el dataset de ejemplo de un taller mecanico; GIRO aplica a cualquier negocio.)

## Apertura (30 s)

> "**GIRO** es una plataforma de inteligencia comercial para pymes: transforma los
> datos operativos de tu negocio en decisiones. El stack es 100% open source
> (Streamlit, DuckDB, scikit-learn, PSPP): costo de licencias **cero**, solo
> pagarias infraestructura si el volumen crece."

## 1. Resumen

> "El taller factura **$2,75M CLP** en **318 ordenes** con un ticket promedio de
> **$8.646**. Lo relevante: los datos de cada vehiculo ya estan estructurados en
> un almacen analitico (DuckDB) listo para crecer."

- KPIs en vivo: ingresos, facturas, ticket promedio, clientes activos (50).

## 2. Ingresos por vehiculo (diferenciador)

> "No analizamos solo por cliente, sino **por vehiculo**: un Chevrolet Tracker 2015
> aporta **$99.507 CLP** en 7 visitas. Esto permite rastrear la rentabilidad de
> cada unidad, anticipar mantenimiento y decidir que flotas conviene atraer."

- Pestaña "Ingresos por vehiculo" en Vehiculos: top 15 + detalle descargable.

## 3. Clientes (RFM)

> "Segmentacion automatica (recencia, frecuencia, monto): **10 clientes de alto
> valor**, 4 leales, 2 campeones. Pero ojo: **11 en riesgo y 6 perdidos**.
> Una campana de reactivacion tocaria ~34% de la cartera con impacto medible."

## 3b. Negocio (cierre de inversion, obligatorio)

> "Aqui la pagina que me importa para ustedes: **unidad economica en vivo**.
> El taller factura **$1,33M CLP en 12 meses** con ARPU de $2.313 y un churn
> implicito de ~12%. Tiene **$783K de cartera en riesgo** (30%); GIRO puede
> recuperar ~$235K ejecutando las next-best-actions.
>
> Simulando sobre esos datos reales: con GIRO el escenario agresivo arroja
> **$1,76M de ingresos extra** en 12 meses vs no hacer nada. Y esto es la
> plataforma: **COGS por tenant de $3.000 CLP/mes, margen bruto >99%,
> break-even en ~22 clientes Pro (~$8,3M MRR)**. A 25 clientes el MRR es
> $8,25M con margen neto positivo; a 50, $16,5M."

- Pagina "Negocio": salud de cartera, cartera en riesgo, ROI por plan y
  tabla de MRR por tamano de cartera con break-even.

## 4. Servicios y demanda

> "Los 120 servicios detectados con estacionalidad mensual: sabemos que demanda
> tendra cada servicio en los proximos meses."

## 5. Inventario

> "Rotacion y cobertura de stock: la app senala **que reponer y cuando**, y evita
> faltantes u overstock. Reglas de negocio sobre los mismos datos."

## 6. Predicciones (ML embebido)

> "Modelos de machine learning (regresion + lag, Random Forest + RFM) entrenados
> sobre los propios datos: predicen **ingresos, demanda, churn e inventario**.
> Se recalculan solos al procesar los datos; sin servicios externos pagos."

## 7. Datos + PSPP

> "Importa y exporta a **PSPP/SPSS** (estandar academico y de investigacion),
> CSV y Excel. Los datos no quedan atrapados en ninguna plataforma:
> interoperabilidad total, sin vendor lock-in."

## Cierre de inversion

> "Como escala: arquitectura modular (ETL -> DuckDB -> analitica), app publica y
> gratuita hoy, lista para conectar una base SQL/PostgreSQL cuando el volumen lo
> pida, sin redisenar la interfaz. La base de costo es predecible y cercana a cero."

## Notas

- Recorre en orden: Resumen -> Negocio -> Vehiculos (Ingresos) -> Clientes ->
  Servicios -> Inventario -> Predicciones -> Datos (PSPP/ETL).
- Cierra la demo con la pestana Procesar (ETL) mostrando el panel de rendimiento
  (tiempos reales, tablas core y vistas analiticas).
- Cifras reales actuales (ejemplo del dataset): ingresos $2.749.288 CLP,
  318 facturas, 50 clientes, 88 vehiculos, 83 con ingresos; 12m: $1.332.424 CLP.