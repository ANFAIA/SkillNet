# A2TL-Video

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![npm version](https://img.shields.io/npm/v/a2tl-video.svg)](https://www.npmjs.com/package/a2tl-video)
[![Build Status](https://img.shields.io/github/actions/workflow/status/JoseEstevez520/a2tl-video/ci.yml?branch=main)](https://github.com/JoseEstevez520/a2tl-video/actions)
[![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6.svg?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)

**Describe a video in 12 lines. Get a professional MP4 or instant browser playback.**

```
VDSL/1
theme dark-tech
canvas 1920x1080

scene "The Problem" 6s crossfade
  text "Your data has no walls." hero center word-stagger 0-4s
  label "only suggestions" center 2.5s

scene "The Solution" 8s blur-crossfade
  viz 0.5-8s build-up
    type: flow-diagram
    steps:
      - label: "Label" desc: "tag your data" icon: 1 color: blue
      - label: "Check" desc: "verify at the gate" icon: 2 color: green
      - label: "Record" desc: "trace every crossing" icon: 3 color: amber
    connectors: arrow
```

Part of **A2TL** (Agent to Transformation Language). See also [a2tl-web](https://github.com/JoseEstevez520/a2tl-web) for web pages.

---

## Why VDSL

An AI agent writes a simple `.vdsl` spec. The renderer handles animation, layout, and typography.

| Metric (74s video) | VDSL | Remotion JSX | HTML player |
|---|---:|---:|---:|
| Tokens (tiktoken) | **1,173** | 2,257 | 21,305 |
| Savings vs VDSL | -- | +48% | +94% |

A simpler 13s video: **168 tokens** VDSL vs 501 JSX (66% savings) vs 10,968 HTML (98% savings).

**What you get:**

- **Agent writes spec, gets pro video** -- declarative format, no design decisions
- **Zero-dependency web playback** -- self-contained HTML, no render step needed
- **Error-proof format** -- constrained and declarative; the agent cannot break it
- **4 themes, 12 components** -- inline `palette`/`font` overrides in the header
- **Embeddable** -- `<vdsl-player>` web component and React `<A2TLVideoPlayer>`

## Quick Start

```bash
git clone https://github.com/JoseEstevez520/a2tl-video
cd a2tl-video
npm install && npm run build
cd render && npm install && cd ..

# Render an example to MP4
npx vdsl render examples/communication.vdsl -o communication.mp4

# Or generate a self-contained HTML player (instant, no Remotion)
npx vdsl play examples/hello-world.vdsl
```

## Pipeline

```
video.vdsl       you write this (12-98 lines, 168-1,173 tokens)
    |  vdsl compile
compiled JSX     auto-generated Remotion component
    |  vdsl render
video.mp4        professional output
```

Or skip MP4 entirely: `vdsl play` produces a self-contained HTML file that plays in any browser.

## Format Reference

Format identifier: `VDSL/1`. File extension: `.vdsl`. Full spec: [docs/spec.md](docs/spec.md).

### Components

**Text (Level 2 -- predefined, always looks good)**

`text` -- reveal animations (fade, word-stagger, typewriter, slide-up) |
`text-cycle` -- phrases with hard-cut transitions |
`label` -- positioned tag |
`icon` -- inline SVG from bundled Lucide set (~280 icons) |
`code` -- monospace with typewriter effect |
`byline` -- credit/attribution

**Structure (Level 2)**

`triptych` -- three items in a row |
`step-sequence` -- numbered cycling steps |
`comparison` -- side-by-side cards with 3D entry |
`card` -- centered card with content

**Visualizations (Level 3 -- structured data, rich animated output)**

`node-graph` | `flow-diagram` | `boundary-sim` | `workspace` | `protocol-compare` | `trace-log` | `custom` (raw SVG)

### Scene transitions

`cut` | `crossfade` | `blur-crossfade` | `push-right` | `push-left` | `push-up` | `zoom-through`

### Timing

```
0-5s      start at 0s, end at 5s
3.2s      appear at 3.2s
0.5-9s    start at 0.5s, end at 9s
```

## Themes

One line changes the entire look: `theme dark-tech`

| Theme | Style |
|---|---|
| `clean` | White background, neutral ink, system fonts |
| `cobalt-grid` | Cream paper, cobalt ink, graph-paper grid, serif |
| `dark-tech` | Near-black, cyan accent, sans-serif |
| `warm-editorial` | Ivory, warm dark ink, serif |

Override inline without a separate file:

```
VDSL/1
theme dark-tech
palette bg:#0d0f1a ink:#ff4d6d
font display:"Playfair Display"
```

## Embedding

### Web component

```html
<script src="embed/vdsl-player.js"></script>
<vdsl-player src="video.html" ratio="16/9" autoplay></vdsl-player>
```

Attributes: `src`, `srcdoc`, `ratio` (default `16/9`), `autoplay`, `maxwidth` (default `100%`).

### Programmatic API

The player exposes `window.vdslPlayer` inside the frame:

`play()` | `pause()` | `seek(frame)` | `seekTime(seconds)` | `frame` | `fps` | `totalFrames`

## CLI

```bash
npx vdsl compile video.vdsl -o composition.jsx   # VDSL -> Remotion JSX
npx vdsl render  video.vdsl -o output.mp4         # VDSL -> MP4
npx vdsl play    video.vdsl                       # VDSL -> self-contained HTML
npx vdsl preview video.vdsl                       # open in Remotion Studio
npx vdsl themes                                   # list available themes
npx vdsl init    my-explainer                     # scaffold a new .vdsl file
```

## License

MIT -- see [LICENSE](LICENSE).

Built on [Remotion](https://remotion.dev).
