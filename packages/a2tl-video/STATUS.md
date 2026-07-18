# A2TL-Video — Estado Actual y Direccion

## Que se ha construido

- **Parser**: VDSL texto → JSON spec. Funcional. Soporta text, text-cycle, label, triptych, step-sequence, comparison, card, code, trace-log, viz blocks.
- **Compiler**: JSON spec → Remotion JSX. Funcional. Genera codigo importable desde `vdsl/components`.
- **CLI** (`vdsl`): `init`, `compile`, `render`, `preview` (Remotion Studio), `play` (HTML).
- **17 componentes Remotion**: GridCanvas, WordReveal, TextCycle, TypewriterText, FadeText, Label, Byline, Triptych, StepSequence, NodeGraph, FlowDiagram, BoundarySim, WorkspaceDiagram, Comparison, TraceLog, ProtocolCompare, FormulaCard.
- **4 temas**: clean, cobalt-grid, dark-tech, warm-editorial.
- **Web renderer**: Generates standalone HTML with JS runtime for instant browser playback.
- **Render project**: Proyecto Remotion local para `vdsl render` (MP4 via Chromium).

## Problemas actuales

1. **Render MP4 demasiado lento**: 2-3 minutos para 74s de video. Chromium renderiza frame a frame. Inviable para SkillNet (usuario esperando).

2. **Web renderer (HTML) con bugs**:
   - Elementos aparecen en posicion incorrecta (arriba izquierda en vez de centrados)
   - Timing de escenas no sincronizado correctamente
   - Escenas se solapan o no se muestran
   - Calidad visual pobre comparada con Remotion

3. **Calidad visual insuficiente**: Los componentes Remotion tienen efectos (word-stagger con blur, grid con drift, glows), pero el HTML player no los replica.

## Vision para SkillNet

El caso de uso real no es una CLI local. Es:

> Un usuario entra en SkillNet → el sistema genera un video con A2TL-Video → se reproduce al instante en la pagina.

Requisitos:
- El video debe mostrarse DENTRO de un elemento de la pagina (no pantalla completa)
- Debe reproducirse al instante, sin esperas de renderizado
- El usuario puede descargar el MP4 si quiere, pero la experiencia principal es reproduccion inmediata
- El backend genera el VDSL (con IA), el frontend lo reproduce

## Arquitectura propuesta

```
Backend (SkillNet):
  Request del usuario → IA genera .vdsl → Sirve JSON + HTML player
                                                
Frontend (SkillNet):
  Renders A2TL-Video in a <div class="vdsl-player"> 
  Reproduccion instantanea via Web APIs (canvas, Web Animations, MediaRecorder)
  Opcional: grabacion a MP4 en cliente via MediaRecorder
```

El servidor nunca renderiza MP4. Solo sirve el JSON del video. El navegador reproduce y opcionalmente graba.

## Decisiones pendientes

1. **Motor de reproduccion**:
   - (a) HTML+CSS+JS (actual, funcional pero con bugs)
   - (b) Canvas 2D Web API (mas control, mas complejo)
   - (c) WebGL (sobra para explainer videos)

2. **Formato de distribucion**:
   - (a) HTML embebible con estilos aislados (Shadow DOM)
   - (b) Web Component (`<vdsl-player src="spec.json">`)
   - (c) React component (`<VDSLPlayer spec={spec} />`)

3. **Captura a video**:
   - (a) MediaRecorder API (graba mientras reproduce, tiempo real)
   - (b) Canvas.captureStream() + MediaRecorder (mas control)
   - (c) Servidor asincrono con Remotion Lambda (pago, 10-20s)

## Proxima iteracion recomendada

1. Debuggear el web renderer: fix de posiciones, timings, superposicion de escenas
2. Empaquetar como React component `<VDSLPlayer>` para SkillNet
3. Probar MediaRecorder para captura a MP4 en cliente
4. Decidir si el MP4 se genera en cliente o servidor
