---
description: Revisa y reescribe el copy de la UI — botones, errores, estados vacíos, textos de carga, tooltips — para que suene intencionado, cercano y en español correcto. No copy genérico de IA.
---

# /ade-write — Pase de copy

Revisas el texto que ve el usuario y reescribes lo que suena genérico, frío o mecánico. Todo en **español**, en la voz del negocio.

**Objetivo de la invocación:** `$ARGUMENTS`
(Si está vacío, trabaja sobre `ui/pages/resumen.py` y dilo.)

**Scope:** solo el copy de la UI. **No** documentación, no mensajes de commit, no comentarios de código, no docstrings.

## Precondición

No necesita ir después de `/ade-build` ni de `/ade-style` — puede correr solo. Pero si ya hay una metáfora establecida por `/ade-style`, el copy debe hablar su lenguaje (Principio 7).

## Paso 0 — Retrato del producto

La persona y el peso emocional determinan la calibración del tono. GIRO:

- **Persona**: dueño o gerente de una pyme, sin alfabetización analítica, 3 minutos al día.
- **Peso emocional**: routine profesional con picos de high-stakes. La calidez **nunca** puede reducir la precisión de un número ni el seriousness de una alerta.
- **Idioma**: español. Tono: cercano y respetuoso, como un contador competente explicándote tu propio negocio.

## La voz en una frase

*Un guía claro que descompone lo complejo, que te trata como alguien capaz, y que conecta el dato con lo que significa para tu negocio.*

**No** es un profesor condescendiente, **no** es un vendedor sonriendo, **no** es un sistema de alertas.

## Paso 1 — Escanea todo el copy

Extrae cada texto visible del usuario:

| Categoría | Ejemplos en GIRO |
|---|---|
| Títulos de página | `cabecera(titulo=...)`, `titulo_seccion(...)` |
| Etiquetas de botones | `st.button("Generar reporte")` |
| Elementos de form | `label=`, placeholders, `help=` |
| Mensajes de error | `st.error(...)` en carga de CSV, login, conexión |
| Estados vacíos | `vacio(mensaje, detalle=...)` |
| Estados de carga | `st.spinner(...)`, `st.status(...)` |
| Confirmaciones | `st.success(...)` |
| Navegación | títulos de `st.sidebar`, `st.tabs` |
| Tooltips | `help=` en botones e inputs |
| Metadatos | fechas, conteos, unidades |

## Paso 2 — Aplica los siete principios

### Principio 1 — Cercanía, no distancia

| Frío | Cercano |
|---|---|
| "Debe introducir una contraseña" | "Necesitamos tu contraseña para entrar" |
| "Su sesión ha expirado" | "Tu sesión se cerró. Volvamos a entrar." |
| "Error de autenticación" | "Ese usuario o esa contraseña no coinciden." |
| "Acceso denegado" | "Esta sección necesita un usuario con permisos de administrador." |
| "No autorizado" | "Primero entra con tu cuenta." |

### Principio 2 — La brevedad es kindness

Cada palabra de más es fricción. Recorta hasta que duela, luego devuelve **una** palabra.

| Verboso | Breve |
|---|---|
| "Por favor haz clic en el botón para enviar tu formulario" | "Guardar cambios" |
| "No se encontraron resultados que coincidan con tus criterios de búsqueda" | "Nada coincide. Prueba otros términos." |
| "Ocurrió un error al procesar tu solicitud" | "Algo falló. Intenta en un momento." |
| "¿Estás seguro de que quieres eliminar este registro? Esta acción no se puede deshacer." | "¿Eliminar este registro? No se puede deshacer." |
| "Cargando datos del workspace principal…" | "Abriendo tu taller…" |

### Principio 3 — Propósito antes que acción

La gente necesita saber **por qué** antes de saber **qué**.

| Solo acción | Con propósito |
|---|---|
| "Iniciar sesión" | "Entra a tu taller" |
| "Subir CSV" | "Tus datos de este mes" |
| "Filtrar por año" | "Mira solo el 2026" |
| "Exportar datos" | "Llévate el detalle en Excel" |
| "Generar reporte" | "Tu resumen del mes, listo para enviar" |

### Principio 4 — Invita, no ordenes

| Comando | Invitación |
|---|---|
| "Selecciona un cliente" | "¿De quién quieres el historial?" |
| "Elige un periodo" | "¿Qué mes te interesa?" |
| "Ingresa tu email" | "¿A quién te enviamos el reporte?" |

### Principio 5 — Conecta el dato con lo que significa

| Desconectado | Conectado |
|---|---|
| "91 registros" | "91 facturas este mes" |
| "Cargando..." | "Abriendo el almacén…" |
| "Guardado" | "Listo, ya está en tu registro" |
| "Error 404" | "Esa pantalla no existe. Vuelve al resumen." |
| "42" | "42 facturas este mes" |

Un número sin unidad ni periodo no es un dato. **Es el defecto de copy más frecuente en este tipo de producto.**

### Principio 6 — Errores compasivos (nunca culpables)

El error debe sentirse como un colega que ayuda, no como un portero.

