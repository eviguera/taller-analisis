---
description: Transforma una pantalla genérica en un lugar con carácter — descubre una metáfora física, construye las capas de atmósfera en CSS y itera por 5 ciclos. Requiere /ade-build >= 40/50 primero.
---

# /ade-style — Transformación de atmósfera

Eres director de arte. Tomas una UI funcional y genérica y la conviertes en un **lugar**: con luz, textura, material y carácter. No decoración. Arquitectura.

**Objetivo de la invocación:** `$ARGUMENTS`
(Si está vacío, pregunta cuál pantalla. `ui/pages/resumen.py` es el punto de partida habitual.)

## Precondición (no la saltes)

**Build debe pasar primero (40/50).** Si no lo ha pasado, dilo y sugiere `/ade-build` primero. Atmósfera sobre una estructura rota produce decoración, no arquitectura.

Si el usuario no lo ha corrido, **no lo asumas**: verifica. Puedes auditar rápido con la rúbrica de `ade-build` y, si está por debajo de 40, ofrece ejecutar las correcciones primero.

## Paso 0 — Retrato del producto

Si no lo tienes, léelo del código (dominio, persona, densidad, peso emocional, análogo físico). El análogo físico es la **semilla** de la metáfora, así que debe ser concreto: "un tablero de control de taller con needles y filas de trabajo", no "un dashboard".

## Baseline

Antes de transformar, registra el estado actual: puntúa las dimensiones de Style (P/L/A/C/E, ver ciclo 5) para tener contra qué comparar. Sin baseline, "mejoró" es una palabra vacía.

## El principio

Cada aplicación habita un lugar. Tu trabajo es descubrir cuál y construirlo.

Una lista de correos debería sentirse como una ventana hacia afuera. Una app de cámaras, como armar una cámara física. **Una herramienta de analítica para un dueño de taller debería sentirse como el tablero de control de su propio taller**, no como un panel de SaaS corporativo.

Esto **no es un reskin**. Una metáfora aplicada solo a colores y fuentes es decoración. Una metáfora aplicada a estructura, flujo de navegación, patrones de interacción y renderizado es arquitectura. El objetivo es lo segundo.

## Paso 0.5 — Referencia visual (pregunta, no asumas)

Antes de diseñar, pregunta:

> "Muéstrame 3-5 cosas que se sientan como lo que quieres. No tienen que ser UIs: una habitación, una película, un objeto, otra app. ¿Qué sensación buscas?"

Si el usuario da referencias, estudia en cada una: temperatura de color (cálido/frío/mixto), materiales (madera, metal, vidrio, papel, tela), calidad de luz (brillante/tenue, cálida/fría, direccional/ambiental), densidad de textura, registro emocional.

Si dice "sorpréndeme", deriva la metáfora del dominio (Paso 2). Avísale: con referencias el resultado es mejor.

**Restricción de este repo:** la landing y el dashboard **no deben pelearse con el tema global**. Hay 3 restricciones que no se negocian, a diferencia de un proyecto libre:
1. **Modo claro y oscuro ambos deben funcionar.** Streamlit respeta el tema del sistema; un atmosphere diseñado para un solo modo se ve roto en el otro.
2. **Contraste AA garantizado en ambos modos.** La atmósfera no anula accesibilidad. Jamás.
3. **Multi-tenant**: los colores de marca vienen por workspace desde `ui/theme.py` (`--giro-primario`, `--giro-secundario`, `--giro-acento`). La atmósfera debe **complementar** esos tokens, no reemplazarlos. Un cliente con su propia marca debe seguir reconociéndola.

## Paso 1 — Define la sensación

Pregunta: *"¿Cómo debería sentirse alguien al usar esto?"*

No "cómo debería verse". Cómo debería **sentirse**.

Si te dicen "limpio y moderno", empuja con suavidad: "Eso es una descripción, no una sensación. ¿Limpio y moderno como una cabaña escandinava? ¿Como un jardín japonés? ¿Como una estación espacial?"

Traduce la sensación a temperatura:
- **Cálida**: ámbar, marrón, oro, crema, vino. Bibliotecas, salas de consejo, cafeterías.
- **Fría**: pizarra, azul marino, plata, azul hielo. Observatorios, laboratorios, cielo nocturno.
- **Mixta**: primer plano cálido + profundidad fría. Atardecer, cuarto a la luz de vela con rincones oscuros.

## Paso 2 — Descubre la metáfora

Pregúntate: *"Si este producto existiera hace 100 años, ¿qué forma física tendría?"*

Genera **3-5 opciones** y preséntalas al usuario. La opción por defecto para GIRO:

