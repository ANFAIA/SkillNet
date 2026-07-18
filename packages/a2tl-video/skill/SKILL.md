---
name: a2tl-video
description: Generate animated explainer videos as an instant, embeddable HTML web player from a compact A2TL-Video spec (.vdsl format). Use when the user wants a video, animation, or motion graphic for docs, courses, landing pages, or presentations — anything that should play in the browser. Part of the A2TL family (a2tl-web, a2tl-video).
---

# A2TL-Video (web player)

Use this skill to turn content into an animated explainer. You write a small
`.vdsl` file (a compact, ~30-100 line spec) and A2TL-Video renders it to a
**single, self-contained HTML file** that plays instantly in any browser --
auto-fitting stage, play/pause, and a scrub bar, all inline with no build step
and no external assets. There is **no MP4 and no video-encoding step**: the
deliverable is the web player, which also embeds directly into a page.

A2TL-Video is part of the **A2TL** (Agent to Transformation Language) family
alongside **a2tl-web** (for web pages).

## When to use

- User wants a video/animation about a concept, feature, or process
- User wants to add an animated explainer to documentation, a course, or a landing page
- User says "make a video about…", "animate this", "create an explainer for…"

## How to use

1. Read the content the user wants to visualize.
2. Write a `.vdsl` file (see the format below).
3. Produce the player, either way:
   - **CLI:** `npx vdsl play <file>.vdsl` -- writes `<file>.html` next to it. Open it to play; it embeds anywhere.
   - **MCP tool:** call `render_player` with `{ spec, theme?, output? }`. It returns the self-contained HTML (and writes a `.html` when you pass `output`).
4. Iterate on the spec and re-render. Do **not** try to produce an MP4 -- the product is the HTML web player.

Two more MCP tools help you stay accurate:
- `list_components` — the components, viz types, reveals, transitions, positions, accents, fonts, and theme names this build supports.
- `list_icons` — the exact icon names valid for `icon "<name>"`.

## Document structure

```
VDSL/1                      # required version header, must be the first line
theme dark-tech             # base theme (see Themes)
palette ink:"#0b1020" bg:"#f7f7f2"   # optional: inline colour overrides
font display:"Georgia" body:"Inter"  # optional: inline font overrides
canvas 1920x1080            # optional stage size (default 1920x1080)

scene "<title>" <duration>s <transition>
  <component> <args…> <timing>
  <component> <args…> <timing>
```

- **Header:** `VDSL/1` first, then `theme`, optional `palette` / `font` override
  lines (a couple of `key:"value"` pairs re-skin the whole video), and optional
  `canvas WxH`.
- **Scenes:** `scene "Title" <duration>s <transition>`. Components are the
  indented lines under a scene.
- **Timing** is `start-end` in seconds (`0-3s`, `1.5-4s`) or an open `1.5s`
  (from that time to the end of the scene). Timings are scene-relative.

## Components (accurate to this build of A2TL-Video)

### Text & labels
- `text "<content>" <font> <position> <reveal> <timing>` — headline or body copy.
- `text-cycle <position> <font>` + indented phrases — hard-cut cycling phrases:
  ```
  text-cycle center hero
    "First idea"  0-2s
    "Then this"   2-4s  underline
  ```
  (each phrase: `"text" <timing> [accent]`)
- `label "<text>" <position> <timing>` — small kicker / eyebrow.
- `byline "<text>" <position> <timing>` — attribution / footer line.
- `icon "<name>" <position> <timing> [color]` — inline Lucide SVG. Use a name
  from `list_icons` (e.g. `icon "check-circle" upper-right 1-3s green`).

### Composite blocks (these build up progressively across their window)
- `triptych <timing> <reveal>` + item lines — three-up panel. Each item line is
  `"Title" "optional caption"`:
  ```
  triptych 0-5s stagger
    "Fast" "renders instantly"
    "Small" "~50 lines"
    "Portable" "one HTML file"
  ```
- `step-sequence <timing>` + step lines — numbered steps; an optional leading
  bare icon name replaces the number:
  ```
  step-sequence 0-6s
    "1. Write" "author a .vdsl spec"
    rocket "2. Render" "get an HTML player"
  ```
