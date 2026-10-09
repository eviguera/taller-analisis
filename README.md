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

Arquitectura hexagonal: el núcleo (`src/puertos`, `src/aplicacion`, `src/core`)
no depende de ni Streamlit, ni FastAPI, ni de un motor de base de datos
concreto. Cada entrada (UI, API, CLI) y cada salida (almacenamiento) es un
adaptador intercambiable.

```
taller-analisis/
├── data/                    # Datos de ejemplo (CSV/SAV) + almacen y cache
├── config/                  # config.yaml y usuarios.yaml (por workspace)
├── src/
│   ├── puertos/             # Interfaces del hexágono
│   │   ├── almacen.py       # PuertoAlmacen (consulta, ETL, estructura)
│   │   ├── modelos.py       # PuertoRegistroModelos (persistencia ML)
│   │   └── carga.py         # PuertoCarga + CargaResultado (lectores)
│   ├── aplicacion/          # Casos de uso: SIN streamlit, SIN motor concreto
│   │   └── almacen.py       # firma, sincronizar, estructura, vista, consulta
│   ├── core/                # Núcleo del dominio
│   │   ├── pipeline.py      # ETL (procesar_etl, load_all)
│   │   ├── hechos.py        # Tabla de hechos factura_detalle + demanda real
│   │   ├── auth.py          # Usuarios, roles, sesiones, workspaces
│   │   ├── conector_sql.py  # Conectores ERP/SQL + warehouse multi-DB
│   │   └── config.py        # AppConfig (clave = workspace)
│   ├── storage/             # Adaptador de SALIDA (PuertoAlmacen)
│   │   ├── store.py         # DataStore (DuckDB embebido, el defecto)
│   │   ├── postgres.py      # AlmacenPostgres (opt-in, una base por workspace)
│   │   ├── dialecto.py      # SQL dialecto DuckDB/Postgres
│   │   └── schema.py        # Esquema core/analitica y vistas
│   ├── api/                 # Adaptador de ENTRADA HTTP (FastAPI)
│   │   ├── app.py           # crear_app() — uvicorn --factory
│   │   ├── rutas.py         # /api/salud, estado, vistas, consulta, empresas
│   │   ├── deps.py          # Sesión, permisos, aislamiento por workspace
│   │   └── esquemas.py      # Modelos pydantic de respuesta
│   ├── loaders/             # csv / excel / parquet / pspp + factory
│   ├── data_loader.py       # get_store(): ÚNICO punto de decisión de motor
│   ├── formatos.py          # miles/moneda compartidos (UI, reportes, CLI)
│   ├── analyzer.py          # Análisis exploratorio (KPIs, RFM, estacionalidad)
│   ├── predictions.py       # Modelos de predicción (registro por workspace)
│   ├── model_registry.py    # Persistencia de modelos (joblib) por empresa
│   ├── recomendaciones.py   # Giro Recomienda: next best action
│   ├── alerts.py            # Motor de alertas de negocio (+ reporte y email)
│   ├── negocio.py           # Unidad económica de GIRO y ROI
│   ├── simulador.py         # Simulador de escenarios (12m + EBITDA)
│   ├── workspaces.py        # Multiempresa: workspaces aislados por carpeta
│   └── reporting/           # GIRO Reportes: motor white-label (HTML)
├── ui/                      # Adaptador de ENTRADA Streamlit
│   ├── app.py               # Shell (barra, navegación, permisos)
│   ├── context.py           # Adaptador fino: delega en src.aplicacion
│   ├── components.py        # Wrappers (kpi_grid, panel, vacio, badge, ...)
│   ├── theme.py             # Tema de marca por workspace (colores + CSS)
│   └── pages/               # 12 páginas del dashboard
├── dashboard.py             # Entrada 1: dashboard (Streamlit :8501)
├── landing.py               # Entrada 2: landing pública (Streamlit :8502)
├── main.py                  # Entrada 3: CLI
│                            # (la API HTTP es la entrada 4, :8503)
├── entrypoint.sh            # Contenedor: los 3 procesos + healthchecks
└── tests/                   # unittest de la librería estándar
```

### Dependencias entre capas

```
entradas (ui/ · src/api/ · main.py)
        │  solo llaman a…
        ▼
src/aplicacion  ──usa──►  src/puertos (interfaces)
        │                       ▲
        │                       │ implementan
        ▼                       │
src/core (dominio, ETL)    src/storage (DataStore · AlmacenPostgres)
                                  ▲
                                  │ decide get_store() en src/data_loader.py
```

Regla: `src/aplicacion` no importa `streamlit`, `fastapi` ni `duckdb` (hay
tests que lo garantizan), y todo acceso al almacen pasa por `get_store()`.


## Uso

### 1. Dashboard web (recomendado)

```bash
python main.py dashboard
# o directamente:
streamlit run dashboard.py
```