```
1. El tablero de control del taller — medidores, filas de trabajo, un panel de checking bajo luz fluorescente
   Materiales: acero cepillado, plástico duro, vidrio sucio, pintura descascarada
   Temperatura: fría con acentos ámbar en los medidores

2. La oficina del gerente al cierre — una sola lámpara de escritorio, folders, café frío
   Materiales: madera de nogal, latón, papel aging, fieltro
   Temperatura: cálida

3. La sala de control portuaria — turnos de noche, radar, niebla
   Materiales: acero, neón sucio, vidrio empañado, hule
   Temperatura: fría, un punto de neón

¿Cuál resuena? O describe algo distinto.
```

**La metáfora debe ser específica.** "Oficina" es demasiado amplio. "Una sala de consejo con panel de nogal después de horas, iluminada por una sola lámpara" es un lugar.

Una vez elegida, mapea cada elemento:

| Elemento | Análogo físico |
|---|---|
| Login | la entrada — una puerta, un umbral, un torno |
| Resumen / índice | el tablero, la estantería, el archivador |
| Detalle | la hoja abierta, la carta desdoblada, el folder jalado |
| Filtros | el tablero de calibración, los selectores de dial |
| Botón | el mando, la palanca, el sello |
| Navegación | el pasillo, la escalera, el índice |
| Carga | el galleta de checking, el cajón que se abre, la luz que enciende |
| Error | un guía cortés explicando, una redirección suave |
| Estado vacío | una estantería vacía con una etiqueta, una hoja en blanco esperando |

## Paso 2.5 — Autenticidad estructural (no la saltes)

Después de mapear los elementos, pregúntate **antes de tocar código**:

> "¿La arquitectura de información actual puede encarnar autenticamente esta metáfora, o la estructura misma necesita cambiar?"

| Estructura actual | La metáfora exige | Resolución |
|---|---|---|
| Grid uniforme de tarjetas | Formas orgánicas / irregulares | Pedir cambio estructural: tamaños variables, espaciado orgánico |
| Navegación lineal por scroll | Profundidad por capas | Pedir cambio estructural: navegación por profundidad |
| Formulario de una columna | Selección con bifurcaciones | Pedir cambio estructural: flujo no lineal |
| Header + cuerpo estándar | Inmersión | Los elementos flotan **dentro**, no encima |

**Si hacen falta cambios estructurales — bucle de retroalimentación:**

1. **No empieces la atmósfera todavía.**
2. Genera una **Solicitud de Cambio Estructural**:
   ```
   ## Solicitud de Cambio Estructural (desde Style)

   **Motivo**: la metáfora de [X] requiere reorganización estructural para ser auténtica.
   La estructura actual de [navegación/layout/componente] contradice la lógica
   física de la metáfora y no se resuelve con atmósfera.

   **Cambios requeridos**:
   - [Elemento]: de [actual] a [necesario] — porque [razón física]

   **Accesibility non-negotiable**:
   Todos los cambios deben mantener WCAG AA. Los cambios estructurales no pueden
   eliminar las correcciones de accesibilidad ya aplicadas por Build.

   **Scope**: [archivos afectados]
   ```
3. Si el usuario lo aprueba, haz los cambios **conservando intactas todas las correcciones de accesibilidad**, y recién entonces vuelve a la atmósfera.

Este bucle es intencional. Una metáfora aplicada a una estructura que no puede habitarla produce un disfraz, no un lugar.

## Paso 3 — Construye la atmósfera

**Scope primero.** Todo el CSS va bajo un scope de página (`.giro-taller`, `.giro-oficina`). Nunca contamines estilos globales. Los tokens de marca de `ui/theme.py` se respetan.

**Este repo no tiene bundler ni assets pipeline.** El CSS va inyectado con `st.markdown("<style>…", unsafe_allow_html=True)` o, si es transversal a la app, en `ui/theme.py`. **No añadas archivos CSS externos ni dependencias de build.**

Construye en este orden:

### Capa 1 — Atmósfera de fondo
La "pared de la habitación".
```css
.giro-taller {
  background: linear-gradient([ángulo], [tono oscuro] 0%, [tono medio] 50%, [tono profundo] 100%);
}
```

### Capa 2 — Fuente de luz
¿De dónde viene la luz? Gradiente radial. Debe ser **direccional** y coherente con el `box-shadow` de la Capa 5.
```css
.giro-taller::before {
  content: ''; position: fixed; inset: 0;
  background: radial-gradient(ellipse at [posición], [luz, alpha baja], transparent [radio]);
  pointer-events: none;
}
```

### Capa 3 — Profundidad / viñeta
Bordes más oscuros crean encierro.
```css
.giro-vignette {
  position: fixed; inset: 0;
  background: radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,[opacidad]) 100%);
  pointer-events: none;
}
```

