---
description: Audita y repara la estructura de una pantalla Streamlit — copy, layout, énfasis, accesibilidad y feedback. Puntúa 5 dimensiones, repara en orden A→L→C→E→R y verifica.
---

# /ade-build — Auditoría y reparación de estructura de UI

Auditas una pantalla o componente contra el framework **Build**, y **arreglas** lo que está roto. No solo reportas.

**Objetivo de la invocación:** `$ARGUMENTS`
(Si está vacío, trabaja sobre `ui/pages/resumen.py` — la pantalla principal del dashboard — y dilo.)

## Qué evalúa Build

| Dimensión | Pregunta | Prioridad |
|---|---|---|
| **A** — Accesibilidad | ¿Puedo usarlo cualquiera? (teclado, lector de pantalla, contraste, targets) | **1 — siempre primero** |
| **L** — Layout | ¿La información está ordenada con jerarquía y espaciado consistente? | 2 |
| **C** — Copy | ¿El texto es claro, humano y orientado a la acción? | 3 |
| **E** — Énfasis | ¿Hay exactamente UNA acción primaria por viewport? | 4 |
| **R** — Recompensa | ¿Toda acción da feedback? ¿Los errores son compasivos? | 5 |

**Umbral de aprobación: 40/50.** Por debajo de 40, la pantalla no está lista y lo dices.

## Paso 0 — Retrato del producto (obligatorio)

Antes de evaluar, construye el retrato. Si no lo tienes, léelo del código:

- **Dominio**: BI para PYMEs. Los datos de ejemplo son de un taller mecánico; el esquema es transversal.
- **Persona**: dueño o gerente de una pyme, sin alfabetización analítica, 3 minutos al día.
- **Densidad**: alta → clasificación **`data-heavy` + `enterprise`**.
- **Peso emocional**: routine profesional con picos de high-stakes (facturación, churn, inventario).
- **Análogo físico**: un tablero de control de taller — needles, filas de trabajo, paneles de checking.

Si algo es ambiguo, haz **una** pregunta concreta. No cinco vagas.

## Paso 1 — Lee la pantalla completa

No edites a ciegas. Lee la página **y los componentes que usa** (`ui/components.py`, `ui/theme.py`, `ui/context.py`). Identifica:

- Todo el texto visible: títulos, etiquetas, botones, errores, estados vacíos
- Estructura de layout: contenedores, columnas, tabs, espaciado
- Elementos interactivos: botones, inputs, selects, descargas, links
- Jerarquía visual: qué es más grande, más brillante, más prominente
- Mecanismos de feedback: `st.spinner`, `st.status`, `st.success`, `st.error`, `st.warning`, `st.empty`

## Paso 2 — Puntúa cada dimensión (0-10)

| Puntuación | Significado |
|---|---|
| 9-10 | Excelente. Sin violaciones. |
| 7-8 | Bien. Problemas menores que no bloquean. |
| 5-6 | Aceptable. Varios problemas que degradan la experiencia. |
| 3-4 | Malo. Problemas que lastiman la usabilidad. |
| 0-2 | Fallando. Problemas que bloquean al usuario. |

Para `data-heavy` + `enterprise`: **AA mínimo**, copy preciso y denso, layout en grid denso pero escaneable, controles de filtro y orden prominentes, **feedback inline, nunca modales**.

## Paso 3 — Repara en orden A → L → C → E → R

### A — Accesibilidad (prioridad 1, siempre primero)

| Violación | Reparación en Streamlit |
|---|---|
| Navegación por teclado rota | Todo interactivo debe ser widget nativo (`st.button`, `st.link_button`, `st.download_button`, `st.form`). Nunca un `div` con `onclick` de JS. `tabindex` solo para elementos custom. |
| Foco invisible | Añade `outline` o `box-shadow` en `:focus-visible` vía CSS. **Prohibido `outline: none` sin reemplazo.** |
| Contraste < 4.5:1 (texto normal) | Oscurece el texto o aclara el fondo hasta llegar a 4.5:1. Verifica contra la `PALETA` real de `ui/components.py`, no de memoria. Modo claro: `#fbfdff`. Modo oscuro: fondo de `[theme.dark]`. |
| Contraste < 3:1 (texto 18px+) | Igual, con el umbral más bajo. |
| Jerarquía de títulos rota | Un solo `h1` por pantalla, sin saltarse niveles. Streamlit no lo expone → controla con CSS, no confíes en el default. |
| Targets interactivos < 44px | `min-height: 44px` en el CSS de `st.button` / `st.download_button` / `st.form_submit_button`. |
| Sin skip-to-content | Añade un skip-link como primer hijo del contenedor principal. |
| Información solo por color | Añade icono, patrón o texto junto al color. Aplica a series de gráficos con paleta parecida. |
| Etiquetas crudas en inputs | Nunca índices ni nombres de columna: `label=` legible, o dict de opciones con claves en español. |
| Texto de ejes en crudo | `titulo`, `xlabel`, `etiquetas` en los wrappers de `ui/components.py`, no el nombre de la columna. |

### L — Layout (prioridad 2)

| Violación | Reparación |
|---|---|
| Sin sistema de espaciado | Define `--space-1` … `--space-9` (base 4px) en el scope del tema. Reemplaza `padding`/`margin`/`gap` arbitrarios por tokens. |
| Espaciado inconsistente | Todo el `margin`/`padding`/`gap` pasa por tokens. |
| Sin jerarquía visual | Diferencia con **tamaño Y peso**, no solo con color. |
| Contenido sin agrupar | Gestalt proximity: relacionados a `--space-2`/`--space-3`, grupos distintos a `--space-6`/`--space-8`. Usa `st.container(border=...)` y `st.columns`, no `<br>`. |
| Texto sin max-width | `max-width: 65ch` en prosa larga, `margin: 0 auto`. Tablas y gráficos van anchos. |
| Tabs para todo | `st.tabs` solo entre contenidos de peso distinto. Tabs implican jerarquía. |
| Scroll horizontal de página | Las tablas anchas van en un contenedor con scroll propio. |
| Breakpoint roto | Funcional de 360px a 1920px. `st.columns` con `stack` cuando corresponda. |

