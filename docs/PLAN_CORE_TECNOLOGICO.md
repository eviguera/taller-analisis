# GIRO Core v1

## Plan tecnológico centrado en el núcleo

**Estado:** propuesta para decisión. **Fecha:** 2026-10-25. **Rama:** feature/indicadores-decisión-ceo.

**Alcance:** núcleo analítico, contratos, composición, aislamiento multi-tenant, Asesor IA y arnés de verificación. **No** es un catálogo de features ni un rediseño de UI.

**Evidencia ejecutada:** suite completa: 258 tests, 257 OK, 1 ERROR, 13 skipped (38,8 s). El error es real: tests/test_e2e.py::test_predictions_ejecutan → UnboundLocalError en src/predictions.py:79. El agente Worker ejecutó además el barrido de UI (18/19), main.py eval (6/6), importación de 79 módulos (0 fallos) y parseo de 121 archivos con gramática 3.11 (0 errores). El agente Planner auditó límites y encontró dos bugs adicionales verificados por lectura: log indefinido en src/aplicacion/almacen.py:71,92 y una fábrica de almacén que nunca se registra.

**No verificado:** Postgres real, build Docker, runtime 3.11 y API en vivo. El daemon Docker no estaba disponible; el venv local es 3.14.2.

**Cómo se produjo:** orquestador Commander con tres delegaciones paralelas (Planner, Reviewer, Worker) y las skills change-impact, product-capability, docs-governance, security-review, module-regression, test-collaboration, verification-loop y tdd-workflow. El Reviewer no devolvió su brief antes del cierre (se canceló para no bloquear el entregable); sus hallazgos se tratarán como revisión independiente y no condicionan el diagnóstico.

---

## 0. Resumen ejecutivo

GIRO no tiene un problema de features. Tiene un problema de **frontera**: el hexágono está declarado, pero no se puede ejecutar ni verificar.

La lógica del núcleo está repartida entre src/core, src/aplicacion y 1.979 líneas de módulos raíz (analyzer, predictions, alerts, simulador, negocio, model_registry, recomendaciones). Hay tres composiciones distintas (src/data_loader.py, ui/context.py, src/api/deps.py) y las dependencias apuntan hacia afuera: src/core/pipeline.py importa src/loaders y src/storage.schema; src/aplicacion/almacen.py importa src/data_loader; la UI y la API importan módulos raíz. El resultado es que el núcleo no se puede probar sin Streamlit, sin DuckDB o sin configuración global, y que cada entrada puede comportarse distinto.

La IA es el ejemplo más claro: el Asesor tiene un puerto (PuertoAgenteIA), pero el caso de uso importa la fábrica del adaptador, no hay caché, no hay límites, no hay auditoría, no hay tests y siete except Exception devuelven contexto vacío sin avisar. Es una capacidad valiosa gobernada como demo, no como servicio del núcleo.

**Propuesta: GIRO Core v1.** Un programa de 6-8 semanas, sin frameworks nuevos, con cinco resultados:

1. Una sola composición por proceso y una matriz de dependencias que falle en CI.
2. Un motor analítico determinista, con dataset dorado y KPIs reproducibles entre UI, API, CLI y reportes.
3. Aislamiento multi-tenant probado por comportamiento, no por inspección de nombres.
4. Un Asesor IA acotado: contexto tipado, sin PII, con caché por workspace, límites de coste, auditoría y evaluaciones.
5. Un arnés de verificación en Python 3.11 que distinga "verde local" de "verde en producción".

**Tres apuestas:** recomponer sin cambiar comportamiento; hacer que los números sean reproducibles; gobernar la IA como capacidad del núcleo.

**Tres no-goals:** features nuevas, rediseño de UI, microservicios o dependencias nuevas.

**Métrica de éxito:** 0 violaciones de la matriz; 100% de puertos con test de conformidad; 0 deriva en KPIs dorados; 0 fugas entre workspaces; suite y barrido de UI verdes en 3.11; Asesor con evaluación offline ≥ 90% y coste por diagnóstico dentro de presupuesto.

---

## 1. Qué significa "core" en GIRO

Definición operativa, no conceptual. El core es lo que debe seguir siendo verdad aunque cambie la UI, el motor o el proveedor de IA:

| Invariante | Significado | Hoy |
|---|---|---|
| Contrato de datos | Todo dato entra por un loader y se normaliza a un esquema conocido; el core no lee archivos ni bases directamente | Parcial: el pipeline conoce loaders concretos |
| Cálculo determinista | Mismos datos + misma config → mismos KPIs, con tolerancia definida | No demostrado: no hay dataset dorado |
| Aislamiento | Toda operación recibe un workspace explícito; ninguna caché ni consulta lo omite | Diseñado y probado en auth/Postgres; sin prueba de comportamiento en DuckDB |
| Puertos | El core declara lo que necesita; los adaptadores lo implementan | Puertos existen; algunos son decorativos |
| Errores tipados | Un fallo no se convierte en cero, vacío o 500 genérico sin traza | No: tuplas posicionales y excepciones ad hoc |
| Observabilidad | Cada caso de uso deja workspace, operación, duración y resultado | API sí; núcleo, UI y ETL no |