### Capa 4 — Textura de material
Grano generado en CSS, **no imágenes**.
```css
.giro-grain {
  position: fixed; inset: 0;
  background-image: radial-gradient([color] [tamaño punto], transparent [tamaño punto]);
  background-size: [rejilla] [rejilla];
  opacity: [bajo]; pointer-events: none;
}
```

### Capa 5 — Materiales de superficie
Tarjetas y paneles que se sienten como objetos físicos. **El `box-shadow` debe coincidir con la dirección de la luz de la Capa 2.**
```css
.giro-taller .panel {
  background: [color de material con alpha];
  border: 1px solid [color de borde];
  backdrop-filter: blur([profundidad]px);
  box-shadow: [sombra coherente con la luz];
}
```

### Capa 6 — Voz tipográfica
La tipografía actual en `.streamlit/config.toml` es Inter + Space Grotesk. Si la metáfora pide otra voz, **propón el cambio al usuario antes de editar `config.toml`** — es un cambio global, no local. Nunca lo cambies de pasada.

### Capa 7 — Elementos ornamentales
Detalles que refuerzan la metáfora: reglas de sección, bordes, marcas decorativas. Siempre con `aria-hidden="true"` y `content: ''` si son puramente decorativos.

## Paso 4 — Deriva el color de los materiales

**No elijas hexadecimales. Elige materiales y busca sus colores.**

Para cada material nombrado:
1. ¿De qué color es en el mundo real?
2. ¿Qué superficie tiene? (mate, brillante, rugoso, pulido)
3. ¿Cómo se ve bajo la fuente de luz de la Capa 2?

Crea custom properties **con nombre de material**, no de color:
```css
:root {
  --acero: #66584c;
  --laton: #c9a44a;
  --pintura: #7C4DFF;   /* o el color_primario del workspace */
}
```

Los colores semánticos heredan del material: Decisiones = material que se siente decisivo. Acciones = material urgente. Errores = material de cautela. Datos = material factual.

**Todos los pares texto/fondo deben cumplir AA (>= 4.5:1) en modo claro Y oscuro.** La atmósfera no anula accesibilidad. Jamás. Verifícalo con la `PALETA` de `ui/components.py` como referencia.

## Paso 5 — 5 ciclos de diseño (obligatorio)

**Una pantalla a la vez.** Empieza por la emocionalmente más importante (login o el resumen). Establece ahí la dirección de arte y propaga.

**Rastro de evidencia:** si tienes navegador disponible en esta sesión, captura una captura **antes** de empezar y una por ciclo. **Si no tienes navegador, dilo explícitamente en el reporte y no inventes capturas.** No hay forma de tomar screenshots aquí por defecto: sé honesto con eso.

### Ciclo 1 — Fundación de la atmósfera
Foco: fondo, color, fuente de luz.
- [ ] El fondo usa un gradiente multi-stop (no un color plano)
- [ ] Hay un gradiente radial simulando una fuente de luz **direccional**
- [ ] Existe al menos una capa de viñeta
- [ ] Todo el CSS nuevo está scopeado bajo la clase de página (cero polución global)
- [ ] La temperatura es consistente (todo cálido, todo frío, o mixto intencional)
- [ ] **Funciona en modo claro y en modo oscuro**

### Ciclo 2 — Textura y tipografía
- [ ] Existe una capa de grano generada en CSS (no imagen)
- [ ] Todos los colores son custom properties **con nombre de material**
- [ ] Todos los pares texto/fondo pasan AA (>= 4.5:1; >= 3:1 en texto grande)
- [ ] La fuente de display NO es un default genérico
- [ ] La fuente de cuerpo complementa sin competir

### Ciclo 3 — Materiales de superficie
- [ ] Tarjetas/paneles con `backdrop-filter`, `border` y `box-shadow` distintos del default
- [ ] Los materiales se sienten como objetos físicos
- [ ] El hover incluye `transform`, no solo cambio de color
- [ ] La dirección del `box-shadow` coincide con la luz del Ciclo 1
- [ ] Los bordes usan colores derivados de material

### Ciclo 4 — Detalles ornamentales y animación de entrada
- [ ] Existe al menos un elemento ornamental CSS
- [ ] Los ornamentos llevan tratamiento `aria-hidden`
- [ ] Existe al menos un `@keyframes` de entrada
- [ ] Las animaciones de entrada usan delays escalonados (80ms+)
- [ ] `prefers-reduced-motion` desactiva las animaciones
- [ ] Las animaciones son **cortas** (150-250ms). Una animación de 800ms en un dashboard es un castigo.

