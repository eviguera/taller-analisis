# AGENTS.md — GIRO (taller-analisis)

Plataforma de analítica para PYMEs. Un contenedor, dos apps Streamlit, multi-tenant.

Este archivo se carga siempre. Los agentes especializados viven en `.opencode/agent/`.

## Qué es este repo

| | |
|---|---|
| Entry points | `dashboard.py` (:8501, autenticado) · `landing.py` (:8502, público) · `main.py` (CLI) |
| Núcleo / ETL | `src/core/` — `pipeline.py`, `hechos.py`, `conector_sql.py`, `warehouse.py`, `auth.py`, `config.py`, `templates.py` |
| Almacenamiento | `src/storage/` — `schema.py` (vistas DuckDB), `store.py` |
| Carga | `src/loaders/` — `base.py` + csv / excel / parquet / pspp, `factory.py` |
| Analítica | `src/analyzer.py`, `predictions.py`, `model_registry.py`, `recomendaciones.py`, `alerts.py`, `simulador.py`, `negocio.py` |
| Reportes | `src/reporting/` — motor de reportes HTML white-label |
| UI | `ui/` — `app.py`, `context.py`, `components.py`, `theme.py`, `login.py`, `pages/*.py` (12 páginas) |
| Multi-tenant | `src/workspaces.py` |

Datos de ejemplo: taller mecánico (50 clientes, 88 vehículos, 40 servicios, 350 facturas, 24 productos). **El esquema es transversal** — el producto se vende a cualquier negocio. No hardcodees "taller", "vehículo" ni "kilometraje" en lógica de negocio.

## Cómo trabajar aquí

**Idioma: español.** Código, docstrings, comentarios, copy de la UI y nombres de variables. Los términos del dominio (`factura`, `cliente`, `orden`, `workspace`) van en español y se consistentes.

**Estilo de código: el del archivo circundante.** El repo ya tiene un estilo consistente y en español. Míralo antes de escribir; la excepción es el bug.

**Verificación real, y poca:**
- `.venv/bin/python -c "import src.modulo"` — el venv del repo tiene las deps.
- Ejecuta el flujo cuando exista forma de hacerlo (`main.py`, el CLI, una función concreta).
- **Este repo no tiene `pyproject.toml`, ni ruff, ni mypy, ni pytest, ni Makefile.** No ejecutes esas herramientas esperando que existan. Si propones añadirlas, hazlo como recomendación explícita.
- **Si no pudiste ejecutar nada, dilo.** "No verificado en ejecución" es honesto; "listo" sin correrlo es una mentira. Es la regla más importante de este archivo.

**Comandos:**
```bash
.venv/bin/python main.py --help
.venv/bin/streamlit run dashboard.py   # :8501
.venv/bin/streamlit run landing.py     # :8502
docker compose up -d --build
```

## Reglas inviolables

1. **Aislamiento por workspace.** Ninguna función de negocio lee ni escribe fuera del workspace que recibe. **Las claves de caché (`@st.cache_data`, `@st.cache_resource`) deben incluir el workspace** — omitirlo es una fuga de datos entre clientes, no un bug de rendimiento.
2. **Nada de secretos en el código.** Solo `os.environ`. Nunca en el código, el `Dockerfile`, el `docker-compose.yml` ni los logs. El contenedor corre en `0.0.0.0`, así que la app **exige** autenticación y `GIRO_AUTH_SECRET`.
3. **Sin datos de tenants en la imagen ni en el repo.** `.dockerignore` excluye `data/`, `workspaces/`, `reports/`, `*.duckdb`, `*.parquet`, `*.joblib`, `config/usuarios.yaml`. Ese contrato no se rompe.
4. **SQL siempre parametrizado.** Bind parameters, nunca f-strings ni concatenación. Los identificadores dinámicos (nombre de tabla/columna) se validan contra una allowlist.
5. **Sin deserializar datos externos con `pickle`/`joblib`** sin validar el origen: es RCE. Aplica a `src/model_registry.py`.
6. **Python 3.11** (lo fija `Dockerfile`). El venv local puede ser más nuevo; no uses APIs que no existan en 3.11.
7. **Cero efectos secundarios a nivel de import.** Nada de `st.set_page_config`, `duckdb.connect()` ni lectura de disco en import.
8. **Nada de `except Exception: pass`.** Un error tragado convierte un bug visible en uno invisible.
9. **No añadas dependencias** sin justificarlo. Stack actual: pandas, numpy, duckdb, pyarrow, scikit-learn, plotly, matplotlib, streamlit, jinja2, joblib, pyreadstat, PyYAML, sqlalchemy, psycopg2-binary, pymysql.
10. **No introducas frameworks nuevos.** Es un monolito de analítica. No traigas FastAPI, React, un ORM ni una capa de abstracción de servicios.
11. **No hagas commit ni push** salvo que el usuario lo pida explícitamente.

## Dónde vive cada cosa

- **Lógica de negocio / Python** → `python-senior`
- **UI, CSS, páginas Streamlit** → `ui-engineer`. Usa los wrappers de `ui/components.py` (`kpi_grid`, `panel`, `vacio`, `badge`, `miles`, `moneda`, `grafico_*`) y los tokens de `ui/theme.py`. **Nunca escribas `st.plotly_chart` crudo ni HTML suelto en una página.** El tema base está en `.streamlit/config.toml` y no se edita para arreglar una pantalla.
- **Flujo de usuario, usabilidad, recorridos** → `ux-researcher` (solo lectura, no implementa)
- **Esquema, SQL, consultas, conectores** → `sql-arquitecto`
- **Carga de datos, ETL, calidad** → `data-engineer`
- **KPIs, métricas, modelos, insights** → `data-analyst`
- **Revisión antes de entregar** → `code-reviewer` (solo lectura, no arregla)
- **Contenedores** → `docker-expert`

## Comandos de UI (`/ade-*`)

Pipeline de diseño en 3 pasos, adaptado de `agentic-design-engineering`. **El orden importa**: una atmósfera sobre una estructura rota es decoración.

| Comando | Qué hace | Umbral |
|---|---|---|
| `/ade-build [pantalla]` | Audita y **repara** A/L/C/E/R, en orden A→L→C→E→R | 40/50 |
| `/ade-style [pantalla]` | Descubre la metáfora física y construye la atmósfera en 5 ciclos | fidelidad >= 3/4 |
| `/ade-write [pantalla]` | Reescribe el copy en español: botones, errores, vacíos | 40/70 |

Sin argumentos, cada uno trabaja sobre `ui/pages/resumen.py` y lo dice.

`/ade-style` **exige** que `/ade-build` haya pasado 40/50. `/ade-write` puede correr solo.

**Todos se ejecutan con las mismas reglas de `ui-engineer`:** wrappers de `ui/components.py`, nada de `st.plotly_chart` crudo, `config.toml` es global, y los tres deben funcionar en **modo claro y oscuro**. Ninguno escribe archivos de log en el repo: el reporte va en la conversación. Este producto se entrega a clientes, no se ensucia con artefactos de auditoría.

## Git

- No commitees sin que lo pidan. Cuando lo pidan, revisa `git status`, `git diff`, `git log --oneline -10` y stagea solo lo intencionado.
- El `.gitignore` ya excluye datos, modelos y secretos. Si algo de eso aparece en `git status`, es un problema.
- No reescribas historia, no fuerces push, no saltes hooks.