- `comparison <timing> <animation>` + `left` / `right` lines — side-by-side cards:
  ```
  comparison 0-5s split-tilt
    left  "Before" "manual editing" badge "slow" red
    right "After"  "one spec"       badge "fast" green
  ```
- `card <position> <reveal> <timing>` + children — a framed card that assembles
  line-by-line. Children: `formula "…"`, `arrow`, `result "…"`, `subtitle "…"`,
  `icon <name>`.
- `code "<content>" <reveal> <timing>` — a code block (optional `shrink <n>
  move-top <timing>` child to shrink and rise).
- `trace-log <timing> <reveal>` + `columns …` / entry lines / `badge "…"` — a
  log/table that fills row by row.

### Diagrams (viz escape hatch)
`viz <timing> <reveal>` with a `type:` and structured (YAML-like) children:
```
viz 0-6s fade
  type: flow-diagram
  nodes:
    - "Input"
    - "Parse"
    - "Render"
```
`type:` is one of `node-graph`, `flow-diagram`, `boundary-sim`, `workspace`,
`protocol-compare`, `trace-log`, or `custom` (with a `"""…"""` raw inline-SVG
block). An unknown/absent type still renders a titled panel, never nothing.

## Vocabulary reference

- **fonts:** `display`, `display-italic`, `body`, `mono`, `hero`
- **positions:** `center`, `upper-left`, `upper-right`, `bottom-center`, `bottom-right`
- **reveals:** `fade`, `word-stagger`, `typewriter`, `slide-up`, `scale-in`, `none`
- **accents** (text-cycle phrases): `underline`, `strike`, `hero`, `dim`, `glow`
- **transitions** (scene handoff): `cut`, `crossfade`, `blur-crossfade`, `push-left`, `push-right`, `push-up`, `zoom-through`
- **themes:** `clean`, `cobalt-grid`, `dark-tech`, `warm-editorial`

Prefer `list_components` / `list_icons` at run time — they are read from this
build's code, so they never drift from what actually renders.

## Full example

```
VDSL/1
theme dark-tech
canvas 1920x1080

scene "Intro" 4s cut
  text "Ship explainers in minutes" hero center word-stagger 0-3s
  label "no video encoding — just HTML" bottom-center 1.5-4s

scene "How it works" 6s crossfade
  step-sequence 0-6s
    "1. Write" "a compact .vdsl spec"
    "2. Render" "one self-contained HTML player"
    "3. Embed" "drop it into any page"

scene "Why" 5s crossfade
  triptych 0-5s stagger
    "Instant" "opens and plays"
    "Portable" "single HTML file"
    "Embeddable" "<vdsl-player>"

scene "Close" 3s crossfade
  text "Describe it. Play it." display center fade 0-3s
  byline "made with A2TL-Video" bottom-right 1-3s
```

## Embedding the player

The generated `.html` opens and plays on its own. To embed it in a page, use the
`<vdsl-player>` web component, which hosts the player in a style-isolated iframe:

```html
<script src="embed/vdsl-player.js"></script>
<vdsl-player src="video.html" ratio="16/9" autoplay></vdsl-player>
```

Attributes: `src` (URL of a generated player HTML), `srcdoc` (inline player HTML),
`ratio` (default `16/9`), `autoplay`, `maxwidth`. Inside the frame the player
exposes `window.vdslPlayer` (`play()`, `pause()`, `seek(frame)`,
`seekTime(sec)`, `frame`, `fps`, `totalFrames`); from the component reach it via
`element.player`.

## Tips

- Keep scenes ~3-8s. Roughly ~30 lines of .vdsl ≈ ~15s of playback; scale from there.
- Composite blocks (triptych, step-sequence, card, trace-log, viz) build their
  parts progressively — author them as a small set of clear beats, not a wall.
- Use `crossfade` / `blur-crossfade` between scenes for a smooth flow; `cut` for a snap.
- One idea per scene; let text reveals (`word-stagger`, `typewriter`) pace the reading.
- Always deliver the HTML player -- never attempt an MP4 render.