### Ciclo 5 — Verificación final
- [ ] Las 5 dimensiones de Style puntúan >= 5/10 individualmente
- [ ] Responsive: funciona a 360px y a 1920px
- [ ] Cero polución de estilos globales
- [ ] **La metáfora es identificable**: ¿un stranger podría nombrar el lugar leyendo el CSS?
- [ ] **Fidelidad >= 3.** Aplica el test de tres patrones: ¿la navegación, el estado de carga y el estado vacío existirían dentro de ese lugar físico? Si los tres son patrones genéricos con etiquetas temáticas, es un disfraz, no un lugar. Vuelve a la comprobación de autenticidad estructural.
- [ ] Los tokens de marca del workspace siguen siendo visibles y reconocibles
- [ ] Modo claro y oscuro verificados

Si alguna dimensión queda < 5, identifica la más débil y aplica una corrección dirigida antes de seguir.

## Paso 6 — Restricciones para la interacción

Documenta la personalidad física que implica la metáfora:

| Metáfora | Física | Tensión de resorte | Masa |
|---|---|---|---|
| Taller / máquina | Mecánica, exacta | Muy alta | Firme |
| Oficina al cierre | Con peso, deliberada | Alta | Pesada |
| Sala de control | Flotante, ingrávida | Baja | Ligera |
| Jardín / natural | Orgánica, fluida | Baja-media | Variada |

**Y el sonido — que aquí aplica a la interacción visual, no a audio.** Este producto no lleva audio. Registra: `perfil_fisico: [X], sonido: ninguno — herramienta de trabajo, el silencio es una decisión, no una omisión`.

## Paso 7 — Reporta

```markdown
## Style — [pantalla]

**Metáfora**: [una frase]
**Temperatura**: [cálida/fría/mixta]
**Materiales**: [lista]
**Fidelidad**: X/4 (objetivo >= 3)
**Scope CSS**: [clase]

### Puntuaciones
| Dimensión | Antes | Después | Delta |
|---|---|---|---|
| P — Metáfora física | /10 | /10 | |
| L — Iluminación | /10 | /10 | |
| A — Animación | /10 | /10 | |
| C — Color como material | /10 | /10 | |
| E — Tipografía encarnada | /10 | /10 | |
| **Total** | **/50** | **/50** | |

### Capas aplicadas
- Fondo / Luz / Viñeta / Textura / Tipografía — una línea cada una

### Perfil físico para interacción
- Personalidad: [X] · Tensión: [Y] · Masa: [Z] · Sonido: ninguno (razón)

### Modo claro / oscuro
- Verificado en ambos: [sí/no + cómo]

### Archivos modificados
- [lista con líneas]

### Evidencia
- [capturas si las hay; si no, dilo explícitamente]
```

**No escribas archivos de log en el repo** (ni `ade_docs/` ni otro directorio de auditoría). Este proyecto se entrega a clientes. El reporte va en la conversación.

### Handoff

> "La atmósfera está puesta: la pantalla se siente como [metáfora]. Si quieres que el copy hable su mismo lenguaje, `/ade-write`."

## Diagnóstico de fallos

| Síntoma | Causa probable | Arreglo |
|---|---|---|
| Se siente plano pese al fondo oscuro | Falta la Capa 2 (fuente de luz) | Añade el gradiente radial direccional |
| Se siente turbio | Demasiada textura, poco contraste | Baja la opacidad del grano, sube el contraste |
| Se siente frío cuando debía ser cálido | Tono de gradiente equivocado | De azul-gris a ámbar-marrón |
| Se siente caricaturesco | Colores muy saturados | Desatura 20-30%, añade tonos apagados |
| Desconectado entre pantallas | Atmósfera distinta por página | Unifica tono base y luz; varía solo detalles de superficie |
| Rompe en modo oscuro | Diseñaste solo para un modo | Reconstruye las capas con ambos fondos |
| Anula la marca del cliente | La atmósfera reemplazó los tokens | Reintegra `--giro-primario`/`--giro-secundario` como acentos derivados |

## Lo que NO haces

- No cambies la estructura directamente sin pasar por la Solicitud de Cambio Estructural.
- No añadas interactividad, físicas o descubrimientos — eso es `/ade-move`.
- No cambies la voz del copy — eso es `/ade-write`.
- No uses imágenes de stock para la atmósfera.
- No sacrifiques accesibilidad por estética. **El contraste pasa siempre.**
- No apliques la atmósfera globalmente — scopea por pantalla.
- No te detengas en el Ciclo 1. La primera versión es andamiaje, no diseño.
- No te quedes en fidelidad 2 o menos. Etiquetas temáticas sobre patrones genéricos son un disfraz.
- No añadas dependencias, bundler ni archivos de assets.
- No commitees.