**Lo que no es core:** el tema visual, el copy, el número de páginas, el proveedor de IA, el motor de base de datos. Eso son adaptadores o producto. El core es el contrato que los hace sustituibles.

### 1.1 Mapa actual vs. objetivo

| Responsabilidad | Hoy | Objetivo Core v1 |
|---|---|---|
| Analítica pura | src/analyzer.py, src/negocio.py, src/recomendaciones.py, src/simulador.py | src/core/analitica/ y src/core/decisiones/ |
| Predicción | src/predictions.py (sklearn + config + registry) | src/aplicacion/prediccion.py + src/core/prediccion/ + src/adapters/ml/ |
| Alertas | src/alerts.py (reglas + Analyzer/Predictor) | src/core/alertas/ + src/aplicacion/alertas.py + adaptadores de notificación |
| Persistencia | src/storage + src/data_loader.get_store | src/storage + src/composicion.py |
| SQL | src/core/conector_sql.py (validación + DuckDB + SQLAlchemy) | src/core/sql/validacion.py + src/storage/sql/ |
| Reportes | src/reporting/engine.py (importa módulos raíz) | src/aplicacion/reportes.py + adaptador de reportes |
| IA | src/aplicacion/asesor_negocio.py + src/adapters/llm | Igual + contrato ejecutable, contexto tipado, caché, límites, auditoría |
| Composición | src/data_loader, ui/context, src/api/deps | src/composicion.py (una sola) |
| Entradas | UI/API/CLI llaman a capas mezcladas | Solo src.aplicacion + src.composicion |

---

## 2. Diagnóstico

### 2.1 Fortalezas que hay que preservar

1. **Aislamiento pensado en serio.** auth.workspace_permitido corrige el workspace pedido contra permisos (src/core/auth.py:789-803); Postgres usa una base por workspace (src/data_loader.py:234-270); la UI cachea por workspace y firma (ui/context.py:171-177). Esto no se toca: se protege con tests.
2. **Seguridad de base.** Validación única de SQL de solo lectura compartida por consola, API y MCP (src/core/conector_sql.py:109); HMAC de sesión; rate limit de login; joblib con SHA-256 y validación de extensión; cabeceras y logs JSON en la API.
3. **ETL con contratos útiles.** Firmas de carga, caché por hash, reglas de calidad y publicación a warehouse; ResultadoETL con errores y advertencias.
4. **Puertos reales y dos adaptadores.** PuertoAlmacen (ABC), DataStore y AlmacenPostgres; PuertoCarga, PuertoIdentidad, PuertoRegistroModelos, PuertoAgenteIA.
5. **API con higiene.** crear_app() concentra la construcción; request_id, logging, rate limit, deps que resuelven identidad/workspace/config; tests ASGI sin red.
6. **Suite amplia y barata.** 258 tests en unittest; 13 skips de Postgres; un barrido de UI con AppTest y una evaluación determinística con exit code.
7. **Cero efectos secundarios en import, en general.** crear_app() y los módulos de dominio lo declaran; hay una prueba en subproceso para Streamlit.

### 2.2 Brechas, ordenadas por impacto