### C — Copy (prioridad 3)

Todo en **español**, en la voz del negocio. Consistencia de términos: `factura`, `cliente`, `vehículo`, `orden`, `workspace`.

| Violación | Reparación |
|---|---|
| Botón en voz pasiva | Verbo activo: "El archivo puede subirse" → "Subir archivo". |
| Etiquetas genéricas | `Submit` → "Guardar cambios". `OK` → "Crear cliente". `Cancel` → "Volver". |
| Errores que culpan | "Entrada inválida" → "No pudimos leer el CSV. Revisa que tenga: cliente_id, fecha, total." |
| Estado vacío sin salida | Siempre con `vacio(mensaje, detalle=...)` de `ui/components.py`: "Aún no hay facturas. Importa un CSV o genera datos de ejemplo." |
| Nombres de columna como etiqueta | `total` → "Total facturado". `clientes_recurrentes` → "Clientes que vuelven". |
| Jerga técnica | Nivel de lectura 6-8. Una etiqueta de KPI, no un párrafo. |
| Cifras sin unidad ni periodo | Usa `miles()` y `moneda()`. Nunca `str()` crudo. |

### E — Énfasis (prioridad 4)

| Violación | Reparación |
|---|---|
| Varias acciones primarias compitiendo | Degrada todas menos la importante a secundario o fantasma. |
| Sin acción primaria clara | Identifica LA cosa que el usuario debería hacer. Que sea la más grande, la de más contraste, la primera. |
| Peso no distribuido por ratio áureo | Primaria 100%, secundaria 61.8%, terciaria 38.2%. Aplícalo en tamaño, color y posición. |
| KPIs desordenados | Lo que se monitorea arriba; lo que se investiga abajo. |

### R — Recompensa (prioridad 5)

| Violación | Reparación |
|---|---|
| Acción sin estado de carga | `st.spinner("Calculando…")` con mensaje, o `st.status()` para cargas largas. Nunca spinner mudo. |
| Sin confirmación de éxito | `st.success(...)` tras generar, guardar o exportar. El usuario debe saber qué pasó. |
| Error como recarga o modal | `st.error` inline, junto al control que falló. Nunca modal para validación. |
| Sin feedback hover/focus | CSS: `transform: translateY(-1px)` + `box-shadow` en hover, `transform: scale(0.98)` en `:active`. |

## Paso 4 — Verifica (no te lo saltes)

1. **Este repo no tiene build ni lint.** No corras `npm`, `ruff` ni `pytest` esperando que existan.
2. Verifica sintaxis: `.venv/bin/python -c "import ast; ast.parse(open('ARCHIVO').read())"`.
3. Mejor aún: `.venv/bin/python -c "import ui.pages.MODULO"` para confirmar que el módulo importa.
4. Si puedes, levanta la app: `.venv/bin/streamlit run dashboard.py` (o `landing.py` si es esa pantalla) y **mira el render**.
5. **Repuntúa las 5 dimensiones** y confirma que subieron.
6. Si no pudiste ver la UI renderizada, **dilo explícitamente** en el reporte. No afirmes que se ve bien si no lo viste.

## Paso 5 — Reporta

```markdown
## Build Audit — [pantalla]

| Dimensión | Antes | Después | Estado |
|---|---|---|---|
| A — Accesibilidad | X/10 | Y/10 | Corregido / Mejorado / Sin cambios |
| L — Layout | X/10 | Y/10 | |
| C — Copy | X/10 | Y/10 | |
| E — Énfasis | X/10 | Y/10 | |
| R — Recompensa | X/10 | Y/10 | |
| **Total** | **XX/50** | **YY/50** | objetivo 40+ |

### Violaciones corregidas
- `archivo:línea` — qué cambió

### Issues restantes
- severidad (critical/major/minor) — por qué no se corrigió

### Verificación
- comandos ejecutados y salida real
- si viste el render o no

### Bloqueantes
- lo que un componente no soporta y exige decisión del usuario
```

**No escribas archivos de log en el repo.** Este proyecto se entrega a clientes; no dejes artefactos de auditoría ahí. El reporte va en la conversación. Si el usuario quiere persistirlo, lo pide.

### Handoff

- **40+**: "La estructura pasa. Si quieres que la pantalla se sienta como un lugar y no como una tabla genérica, `/ade-style`."
- **<40**: "La estructura necesita más trabajo: [issues críticos]. Arreglalos antes de ir a la atmósfera."

## Lo que NO haces

- No añadas features ni funcionalidades que no existen.
- No refactorices código ajeno a la violación.
- No añadas comentarios ni docstrings a código que no modificaste.
- No cambies la atmósfera visual — eso es `/ade-style`.
- No añadas interactividad ni animaciones — eso es `/ade-move`.
- No cambies la voz del copy más allá de claridad — eso es `/ade-write`.
- No escribas `st.plotly_chart`, `st.dataframe` crudo ni HTML suelto. Todo pasa por `ui/components.py`.
- No toques `.streamlit/config.toml` para arreglar una pantalla.
- No muestres datos reales de tenants ni secretos en ejemplos o capturas.
- No commitees.

**Arregla la estructura. Nada más. Nada menos.**