| Culpable | Compasivo |
|---|---|
| "Contraseña inválida" | "Esa contraseña no coincide. Prueba otra vez." |
| "Campo requerido" | "Necesitamos esto para continuar." |
| "Formato inválido" | "Eso no se ve bien. Prueba con: cliente, fecha, total." |
| "Demasiados intentos" | "Vamos más despacio. Intenta en un minuto." |
| "Error de servidor" | "Falló algo de nuestro lado. Ya lo estamos revisando." |
| "No se pudo leer el archivo" | "No pudimos leer ese CSV. Revisa que tenga las columnas: cliente_id, fecha, total. Si falta algo, dinos cuál y te ayudamos." |

El error tiene que **decir qué hacer**, no solo qué falló. Para un dueño de taller, "Error de formato" es un muro.

### Principio 7 — Lenguaje de metáfora (si `/ade-style` ya corrió)

| Genérico | Metáfora: taller | Metáfora: sala de control |
|---|---|---|
| "Iniciar sesión" | "Entrar al taller" | "Abrir el turno" |
| "Ver detalle" | "Abrir la orden" | "Revisar la señal" |
| "Cargando" | "Consultando el taller…" | "Ajustando el dial…" |
| "Sin datos" | "Aún no hay órdenes registradas" | "Sin señal en este canal" |
| "Volver" | "Regresar al tablero" | "Volver a la vista general" |

**Consistencia absoluta**: no mezcles metáforas en una misma pantalla.

## Paso 3 — Reescribe y aplica

Para cada texto que viola un principio:
1. Identifica el principio violado
2. Escribe el reemplazo
3. Edita el archivo directamente

### Reglas de copy de este repo (no negociables)

- **Es una herramienta de negocio, no un juego.** La calidez no puede reducir la precisión de un número. "Tu margen cayó 8 puntos" no se suaviza a "tu margen bajito".
- **Los errores de datos son técnicos y deben decirlo.** "No pudimos leer el CSV. Faltan las columnas: cliente_id, fecha." Eso es información útil, no un error feo.
- **El copy de un modelo predictivo debe declarar su incertidumbre.** "Estimamos 12 clientes en riesgo" no "12 clientes se irán".
- **Consistencia de términos, siempre**: `factura`, `cliente`, `vehículo`, `orden`, `servicio`, `producto`. Nunca mezcles "factura"/"invoice" ni dos sinónimos para lo mismo.
- **Números con `miles()` y `moneda()`.** Nunca `str()` crudo.
- **Tú / usted:** el repo usa español de PyMME. Elige una forma y mantenla. Mezclar "tú" y "usted" en la misma pantalla es un bug de voz.

**No cambies:**
- Copy técnico que el usuario no ve (logs, nombres de variables)
- Copy que `/ade-style` ya transformó a lenguaje de metáfora
- Errores que ya son compasivos
- Etiquetas que ya son específicas y activas

## Paso 4 — Verifica consistencia

Lee todo el copy de la pantalla en orden. Debe sonar como **una sola persona** hablando.

- [ ] Sin niveles de formalidad mezclados (nada de "¡Hola!" junto a "Se le informa")
- [ ] Consistencia de "tú" / "usted"
- [ ] Metáforas consistentes (no dos en una pantalla)
- [ ] El tono de los errores es el mismo que el del éxito (misma persona, distinta situación)
- [ ] Ningún número sin unidad ni periodo
- [ ] Nada suena a texto generado por máquina
- [ ] Los estados vacíos dicen qué hacer a continuación

## Paso 5 — Reporta

```markdown
## Write Review — [pantalla]

**Copy revisado**: N elementos de texto
**Reescrituras**: N

### Puntuaciones
| Principio | Antes | Después | Delta |
|---|---|---|---|
| 1 — Cercanía | /10 | /10 | |
| 2 — Brevedad | /10 | /10 | |
| 3 — Propósito | /10 | /10 | |
| 4 — Invitación | /10 | /10 | |
| 5 — Conexión | /10 | /10 | |
| 6 — Compasión | /10 | /10 | |
| 7 — Metáfora | /10 | /10 | |
| **Total** | **/70** | **/70** | objetivo 40+ |

### Cambios
| Elemento | Antes | Después | Principio |
|---|---|---|---|
| Botón | "Generar" | "Tu resumen del mes, listo para enviar" | Propósito |
| Error | "Formato inválido" | "No pudimos leer el CSV. Revisa que tenga: cliente_id, fecha, total." | Compasión |
| Vacío | "Sin datos" | "Aún no hay facturas. Importa un CSV o genera datos de ejemplo." | Conexión |
| Predicción | "Clientes en riesgo" | "Estimamos 12 clientes en riesgo" | Precisión |

### Consistencia de voz
[coherente / necesita trabajo + el motivo]

### Archivos modificados
- [lista]
```

**No escribas archivos de log en el repo.** El reporte va en la conversación.

### Handoff

> "El copy ya suena intencionado: la pantalla funciona (`/ade-build`), se siente como un lugar (`/ade-style`) y habla con voz humana (`/ade-write`)."

## Lo que NO haces

- No cambies la estructura — eso es `/ade-build`.
- No cambies la atmósfera — eso es `/ade-style`.
- No reescribas copy que ya está bien.
- No alargues el copy para que suene "más cálido". **Calidez y brevedad coexisten.**
- No uses emojis salvo que el usuario lo pida explícitamente.
- No sacrifiques claridad por personalidad. **Claro siempre gana.**
- No suavices un dato malo. Un número feo con contexto vale más que un número dorado sin contexto.
- No commitees.
