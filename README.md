# GIRO - Inteligencia de negocio

GIRO es una plataforma de analitica escalable para **cualquier pequena y mediana
empresa**: convierte tus datos operativos (clientes, ventas, unidades, catalogo e
inventario) en decisiones. Incluye analisis por cliente y por unidad, predicciones
(ingresos, demanda, churn e inventario) e interoperabilidad con PSPP/SPSS.

> Los datos de ejemplo son de un **taller mecanico** (50 clientes, 88 vehiculos,
> 40 servicios, 350 facturas, 24 productos). El esquema de datos es el mismo para
> cualquier negocio; cambia la configuracion en `config/config.yaml`.

## Requisitos

- Python 3.10+
- Instalar dependencias: `pip install -r requirements.txt`

## Estructura

```
taller-analisis/
├── data/                    # Archivos CSV con los datos del taller
│   ├── clientes.csv         # id, nombre, telefono, email, fecha_registro
│   ├── vehiculos.csv        # id, cliente_id, marca, modelo, anio, placa, color, kilometraje
│   ├── servicios.csv        # id, nombre, precio_base, tiempo_estimado_min
│   ├── facturas.csv         # id, cliente_id, vehiculo_id, fecha, total, descuento, estado, detalles
│   └── inventario.csv       # id, producto, categoria, precio_costo, precio_venta, stock_actual, stock_minimo
├── src/
│   ├── data_loader.py       # Carga y limpieza de datos
│   ├── analyzer.py          # Analisis exploratorio (KPIs, RFM, estacionalidad)
│   ├── predictions.py       # Modelos de prediccion
│   ├── model_registry.py    # Persistencia de modelos (joblib) por empresa
│   ├── recomendaciones.py   # Giro Recomienda: next best action + mantenimiento
│   ├── alerts.py            # Motor de alertas de negocio (+ reporte y email)
│   ├── workspaces.py        # Multiempresa: workspaces aislados por carpeta
│   ├── simulador.py         # Simulador what-if (escenarios 12m + EBITDA)
│   ├── reporting/           # GIRO Reportes: motor de reportes white-label
│   │   ├── catalogo.py      # Tipos de reporte (resumen/ventas/clientes/...)
│   │   ├── branding.py      # Marca del cliente y del reventor (colores, logo)
│   │   ├── insights.py      # Lectura estrategica automatica (reglas)
│   │   ├── secciones.py     # Renderers HTML: KPIs, graficos, tablas
│   │   └── engine.py        # GeneradorReportes: ensambla HTML + PDF/email
│   ├── core/                # Config, pipeline ETL y hechos relacionales
│   │   ├── hechos.py        # Tabla de hechos factura_detalle + demanda real
│   │   ├── conector_sql.py  # Conectores ERP/SQL (sqlite, duckdb, csv, url)
│   │   └── templates.py     # Plantillas de vertical (7 sectores)
│   ├── storage/             # DuckDB: esquema core/analitica y vistas SQL
│   └── reports.py           # Generacion de reportes HTML (legacy)
├── ui/
│   ├── theme.py             # Tema de marca por workspace (colores + CSS)
│   ├── pages/simulador.py   # Pagina del simulador what-if
│   └── pages/reportes.py    # Pagina de reportes ejecutivos white-label
├── dashboard.py             # Dashboard web interactivo (Streamlit)
├── landing.py               # Landing publica de ventas (demo en kiosco)
├── docs/pitch.md            # Pitch de inversion 1 pagina (startup)
├── generate_data.py         # Genera datos de ejemplo (opcional)
├── main.py                  # Interfaz de linea de comandos
└── reports/                 # Reportes HTML generados (por workspace y tipo)
```

## Uso

### 1. Dashboard web (recomendado)

```bash
python main.py dashboard
# o directamente:
streamlit run dashboard.py
```

