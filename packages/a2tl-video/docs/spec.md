# A2TL-Video Format Specification (VDSL/1)

A2TL-Video (formerly VDSL) -- compact format for AI agents to describe explainer videos. 48–66% fewer tokens than Remotion JSX, 94–98% fewer than equivalent HTML (measured with tiktoken). Part of the A2TL family alongside a2tl-web.

Format version identifier: `VDSL/1` (first line of every `.vdsl` file).

## Filosofía

Misma que UIDL: la IA dice **QUÉ** mostrar. El renderer decide **CÓMO** animarlo.

Nivel 2 para el 80% (primitivos predefinidos con calidad garantizada).
Nivel 3 para el 20% (bloque `viz` donde el agente genera SVG/JSX custom para visualizaciones únicas).

## Estructura

```
VDSL/1
theme <nombre>
canvas <ancho>x<alto>

scene "<título>" <duración> <transición>
  <componente> <contenido> <animación> <timing>
```

## Componentes Level 2 (predefinidos, calidad garantizada)

### Texto
```
text "<contenido>" <font> <posición> <reveal> <timing>
```
- font: display | display-italic | body | mono | hero
- posición: center | upper-left | upper-right | bottom-center
- reveal: fade | word-stagger | typewriter | slide-up | none
- timing: <inicio>-<fin> en segundos, o <inicio> (fade in a partir de)

### Texto cíclico (hard-cut entre frases)
```
text-cycle <posición> <font>
  "<frase 1>" <timing> [accent]
  "<frase 2>" <timing> [accent]
```
- accent: underline | strike | hero | dim | glow

### Etiqueta
```
label "<texto>" <posición> <timing>
```

### Triptych (tres elementos en línea)
```
triptych <timing> <reveal>
  "<elemento 1>"
  "<elemento 2>"
  "<elemento 3>"
```
- reveal: stagger | simultaneous

### Secuencia de pasos
```
step-sequence <timing>
  "<número>. <TÍTULO>" "<descripción>"
  ...
```

### Comparación lado a lado
```
comparison <timing> <animación>
  left "<título>" "<subtítulo>" badge "<texto>" <color>
  right "<título>" "<subtítulo>" badge "<texto>" <color>
```
- animación: split-tilt | slide-in | fade

### Tarjeta centrada
```
card <posición> <reveal> <timing>
  formula "<A>" "<op>" "<B>"
  arrow
  result "<resultado>" <font>
  subtitle "<texto>"
```

### Código
```
code "<contenido>" <reveal> <timing>
  [shrink <factor> move-top <timing>]
```

### Bloque de log
```
trace-log <timing> <reveal>
  "<col1>" "<col2>" "<col3>"
  ...
```

### Crédito
```
byline "<texto>" <posición> <timing>
```

## Componente Level 3: `viz` (visualización custom)

Para diagramas y gráficas que no caben en los primitivos:

```
viz <timing> <reveal>
  type: <node-graph | flow-diagram | boundary-sim | workspace | protocol-compare | trace-log | custom>
  """
  <SVG o descripción estructurada>
  """
```

El agente genera el contenido SVG/estructurado. El renderer:
1. Lo envuelve en un contenedor con el tema activo
2. Aplica la animación de entrada (reveal)
3. Si es un tipo conocido (node-graph, flow-diagram), aplica animaciones internas predefinidas
4. Si es custom, anima las partes marcadas con `data-animate="<tipo>"`

### Tipos de viz predefinidos

**node-graph**: Nodos y conexiones animados
```
viz 0-9s fade
  type: node-graph
  nodes:
    - id: jose label: "Jose" access: [A,B] x: 60 y: 40
    - id: pepito label: "Pepito" access: [A] x: 200 y: 40
  edges:
    - from: jose to: A color: blue
    - from: pepito to: A color: blue
  compartments:
    - id: A x: 130 y: 150 color: blue
    - id: B x: 200 y: 150 color: amber
```

**flow-diagram**: Flujo con pasos conectados
```
viz 0-9s stagger
  type: flow-diagram
  steps:
    - label: "Arranque" desc: "read-in" icon: 1 color: blue
    - label: "Trabajo" desc: "procesa" icon: 2 color: purple
    - label: "Frontera" desc: "verifica" icon: 3 color: amber
  connectors: arrow
```

**boundary-sim**: Simulación de frontera PASS/BLOCK
```
viz 0-8s animate-flow
  type: boundary-sim
  packet: "Dato A" label: A
  gate: "∈" check: inclusion
  recipient: "Jose" access: [A,B]
  result: pass
```

**workspace**: Diagrama de espacio compartido
```
viz 0-9s build-up
  type: workspace
  shared: "COMPARTIDO"
  zones:
    - side: left label: "PRIVADO A" tag: "etiqueta: A"
    - side: right label: "PRIVADO B" tag: "etiqueta: B"
```

**protocol-compare**: Tabla comparativa de protocolos con badges AUTH/DATA (✓/✕)
```
viz 0-8s stagger
  type: protocol-compare
  protocols:
    - name: "HTTP" auth: no data: no
    - name: "mTLS" auth: yes data: yes
```