Se abrira en el navegador (por defecto http://localhost:8501) con secciones:
- **Resumen General**: KPIs, filtros de fecha, ingresos, estacionalidad y tendencia (vistas DuckDB)
- **Negocio**: unidad economica de la plataforma y ROI (retention, ARPU, cartera
  en riesgo, valor recuperable y MRR por escenario) — para pitch de inversion
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

### 1c. API HTTP (FastAPI)

```bash
# En local (el venv del repo lleva fastapi y uvicorn):
uvicorn --factory src.api.app:crear_app --port 8503
# o:
python -m src.api.app
```

Sirve el mismo núcleo que el dashboard: mismos casos de uso de
`src/aplicacion`, mismos permisos y el mismo aislamiento por workspace.

| Endpoint | Auth | Qué hace |
|---|---|---|
| `GET /api/salud` | no | Salud del servicio (único público, no toca datos) |
| `GET /api/estado` | sí | Radiografía analítica del workspace (KPIs + alertas) |
| `GET /api/vistas` · `GET /api/vistas/{nombre}` | sí | Catálogo y datos de las vistas analíticas |
| `POST /api/consulta` | admin | SQL de solo lectura sobre el workspace |
| `GET /api/empresas` | sí | Workspaces visibles para la sesión |

La sesión llega por `Authorization: Bearer <token>` o por cookie; sin sesión
(respuesta 401), y `?workspace=` nunca saca al usuario de su propio workspace.
Documentación interactiva en `http://localhost:8503/docs`.

### 1d. Motor de almacen: DuckDB (defecto) u Postgres (opt-in)

El almacen lo decide **una sola variable**, `GIRO_ALMACEN_MOTOR`:

```bash
# Defecto: DuckDB embebido, un fichero por workspace, un solo contenedor.
unset GIRO_ALMACEN_MOTOR

# Opt-in: Postgres (una base de datos POR workspace, equivalente al .duckdb).
export GIRO_ALMACEN_MOTOR=postgres
export GIRO_PG_HOST=127.0.0.1 GIRO_PG_PORT=5432
export GIRO_PG_USER=giro     GIRO_PG_PASSWORD=...
export GIRO_PG_DBPREFIX=giro # el workspace "demo" vive en giro_demo
```

Cada workspace necesita su base creada una vez (`giro_<clave>`) — es la
unidad de aislamiento: si dos workspaces compartieran base, el ETL de uno
(`DROP TABLE` + `CREATE`) borraría las tablas del otro. Ningún código de
negocio sabe qué motor hay detrás: pide un `PuertoAlmacen` y `get_store()`
en `src/data_loader.py` lo resuelve.

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

### 2c. Unidad economica y ROI (pagina **Negocio**)

La pagina **Negocio** calcula en vivo, sobre los datos de cada workspace, el
valor que GIRO genera (retencion de cartera, ARPU, churn, cartera en riesgo,
valor recuperable y ROI de la suscripcion) y la unidad economica de la
plataforma (COGS por tenant, margen bruto, MRR y break-even). Es la hoja de
ruta del pitch de inversion (`docs/pitch.md`) y esta activa tambien en modo
kiosco para la demo.

Los parametros economicos de la plataforma viven en `suscripcion:` del config
(planes, costo por tenant, gasto fijo mensual y tasa de recuperacion) y se
pueden editar por workspace.

```yaml
suscripcion:
  planes: {Core: 150000, Pro: 450000, Enterprise: null}
  costo_tenant_mensual: 3000        # CLP/mes por workspace
  gasto_fijo_mensual: 7000000       # CLP/mes (2 ing. + 1 comercial)
  tasa_recuperacion_riesgo: 0.30    # % de cartera en riesgo que GIRO recupera
```

### 4. Workspaces (multiempresa)

Cada empresa vive en `workspaces/<clave>/` con su propia configuracion
(`config/config.yaml`), sus datos, su DuckDB y sus modelos (`data/models`),
totalmente aislados. Al crear una se puede aplicar una **plantilla de vertical**
(`--sector taller|clinica|retail|logistica|farmacia|restoran|constructora`, o el
selector Sector en la UI) que preconfigura inventario, mantenimiento, alertas y
tema de marca. El workspace activo se elige en el sidebar de la app, via CLI
con `--data` o con la variable `GIRO_WORKSPACE`.

La clave se valida contra `^[a-z0-9][a-z0-9_-]{0,63}$` antes de tocar el disco,
asi que ni la UI ni la CLI pueden construir una ruta fuera de `workspaces/`
(`../../etc`, `/etc/passwd` o un `..` suelto se rechazan).

### 4b. Usuarios, roles y acceso (autenticacion)

La app exige inicio de sesion. El registro de usuarios vive en
`config/usuarios.yaml` (permisos `0600`, fuera de git) y las contrasenas se
guardan con **scrypt** + sal por usuario; nunca en claro.

```bash
# Crear el primer administrador (tambien se puede hacer desde la UI al abrirla).
# Si omites --password, la contrasena se pide de forma oculta.
python main.py usuarios crear ana --admin

# Crear un cliente con acceso a una empresa concreta
python main.py usuarios crear carlos --workspace clinica-norte

# Listar, rotar clave y dar/cortar acceso a un workspace
python main.py usuarios listar
python main.py usuarios password ana --password 'otra-clave-larga'
python main.py usuarios acceso carlos --workspace clinica-norte --activo si
python main.py usuarios acceso carlos --workspace clinica-norte --activo no
python main.py usuarios acceso carlos --todas            # acceso total
```

**Roles.** `admin` ve todos los workspaces y administra la plataforma;
`cliente` solo ve los que tiene asignados. El aislamiento se aplica en el
servidor (`ui/context.py`), no en la interfaz: un `cliente` que manipule
`st.session_state` o la URL no logra ver un workspace ajeno.

> `principal` no es un tenant: resuelve contra `data/` y `config/config.yaml` de
> la raiz, o sea el dataset de demostracion que el kiosco ya sirve sin login.
> Aparece siempre en el selector. Los datos de un cliente van **siempre** en
> `workspaces/<clave>/data/`, nunca en `data/`.

**Que ve cada rol.**

| | admin | cliente |
|---|---|---|
| Dashboards, alertas, reportes, simulador | si | si |
| Selector y creacion de workspaces | si | no |
| **Datos → Conectores ERP/SQL** | si | no |
| **Datos → Consultas SQL** | si | no |

La consola SQL queda restringida a admin y, ademas, a consultas de solo lectura
(`SELECT`/`WITH`/`EXPLAIN`/`SHOW`/`TABLE`/`VALUES`); se rechazan escritura,
`ATTACH`, lectura de archivos, `PRAGMA` y sentencias multiples.

**SSO (OIDC).** Opcional, en `.streamlit/secrets.toml`:

```toml
[auth]
oidc_client_id = "..."
oidc_client_secret = "..."
oidc_metadata_url = "https://login.tu-empresa.com/.well-known/openid-configuration"
oidc_redirect_uri = "https://tu-dominio.com/dashboard"
oidc_admin_emails = ["admin@tu-empresa.com"]   # opcion: quienes son admin
```

Solo ser admin requiere match explicito en `GIRO_AUTH_ROLES`
(`{"@tu-empresa.com": "admin"}`). El alcance de empresas se hereda del
registro local, nunca del simple hecho de tener el correo verificado: en
multiempresa, dar por hecho que un correo verificado equivale a entregar el
portfolio completo a cualquiera que consiga una cuenta en el IdP. Aplica el
mismo criterio del login local:

```bash
python main.py usuarios acceso hola@acme.cl --workspace clinica-norte
```

Un correo OIDC sin asignacion previa entra acotado al workspace publico de
demostracion y no ve datos de ningun cliente.

**Modo kiosco.** `?kiosco=1` (por ejemplo `http://localhost:8501/?kiosco=1`)
abre una vista publica de solo lectura para demos: oculta configuracion,
conectores, consola SQL y el selector de empresas.

**Variables de entorno.**

| Variable | Por defecto | Para que sirve |
|---|---|---|
| `GIRO_AUTH_SECRET` | se genera y persiste | Firma de la cookie de sesion. **Definala en produccion** |
| `GIRO_AUTH_USERS` | `config/usuarios.yaml` | Ubicacion del registro |
| `GIRO_AUTH_DIAS` | `12` | Duracion de la sesion (dias) |
| `GIRO_AUTH_PERSISTIR_URL` | `0` | `1` refleja el token en la URL. Solo para pestanas privadas: el token queda en el historial y en el `Referer` |

La autenticacion se **exige** cuando el servidor escucha fuera de localhost
(como en Docker, HF Spaces o un VPS). Para desactivarla en local, pon
`GIRO_AUTH=0` y deja el servidor en `127.0.0.1`.

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
export GIRO_AUTH_SECRET="$(openssl rand -hex 32)"
docker compose up -d --build
# → dashboard http://localhost:8501  ·  landing http://localhost:8502
# Al abrir el dashboard por primera vez, la UI te pide crear el admin.

# O sin compose
docker build -t giro-analytics .
docker run -d -p 8501:8501 -p 8502:8502 -e GIRO_AUTH_SECRET="$(openssl rand -hex 32)" \
  --name giro-venta giro-analytics
```

El contenedor corre como usuario **no root** (uid 1001) y la imagen no lleva
datos de tenants, secretos ni modelos entrenados: eso va en volumen. Al exponer
el puerto, la app exige autenticacion, asi que `GIRO_AUTH_SECRET` es obligatorio
en produccion.

Configuracion en runtime (env): `GIRO_DASH_PORT`, `GIRO_LANDING_PORT`
(no hace falta cambiarlos por defecto), `GIRO_WORKSPACE` (workspace inicial),
`GIRO_AUTH_SECRET` (firma de sesion) y
`GIRO_DEMO_URL` (a donde apunta el CTA "Ver demo" de la landing; en produccion
usa tu dominio publico: `https://micliente.com/dashboard/?kiosco=1`).
Para conservar datos entre reinicios, descomenta los volumenes de
`docker-compose.yml` (`/app/data`, `/app/workspaces`, `/app/reports`) y monta el
registro de usuarios en `/app/config/usuarios.yaml`.

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