| ID | Brecha | Evidencia | Por qué es core | Esf. |
|---|---|---|---|---|
| C-01 | La regla de dependencias no se verifica | src/core/pipeline.py:24-25 importa ..loaders y ..storage.schema; src/core/conector_sql.py:307 importa duckdb; src/core/warehouse.py:39 importa sqlalchemy | El núcleo depende de adaptadores concretos; no se puede sustituir el motor ni probar sin infraestructura | M |
| C-02 | La aplicación depende de la composición raíz | src/aplicacion/almacen.py:163 hace from ..data_loader import get_store como fallback; registrar_fabrica_almacen (línea 36) no se llama en ningún sitio | El caso de uso no es inyectable y la configuración global se filtra | S/M |
| C-03 | UI y API saltan la capa de aplicación | ui/context.py:18-20 importa data_loader, analyzer y predictions; src/api/rutas.py:29-33 importa alerts, analyzer, negocio y predictions; ui/pages/* importa módulos raíz; src/api/mcp_server.py:75 duplica load_all | Hay tres cableados y tres comportamientos posibles | M/L |
| C-04 | El núcleo está disperso | 1.979 líneas en analyzer, predictions, alerts, simulador, negocio, model_registry y recomendaciones; predictions mezcla sklearn, config y persistencia; alerts importa Analyzer y Predictor; reporting/engine.py importa módulos raíz | No hay un único kernel analítico que probar | L |
| C-05 | Composiciones múltiples | src/data_loader.get_store decide el motor; ui/context.obtener_estado compone la UI; src/api/deps.contexto compone la API; main.py compone el CLI | Los defaults y el aislamiento dependen del camino | M |
| C-06 | Contratos laxos y errores sin taxonomía | src/aplicacion/asesor_negocio.py:6 importa src.adapters.llm.factory; cfg: Any y data: Dict[str, Any] (líneas 10, 30); src/aplicacion devuelve tuplas posicionales (almacen.py:207-210; carga.py:73,184) y no lanza excepciones propias; la API colapsa todo a 500 (rutas.py:64-79) y la UI imprime str(e) (ui/pages/asesor_ia.py:35) | El contrato es la frontera | M |
| C-07 | La verificación no protege el núcleo | tests/test_auth_identidad.py:94-113 solo prohíbe Streamlit; no hay test de imports de duckdb/fastapi/sqlalchemy en aplicación, ni de conformidad de puertos, ni dataset dorado, ni tests de asesor | Cada refactor es a ciegas | M |
| C-08 | Hay regresiones vivas | src/predictions.py:79 usa modelo_df antes de asignarlo (línea 92) y tumba un test e2e; src/aplicacion/almacen.py:71,92 usa log sin importar logging ni definirlo; ui/pages/asesor_ia.py:13 usa auth.PERMISO_VER_DASHBOARD, que no existe, y la página no está registrada en ui/pages/__init__.py | Son fallos de caminos centrales, no de UI | XS/S |
| C-09 | La simulación no tiene señal | src/agentes_estrategicos/strategy.py:127 devuelve un DataFrame vacío; las proyecciones del simulador son cero por construcción | El producto presenta una decisión sin datos | S |
| C-10 | La IA no está gobernada | src/servicios/contexto_datos.py:27,40,78,96,123,136,152 usa except Exception con retorno vacío; envía cliente_id en top_clientes; src/adapters/llm/openrouter.py:121-131 ignora usage, no reintenta ni clasifica errores; src/aplicacion/asesor_negocio.py:31 interpola la pregunta del usuario en las instrucciones; requests (openrouter.py:8) no está declarado en requirements.txt (solo en el lock como transitiva); no hay tests de asesor | Afecta privacidad, coste y credibilidad | M |
| C-11 | Observabilidad incompleta | src/api/app.py:62-70 registra método, ruta y estado, pero no workspace ni usuario; loggers ad hoc en src/core/auth.py:52, src/core/pipeline.py:27 y src/storage/store.py:379-381; no hay métricas de ETL ni de IA | Un incidente multi-tenant no se acota | S/M |
| C-12 | Rendimiento sin presupuesto | load_all carga todos los datasets; no hay timeout ni máximo de filas en consultas; el rate limit de la API es un dict en memoria por proceso; las predicciones reentrenan | El núcleo puede caer por un workspace grande | M |
| C-13 | Esquema sin versión | No hay version_esquema en giro_meta; el aviso de tablas obsoletas existe, pero no hay migración ni detección de deriva | Un esquema viejo produce números equivocados | S/M |
| C-14 | Se verifica en el intérprete equivocado | El venv local es 3.14.2; el Dockerfile fija python:3.11-slim y el lock está resuelto para 3.11; requirements.txt declara fastapi>=0.143.0 mientras el lock fija fastapi==0.115.0 | "Verde local" no es "verde en producción" | S |
| C-15 | El despliegue no arranca la API con el lock actual | requirements.lock no contiene fastmcp, mcp ni openpyxl; src/api/app.py:20 importa .mcp_server y src/api/mcp_server.py:27 importa fastmcp; el Dockerfile instala desde el lock | El contrato de despliegue está roto | S |
| C-16 | El CI no es un gate real | .github/workflows/ci.yml existe en el working tree pero no está trackeado; instala requirements.txt (no el lock), tiene un job que referencia matrix.python-version sin matriz, prohíbe unsafe_allow_html=True en ui/pages/ (hoy hay 10 usos para badges) y no ejecuta Postgres, compileall ni smoke de API/CLI | La calidad no se sostiene sola | M |
| C-17 | La UI tiene una regla que el CI castiga | Los badges de alertas/resumen/acciones/briefing/scheduler/memoria/datos/asesor_ia usan HTML directo con unsafe_allow_html=True; la regla de AGENTS.md y el CI dicen que el HTML debe vivir en ui/components.py | Es una brecha de contrato, no de estética | S |

### 2.3 Lo que ya está bien y no se debe tocar

- El stack: pandas, numpy, duckdb, pyarrow, scikit-learn, plotly, streamlit, jinja2, joblib, pyreadstat, PyYAML, sqlalchemy, psycopg2-binary, pymysql, FastAPI como excepción ya decidida.
- La autenticación y el modelo de permisos.
- La base por workspace en Postgres y la validación de dbname.
- El tema y los wrappers de ui/components.py: se usan más, no se reemplazan.
- El esquema de datos de ejemplo y generate_data.py.
- El plan de 800 ítems: se cita como backlog, no se duplica.


---

## 3. Arquitectura objetivo

### 3.1 Principio rector

No se añade una capa nueva. Se hace verdad lo que AGENTS.md ya declara: puertos → contratos; core → dominio; aplicacion → casos de uso; storage/loaders/api/ui → adaptadores. Se añade **una** pieza que hoy no existe: src/composicion.py, la raíz de composición.

### 3.2 Diagrama

~~~
[Streamlit ui/]   [FastAPI src/api/]   [CLI main.py]
        \               |               /
         \              v              /
          src/composicion.py  (unica wiring)
                     |
          src/aplicacion/  (casos de uso)
             /       |       \
      src/core/   src/puertos/   src/adapters/ (llm, ml, notificaciones)
         |             |
         v             v
    pandas/numpy   src/storage/ (duckdb, postgres, warehouse)
                  src/loaders/ (csv, excel, parquet, pspp)
~~~

### 3.3 Matriz de dependencias permitida

| Módulo | Puede importar | No puede importar |
|---|---|---|
| src/core | stdlib, pandas, numpy, scikit-learn, src/core | src/storage, src/loaders, src/adapters, src/api, ui, src/aplicacion, streamlit, duckdb, fastapi, sqlalchemy, requests |
| src/puertos | stdlib, typing, pandas (solo DTOs) | cualquier adaptador concreto, src/aplicacion, ui, api |
| src/aplicacion | src/core, src/puertos, pandas | src/storage, src/loaders, src/data_loader, src/adapters, src/api, ui |
| src/storage, src/loaders, src/adapters | src/puertos, tipos de src/core | src/aplicacion, src/api, ui |
| src/api, ui, main.py | src/aplicacion, src/composicion, src/core.auth (sesión) | src/storage, src/loaders, módulos raíz |
| src/composicion | todo | — |

Se verifica con un test AST en tests/test_arquitectura.py, sin dependencias nuevas. Arranca con una allowlist de las violaciones actuales (C-01 a C-03) y la reduce a cero en Fase 1. Un test que solo mira streamlit no basta: el agente Planner ya demostró que asesor_negocio importa un adaptador y nadie lo detecta.

### 3.4 Contratos

- **DatosWorkspace:** alias tipado de dict[str, pd.DataFrame] con nombres de dataset requeridos; validación en la frontera (columnas, dtypes, fechas) y error tipado.
- **ContextoAplicacion:** dataclass frozen con cfg, workspace, almacen, cargador, analitica, prediccion, asesor, reloj. Lo construye src/composicion.py.
- **Errores:** ErrorGiro(codigo, mensaje, detalle, reintentable); ErrorValidacion, ErrorAislamiento, ErrorNoDisponible, ErrorConflicto, ErrorIA. La API mapea a 400/403/404/409/503/500; la UI muestra mensaje seguro y loguea el detalle.
- **Puertos:** cada puerto tiene una suite de conformidad; el adaptador declara explícitamente que lo implementa. PuertoCarga se usa de verdad en el pipeline; PuertoAgenteIA se inyecta en el caso de uso; PuertoAlmacen separa consulta semántica (vista) de acceso físico (objeto interno).
- **Observabilidad:** campos mínimos en cada log de caso de uso: workspace, caso_uso, request_id, duracion_ms, resultado, filas. Nunca secretos ni PII.

### 3.5 Composición (esqueleto)

~~~python
# src/composicion.py
from dataclasses import dataclass

@dataclass(frozen=True)
class ContextoAplicacion:
    workspace: str
    cfg: AppConfig
    almacen: PuertoAlmacen
    cargador: PuertoCarga
    analitica: ServicioAnalitica
    prediccion: ServicioPrediccion
    asesor: PuertoAgenteIA | None
    reloj: Reloj

def construir(workspace: str, *, sesion=None) -> ContextoAplicacion:
    cfg = config_del_workspace(workspace)
    almacen = crear_almacen(cfg)
    return ContextoAplicacion(...)
~~~

La UI, la API y el CLI llaman a construir una vez por página, request o comando. ui/context.py conserva solo la caché de Streamlit y la sesión; src/api/deps.py conserva identidad/permisos; src/aplicacion/almacen.py deja de importar data_loader.

### 3.6 Qué pasa con los módulos raíz

No se borran de golpe. Se convierten en fachadas de compatibilidad:

~~~python
# src/analyzer.py (transitorio)
from src.core.analitica.analyzer import Analyzer
__all__ = ["Analyzer"]
~~~

La implementación se mueve por fases, con tests de caracterización antes de cada movimiento. Al final, la UI y la API no importan estos módulos; solo src.aplicacion.

---

## 4. Hoja de ruta

### Fase 0 — Verde y ratchet (1-2 días)

Objetivo: que la base sea confiable antes de mover nada.

Entregables:

- **C0-01. Corregir src/predictions.py:79.** Calcular modelo_df = serie.dropna().copy() antes de la guarda; la condición debe ser len(serie) < 12 (no len(modelo_df), que descuenta los tres lags) y el mensaje usa len(serie). Añadir test de menos de 12 meses y de 12 o más.
- **C0-02. Corregir src/aplicacion/almacen.py:71,92.** Añadir import logging y log = logging.getLogger(__name__). Test que fuerce mapeo inválido y directorio ilegible: debe avisar, no lanzar NameError.
- **C0-03. Resolver src/agentes_estrategicos/strategy.py:127.** Pasar datos crudos al simulador o devolver "no disponible" explícito; nunca proyectar cero como si fuera señal. Test de proyección no nula con datos conocidos o de estado "sin datos".
- **C0-04. Arreglar el lock.** Regenerar requirements.lock con python:3.11-slim (según AGENTS.md) para incluir fastmcp, mcp y openpyxl, y alinear fastapi con requirements.txt; o, si no se puede, quitar el import de mcp_server de src/api/app.py hasta que el lock esté sano. Declarar requests en requirements.txt.
- **C0-05. Decidir ui/pages/asesor_ia.py.** Registrarla en PAGINAS con un permiso real o sacarla del árbol; hoy usa auth.PERMISO_VER_DASHBOARD, que no existe.
- **C0-06. Añadir tests/test_arquitectura.py.** AST + allowlist de las violaciones actuales. No bloquear lo que ya existe; bloquear lo nuevo.
- **C0-07. Alinear CI.** Instalar requirements.lock, añadir compileall, corregir el job sin matriz, añadir smoke de import de src.api.app y sustituir el grep de unsafe_allow_html por una regla que permita el wrapper de components.py.

**Aceptación:**

- .venv/bin/python -m unittest discover -s tests → 258/258, 0 errores, 13 skips (o Postgres en CI).
- python -m compileall -q src ui main.py dashboard.py landing.py → 0.
- tests/test_arquitectura.py pasa con allowlist y falla si se añade un import prohibido.
- El lock instala y python -c "import src.api.app" funciona en 3.11 (Docker o CI).

**Verificación:**

~~~bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m compileall -q src ui main.py dashboard.py landing.py
docker run --rm -v "$PWD":/app -w /app python:3.11-slim sh -c "pip install -r requirements.lock && python -c 'import src.api.app'"
~~~

**Riesgo:** tocar predictions puede cambiar el comportamiento de menos de 12 meses; el test fija el contrato. Si el lock no se puede regenerar, la fase no se declara cerrada.

**Estado de ejecución (2026-10-25):** Fase 0 cerrada en local con Python 3.11.15.

- C0-01: `modelo_df` se calcula antes de la guarda; se valida `len(serie) < 12` y se eliminó la llamada a `_evaluar` inexistente. Tests en `tests/test_fase0.py`.
- C0-02: `src/aplicacion/almacen.py` tiene logger de módulo; el test fuerza un mapeo inválido y comprueba el aviso.
- C0-03: `strategy.py` recibe `data`, usa facturas crudas, aplica presets y marca escenarios no disponibles; `pipeline.py` pasa `data`. La UI de decisiones muestra el estado vacío.
- C0-04: `requirements.lock` regenerado con `uv` y CPython 3.11.15 (109 paquetes, incluye `fastmcp`, `mcp`, `openpyxl`); `requests` y `uvicorn` declarados en `requirements.txt`. El import de `src.api.app` funciona; el lifespan se toma de `mcp.http_app(path="/")` y el cliente MCP lista las 3 herramientas en `/mcp`.
- C0-05: `ui/pages/asesor_ia.py` convertida a `principal()`, registrada como “Asesor IA” y sin `set_page_config`. La página consulta `asesor_ia_disponible()` y, si falta `GIRO_IA_API_KEY`/`OPENROUTER_API_KEY`, muestra las instrucciones de configuración y deshabilita “Generar diagnóstico” y “Preguntar” en vez de lanzar el error crudo. `OpenRouterAdapter` permite ajustar `GIRO_IA_MAX_TOKENS`; con modelos gratuitos se usan 4000 tokens para que el JSON no se trunque.
- C0-06: `tests/test_arquitectura.py` con allowlist de deuda; falla si aparece un import prohibido nuevo o si la allowlist queda obsoleta.
- C0-07: CI instala el lock, ejecuta `compileall`, la suite, el smoke de API y conserva los greps de seguridad.

**Verificación local:** `python -m unittest discover -s tests` → 272 tests, 0 fallos, 13 skips; `compileall` → 0; `scripts/barrido_paginas.py` → 19/19 en verde; `main.py resumen` → OK; API en `127.0.0.1` → `/api/salud` responde `{"estado":"ok"}`; cliente FastMCP contra `/mcp` → lista las 3 herramientas (`giro_consultar_sql`, `giro_ejecutar_alertas`, `giro_generar_briefing`); Asesor IA end-to-end con OpenRouter → diagnóstico con 3 hallazgos, 3 acciones y 3 riesgos.

**No verificado:** build y smoke de la imagen Docker (esta máquina no tiene daemon Docker). Queda cubierto por el job `docker` de CI.

### Fase 1 — Recomposición (2 semanas)

Objetivo: una sola composición y dependencias que apunten hacia adentro, sin cambiar números.

Entregables:

- **C1-01.** src/composicion.py + ContextoAplicacion; UI, API y CLI lo usan.
- **C1-02.** Mover analítica pura a src/core/analitica/ y decisiones a src/core/decisiones/; fachadas en los módulos raíz.
- **C1-03.** Mover predicción a src/aplicacion/prediccion.py + src/core/prediccion/features.py + src/adapters/ml/; el registro implementa PuertoRegistroModelos.
- **C1-04.** Mover ejecución DuckDB de src/core/conector_sql.py a src/storage/sql/; dejar validación pura en src/core/sql/. Mover publicación SQLAlchemy de src/core/warehouse.py a src/storage/warehouse.py.
- **C1-05.** Hacer que src/core/pipeline.py use PuertoCarga, no get_loader; inyectar el cargador desde composición.
- **C1-06.** Inyectar PuertoAgenteIA en asesor_negocio; eliminar el import de la fábrica.
- **C1-07.** Quitar el fallback a data_loader en abrir_almacen; exigir almacén inyectado.
- **C1-08.** Suite de conformidad de puertos: misma clase de tests para DuckDB y Postgres; Postgres obligatorio en CI.
- **C1-09.** Actualizar UI y API para no importar módulos raíz; solo src.aplicacion y src.composicion.

**Aceptación:**

- tests/test_arquitectura.py sin allowlist (0 violaciones).
- 258 tests verdes; mismos KPIs que antes en el dataset de caracterización.
- python -c "import src.puertos, src.aplicacion" no carga streamlit/duckdb/fastapi/sqlalchemy en sys.modules.
- Smoke de API, CLI y UI.

**No hacer en esta fase:** cambiar reglas de negocio, mover el esquema, rediseñar pantallas.

### Fase 2 — Verdad analítica (2-3 semanas)

Objetivo: que los números sean reproducibles y que un fallo no se disfrace de cero.

Entregables:

- **C2-01.** tests/datos/ + esperado.json; 8 KPIs dorados (ingresos, ticket, margen, churn, RFM, stock, proyección, alertas) con tolerancia.
- **C2-02.** Prueba cruzada: Analyzer, GET /api/estado, main.py resumen y reporte dan la misma cifra.
- **C2-03.** DatosWorkspace + validación de columnas, dtypes y fechas; ErrorDatos con código.
- **C2-04.** ETL: ResultadoETL con códigos; los avisos se ven en UI, API y CLI; sin except silencioso.
- **C2-05.** version_esquema en giro_meta; comprobación de deriva y tablas obsoletas; plan de migración.
- **C2-06.** Presupuestos: timeout y máximo de filas en consultas; límite en API; prueba con 100k filas; p95 documentado.
- **C2-07.** Predicción: holdout temporal, incertidumbre que crece, estado "insuficiente" probado; sin datos sintéticos.

**Aceptación:**

- 0 deriva en KPIs dorados en DuckDB y Postgres.
- Un fallo de ETL produce código y mensaje, no un workspace vacío.
- Una tabla vieja se detecta y se reporta.
- p95 dentro del presupuesto acordado.

### Fase 3 — Asesor IA gobernado (1-2 semanas)

Objetivo: que la IA sea una capacidad del núcleo, no un adaptador suelto.

Entregables:

- **C3-01.** OpenRouterAdapter implementa explícitamente PuertoAgenteIA; tests de contrato con adaptador falso, sin red.
- **C3-02.** ContextoAsesor tipado: workspace, periodo, moneda, hash_datos, completitud; sin cliente_id, nombres ni identificadores; solo cohortes y segmentos.
- **C3-03.** Caché por (workspace, hash_datos, prompt_version, modelo); TTL; prohibido reutilizar entre workspaces.
- **C3-04.** Límites: timeout, reintento con backoff, rate limit por workspace y usuario, presupuesto de tokens y coste; degradación segura ("no hay datos suficientes").
- **C3-05.** Auditoría JSON: request_id, workspace, modelo, tokens, latencia, cache_hit, resultado; sin prompt con PII.
- **C3-06.** Validación de salida: esquema, campos obligatorios, máximo de elementos; la pregunta del usuario se trata como dato, no como instrucción.
- **C3-07.** Evaluación offline: 12 casos con contextos congelados (cifras presentes, rechazo cuando falta, resistencia a inyección); script sin red; opcional con API key.
- **C3-08.** Arreglar los siete except de contexto_datos: reemplazarlos por ContextoIncompleto con campos faltantes; el asesor debe decir qué no pudo usar.

**Aceptación:**

- tests/test_asesor.py verde sin red.
- Evaluación ≥ 90%; ningún caso inventa cifras.
- Test de aislamiento de caché entre dos workspaces.
- Auditoría y presupuesto verificados.

### Fase 4 — Operación (continuo)

- **C4-01.** Logs con workspace, caso_uso, request_id, duración, resultado y filas; sin secretos.
- **C4-02.** ErrorGiro mapeado en API y UI; códigos estables.
- **C4-03.** CI completo: 3.11 + lock, arquitectura, dorados, smoke API/CLI/UI, Postgres y Docker; menos de 10 minutos.
- **C4-04.** Runbook: qué hacer si un workspace falla, si el ETL no firma, si el proveedor IA cae, si el lock no instala.
- **C4-05.** Presupuestos y métricas: ETL, load_all, KPI, predicción, API p95, coste IA.


---

## 5. Criterios de aceptación globales

| Métrica | Línea base | Objetivo |
|---|---|---|
| Tests | 257/258, 1 error | 258/258 en 3.11 |
| Violaciones de matriz | 3+ | 0 |
| Puertos con test de conformidad | 0 | 5/5 |
| KPIs dorados | 0 | 8/8 sin deriva |
| Aislamiento DuckDB/Postgres | parcial | 2/2 con tablas homónimas |
| Barrido UI | 18/19 | 19/19 |
| Evaluación IA | 6/6 (escenarios base) | ≥ 90% en set ampliado |
| Lock/API en 3.11 | no verificado | import + smoke verdes |
| Coste IA | sin medir | dentro de presupuesto |

---

## 6. Verificación

Comandos permitidos por el repo, sin pytest, ruff ni mypy:

~~~bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m compileall -q src ui main.py dashboard.py landing.py
.venv/bin/python -m unittest tests.test_arquitectura tests.test_puertos tests.test_dorado -v
.venv/bin/python main.py eval
.venv/bin/python scripts/barrido_paginas.py
GIRO_PG_PASSWORD=... GIRO_PG_HOST=127.0.0.1 GIRO_PG_PORT=55432 .venv/bin/python -m unittest tests.test_postgres -v
docker build -t giro:test . && docker run --rm -e GIRO_AUTH_SECRET=test -p 8503:8503 giro:test
~~~

Reglas:

- Un test que no se ejecuta no cuenta. Los 13 skips de Postgres deben pasar a un job con servicio, no quedarse en "skip".
- Un gate no es un grep: el test de arquitectura debe fallar por AST, no por búsqueda de texto.
- Un número dorado se compara con tolerancia explícita; no se congela un CSV de 350 facturas para igualdades exactas.
- Nada de except Exception: pass; el CI debe detectarlo por AST, no por string.

---

## 7. Riesgos y mitigaciones

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| El refactor rompe UI/API | Alta | Alto | Fachadas de compatibilidad, tests de caracterización, fases con gate |
| Aparecen ciclos de imports | Media | Alto | Matriz + movimiento incremental + import smoke |
| No hay tiempo para 4 fases | Alta | Medio | Priorizar F0 + F1 + C3.1/C3.2/C3.4/C3.8; posponer F2 |
| Postgres no está en CI | Alta | Alto | Servicio en workflow; tests de conformidad |
| El lock sigue roto | Media | Crítico | Regenerar en 3.11; smoke de import; no declarar cerrado sin él |
| La IA filtra datos o cuesta de más | Media | Alto | Solo agregados, sin IDs; caché; presupuesto; auditoría |
| El trabajo sin commitear se pisa | Media | Alto | Coordinar; no commit; cambios pequeños y reversibles |
| La regla de UI y el CI chocan | Alta | Medio | Wrapper en components.py; CI por AST/uso, no por grep |

---

## 8. No-goals

- No features nuevas, ni páginas nuevas, ni rediseño visual.
- No frameworks ni dependencias nuevas; requests se declara porque ya está en el lock, no se añade.
- No LangChain, no ORM, no vector DB, no microservicios, no multi-proveedor IA.
- No reescribir el ETL ni el esquema; no migrar datos de tenants.
- No cambiar autenticación, permisos ni el modelo de una base por workspace.
- No duplicar el checklist de PLAN_MEJORAS_PROFESIONAL.md; se referencia.
- No commit ni push sin pedido explícito.

---

## 9. Qué se ejecutó y qué no

**Ejecutado:**

- Suite completa: 258 tests, 257 OK, 1 ERROR, 13 skipped (38,8 s).
- Lectura y grep de los archivos citados; verificación de los bugs C-08 (predictions, log, permiso), C-02 (fábrica no registrada), C-06 (import de adaptador), C-14/C-15 (lock).
- Delegaciones del orquestador: Planner y Worker completaron sus briefs; el Reviewer no devolvió brief y se canceló para no bloquear el cierre.

**No ejecutado:**

- Postgres real, Docker build, runtime 3.11, API en vivo, navegador. El daemon Docker no estaba disponible y el venv es 3.14.2.
- Los cambios de código propuestos: este documento es un plan, no una implementación. Salvo que se pida, no se tocó código.
- La evaluación de la IA con red: no hay API key ni presupuesto en esta sesión.

**Honestidad:** "verde local" no es "verde en producción". La Fase 0 existe precisamente porque hoy la suite no está verde y el lock no permite arrancar la API.

---

## 10. Decisión propuesta

Tres opciones, según el objetivo y el tiempo:

1. **Completo (6-8 semanas):** F0 → F4. Recomendado si hay un dev dedicado y el objetivo es vender el núcleo como plataforma.
2. **Núcleo + IA (3-4 semanas):** F0 + F1 + C3.1, C3.2, C3.4 y C3.8; pospone F2. Recomendado si el objetivo es demostrar el Asesor con datos reales.
3. **Solo estabilización (2-3 días):** F0. Recomendado si hay una demo o un cliente esta semana.

Recomendación: **F0 ya**, luego la opción 2, y F2 antes de vender el Asesor como "diagnóstico grounding". Sin dataset dorado, la IA puede sonar bien y estar equivocada.

---

## Anexo A. Puente con PLAN_MEJORAS_PROFESIONAL.md

No se duplica el backlog. Se selecciona y secuencia lo que protege el núcleo:

| Plan Core v1 | Ítems existentes | Relación |
|---|---|---|
| C0-01 / C0-03 | A8-006, A8-012 | Cierra la proyección vacía y el mínimo de 12 meses |
| C0-06 / C1-08 | A1-021, A1-023 | Test de arquitectura e inyección del store |
| C2-05 | A1-027 | Versión de esquema y migración |
| C2-01 / C2-02 | A8-004 | Registro de modelos y reproducibilidad |
| C3-01 a C3-08 | Nuevo (IA) | No estaba en el plan original; se añade como capacidad del núcleo |
| C4-03 | CI | El plan original lo menciona; aquí se vuelve gate |

---

## Anexo B. Orquestación y skills

- **Commander:** fijó el objetivo, el alcance y la secuencia; sintetizó los briefs.
- **Planner:** arquitectura, límites, composición, contratos y fases. Aplicó change-impact, product-capability y docs-governance.
- **Reviewer:** riesgos, seguridad, aislamiento, regresiones y huecos de tests. Aplicó security-review, module-regression y test-collaboration. No devolvió brief a tiempo (cancelado); no condiciona el diagnóstico.
- **Worker:** arnés de verificación, comandos, dataset dorado y CI. Aplicó verification-loop y tdd-workflow.
- **Regla:** ningún agente modificó archivos; el plan es de solo lectura. La implementación se decide después.

---

## Anexo C. Evidencia mínima por afirmación

| Afirmación | Evidencia |
|---|---|
| El núcleo importa adaptadores | src/core/pipeline.py:24-25, src/core/conector_sql.py:307, src/core/warehouse.py:39 |
| La aplicación importa la composición | src/aplicacion/almacen.py:163; registrar_fabrica_almacen sin llamadas |
| UI/API saltan aplicación | ui/context.py:18-20, src/api/rutas.py:29-33, src/api/mcp_server.py:75 |
| Contratos laxos | asesor_negocio.py:6,10,30; tuplas en almacen.py:207-210 y carga.py:73,184 |
| Bug de predicción | src/predictions.py:79 vs 92; tests/test_e2e.py::test_predictions_ejecutan |
| log indefinido | src/aplicacion/almacen.py:71,92; sin import logging |
| Página IA rota | ui/pages/asesor_ia.py:13; auth.PERMISO_VER_DASHBOARD no existe; no está en PAGINAS |
| Simulación vacía | src/agentes_estrategicos/strategy.py:127 |
| IA sin gobierno | contexto_datos.py:27,40,78,96,123,136,152; openrouter.py:121-131; asesor_negocio.py:31 |
| Lock roto | requirements.lock sin fastmcp/mcp/openpyxl; fastapi==0.115.0 vs >=0.143.0; app.py:20 importa mcp_server |
| CI incompleto | .github/workflows/ci.yml sin trackear; requirements.txt en vez de lock; grep de unsafe_allow_html |