**custom**: SVG directo (Level 3 puro)
```
viz 0-5s fade
  type: custom
  """
  <svg viewBox="0 0 800 400">
    <circle cx="400" cy="200" r="80" data-animate="scale-in" />
    <text x="400" y="210" data-animate="fade" data-delay="0.5">Custom</text>
  </svg>
  """
```

## Animaciones predefinidas

### Reveals (entrada de elementos)
fade | word-stagger | typewriter | slide-up | scale-in | none

Algunos componentes usan animaciones propias: `split-tilt` (comparison), `stagger` (triptych), `build-up` (viz/composites).

### Transiciones entre escenas
cut | crossfade | blur-crossfade | push-right | push-left | push-up | zoom-through

### Accents (énfasis en texto)
underline | strike | hero | dim | glow

## Temas predefinidos

Cada tema define: paleta, tipografía, fondo, hairlines, componentes base.

- clean: fondo blanco, tinta neutral, fuentes del sistema, sin grid — el default universal
- cobalt-grid: papel crema, tinta cobalto, cuadrícula, Newsreader + Hanken Grotesk + DM Mono
- dark-tech: fondo oscuro, acento cyan, Inter + JetBrains Mono
- warm-editorial: fondo marfil, serif clásica, EB Garamond + Inter
- (extensible: tema = archivo JSON con tokens)

## Personalización inline: `palette` / `font`

Re-skinear un vídeo sin archivo de tema aparte: en la cabecera, tras `theme`, añade directivas `palette` y/o `font`. Sobrescriben el tema base en el sitio.

```
VDSL/1
theme dark-tech
palette bg:#0d0f1a ink:#ff4d6d
font display:"Playfair Display"
```

Un par de líneas en la cabecera reskin todo el vídeo. El conjunto de knobs es pequeño a propósito (la ventaja de A2TL-Video es la brevedad):

- **claves palette**: `bg`, `bg2`, `ink`, `inkSoft`, `inkFaint`, `grid`, `green`, `red`, `amber`, `purple`
- **claves font**: `display`, `body`, `mono`

Si defines `ink` solo, sus derivados (`inkSoft`, `inkFaint`, `grid`) se calculan a partir de él por alpha, así un único color re-afina toda la familia de tinta. Lo que no toques cae al tema base.

## Reproductor web y embebido

No hace falta renderizar a MP4 para ver (o publicar) un vídeo A2TL-Video. `vdsl play <archivo>` genera un **reproductor HTML autocontenido** que se reproduce al instante en el navegador — sin Remotion, sin paso de render, sin recursos externos.

```
vdsl play video.vdsl            → video.html (un solo archivo, autocontenido)
vdsl play video.vdsl --theme dark-tech
```

El escenario fijo 1920×1080 se auto-ajusta y centra en el viewport, con play/pausa y barra de scrub. Dibuja los componentes reales (viz, card, trace-log, reveals de texto), las transiciones entre escenas y micro-movimiento ambiental — el mismo lenguaje visual que la ruta MP4.

### Embeber con `<vdsl-player>`

El web component `embed/vdsl-player.js` aloja el reproductor en un `<iframe>` con estilos aislados (nada se filtra dentro ni fuera):

```html
<script src="embed/vdsl-player.js"></script>
<vdsl-player src="video.html" ratio="16/9" autoplay></vdsl-player>
```

Atributos: `src` (URL de un .html generado), `srcdoc` (HTML del reproductor inline), `ratio` (por defecto `16/9`), `autoplay`, `maxwidth` (por defecto `100%`). También puedes fijar el HTML completo desde JS con la propiedad `.html`.

### API de control programático

Dentro del frame, `window.vdslPlayer` expone: `play()`, `pause()`, `seek(frame)`, `seekTime(segundos)`, y los getters `frame`, `fps`, `totalFrames`. Desde el componente se accede vía el getter `.player` del elemento.

## Medición real (tiktoken, cl100k_base)

Vídeo de 74s, 7 escenas (communication.vdsl):

| Formato | Tokens | Líneas | Ahorro vs HTML |
|---------|--------|--------|----------------|
| HTML player equivalente | 21,305 | — | — |
| Remotion JSX directo | 2,257 | 238 | 89% |
| **A2TL-Video spec** | **1,173** | **98** | **94%** |

Vídeo simple de 13s, 3 escenas (hello-world.vdsl):

| Formato | Tokens | Líneas | Ahorro vs HTML |
|---------|--------|--------|----------------|
| HTML player equivalente | 10,968 | — | — |
| Remotion JSX directo | 501 | 65 | 95% |
| **A2TL-Video spec** | **168** | **18** | **98%** |

## Pipeline

```
contenido.md → (agente, 130–1,173 tokens) → video.vdsl → (parser) → JSON ─┬→ (renderer web) → HTML autocontenido (vdsl play)
                                                                           └→ (compiler Remotion) → MP4 (vdsl render)
```
