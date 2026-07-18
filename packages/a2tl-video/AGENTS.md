# A2TL-Video — Agent to Transformation Language for Video

## Stack

TypeScript, Node.js, Remotion 4, React 19, HTML/CSS/JS.

## Estructura del repo

```
src/
  cli.ts              — CLI (bin: vdsl): init, compile, render, preview, play
  index.ts            — Entry point, exports public API
  parser/             — .vdsl text → JSON spec
    types.ts          — Interfaces (VDSLSpec, Scene, Component, etc.)
    tokenizer.ts      — Tokenizador linea a linea
    index.ts          — Parser principal + structured viz parser
  compiler/           — JSON spec → Remotion JSX
    index.ts          — Compilador principal
    codegen.ts        — Helpers de generacion de JSX
  components/         — 17 componentes Remotion
    layout/           — GridCanvas, Triptych, StepSequence
    text/             — WordReveal, TextCycle, TypewriterText, FadeText, Label, Byline
    diagrams/         — NodeGraph, FlowDiagram, BoundarySim, WorkspaceDiagram, Comparison
    data/             — TraceLog, ProtocolCompare, FormulaCard
    index.ts          — Barrel exports
  themes/             — 4 temas (clean, cobalt-grid, dark-tech, warm-editorial)
  renderer/           — Web renderer (VDSL → HTML playback)
    index.ts          — renderToHTML()
render/               — Proyecto Remotion local para MP4 rendering
examples/             — Ejemplos .vdsl
STATUS.md             — Estado actual, problemas, vision
```

## Pipeline

```
.vdsl → parser → JSON spec → compiler → Remotion JSX → remotion render → MP4
                             → web renderer → HTML (instant playback)
```

## Estado actual

- Parser, compiler, CLI funcionales
- 17 componentes, 4 temas
- Render a MP4 via Remotion funciona pero es lento (2-3 min para 74s)
- Web renderer (HTML) existe pero tiene bugs de posicion y timing
- README actualizado

## Problemas conocidos

1. **Render MP4 lento**: Chromium renderiza frame a frame. Inviable para SkillNet.
2. **Web renderer bugs**: elementos mal posicionados (todo arriba izquierda), timings de escena no sincronizados.
3. **Calidad visual del HTML player**: no replica los efectos de los componentes Remotion.

## Vision

Para SkillNet: usuario pide video → backend genera VDSL (IA) → frontend reproduce al instante en un `<div>` embebido. El servidor NUNCA renderiza MP4. Si se necesita descarga, MediaRecorder en cliente.

## Proxima iteracion

1. Debuggear web renderer (posiciones, timings, overlapping)
2. Probar MediaRecorder para captura a MP4 en cliente
3. Decidir si el MP4 se genera en cliente o servidor

## Notas

- No personalizar para SkillNet (A2TL-Video es generico)
- No audio/TTS por ahora
- React component `<A2TLVideoPlayer>` ya existe en `src/react/`
- MCP server ya existe en `src/mcp/` (comando `vdsl mcp`)
- Funcional > bonito en esta fase