Se abrira en el navegador (por defecto http://localhost:8501) con secciones:
- **Resumen General**: KPIs, filtros de fecha, ingresos, estacionalidad y tendencia (vistas DuckDB)
- **Acciones**: Giro Recomienda (next best action por cliente), mantenimiento predictivo y modelos persistentes
- **Alertas**: reglas de negocio monitorizadas (stock, churn, ingresos, cobranza) con reporte HTML y email
- **Clientes**: segmentacion RFM, top clientes
- **Servicios**: servicios mas solicitados y series de tiempo
- **Vehiculos**: analisis por marca, antiguedad y kilometraje
- **Inventario**: demanda real derivada de los servicios vendidos y reposicion
- **Predicciones**: ingresos, demanda, churn e inventario
- **Simulador**: escenarios what-if de 12 meses (ingresos, EBITDA) con tus datos reales
- **Datos y configuracion**: importacion, ETL, conectores ERP/SQL y exportacion a PSPP
- El sidebar permite **crear y cambiar de empresa (workspace)** y personalizar
  el **tema de marca** (colores) de cada workspace
- **Modo presentacion (kiosco)**: `streamlit run dashboard.py` y entra a
  `http://localhost:8501/?kiosco=1` — oculta los paneles de configuracion para
  una demo/venta limpia

### 1b. Sitio comercial (landing + demo en vivo)

```bash
python main.py landing        # pureto 8502
# o directamente:
streamlit run landing.py --server.port 8502
```

La landing presenta producto, módulos y pricing, con CTA que abre la demo de la
app en modo kiosco. Ideal para desplegar gratis en HF Spaces o Community Cloud
(entry file: `landing.py` o `dashboard.py`).

### 2. Linea de comandos

```bash
# Resumen de los datos y KPIs
python main.py resumen

# Generar reporte HTML (se guarda en reports/)
python main.py report --abrir

# Predicciones (ingresos, demanda, churn, inventario)
python main.py predict --tipo todos --meses 6

# Prediccion especifica
python main.py predict --tipo churn

# Alertas de negocio (stock, churn, ingresos, cobranza) y reporte HTML
python main.py alertas
python main.py alertas --reporte

# Reportes ejecutivos white-label (producto reventa)
python main.py reporte listar                          # tipos disponibles y generados
python main.py reporte generar --tipo todos            # los 5 tipos en lote
python main.py reporte generar --tipo resumen --periodo "Reporte mensual"
python main.py reporte generar --tipo todos --pdf --enviar-email  # PDF + envio SMTP

# Multiempresa: crea, lista o inspecciona un workspace
python main.py workspace crear taller-don-juan --nombre "Taller Don Juan" --moneda CLP --muestra
python main.py workspace crear clinica-norte --sector clinica --muestra   # plantilla vertical
python main.py workspace listar
python main.py workspace config taller-don-juan

# Conectores ERP/SQL (Fase 2)
python main.py conector seed-erp --usar      # snapshot SQLite demo + conectores en config
python main.py conector listar               # origenes configurados
python main.py conector sincronizar          # trae los datos al almacen DuckDB

# Warehouse central multi-DB (Fase 3): publica DuckDB a Postgres/MySQL/SQLite
python main.py warehouse sync --dsn "postgresql://user:pass@host:5432/warehouse"
python main.py warehouse ver  --dsn "postgresql://user:pass@host:5432/warehouse"

# Trabajar sobre un workspace (env GIRO_WORKSPACE)
GIRO_WORKSPACE=taller-don-juan python main.py resumen
GIRO_WORKSPACE=taller-don-juan python main.py dashboard
```

### 2b. Reportes ejecutivos (white-label, para reventa)

**GIRO Reportes** es el motor que convierte los datos de cada empresa en
**reportes ejecutivos automatizados** con la marca del reventor: un documento
autocontenido (HTML imprimible a PDF en A4) con KPIs, lectura estrategica
automatica (insights), analisis por area y predicciones. Ideal para que una
consultora entregue informes periodicos a sus clientes.

- **5 tipos de reporte**: `resumen` (ejecutivo), `ventas`, `clientes` (RFM +
  churn), `inventario` y `predicciones`. Se generan por separado o en lote
  (`--tipo todos`).
- **White-label por cliente**: cada workspace define en `reportes.branding`
  los colores, logotipo (`branding.logo`, ruta dentro de `data/`), datos de la
  consultora y un rotulo de portada (`ocasion`). Si no define colores, hereda
  los de `tema:` del workspace.
- **Lectura estrategica automatica**: reglas que convierten los numeros en
  observaciones accionables (tendencia de ingresos, dependencia de la cartera,
  estacionalidad, segmentos RFM, churn y stock critico).
- **Automatizable (cron)**: el CLI corre sin supervisión y, con SMTP
  configurado en `alertas.smtp`, envía el reporte por email (`--enviar-email`).
  Para PDF real instala la dependencia opcional `weasyprint`; el HTML ya está
  estilizado para imprimir a A4 con `@page` y `break-inside: avoid`.

```yaml
# config/config.yaml (por workspace) · Fase: producto reventa
reportes:
  periodos_meses: [3, 12]                 # ventanas citadas en la portada
  tipos: [resumen, ventas, clientes, inventario, predicciones]
  ocasion: "Reporte ejecutivo"            # rotulo de portada
  branding:
    consultora: "Mi Consultora BI"        # nombre que aparece como emisor
    contacto: "ventas@consultora.cl · +56 9 1234 5678"
    web: "https://consultora.cl"
    logo: "data/logo-cliente.png"         # opcional (base64 incrustado)
    color_primario: "#7C4DFF"             # opcional; hereda de tema:
    pie: "Generado automaticamente con GIRO Analytics."
```

En la UI, la pagina **Reportes** permite editar la marca, elegir tipo y
ocasion, generar, previsualizar y descargar; tambien lista el historico
(`reports/<workspace>/<tipo>/`).

### 4. Workspaces (multiempresa)

Cada empresa vive en `workspaces/<clave>/` con su propia configuracion
(`config/config.yaml`), sus datos, su DuckDB y sus modelos (`data/models`),
totalmente aislados. Al crear una se puede aplicar una **plantilla de vertical**
(`--sector taller|clinica|retail|logistica|farmacia|restoran|constructora`, o el
selector Sector en la UI) que preconfigura inventario, mantenimiento, alertas y
tema de marca. El workspace activo se elige en el sidebar de la app, via CLI
con `--data` o con la variable `GIRO_WORKSPACE`.

### 5. Conectores (alimentacion desde ERP/SQL)

Ademas de archivos (CSV/Excel/PSPP), un workspace puede **poblar sus datasets
desde otros origenes** via la seccion `conectores:` del config:

```yaml
conectores:
  - nombre: "erp_facturas"
    motor: "sqlite"          # sqlite | duckdb | csv | excel | url | sql(DSN)
    fuente: "erp.sqlite"     # relativo a data/ (o URL / DSN)
    consulta: "SELECT * FROM facturas"
    dataset: "facturas"      # dataset canonico de destino
    forzar: true             # true reemplaza la fuente archivo local
```

- El motor **`sql`** conecta tu **ERP / Postgres / MySQL** via SQLAlchemy:
  `fuente: postgresql://user:pass@host:5432/db` o
  `mysql://user:pass@host:3306/db` (drivers: `sqlalchemy`, `psycopg2-binary`,
  `pymysql`). DSNs `sqlite:///...` relativos se resuelven contra `data/`.
- Prueba rapida: `python main.py conector seed-erp --usar` crea un snapshot
  SQLite de tus datasets (simula la exportacion del ERP), registra conectores
  `forzar=true` y de ahi en mas el ETL (`python main.py etl`) o
  `python main.py conector sincronizar` carga DuckDB desde esa BD.
- En la UI lo encuentras en **Datos y configuracion → Conectores ERP/SQL**
  (tabular conectores, sincronizar, crear snapshot y registrar a mano).
- Los conectores con `forzar: false` solo rellenan datasets que falten
  (gap-filling); un conector que falle no rompe el ETL (se reporta como aviso).

### 6. Simulador what-if

La pagina **Simulador** proyecta 12 meses de ingresos y EBITDA sobre tus datos
reales: ticket promedio, clientes activos, churn implicito y estacionalidad de
la serie. Ajusta crecimiento, churn, ticket, margen bruto y gastos fijos (o
saca de un preset), y opcionalmente superpone el modelo de ingresos GIRO
(Gradient Boosting) para comparar. Cada vertical trae **defaults economicos de
su sector** (seccion `simulador:` del config: margen, gasto fijo y crecimiento
por defecto) que se aplican al crear el workspace.

### 7. Warehouse central (multi-DB)

GIRO calcula localmente en DuckDB y **publica** el resultado hacia el warehouse
SQL de tu organizacion (Postgres/Neon, MySQL, SQLite, ...) via SQLAlchemy. Se
publican tres capas: datasets crudos, capa **core** normalizada (facturas,
clientes, detalle de factura) y las **vistas analiticas** listas para BI
(ingresos, churn, RFM, inventario). Las tablas se prefijan con `giro_` para
convivir con las tuyas.

```bash
# Publicar todo el almacen
python main.py warehouse sync --dsn "postgresql://user:pass@host:5432/warehouse"

# Solo la capa core, a un SQLite con otro prefijo
python main.py warehouse sync --dsn "sqlite:///warehouse.sqlite" \
    --esquemas core --prefijo bi_

# Ver que hay publicado
python main.py warehouse ver --dsn "postgresql://user:pass@host:5432/warehouse"
```

Si el almacen local no existe todavia, el sync ejecuta el ETL antes de
publicar (el warehouse refleja lo mismo que ve la analitica). En la UI esta en
**Datos y configuracion → Conectores ERP/SQL → Warehouse central**.

### 8. White-label (reventa)

La seccion `whitelabel:` del config permite rebautizar el panel para reventa:

```yaml
whitelabel:
  titulo: "Mi Consultora BI"      # titulo de la ventana
  footer: "© Mi Consultora"       # pie de pagina (vacio = generico)
  mostrar_footer: true            # false oculta el pie
```

La marca visible (logo, eslogan, colores primario/acento) ya se define por
workspace en `tema:` y se edita en el sidebar; el white-label completa el
titulo de ventana y el pie para entregar el producto con tu marca.

### 9. Empaquetado para venta (contenedor)

El **paquete GIRO** se entrega como un solo contenedor con las dos apps
(orquestadas por `entrypoint.sh`): **dashboard** en `:8501` y **landing de
ventas** en `:8502`. Si cualquiera de las dos caen, el contenedor se detiene
para que el orquestador lo reinicie (fail-closed).

```bash
# Build y arranque local
docker compose up -d --build
# → dashboard http://localhost:8501  ·  landing http://localhost:8502

# O sin compose
docker build -t giro-analytics .
docker run -d -p 8501:8501 -p 8502:8502 --name giro-venta giro-analytics
```

Configuracion en runtime (env): `GIRO_DASH_PORT`, `GIRO_LANDING_PORT`
(no hace falta cambiarlos por defecto), `GIRO_WORKSPACE` (workspace inicial) y
`GIRO_DEMO_URL` (a donde apunta el CTA "Ver demo" de la landing; en produccion
usa tu dominio publico: `https://micliente.com/dashboard/?kiosco=1`).

Es el mismo `Dockerfile` que corre en **Hugging Face Spaces / Streamlit
Community Cloud**: en plataformas de un solo proceso apunta el entry file a
`landing.py` (la app de ventas) o a `dashboard.py` (la app analitica), y la
demo queda en `GIRO_DEMO_URL`.

### 3. Usar tus propios datos

Reemplaza los archivos CSV en `data/` con los tuyos, manteniendo las mismas
columnas. Si tus datos estan en otro directorio:

```bash
python main.py resumen --data /ruta/a/tus/datos
python main.py dashboard --data /ruta/a/tus/datos
```

## Predicciones incluidas

| Tipo | Metodo | Que predice |
|---|---|---|
| Ingresos | Gradient Boosting + lags | Ingresos mensuales a futuro |
| Demanda | Regresion Lineal | Demanda de cada servicio |
| Churn | Random Forest + RFM | Probabilidad de que un cliente deje de visitar |
| Inventario | Demanda real (hechos) + reglas | Cobertura, reposicion y cantidad a pedir |

### Modelos persistentes

Los modelos de churn e ingresos se guardan como `data/models/*.joblib` con sus
metricas (`*.json`); si siguen frescos no se reentrenan en cada sesion y se
reutilizan entre la app, la CLI y el reporte. La pagina **Acciones** permite
reentrenarlos bajo demanda.

## Despliegue gratis (escalabilidad a costo cero)

Todo el stack es software libre (Streamlit Apache-2.0, DuckDB MIT, pandas/scikit-learn BSD,
plotly MIT, PSPP Apache-2.0). No hay licencias ni royalties que pagar; solo gastarias
infraestructura si algun dia superas los planes gratuitos.

### Opcion A - Streamlit Community Cloud (recomendada para demo/pitch)

1. Sube el proyecto a un repositorio en GitHub (no incluyas `data/almacen.duckdb`,
   `data/cache/`, `data/export/`, `data/models/` ni `workspaces/`; se regeneran
   solos al ejecutar el ETL).
2. Entra a https://share.streamlit.io y crea una app nueva desde el repo.
3. Configura: main file `dashboard.py`, Python 3.11.
4. En pocos minutos tienes una URL publica gratuita `https://tu-app.streamlit.app`.

### Opcion B - Hugging Face Spaces (plan CPU gratuito)

El repositorio ya incluye un `Dockerfile` listo para Spaces:

1. Crea un Space: https://huggingface.co/new-space (SDK: Docker).
2. Sube el proyecto (git push) con `requirements.txt`, `Dockerfile` y `data/`.
3. Espera el build y abre la URL `https://hf.co/spaces/<usuario>/<space>`.

### Opcion C - Prueba de escalado sin costo (VPS gratuita)

Si quieres medir rendimiento con muchos usuarios antes de invertir:

- **Oracle Cloud Always Free** o **AWS/GCP free tier*: una VM gratuita donde ejecutar
  `docker build -t taller .` y `docker run -p 8501:8501 taller`.
- **DNS/subdominio gratuitos**: `*.streamlit.app` o `*.hf.space` cubren el enlace público.

### Notas de despliegue

- `data/almacen.duckdb`, `data/cache/`, `data/export/` y `data/models/` se regeneran
  automaticamente al procesar el ETL; no es necesario subirlos a git.
- Las predicciones (scikit-learn) se recalculan sobre los datos cargados; no requiere
  servicios externos pagos.
- Si el volumen crece, DuckDB puede apuntar a un Postgres gratuito (p. ej. Neon/Supabase)
  sin cambiar la interfaz: reconstruir el esquema en `core`/`analitica`.

## Datos de ejemplo

`generate_data.py` crea 50 clientes, 88 vehiculos, 40 servicios, 350 facturas
y 24 productos de inventario con datos realistas ficticios.