import type { VDSLSpec, Scene, Component, Theme } from "../parser/types";
import { themes, resolveTheme, mergeTheme } from "../themes";
import { getIcon } from "../icons";

export function renderToHTML(spec: VDSLSpec, themeName?: string): string {
  const base = themeName ? resolveTheme(themeName) : (spec.theme ? resolveTheme(spec.theme) : resolveTheme("cobalt-grid"));
  const theme = mergeTheme(base, spec.themeOverride);
  const fps = 30;
  const width = spec.canvas?.width ?? 1920;
  const height = spec.canvas?.height ?? 1080;

  const sceneHtml = spec.scenes.map((scene, si) => renderScene(scene, si, spec, theme, fps)).join("\n");

  // Depth vignette. On LIGHT themes bg2 is a touch darker than bg, so tinting the
  // edges toward bg2 reads as a soft, warm darkening. On DARK themes bg2 is
  // LIGHTER than bg (cards must lift off the near-black scene), so that same
  // formula would LIGHTEN the corners — an inverted "halo" vignette. Detect the
  // case by luminance and, for dark themes, darken toward black instead so the
  // stage keeps real depth (never a muddy hole: the centre stays untouched).
  const stageVignette = relLum(theme.colors.bg2) > relLum(theme.colors.bg)
    ? `radial-gradient(ellipse 118% 104% at 50% 36%, rgba(0,0,0,0) 40%, rgba(0,0,0,0.45) 120%)`
    : `radial-gradient(ellipse 118% 104% at 50% 36%, ${theme.colors.bg2}00 42%, ${theme.colors.bg2}dd 118%)`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A2TL-Video Player</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; }
  body { background: #111; overflow: hidden; font-family: system-ui; }
  #player { position: fixed; top: 50%; left: 50%; width: ${width}px; height: ${height}px; background:
      radial-gradient(ellipse 118% 104% at 50% 36%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.05) 120%),
      ${stageVignette},
      ${theme.colors.bg}; border-radius: 8px; box-shadow: 0 0 60px rgba(0,0,0,0.5); overflow: hidden; transform-origin: center center; }
  #controls { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; gap: 12px; align-items: center; background: rgba(0,0,0,0.8); padding: 10px 20px; border-radius: 12px; z-index: 1000; }
  #controls button { background: #333; color: #fff; border: none; padding: 6px 16px; border-radius: 6px; cursor: pointer; font-size: 14px; }
  #controls button:hover { background: #555; }
  #controls input[type=range] { width: 200px; }
  #controls label { color: #aaa; font-size: 12px; min-width: 60px; }
  .scene-layer { position: absolute; inset: 0; }
  .vdsl-el { position: absolute; will-change: transform, opacity; }
  .theme-grid { width: 100%; height: 100%; position: absolute; inset: 0; pointer-events: none; }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
  @keyframes slideUp { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes typewriter { from { width: 0; } to { width: 100%; } }
</style>
</head>
<body>
<div id="player">
  ${sceneHtml}
</div>
<div id="controls">
  <button id="playBtn">▶</button>
  <input type="range" id="seekBar" min="0" max="100" value="0">
  <label id="timeLabel">0:00</label>
</div>
<script>
(function() {
  const player = document.getElementById('player');
  const fps = ${fps};
  const totalFrames = ${spec.scenes.reduce((s, sc) => s + Math.round(sc.duration * fps), 0)};
  const scenes = ${JSON.stringify(spec.scenes.map((s) => ({ duration: Math.round(s.duration * fps), startFrame: 0, transition: s.transition || "cut" })))};
  let currentFrame = -1;
  let playing = false;
  let rafId = null;

  let acc = 0;
  const sceneStarts = scenes.map((s) => { const start = acc; acc += s.duration; return start; });
  const sceneLayers = Array.prototype.slice.call(document.querySelectorAll('.scene-layer'));

  function getSceneForFrame(frame) {
    for (let i = sceneStarts.length - 1; i >= 0; i--) {
      if (frame >= sceneStarts[i]) return i;
    }
    return 0;
  }

  // --- Motion helpers: everything is a pure function of the current frame so
  // it stays correct under seeking/scrubbing. ---
  var ENTER = 14;      // entrance duration (frames) for an element/child
  var EDGE_DUR = 16;   // edge draw-on duration
  // --- Round 15: progressive, WINDOW-SPREAD assembly at a HUMAN reading pace.
  // A composite no longer pops all its parts in within ~1s at the start; instead
  // its N distinct entrance SLOTS are distributed across a BUILD PHASE of ~75%
  // of the element's own authored window (leaving dwell time to absorb the
  // finished picture before it exits). The per-slot step is computed at runtime
  // from each container's window + slot count (see stgStep) and clamped to a
  // comfortable human range so parts never blur past nor drag: ---
  var STG_MIN = 24;    // ~0.8s: a viewer can read/absorb each part
  var STG_MAX = 54;    // ~1.8s: never lets the build drag
  var BUILD_FRAC = 0.75; // fraction of the window spent building (rest = dwell)

  // Per-slot stagger step (frames) for a composite with "slots" distinct
  // entrance slots and authored window duration D frames (Infinity => open
  // window). Pure function => seek-safe. Spreads the build across ~BUILD_FRAC of
  // the window, clamped to [STG_MIN, STG_MAX], then capped so the LAST part
  // finishes entering (+ENTER) by ~90% of the window (a little dwell to spare).
  function stgStep(D, slots) {
    if (slots < 2) return STG_MIN;
    if (!isFinite(D)) return STG_MIN; // open-ended: comfortable minimum
    var step = (D * BUILD_FRAC) / slots;
    if (step < STG_MIN) step = STG_MIN;
    if (step > STG_MAX) step = STG_MAX;
    var maxStep = (D * 0.9 - ENTER) / (slots - 1); // guarantee it all fits
    if (maxStep > 0 && step > maxStep) step = maxStep;
    return step < 1 ? 1 : step;
  }
  // --- Dead-air bridging: every timed element fades in a touch BEFORE its cue
  // (LEAD) and fades out a touch AFTER its end (TAIL) so consecutive elements
  // overlap instead of leaving a blank gap — within a scene AND across the
  // transition window (TAIL >= TWIN keeps the outgoing scene populated for the
  // whole handoff). Purely frame-driven, so scrubbing stays correct. ---
  var LEAD = 12;       // entrance reaches full ~at the authored cue
  var TAIL = 18;       // exit fade extends past the authored end
  // --- Same-slot succession (Round 11): when a NEW element takes over the exact
  // same on-screen slot (same band+lane, or same corner for 'full') right after
  // this one, the dead-air TAIL/LEAD used to leave the two ghosting on top of
  // each other (the "overlap"). Instead we do a clean HARD CUT (the same
  // guarantee text-cycle already uses): the outgoing stays FULL right up to the
  // successor's cue (so no blank ever opens), then vanishes on that exact frame,
  // and the incoming appears already SETTLED at full from its cue (no early LEAD
  // fade-in over the outgoing). Result: exactly one of the pair is visible on
  // every frame — no overlap, no blank — and it stays purely frame-driven. ---
  var SETTLED = 100000; // anim clock far past ENTER ⇒ a successor shows settled

  // Respect the viewer's OS "reduce motion" preference: drop decorative motion
  // (ambient float/bob + entrance transform overshoot) and keep only opacity
  // fades, so the video is comfortable for motion-sensitive users. Timing/layout
  // are unaffected.
  var reduceMotion = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  function clamp01(x) { return x < 0 ? 0 : (x > 1 ? 1 : x); }
  function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }
  // Ease-out-back: overshoots slightly past 1 near the end, then settles to
  // EXACTLY 1 at t=1 (f(1) === 1), so entrances arrive with a springy little
  // overshoot but land dead on identity. s tunes the overshoot amount
  // (roughly s*10% peak); kept gentle for taste.
  function easeOutBack(t, s) { s = (s == null ? 1.35 : s); var u = t - 1; return 1 + (s + 1) * u * u * u + s * u * u; }

  // Maps a reveal name + local frame -> {opacity, transform}. Opacity rides an
  // ease-out-cubic (monotonic — never flickers past 1); the TRANSFORM rides an
  // ease-out-back so position/scale settle with a small spring overshoot. Both
  // reach identity exactly at f>=ENTER (b(1)===1) so elements rest perfectly.
  function revealStyle(reveal, f) {
    var t = clamp01(f / ENTER);
    var p = easeOutCubic(t);   // opacity progress
    if (reduceMotion) return { opacity: p, transform: '' }; // fade only, no movement
    var b = easeOutBack(t);    // transform progress (overshoots, settles to 1)
    var tf = '';
    switch (reveal) {
      case 'slide-up':   tf = 'translateY(' + ((1 - b) * 26) + 'px)'; break;
      case 'slide-left': tf = 'translateX(' + ((1 - b) * 44) + 'px)'; break;
      case 'scale-in':   tf = 'scale(' + (0.82 + 0.18 * b) + ')'; break;
      case 'build-up':   tf = 'translateY(' + ((1 - b) * 16) + 'px) scale(' + (0.96 + 0.04 * b) + ')'; break;
      case 'split-tilt': tf = 'perspective(900px) rotateX(' + ((1 - b) * 12) + 'deg) translateY(' + ((1 - b) * 22) + 'px)'; break;
      case 'stagger':    tf = 'translateY(' + ((1 - b) * 22) + 'px) scale(' + (0.94 + 0.06 * b) + ')'; break;
      // grow-up: a chart bar rising from its baseline. Uses the MONOTONIC
      // ease-out-cubic (p, not the overshooting b) so the bar never shoots past
      // its final height and clips its value label. Pair with a CSS
      // transform-origin:bottom on the element so it grows upward from the axis.
      case 'grow-up':    tf = 'scaleY(' + p.toFixed(4) + ')'; break;
      default:           tf = ''; break; // fade: opacity only
    }
    return { opacity: p, transform: tf };
  }

  // --- Scene-to-scene transitions -------------------------------------------
  // Everything is a pure function of the global frame, so it stays correct
  // under seeking. A transition WINDOW of TWIN frames (~0.5s) opens right at a
  // scene boundary; inside it BOTH the outgoing and incoming scene LAYERS are
  // rendered and blended per scenes[i].transition (which governs i-1 -> i).
  var TWIN = 15; // transition window length in frames (~0.5s at 30fps)

  function smoothstep(t) { return t * t * (3 - 2 * t); }

  // Clear any layer-level transform/opacity/filter so the settled look and the
  // per-element animation underneath are untouched outside transitions.
  function resetLayer(layer) {
    layer.style.opacity = '';
    layer.style.transform = '';
    layer.style.filter = '';
    layer.style.zIndex = '';
  }

  // Blend two scene LAYERS (never individual elements). t is 0..1 across window.
  // Canonical VDSL transition names (fade, dissolve, slide, zoom) are mapped to
  // the concrete visual behaviour so both the spec names and the long-form names
  // work identically.
  function applyTransition(out, inc, type, t) {
    var e = smoothstep(clamp01(t));
    out.style.filter = ''; inc.style.filter = '';
    out.style.transform = ''; inc.style.transform = '';
    inc.style.zIndex = '2'; out.style.zIndex = '1';
    switch (type) {
      case 'fade':        // canonical VDSL name
      case 'crossfade':
      case 'dissolve':    // canonical VDSL name — same visual as crossfade
        out.style.opacity = String(1 - e);
        inc.style.opacity = String(e);
        // Breathe: the incoming scene eases up from a whisper of scale so the
        // cut arrives with a little life instead of a flat dissolve. Lands on
        // exactly scale(1) at e=1, and resetLayer clears it once settled.
        inc.style.transform = 'scale(' + (0.994 + 0.006 * e) + ')';
        break;
      case 'blur-crossfade': {
        out.style.opacity = String(1 - e);
        inc.style.opacity = String(e);
        var blur = Math.sin(Math.PI * clamp01(t)) * 10; // peaks mid-transition
        out.style.filter = 'blur(' + blur + 'px)';
        inc.style.filter = 'blur(' + blur + 'px)';
        inc.style.transform = 'scale(' + (0.994 + 0.006 * e) + ')';
        break;
      }
      case 'slide':       // canonical VDSL name — default direction is push-left
      case 'push-left':   // content pushes left: incoming from right, outgoing off left
        out.style.opacity = '1'; inc.style.opacity = '1';
        out.style.transform = 'translateX(' + (-100 * e) + '%)';
        inc.style.transform = 'translateX(' + (100 * (1 - e)) + '%)';
        break;
      case 'push-right': // content pushes right: incoming from left, outgoing off right
        out.style.opacity = '1'; inc.style.opacity = '1';
        out.style.transform = 'translateX(' + (100 * e) + '%)';
        inc.style.transform = 'translateX(' + (-100 * (1 - e)) + '%)';
        break;
      case 'push-up': // content pushes up: incoming from bottom, outgoing off top
        out.style.opacity = '1'; inc.style.opacity = '1';
        out.style.transform = 'translateY(' + (-100 * e) + '%)';
        inc.style.transform = 'translateY(' + (100 * (1 - e)) + '%)';
        break;
      case 'zoom':        // canonical VDSL name
      case 'zoom-through':
        out.style.opacity = String(1 - e);
        inc.style.opacity = String(e);
        out.style.transform = 'scale(' + (1 + 0.4 * e) + ')';
        inc.style.transform = 'scale(' + (0.9 + 0.1 * e) + ')';
        break;
      default: // treat unknown as an instant cut
        out.style.opacity = '0'; inc.style.opacity = '1';
    }
  }

  function updateDisplay(frame) {
    const si = getSceneForFrame(frame);

    // Are we inside a transition window just after a scene boundary?
    // scenes[si].transition governs the (si-1 -> si) handoff.
    var inTransition = false, tprog = 0, outIdx = -1, inIdx = -1, ttype = 'cut';
    if (si > 0 && scenes[si] && scenes[si].transition && scenes[si].transition !== 'cut') {
      var b = sceneStarts[si];
      if (frame >= b && frame < b + TWIN) {
        inTransition = true;
        tprog = (frame - b) / TWIN;
        outIdx = si - 1; inIdx = si; ttype = scenes[si].transition;
      }
    }

    if (inTransition) {
      // Both layers visible; each driven by its OWN scene-local frame so
      // per-element (Round 3) motion keeps working during the blend.
      for (let i = 0; i < sceneLayers.length; i++) {
        sceneLayers[i].style.display = (i === outIdx || i === inIdx) ? 'block' : 'none';
      }
      applyTransition(sceneLayers[outIdx], sceneLayers[inIdx], ttype, tprog);
      // During a transition the LEAD is ALWAYS applied: the scene-level opacity
      // from applyTransition masks the early entrance so elements are "ready"
      // when the incoming scene is fully visible.
      applyElementTiming(sceneLayers[outIdx], frame - sceneStarts[outIdx], true);
      applyElementTiming(sceneLayers[inIdx], frame - sceneStarts[inIdx], true);
      applyAmbient(sceneLayers[outIdx], frame);
      applyAmbient(sceneLayers[inIdx], frame);
      return;
    }

    // Settled: exactly one visible layer, no residual layer-level styling.
    for (let i = 0; i < sceneLayers.length; i++) {
      sceneLayers[i].style.display = (i === si) ? 'block' : 'none';
    }
    const active = sceneLayers[si];
    if (!active) return;
    resetLayer(active);
    // LEAD pre-advances the animation clock so elements appear "ready" when a
    // transition reveals the scene.  When the scene has NO gradual incoming
    // transition (scene 0, or any "cut") there is nothing to mask the early
    // entrance, so we suppress LEAD to guarantee a full visible entrance
    // animation from the first frame.
    var useLead = si > 0 && scenes[si] && scenes[si].transition && scenes[si].transition !== 'cut';
    applyElementTiming(active, frame - sceneStarts[si], useLead);
    applyAmbient(active, frame);
  }

  // --- Ambient micro-motion: keeps a settled scene alive between events.
  // Everything is a pure function of the GLOBAL frame so it stays correct under
  // seeking and never accumulates. Amplitudes are deliberately tiny. ---
  function applyAmbient(layer, gf) {
    if (reduceMotion) return; // no decorative float/bob for motion-sensitive viewers
    // (1) The background grid is STATIC. An earlier round drifted it slowly, but
    // a moving background reads as distracting ("el fondo no debe distraer"), so
    // we leave the grid at rest and never touch its transform. All the CONTENT
    // motion below (center-block/viz float, node bob) plus entrance overshoot,
    // edge flow and the transition breathe stay intact.
    // (2) Faint vertical float + a whisper of horizontal parallax on the
    // primary CENTER block (viz/hero). Only bands that host a viz float, so body
    // text stays perfectly placed. Amplitude a few px, ~10s period.
    var bands = layer.querySelectorAll('.scene-band.band-center');
    for (var i = 0; i < bands.length; i++) {
      var band = bands[i];
      if (band.querySelector('[data-el="viz"]')) {
        var fy = Math.sin(gf * 0.021) * 4.0;
        var fx = Math.cos(gf * 0.017) * 2.0;
        band.style.transform = 'translate(' + fx.toFixed(2) + 'px,' + fy.toFixed(2) + 'px)';
      } else {
        band.style.transform = '';
      }
    }
    // (3) Node-graph nodes gently bob, desynced per node so the graph breathes
    // instead of pulsing in lockstep. Composes with the pop-in scale (separate
    // wrapper), amplitude ~2.4px.
    var bobs = layer.querySelectorAll('.node-bob');
    for (var b = 0; b < bobs.length; b++) {
      var idx = parseInt(bobs[b].getAttribute('data-i') || '0', 10) || 0;
      var by = Math.sin(gf * 0.045 + idx * 1.7) * 2.4;
      bobs[b].style.transform = 'translateY(' + by.toFixed(2) + 'px)';
    }
  }

  // Drives per-element, SCENE-RELATIVE timing for a single layer. Extracted so
  // both the outgoing and incoming layers can animate during a transition.
  // useLead: when true the dead-air LEAD is applied (elements pre-fade-in so
  // they are "ready" when a transition reveals the scene). When false (scene 0
  // or any "cut" transition, nothing masks the early entrance) LEAD is
  // suppressed so elements get their full visible entrance animation.
  function applyElementTiming(active, localFrame, useLead) {
    var effectiveLead = useLead ? LEAD : 0;
    const els = active.querySelectorAll('[data-el]');
    for (let k = 0; k < els.length; k++) {
      const el = els[k];
      const start = parseFloat(el.getAttribute('data-start')) || 0;
      const endAttr = el.getAttribute('data-end');
      const end = (endAttr !== null && endAttr !== '') ? parseFloat(endAttr) : Infinity;
      const reveal = el.getAttribute('data-reveal') || 'fade';
      const startFrame = start * fps;
      const endFrame = (end === Infinity) ? Infinity : end * fps;
      el.style.pointerEvents = 'none';

      // --- text-cycle: dedicated CROSSFADE. Each phrase fades over a window XF
      // centred on its start and end, so at every seam the outgoing phrase is at
      // ~0.5 while the incoming is at ~0.5 (they sum to ~1) — no blank instant,
      // and consecutive phrases dissolve into one another. ---
      if (el.getAttribute('data-el') === 'textcycle') {
        // Hard cut (spec: "hard-cut entre frases"). Phrase windows are contiguous
        // [start,end), so at every frame EXACTLY ONE phrase is visible — no blank
        // seam and never two phrases overlapping on the same centre.
        var baseOp = parseFloat(el.getAttribute('data-op'));
        if (isNaN(baseOp)) baseOp = 1;
        if (localFrame >= startFrame && (endFrame === Infinity || localFrame < endFrame)) {
          el.style.visibility = 'visible';
          el.style.opacity = String(baseOp);
          el.style.transform = '';
        } else {
          el.style.opacity = '0';
          el.style.visibility = 'hidden';
          el.style.transform = '';
        }
        continue;
      }

      // Same-slot succession hints (Round 11) live on the wrapping .scene-band:
      //  data-succ = successor's start (seconds) → this element is a predecessor
      //  data-pred = "1"                          → this element is a successor
      var host = el.closest ? el.closest('.scene-band') : el.parentNode;
      var isPred = !!(host && host.getAttribute && host.getAttribute('data-pred'));
      var succAttr = (host && host.getAttribute) ? host.getAttribute('data-succ') : null;
      var succFrame = (succAttr !== null && succAttr !== '') ? parseFloat(succAttr) * fps : null;

      // A successor (isPred) drops its LEAD so it never fades in early over the
      // outgoing, and shows already SETTLED (its entrance reveal is suppressed
      // only at THIS replacement seam) so it is at full opacity the instant it
      // appears — a crisp cut, never a fade-in that dips toward blank.
      const leadN = isPred ? 0 : effectiveLead;
      const visStart = startFrame - leadN;
      // A predecessor stays FULL until its successor's cue and then vanishes on
      // that exact frame (visEnd = succFrame). Otherwise the classic dead-air
      // TAIL bridges to whatever (if anything) comes next.
      let visEnd;
      if (succFrame != null) {
        visEnd = succFrame;
      } else {
        visEnd = (endFrame === Infinity) ? Infinity : endFrame + TAIL;
      }
      // animFrame drives the reveal. A plain successor is pinned SETTLED so it
      // never animates its entrance on top of / into the outgoing (Round 11
      // hard cut). BUT a COMPOSITE successor (has .stg parts) must still BUILD
      // progressively from its cue (Round 15) — the predecessor has already
      // vanished on this exact frame (visEnd === succFrame === our cue), so
      // there's nothing to overlap. It just drops the early LEAD so no part
      // shows before the cue.
      const hasStg = !!(el.querySelector && el.querySelector('.stg'));
      const animFrame = isPred
        ? (hasStg ? (localFrame - startFrame) : SETTLED)
        : (localFrame - startFrame + effectiveLead);

      if (localFrame >= visStart && localFrame < visEnd) {
        // NOTE: never touch el.style.display here — it holds the flex layout
        // that centres/positions the content. Toggle opacity + visibility only.
        el.style.visibility = 'visible';

        // Exit fade: a predecessor is FULL right up to its successor's cue (the
        // visEnd gate above hides it exactly on that frame — a hard cut, no
        // fade). Otherwise the dead-air TAIL after the authored end.
        let exitMul = 1;
        if (succFrame == null && endFrame !== Infinity && localFrame >= endFrame) {
          exitMul = clamp01((visEnd - localFrame) / TAIL);
        }

        if (reveal === 'word-stagger') {
          el.style.opacity = exitMul;
          el.style.transform = '';
          const words = el.querySelectorAll('.word');
          words.forEach((w, i) => {
            const wf = animFrame - i * 4;
            const opacity = Math.min(1, Math.max(0, wf / 10));
            const ty = Math.max(0, 30 - Math.min(1, wf / 14) * 30);
            w.style.opacity = opacity;
            w.style.transform = 'translateY(' + ty + 'px)';
            w.style.filter = wf < 12 ? 'blur(' + Math.max(0, 4 - Math.max(0, wf) / 12 * 4) + 'px)' : 'none';
          });
          // Accent rule fades in just behind the words (kept subtle).
          const rule = el.querySelector('.accent-rule');
          if (rule) rule.style.opacity = String(clamp01((animFrame - 6) / 14) * 0.92);
        } else if (reveal === 'typewriter') {
          el.style.opacity = exitMul;
          el.style.transform = '';
          const chars = Math.floor(Math.max(0, animFrame) / 2);
          // Reveal text character-by-character (seek-safe: pure f(frame)).
          var twSpan = el.querySelector('.tw-text');
          if (twSpan) {
            var full = twSpan.getAttribute('data-fulltext') || '';
            twSpan.textContent = full.slice(0, chars);
          }
          // Blink the cursor while typing, hide once done.
          var twCur = el.querySelector('.tw-cursor');
          if (twCur) {
            twCur.style.opacity = chars >= (twSpan ? (twSpan.getAttribute('data-fulltext') || '').length : 0) ? '0' : String(0.5 + 0.3 * Math.sin(animFrame * 0.3));
          }
        } else {
          // Composite blocks tag their children with .stg (+ data-stagger).
          // If present, the container stays visible and each child eases in on
          // its own offset; otherwise the reveal drives the element itself.
          const stg = el.querySelectorAll('.stg');
          if (stg.length) {
            el.style.opacity = exitMul;
            el.style.transform = '';
            // Each child's entrance SLOT: node-graph tags an assembly-order
            // data-seq (nodes and edges interleaved so it reads node→edge→node);
            // every other composite falls back to its authored data-stagger.
            // Multiple children can share a slot (e.g. a flow arrow rides with
            // its card), so the number of distinct slots = maxSlot + 1.
            var slotOf = function(c) {
              var v = c.getAttribute('data-seq');
              if (v == null || v === '') v = c.getAttribute('data-stagger');
              return parseInt(v || '0', 10) || 0;
            };
            var slots = 1;
            for (let s = 0; s < stg.length; s++) {
              var sv = slotOf(stg[s]) + 1;
              if (sv > slots) slots = sv;
            }
            // Dynamic, window-spread step for THIS container (see stgStep).
            var STEP = stgStep(endFrame - startFrame, slots);
            for (let s = 0; s < stg.length; s++) {
              const child = stg[s];
              const idx = slotOf(child);
              if (child.classList && child.classList.contains('edge-draw')) {
                // Draw-on: solid dash of the full length, offset full->0. Once
                // complete we clear the inline styles so the resting
                // stroke-dasharray attribute (dashed/dotted) reappears. The
                // edge's slot lands AFTER both its endpoint nodes (assembly
                // order), so it draws on once they exist.
                const cf = animFrame - idx * STEP;
                if (reduceMotion) {
                  // Motion-sensitive: no draw-on sweep — fade the edge in on the
                  // same staggered slot so the graph still assembles gradually.
                  const fp = easeOutCubic(clamp01(cf / EDGE_DUR));
                  child.style.strokeDasharray = '';
                  child.style.strokeDashoffset = '';
                  child.style.opacity = String(0.6 * fp);
                  continue;
                }
                const ep = easeOutCubic(clamp01(cf / EDGE_DUR));
                if (ep >= 1) {
                  // Drawn: restore the resting dash pattern (from the attribute)
                  // and give it a faint, slow FLOW by marching the dash offset.
                  // Frame-driven (localFrame) so it stays seek-safe; on a solid
                  // edge the offset is a no-op. Very slow (~0.22px/frame).
                  child.style.strokeDasharray = '';
                  child.style.strokeDashoffset = String(-(localFrame * 0.22).toFixed(2));
                  child.style.opacity = '';
                } else {
                  if (child.__len == null && child.getTotalLength) {
                    try { child.__len = child.getTotalLength(); } catch (e) { child.__len = 0; }
                  }
                  const L = child.__len || 0;
                  child.style.strokeDasharray = String(L);
                  child.style.strokeDashoffset = String(L * (1 - ep));
                  child.style.opacity = String(0.6 * Math.min(1, ep + 0.15));
                }
              } else {
                // A child may override the container reveal with its own
                // data-reveal (custom-viz SVG maps data-animate → this); absent
                // that, it inherits the container's reveal (built-in vizzes).
                const childReveal = child.getAttribute('data-reveal') || reveal;
                const cf = animFrame - idx * STEP;
                const rs = revealStyle(childReveal, cf);
                child.style.opacity = rs.opacity;
                child.style.transform = rs.transform;
              }
            }
          } else {
            const rs = revealStyle(reveal, animFrame);
            el.style.opacity = rs.opacity * exitMul;
            el.style.transform = rs.transform;
          }
        }
      } else {
        el.style.opacity = 0;
        el.style.visibility = 'hidden';
      }
    }

    // --- Count-up numbers (chart counter) -----------------------------------
    // Any .countup rides an ease-out-cubic from 0 to data-to across data-dur
    // frames starting at data-start (scene-relative seconds). Pure function of
    // localFrame ⇒ scrubbing lands on the exact interpolated value; the wrapping
    // viz element's reveal still owns the fade/scale entrance and visibility.
    var cups = active.querySelectorAll('.countup');
    for (var c = 0; c < cups.length; c++) {
      var cu = cups[c];
      var cst = (parseFloat(cu.getAttribute('data-start')) || 0) * fps;
      var cdur = parseFloat(cu.getAttribute('data-dur')) || 30;
      var cto = parseFloat(cu.getAttribute('data-to')) || 0;
      var cdec = parseInt(cu.getAttribute('data-decimals') || '0', 10) || 0;
      var cpre = cu.getAttribute('data-prefix') || '';
      var csuf = cu.getAttribute('data-suffix') || '';
      var ct = clamp01((localFrame - cst) / cdur);
      var cval = cto * easeOutCubic(ct);
      cu.textContent = cpre + cval.toFixed(cdec) + csuf;
    }
  }

  var lastTickTime = 0;
  var frameDuration = 1000 / fps; // ms per frame (e.g. 33.3ms at 30fps)
  var accumulator = 0;

  function tick(now) {
    if (!playing) return;
    if (lastTickTime === 0) lastTickTime = now;
    var delta = now - lastTickTime;
    lastTickTime = now;
    // Cap delta to avoid spiral after tab switch / debugger pause
    if (delta > 200) delta = frameDuration;
    accumulator += delta;
    var advanced = false;
    while (accumulator >= frameDuration) {
      accumulator -= frameDuration;
      currentFrame++;
      advanced = true;
    }
    if (advanced) {
      if (currentFrame >= totalFrames) { currentFrame = 0; }
      updateDisplay(currentFrame);
      const t = currentFrame / fps;
      document.getElementById('seekBar').value = (currentFrame / totalFrames) * 100;
      const mins = Math.floor(t / 60);
      const secs = Math.floor(t % 60);
      document.getElementById('timeLabel').textContent = mins + ':' + (secs < 10 ? '0' : '') + secs;
    }
    rafId = requestAnimationFrame(tick);
  }

  document.getElementById('playBtn').addEventListener('click', function() {
    playing = !playing;
    this.textContent = playing ? '⏸' : '▶';
    if (playing) { lastTickTime = 0; accumulator = 0; if (currentFrame < 0) currentFrame = 0; rafId = requestAnimationFrame(tick); }
    else { if (rafId) cancelAnimationFrame(rafId); }
  });

  document.getElementById('seekBar').addEventListener('input', function() {
    const pct = parseFloat(this.value) / 100;
    currentFrame = Math.floor(pct * totalFrames);
    if (!playing) updateDisplay(currentFrame);
    const t = currentFrame / fps;
    const mins = Math.floor(t / 60);
    const secs = Math.floor(t % 60);
    document.getElementById('timeLabel').textContent = mins + ':' + (secs < 10 ? '0' : '') + secs;
  });

  currentFrame = 0;
  updateDisplay(0);

  // --- Fit the fixed-size stage into the viewport (fills + centres; robust in
  // an <iframe>: #player is position:fixed so its 1920x1080 layout box never
  // forces overflow, and we re-fit on resize + a few rAFs after load). ---
  function fit() {
    const scale = Math.min(window.innerWidth / player.offsetWidth, window.innerHeight / player.offsetHeight);
    player.style.transform = 'translate(-50%, -50%) scale(' + scale + ')';
  }
  window.addEventListener('resize', fit);
  if (window.ResizeObserver) { try { new ResizeObserver(fit).observe(document.documentElement); } catch (e) {} }
  fit();
  requestAnimationFrame(fit);
  setTimeout(fit, 120);
  setTimeout(fit, 400);

  // --- Programmatic control API (embedding + headless screenshots) ---
  function doSeek(f) {
    currentFrame = Math.max(0, Math.min(totalFrames - 1, Math.round(f)));
    updateDisplay(currentFrame);
    document.getElementById('seekBar').value = (currentFrame / totalFrames) * 100;
  }
  window.vdslPlayer = {
    seek: doSeek,
    seekTime: function (sec) { doSeek(sec * fps); },
    play: function () { if (!playing) { playing = true; lastTickTime = 0; accumulator = 0; document.getElementById('playBtn').textContent = '⏸'; if (currentFrame < 0) currentFrame = 0; rafId = requestAnimationFrame(tick); } },
    pause: function () { playing = false; if (rafId) cancelAnimationFrame(rafId); document.getElementById('playBtn').textContent = '▶'; },
    get totalFrames() { return totalFrames; },
    get fps() { return fps; },
    get frame() { return currentFrame; }
  };
  window.__vdslReady = true;

  // Hide controls after mouse idle
  let hideTimer = null;
  document.addEventListener('mousemove', function() {
    document.getElementById('controls').style.opacity = '1';
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(function() {
      if (playing) document.getElementById('controls').style.opacity = '0.2';
    }, 3000);
  });
})();
</script>
</body>
</html>`;
}

function renderScene(scene: Scene, si: number, spec: VDSLSpec, theme: Theme, fps: number): string {
  const startFrame = spec.scenes.slice(0, si).reduce((s, sc) => s + Math.round(sc.duration * fps), 0);
  const durFrames = Math.round(scene.duration * fps);
  const startSec = startFrame / fps;
  const endSec = (startFrame + durFrames) / fps;

  const gridHtml = theme.grid ? renderGrid(theme, si) : "";

  // Build the render items first so we can resolve time-aware collisions before
  // committing to vertical positions.
  const items = scene.components
    .map((comp) => ({
      comp: comp as any,
      band: layoutBand(comp),
      html: renderComponent(comp, theme, startSec),
      lane: 0,
      laneCount: 1,
    }))
    .filter((it) => it.html);

  // Time-aware lane assignment: within a band, components whose authored
  // windows OVERLAP get split into separate vertical lanes so they never stack
  // on the same spot. Components that are merely sequential keep sharing one
  // full-size lane (so single-component / hand-authored scenes are unchanged).
  assignLanes(items, scene.duration);

  const componentHtml = items
    .map((it) => {
      // Wrap each component in a positioned "band" region so simultaneously
      // visible components land in different vertical zones instead of all
      // stacking at inset:0 center and overlapping. The component keeps its
      // own `position:absolute;inset:0;flex-center`, which now centres it
      // WITHIN the band (or lane) box rather than across the whole scene.
      const succAttr = (it as any)._succ != null ? ` data-succ="${(it as any)._succ}"` : "";
      const predAttr = (it as any)._pred ? ` data-pred="1"` : "";
      // Offset time-overlapping same-corner items so they don't sit on top of
      // each other (top corners stack downward, bottom corners upward).
      const cs = (it as any)._cornerStack || 0;
      let extra = "";
      if (it.band === "full" && cs > 0) {
        const p = String((it.comp && it.comp.position) || "");
        const dir = p.indexOf("bottom") === 0 ? -1 : 1;
        extra = `transform:translateY(${dir * cs * 96}px);`;
      }
      return `<div class="scene-band band-${it.band}"${succAttr}${predAttr} style="${bandLaneStyle(it.band, it.lane, it.laneCount)};${extra}">${it.html}</div>`;
    })
    .join("\n");

  return `<div class="scene-layer" data-scene="${si}" style="display:none">
    ${gridHtml}
    ${componentHtml}
  </div>`;
}

/** The authored [start, end) window of a component, in seconds. Falls back to
 *  the whole scene when a component has no explicit timing (e.g. text-cycle,
 *  whose span is the union of its phrases). */
function compInterval(comp: any, sceneDur: number): [number, number] {
  let s = comp?.timing && typeof comp.timing.start === "number" ? comp.timing.start : undefined;
  let e = comp?.timing && typeof comp.timing.end === "number" ? comp.timing.end : undefined;
  if (s === undefined) {
    const phrases = comp?.phrases;
    if (Array.isArray(phrases) && phrases.length && phrases[0] && phrases[0].timing) {
      s = Math.min(...phrases.map((p: any) => (p.timing && typeof p.timing.start === "number" ? p.timing.start : 0)));
      e = Math.max(...phrases.map((p: any) => (p.timing && typeof p.timing.end === "number" ? p.timing.end : sceneDur)));
    }
  }
  if (typeof s !== "number") s = 0;
  if (typeof e !== "number") e = sceneDur;
  return [s, e];
}

/** A coarse "kind" so we can tell a list of like items (which should stack)
 *  from a sequence of different blocks (which may share a lane and crossfade). */
function kindOf(comp: any): string {
  if (comp && comp.type === "text") return "text:" + (comp.font || "body");
  return comp ? String(comp.type) : "?";
}

/** Lane assignment per band. Two items always get separate lanes when their
 *  authored windows truly OVERLAP. Additionally, like-kind items that belong to
 *  the same overlap CLUSTER (a busy run of simultaneous content, e.g. a build-up
 *  list) are kept apart even where they only abut — so the list stacks instead
 *  of swapping in place. Merely-sequential, differently-kinded, or isolated
 *  items still share one full-size lane (so hand-authored scenes are unchanged).
 *  "full" (corner-anchored) items are never sub-slotted. */
function assignLanes(items: any[], sceneDur: number): void {
  const EPS = 0.02;
  const BRIDGE = 0.7; // ~ the TAIL fade, so like-kind neighbours don't ghost
  const SUCC_WIN = 0.6; // a same-slot successor within this window closes the gap
  // Interval + kind up front for EVERY item (full/corner items included, so
  // corner-anchored successions are detectable too).
  for (const it of items) {
    it.lane = 0;
    it.laneCount = 1;
    const [s, e] = compInterval(it.comp, sceneDur);
    it._s = s;
    it._e = e;
    it._kind = kindOf(it.comp);
    it._succ = null;   // successor start (sec) if another item takes this slot next
    it._pred = false;  // true if this item takes over a slot from a predecessor
  }
  const byBand: Record<string, any[]> = {};
  for (const it of items) {
    if (it.band === "full") continue;
    (byBand[it.band] = byBand[it.band] || []).push(it);
  }
  for (const band of Object.keys(byBand)) {
    const group = byBand[band];
    const sorted = [...group].sort((a, b) => a._s - b._s || a._e - b._e);
    // Cluster = maximal run of transitively strictly-overlapping windows.
    let cid = -1;
    let runEnd = -Infinity;
    for (const it of sorted) {
      if (it._s < runEnd - EPS) {
        runEnd = Math.max(runEnd, it._e);
      } else {
        cid++;
        runEnd = it._e;
      }
      it._cluster = cid;
    }
    // Greedy colouring.
    const lanes: { end: number; kind: string; cluster: number }[] = [];
    for (const it of sorted) {
      let placed = false;
      for (let l = 0; l < lanes.length; l++) {
        const ln = lanes[l];
        const strictOverlap = it._s < ln.end - EPS;
        const likeCluster = it._kind === ln.kind && it._cluster === ln.cluster && it._s < ln.end + BRIDGE;
        if (!strictOverlap && !likeCluster) {
          it.lane = l;
          ln.end = Math.max(ln.end, it._e);
          ln.kind = it._kind;
          ln.cluster = it._cluster;
          placed = true;
          break;
        }
      }
      if (!placed) {
        it.lane = lanes.length;
        lanes.push({ end: it._e, kind: it._kind, cluster: it._cluster });
      }
    }
    const count = lanes.length;
    for (const it of group) it.laneCount = count;
  }

  // --- Succession pass. Group items by their actual on-screen SLOT: band+lane
  // for laned bands, or band+position for corner-anchored "full" items (two
  // upper-left captions share a slot; an upper-left and a bottom-right do not).
  // Within a slot the items are sequential (overlapping ones were split into
  // separate lanes), so a component immediately followed by another in the SAME
  // slot is a REPLACEMENT: the predecessor must not linger with its dead-air
  // TAIL on top of the successor's LEAD. Mark the pair so the runtime cuts
  // cleanly. Items with a genuine gap (nothing follows within SUCC_WIN) keep the
  // dead-air bridge untouched. ---
  const slots: Record<string, any[]> = {};
  for (const it of items) {
    const key = it.band === "full"
      ? "full:" + String((it.comp && it.comp.position) || "center")
      : it.band + ":" + it.lane;
    (slots[key] = slots[key] || []).push(it);
  }
  for (const key of Object.keys(slots)) {
    const arr = slots[key].sort((a, b) => a._s - b._s || a._e - b._e);
    for (let i = 0; i < arr.length - 1; i++) {
      const cur = arr[i];
      const nxt = arr[i + 1];
      // nxt starts at/after cur ends (same slot ⇒ not a real time overlap) and
      // within the bridging window ⇒ nxt covers the slot, so trim cur's tail.
      if (nxt._s >= cur._e - EPS && nxt._s <= cur._e + SUCC_WIN) {
        cur._succ = nxt._s;
        nxt._pred = true;
      }
    }
  }

  // --- Corner stacking. Two "full" (corner-anchored) items pinned to the SAME
  // corner and visible AT THE SAME TIME (e.g. a label + an icon both upper-left)
  // would sit on top of each other — the lane system skips corner items. Give
  // time-overlapping same-corner items a stack index so the runtime can offset
  // them apart. Non-overlapping (sequential) corner items keep index 0. ---
  const corners: Record<string, any[]> = {};
  for (const it of items) {
    if (it.band !== "full") continue;
    const pos = String((it.comp && it.comp.position) || "center");
    (corners[pos] = corners[pos] || []).push(it);
  }
  for (const pos of Object.keys(corners)) {
    const arr = corners[pos].sort((a, b) => a._s - b._s || a._e - b._e);
    for (let i = 0; i < arr.length; i++) {
      const used = new Set<number>();
      for (let j = 0; j < i; j++) {
        if (arr[j]._s < arr[i]._e - EPS && arr[i]._s < arr[j]._e - EPS) used.add(arr[j]._cornerStack || 0);
      }
      let idx = 0;
      while (used.has(idx)) idx++;
      arr[i]._cornerStack = idx;
    }
  }
}

/** Region for one lane of a band. With a single lane this is byte-identical to
 *  the classic band region (so existing hand-authored scenes are unchanged);
 *  with N>1 lanes the band's vertical span is divided into N stacked rows. */
function bandLaneStyle(band: "top" | "center" | "bottom" | "full", lane: number, count: number): string {
  if (band === "full" || count <= 1) return bandRegionStyle(band);
  let regionTop: number;
  let regionH: number;
  if (band === "top") {
    regionH = Math.min(52, count * 16);
    regionTop = 0;
  } else if (band === "bottom") {
    regionH = Math.min(64, count * 18);
    regionTop = 100 - regionH - 4;
  } else {
    // center: use a touch more of the stage when split so rows stay legible.
    regionTop = 15;
    regionH = 70;
  }
  const laneH = regionH / count;
  const top = regionTop + lane * laneH;
  return `position:absolute;left:0;right:0;top:${top.toFixed(2)}%;height:${laneH.toFixed(2)}%;pointer-events:none`;
}

/**
 * Assigns a component to a vertical layout band:
 *  - "top":    eyebrows / labels / kickers
 *  - "center": the primary block (viz / card / trace-log / comparison /
 *              triptych / step-sequence / code / hero-or-display text)
 *  - "bottom": supporting body text
 *  - "full":   components with an explicit corner position keep the whole
 *              scene as their frame so their corner anchoring is preserved.
 */
function layoutBand(comp: any): "top" | "center" | "bottom" | "full" {
  const pos = comp.position;
  // Any explicit non-center placement (upper-left/right, bottom-*) stays put.
  if (typeof pos === "string" && pos !== "center") return "full";
  switch (comp.type) {
    case "label":
      return "top";
    case "byline":
      return "full";
    case "text":
      // All prose (hero/display headlines AND body copy) lives in the central
      // spotlight; time-aware lane assignment (see assignLanes) keeps a body
      // caption from colliding with a simultaneous headline, and lets a list of
      // body lines stack instead of being crushed into a thin bottom strip.
      return "center";
    default:
      return "center";
  }
}

/** Absolute region for each band. CENTER gets the dominant central space. */
function bandRegionStyle(band: "top" | "center" | "bottom" | "full"): string {
  switch (band) {
    case "top": return "position:absolute;left:0;right:0;top:0;height:17%;pointer-events:none";
    case "bottom": return "position:absolute;left:0;right:0;bottom:0;height:17%;pointer-events:none";
    case "center": return "position:absolute;left:0;right:0;top:17%;bottom:17%;pointer-events:none";
    case "full":
    default: return "position:absolute;inset:0;pointer-events:none";
  }
}

// Two-tier engineering / graph-paper grid. Minor lines use theme.colors.grid
// (which already carries the theme's intended low alpha), major lines every 4th
// cell use theme.colors.inkFaint (same hue, a touch stronger) so the ruling
// reads clearly without ever competing with content. Both are derived from
// theme tokens, so it works for dark themes too.
function renderGrid(theme: Theme, si: number): string {
  const minor = theme.colors.grid;
  const major = theme.colors.inkFaint;
  // Pattern ids MUST be unique per scene: every scene-layer carries its own
  // grid SVG, and duplicate ids make `url(#..)` resolve to the first match
  // (which lives in a display:none layer and paints inconsistently).
  const mId = `grid-minor-${si}`;
  const MId = `grid-major-${si}`;
  // The grid is over-sized by exactly one MAJOR cell (192px) on every side and
  // its viewBox grows to match (2304x1464 for a 1920x1080 stage), so minor and
  // major lines land in the SAME on-screen positions as an inset:0 grid while
  // leaving a hidden margin for the ambient drift (see applyAmbient) to slide
  // into. The over-size (192) matches the major period, so alignment is exact.
  return `<svg class="theme-grid" viewBox="0 0 2304 1464" preserveAspectRatio="none" style="position:absolute;left:-192px;top:-192px;width:calc(100% + 384px);height:calc(100% + 384px);inset:auto;pointer-events:none;will-change:transform">
    <defs>
      <pattern id="${mId}" width="48" height="48" patternUnits="userSpaceOnUse">
        <path d="M 48 0 L 0 0 0 48" fill="none" stroke="${minor}" stroke-width="1"/>
      </pattern>
      <pattern id="${MId}" width="192" height="192" patternUnits="userSpaceOnUse">
        <rect width="192" height="192" fill="url(#${mId})"/>
        <path d="M 192 0 L 0 0 0 192" fill="none" stroke="${major}" stroke-width="1.25"/>
      </pattern>
    </defs>
    <rect width="100%" height="100%" fill="url(#${MId})"/>
  </svg>`;
}

// Rough relative luminance (0..1) of a #rrggbb / #rgb colour. Used only to tell
// a dark theme (bg2 lighter than bg) from a light one so the stage vignette can
// darken in the correct direction. Non-hex inputs fall back to mid-grey.
function relLum(hex: string): number {
  const s = String(hex).trim().replace(/^#/, "");
  let r = 128, g = 128, b = 128;
  if (/^[0-9a-f]{6}$/i.test(s)) {
    r = parseInt(s.slice(0, 2), 16); g = parseInt(s.slice(2, 4), 16); b = parseInt(s.slice(4, 6), 16);
  } else if (/^[0-9a-f]{3}$/i.test(s)) {
    r = parseInt(s[0] + s[0], 16); g = parseInt(s[1] + s[1], 16); b = parseInt(s[2] + s[2], 16);
  }
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function renderComponent(comp: Component, theme: Theme, sceneStartSec: number): string {
  switch (comp.type) {
    case "text": return renderText(comp, theme);
    case "label": return renderLabel(comp, theme);
    case "icon": return renderIcon(comp, theme);
    case "code": return renderCode(comp, theme);
    case "byline": return renderByline(comp, theme);
    case "text-cycle": return renderTextCycle(comp, theme);
    case "triptych": return renderTriptych(comp, theme);
    case "step-sequence": return renderStepSequence(comp, theme);
    case "comparison": return renderComparison(comp, theme);
    case "card": return renderCard(comp, theme);
    case "trace-log": return renderTraceLog(comp, theme);
    case "viz": return renderViz(comp, theme);
    default: return "";
  }
}

// --- Colour resolution (named palette + theme tokens + raw values) ---
function resolveColor(theme: Theme, name: unknown): string {
  if (typeof name !== "string" || name === "") return theme.colors.ink;
  const named: Record<string, string> = {
    blue: "#3B82F6",
    green: theme.colors.green,
    red: theme.colors.red,
    amber: theme.colors.amber,
    purple: theme.colors.purple,
    ink: theme.colors.ink,
    gray: theme.colors.inkSoft,
    grey: theme.colors.inkSoft,
  };
  if (named[name]) return named[name];
  // Already a hex / rgb / css colour → use as-is.
  if (/^#|^rgb|^hsl/.test(name)) return name;
  return theme.colors.ink;
}

// --- Icons (inline SVG, Lucide) ---------------------------------------------
// Each usage inlines ONLY the icons it references — the full LUCIDE_ICONS map
// lives in a .ts module and never reaches the generated HTML; the renderer pulls
// a single icon's inner markup via getIcon() and wraps it in a themable <svg>.
// So a video's HTML contains exactly the icons it uses. Icons are stroke-based
// (stroke="currentColor") so a wrapper `color` themes them; scale via width/height.

/** Themed inline <svg> for a known icon, or null when the name is unknown.
 *  `stroke` sets the drawing colour (via `color` + currentColor). */
function iconSvg(name: unknown, sizePx: number, stroke: string, extraStyle = ""): string | null {
  const inner = getIcon(typeof name === "string" ? name : String(name ?? ""));
  if (inner === null) return null;
  // data-icon is a stable, grep-able marker of which icons a video inlined.
  const marker = String(name).trim().toLowerCase().replace(/[^a-z0-9-]/g, "-");
  return `<svg class="vdsl-icon" data-icon="${marker}" width="${sizePx}" height="${sizePx}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:${stroke};display:block;flex-shrink:0;${extraStyle}">${inner}</svg>`;
}

/** Graceful placeholder for an unknown icon name — a neutral dashed chip that
 *  shows the requested name, so a typo degrades cleanly instead of crashing. */
function iconFallback(name: unknown, sizePx: number, theme: Theme): string {
  const label = escapeHtml(String(name ?? "?"));
  const fontPx = Math.max(9, Math.round(sizePx * 0.14));
  return `<div class="vdsl-icon-fallback" style="width:${sizePx}px;height:${sizePx}px;display:flex;align-items:center;justify-content:center;border:2px dashed ${theme.colors.inkFaint};border-radius:14px;color:${theme.colors.inkSoft};font-family:${theme.fonts.mono};font-size:${fontPx}px;line-height:1.1;text-align:center;padding:6px;overflow:hidden;word-break:break-word">${label}</div>`;
}

// --- Icon (standalone component) ---
// `icon "<name>" <position> <timing> [color]`. Sized ~88px, centred in its band,
// themed via the optional trailing colour token (defaults to theme ink). It is a
// normal `.vdsl-el`, so it fades/scales in and respects the timing/reveal engine.
function renderIcon(comp: any, theme: Theme): string {
  const pos = posToStyle(comp.position || "center");
  const color = resolveColor(theme, comp.color); // undefined → theme.colors.ink
  const size = 88;
  const svg = iconSvg(comp.name, size, color);
  const inner = svg !== null ? svg : iconFallback(comp.name, size, theme);
  return `<div class="vdsl-el" data-el="icon" data-start="${comp.timing.start}" data-end="${comp.timing.end ?? ""}" data-reveal="scale-in" style="${pos}">${inner}</div>`;
}

function asArray(v: unknown): any[] {
  if (Array.isArray(v)) return v;
  if (v === undefined || v === null) return [];
  return [v];
}

/** A truthy check for yes/no/true/false-ish values. */
function isYes(v: unknown): boolean {
  if (v === true) return true;
  if (typeof v === "string") return /^(yes|true|y|si|sí|✓)$/i.test(v.trim());
  return false;
}

// --- Text ---
// Composition (theme-driven, generic): hero/display headlines get a strong type
// scale, tight tracking/leading, an italic serif for `display-italic`, and a
// short cobalt accent rule (2 grid cells wide) below the line so even a single
// centred headline reads as designed rather than a lonely floating line. A
// small optical lift seats it just above the geometric centre of its band.
function renderText(comp: any, theme: Theme): string {
  const reveal = comp.reveal || "fade";
  const isHero = comp.font === "hero";
  const isDisplay = comp.font === "display" || comp.font === "display-italic";
  const italic = comp.font === "display-italic";
  const font = (isHero || isDisplay) ? theme.fonts.display : theme.fonts.body;
  const fontSize = isHero ? 92 : isDisplay ? 60 : 34;
  const fontWeight = isHero ? 800 : isDisplay ? 600 : 450;
  const tracking = isHero ? "-0.03em" : isDisplay ? "-0.02em" : "0";
  const leading = (isHero || isDisplay) ? "1.06" : "1.4";
  const position = comp.position || "center";
  const isCenter = position === "center";
  const pos = posToStyle(position);
  const align = isCenter ? "center" : "left";
  const showAccent = isHero || isDisplay;
  const italicStyle = italic ? "font-style:italic;" : "";
  const textStyle = `font-family:${font};font-size:${fontSize}px;font-weight:${fontWeight};color:${theme.colors.ink};letter-spacing:${tracking};line-height:${leading};${italicStyle}text-align:${align}`;
  const ruleHtml = showAccent
    ? `<div class="accent-rule" style="width:96px;height:4px;border-radius:2px;background:${theme.colors.ink};margin-top:28px;opacity:0.92;${isCenter ? "margin-left:auto;margin-right:auto" : ""}"></div>`
    : "";
  const lift = showAccent ? "transform:translateY(-2%);" : "";
  const colOpen = `<div style="display:flex;flex-direction:column;align-items:${isCenter ? "center" : "flex-start"};max-width:88%;${lift}">`;

  if (reveal === "word-stagger") {
    const words = comp.content.split(" ").map((w: string) => `<span class="word" style="display:inline-block;opacity:0;transform:translateY(30px)">${escapeHtml(w)}</span>`).join(" ");
    return `<div class="vdsl-el" data-el="text" data-start="${comp.timing.start}" data-end="${comp.timing.end ?? ""}" data-reveal="word-stagger" style="${pos}">
      ${colOpen}<div style="${textStyle}">${words}</div>${ruleHtml}</div>
    </div>`;
  }

  if (reveal === "typewriter") {
    const chars = comp.content.length;
    return `<div class="vdsl-el" data-el="text" data-start="${comp.timing.start}" data-end="${comp.timing.end ?? ""}" data-reveal="typewriter" data-chars="${chars}" style="${pos};font-family:${font};font-size:${fontSize}px;font-weight:${fontWeight};color:${theme.colors.ink};letter-spacing:${tracking};overflow:hidden;white-space:pre-wrap;${italicStyle}">
      <span class="tw-text" data-fulltext="${escapeHtml(comp.content)}" style="display:inline"></span><span class="tw-cursor" style="opacity:0.8">█</span>
    </div>`;
  }

  return `<div class="vdsl-el" data-el="text" data-start="${comp.timing.start}" data-end="${comp.timing.end ?? ""}" data-reveal="fade" style="${pos}">
    ${colOpen}<div style="${textStyle}">${escapeHtml(comp.content)}</div>${ruleHtml}</div>
  </div>`;
}

// --- Label ---
function renderLabel(comp: any, theme: Theme): string {
  const pos = posToStyle(comp.position || "center");
  // The pill styling (bg/border/padding) MUST wrap only the text via an inner
  // span — applying it to the inset:0 flex container would tint the whole band.
  return `<div class="vdsl-el" data-el="label" data-start="${comp.timing.start}" data-end="${comp.timing.end ?? ""}" data-reveal="fade" style="${pos}"><span style="font-family:${theme.fonts.mono};font-size:13px;font-weight:700;color:${theme.colors.inkSoft};letter-spacing:0.12em;text-transform:uppercase;background:${theme.colors.ink}08;padding:5px 14px;border-radius:6px;border:1px solid ${theme.colors.grid}">${escapeHtml(comp.text)}</span></div>`;
}

// --- Code ---
function renderCode(comp: any, theme: Theme): string {
  const pos = posToStyle("center");
  // Box styling wraps the code in an inner element (not the inset:0 container),
  // so it reads as a compact code card floating over the grid.
  return `<div class="vdsl-el" data-el="code" data-start="${comp.timing.start}" data-end="${comp.timing.end ?? ""}" data-reveal="typewriter" style="${pos}"><div style="font-family:${theme.fonts.mono};font-size:28px;color:${theme.colors.ink};background:${theme.colors.bg2};padding:20px 28px;border-radius:12px;border:1px solid ${theme.colors.grid};box-shadow:0 16px 44px rgba(0,0,0,0.14);white-space:pre;"><span class="tw-text" data-fulltext="${escapeHtml(comp.content)}"></span><span class="tw-cursor" style="opacity:0.8">█</span></div></div>`;
}

// --- Byline ---
function renderByline(comp: any, theme: Theme): string {
  const pos = posToStyle(comp.position || "bottom-right");
  return `<div class="vdsl-el" data-el="byline" data-start="${comp.timing.start}" data-end="${comp.timing.end ?? ""}" data-reveal="fade" style="${pos};font-family:${theme.fonts.body};font-size:14px;color:${theme.colors.inkSoft}">${escapeHtml(comp.text)}</div>`;
}

// --- TextCycle ---
// Consecutive phrases CROSSFADE at runtime (see the textcycle branch in
// applyElementTiming) so there is never a blank seam. Composition is theme
// driven: a strong display type scale with tight tracking, and per-phrase
// accents — `hero` bumps the scale/weight, `glow` adds a soft cobalt halo,
// `dim` rides a lower base opacity, `underline`/`strike` decorate the line.
function renderTextCycle(comp: any, theme: Theme): string {
  const items = comp.phrases || comp.items || [];
  const html = items.map((item: any) => {
    const accent = item.accent || "";
    const isHeroAcc = accent === "hero";
    const fontSize = isHeroAcc ? 84 : 64;
    const weight = isHeroAcc ? 800 : 700;
    const baseOp = accent === "dim" ? "0.5" : "1";
    const glow = accent === "glow" ? `text-shadow:0 0 26px ${theme.colors.inkSoft}66;` : "";
    const decoStyle = (accent === "underline" || accent === "strike")
      ? `text-decoration:${accent === "underline" ? "underline" : "line-through"};text-decoration-thickness:3px;text-underline-offset:12px;text-decoration-color:${theme.colors.inkSoft};`
      : "";
    return `<div class="vdsl-el" data-el="textcycle" data-op="${baseOp}" data-start="${item.timing.start}" data-end="${item.timing.end ?? ""}" data-reveal="fade" style="position:absolute;inset:0;display:flex;justify-content:center;align-items:center;text-align:center;padding:0 8%;font-family:${theme.fonts.display};font-size:${fontSize}px;font-weight:${weight};letter-spacing:-0.02em;line-height:1.08;color:${theme.colors.ink};${decoStyle}${glow}opacity:0">${escapeHtml(item.text)}</div>`;
  }).join("\n");
  return html;
}

// --- Triptych ---
function renderTriptych(comp: any, theme: Theme): string {
  const itemsHtml = comp.items.map((item: any, i: number) => {
    // First token is the title; any remaining tokens read as a supporting
    // caption on their own line (single-token items just show the title).
    const tokens: string[] = Array.isArray(item.tokens) ? item.tokens : (item.tokens ? [String(item.tokens)] : []);
    const title = tokens[0] ?? "";
    const desc = tokens.slice(1).join(" ");
    const titleHtml = `<div style="font-family:${theme.fonts.display};font-size:24px;font-weight:700;color:${theme.colors.ink};line-height:1.15">${escapeHtml(title)}</div>`;
    const descHtml = desc
      ? `<div style="font-family:${theme.fonts.body};font-size:15px;font-weight:400;color:${theme.colors.inkSoft};margin-top:8px;line-height:1.35">${escapeHtml(desc)}</div>`
      : "";
    return `<div class="stg" data-stagger="${i}" style="flex:1;display:flex;flex-direction:column;justify-content:center;align-items:center;padding:24px;background:${theme.colors.ink}06;border-radius:12px;border:1px solid ${theme.colors.grid};text-align:center;min-height:120px">${titleHtml}${descHtml}</div>`;
  }).join("\n");

  return `<div class="vdsl-el" data-el="triptych" data-start="${comp.timing.start}" data-end="${comp.timing.end ?? ""}" data-reveal="${comp.reveal || "stagger"}" style="position:absolute;inset:0;display:flex;justify-content:center;align-items:center;gap:20px;padding:0 60px">${itemsHtml}</div>`;
}

// --- StepSequence ---
function renderStepSequence(comp: any, theme: Theme): string {
  const steps = comp.steps.map((step: any, i: number) => {
    // Badge shows a known icon (SVG) when the step names one, else the number.
    const badgeSvg = iconSvg(step.icon, 18, theme.colors.bg);
    const badgeInner = badgeSvg !== null ? badgeSvg : String(i + 1);
    return `<div class="stg" data-stagger="${i}" style="display:flex;align-items:center;gap:16px;width:65%;padding:12px 20px;border-radius:10px;background:${theme.colors.ink}04;border:1px solid ${theme.colors.grid}">
        <div style="width:32px;height:32px;border-radius:16px;background:${theme.colors.ink};color:${theme.colors.bg};display:flex;justify-content:center;align-items:center;font-family:${theme.fonts.mono};font-size:13px;font-weight:700;flex-shrink:0">${badgeInner}</div>
        <div><div style="font-family:${theme.fonts.display};font-size:17px;font-weight:600;color:${theme.colors.ink}">${escapeHtml(step.label)}</div>${step.description ? `<div style="font-family:${theme.fonts.body};font-size:13px;color:${theme.colors.inkSoft}">${escapeHtml(step.description)}</div>` : ""}</div>
      </div>`;
  }).join("\n");
  return `<div class="vdsl-el" data-el="step-sequence" data-start="${comp.timing.start}" data-end="${comp.timing.end ?? ""}" data-reveal="${comp.reveal || "stagger"}" style="position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:12px;padding:60px 80px">${steps}</div>`;
}

// --- Comparison ---
function renderComparison(comp: any, theme: Theme): string {
  const left = comp.sides?.find((s: any) => s.side === "left") || comp.left;
  const right = comp.sides?.find((s: any) => s.side === "right") || comp.right;
  if (!left || !right) return "";

  const card = (side: any, _color: string, i: number) => `
    <div class="stg" data-stagger="${i}" style="flex:1;padding:24px;border-radius:14px;background:${theme.colors.bg2};border:1px solid ${theme.colors.grid}">
      ${side.badge ? `<div style="display:inline-block;padding:3px 10px;border-radius:12px;background:${side.badge.color}22;border:1px solid ${side.badge.color}66;margin-bottom:8px"><span style="font-family:${theme.fonts.mono};font-size:10px;font-weight:700;color:${side.badge.color}">${escapeHtml(side.badge.text)}</span></div>` : ""}
      <div style="font-family:${theme.fonts.display};font-size:22px;font-weight:700;color:${theme.colors.ink};margin-bottom:4px">${escapeHtml(side.title)}</div>
      <div style="font-family:${theme.fonts.body};font-size:13px;color:${theme.colors.inkSoft}">${escapeHtml(side.subtitle)}</div>
    </div>`;

  return `<div class="vdsl-el" data-el="comparison" data-start="${comp.timing.start}" data-end="${comp.timing.end ?? ""}" data-reveal="stagger" style="position:absolute;inset:0;display:flex;justify-content:center;align-items:center;gap:20px;padding:0 80px">
    ${card(left, "purple", 0)}
    ${card(right, "green", 1)}
  </div>`;
}

// --- Card ---
function renderCard(comp: any, theme: Theme): string {
  const children = comp.children || [];
  // Each inner line is a .stg child so a multi-part card assembles line-by-line
  // (formula → arrow → result …) instead of popping in whole (Round 15).
  const inner = children.map((ch: any, i: number) => {
    const tag = `class="stg" data-stagger="${i}"`;
    if (ch.type === "formula") {
      return `<div ${tag} style="font-family:${theme.fonts.mono};font-size:34px;font-weight:600;color:${theme.colors.ink}">${escapeHtml(ch.content)}</div>`;
    }
    if (ch.type === "arrow") {
      return `<div ${tag} style="font-size:30px;color:${theme.colors.inkSoft};line-height:1">↓</div>`;
    }
    if (ch.type === "icon") {
      const svg = iconSvg(ch.name, 60, theme.colors.ink);
      const glyph = svg !== null ? svg : iconFallback(ch.name, 60, theme);
      return `<div ${tag} style="display:flex;justify-content:center;align-items:center">${glyph}</div>`;
    }
    if (ch.type === "result") {
      return `<div ${tag} style="font-family:${theme.fonts.display};font-size:40px;font-weight:800;color:${theme.colors.ink}">${escapeHtml(ch.content)}</div>`;
    }
    return `<div ${tag} style="font-family:${theme.fonts.body};font-size:16px;color:${theme.colors.inkSoft}">${escapeHtml(ch.content)}</div>`;
  }).join("\n");

  return `<div class="vdsl-el" data-el="card" data-start="${comp.timing.start}" data-end="${comp.timing.end ?? ""}" data-reveal="${comp.reveal || "scale-in"}" style="position:absolute;inset:0;display:flex;justify-content:center;align-items:center">
    <div style="display:flex;flex-direction:column;justify-content:center;align-items:center;gap:16px;padding:40px 56px;border-radius:20px;background:${theme.colors.bg2};border:1px solid ${theme.colors.grid};box-shadow:0 20px 60px rgba(0,0,0,0.18)">
      ${inner}
    </div>
  </div>`;
}

// --- TraceLog (standalone component) ---
function renderTraceLog(comp: any, theme: Theme): string {
  const columns: string[] = Array.isArray(comp.columns) ? comp.columns : [];
  const entries = comp.entries || [];
  return traceLogHtml(theme, comp.timing, comp.reveal || "fade", columns, entries, comp.badge);
}

// --- Viz dispatcher: NEVER returns empty (always at least a titled panel) ---
function renderViz(comp: any, theme: Theme): string {
  const p = comp.props || {};
  const timing = comp.timing;
  const reveal = comp.reveal || "fade";
  let body = "";
  switch (comp.vizType) {
    case "flow-diagram":     body = vizFlowDiagram(p, theme); break;
    case "node-graph":       body = vizNodeGraph(p, theme); break;
    case "boundary-sim":     body = vizBoundarySim(p, theme); break;
    case "workspace":        body = vizWorkspace(p, theme); break;
    case "protocol-compare": body = vizProtocolCompare(p, theme); break;
    case "trace-log":        return traceLogHtml(theme, timing, reveal, splitColumns(p.columns), asArray(p.entries), typeof p.badge === "string" ? p.badge : undefined);
    case "chart":            body = vizChart(p, theme, timing); break;
    case "custom":           body = vizCustom(p, theme); break;
    default:                 body = vizFallback(comp.vizType, p, theme); break;
  }
  return `<div class="vdsl-el" data-el="viz" data-start="${timing.start}" data-end="${timing.end ?? ""}" data-reveal="${reveal}" style="position:absolute;inset:0;display:flex;justify-content:center;align-items:center;padding:80px 120px">
    <div style="width:100%;max-width:1400px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:24px">${body}</div>
  </div>`;
}

function splitColumns(v: unknown): string[] {
  if (Array.isArray(v)) return v.map(String);
  if (typeof v === "string") return v.split(/\s+/).filter(Boolean);
  return [];
}

// --- viz: flow-diagram (row of numbered cards + arrows) ---
function vizFlowDiagram(p: any, theme: Theme): string {
  const steps = asArray(p.steps);
  const useArrow = (p.connectors ?? "arrow") !== "none";
  const cards = steps.map((s: any, i: number) => {
    const color = resolveColor(theme, s.color);
    const arrow = (useArrow && i < steps.length - 1)
      ? `<div class="stg" data-stagger="${i}" style="color:${theme.colors.inkSoft};font-size:34px;opacity:0.55;padding:0 4px">→</div>`
      : "";
    // Badge: an ICON (SVG, white stroke) when `icon:` names a known icon,
    // otherwise the authored value / step number (so `icon: 1` stays a numeral).
    const badgeSvg = iconSvg(s.icon, 22, "#fff");
    const badgeInner = badgeSvg !== null ? badgeSvg : escapeHtml(String(s.icon ?? i + 1));
    return `<div class="stg" data-stagger="${i}" style="flex:1;min-width:0;padding:24px 20px;border-radius:16px;background:${theme.colors.bg2};border:1px solid ${color}55;box-shadow:0 10px 30px rgba(0,0,0,0.12);position:relative">
        <div style="width:40px;height:40px;border-radius:20px;background:${color};color:#fff;display:flex;justify-content:center;align-items:center;font-family:${theme.fonts.mono};font-size:16px;font-weight:700;margin-bottom:14px">${badgeInner}</div>
        <div style="font-family:${theme.fonts.display};font-size:22px;font-weight:700;color:${theme.colors.ink};margin-bottom:6px">${escapeHtml(s.label ?? "")}</div>
        ${s.desc ? `<div style="font-family:${theme.fonts.body};font-size:14px;line-height:1.4;color:${theme.colors.inkSoft}">${escapeHtml(s.desc)}</div>` : ""}
        <div style="position:absolute;left:20px;right:20px;bottom:12px;height:3px;border-radius:2px;background:${color};opacity:0.5"></div>
      </div>${arrow}`;
  }).join("");
  return `<div style="display:flex;align-items:stretch;justify-content:center;gap:12px;width:100%">${cards}</div>`;
}

// Accepts nodes as an array of objects OR a compact "A,B,C" string. Each bare
// id becomes {id,label}; ids without coordinates are auto-placed on a row.
function normalizeNodes(raw: unknown): any[] {
  let arr = asArray(raw);
  if (arr.length === 1 && typeof arr[0] === "string" && arr[0].indexOf(",") >= 0) {
    arr = arr[0].split(",").map((s) => s.trim()).filter(Boolean);
  }
  return arr.map((n: any) => (typeof n === "string" ? { id: n, label: n } : n));
}

// Accepts edges as an array of objects OR a compact "A-B,B-C" string. Each
// "A-B" / "A->B" / "A→B" token becomes {from,to}.
function normalizeEdges(raw: unknown): any[] {
  let arr = asArray(raw);
  if (arr.length === 1 && typeof arr[0] === "string" && arr[0].indexOf(",") >= 0) {
    arr = arr[0].split(",").map((s) => s.trim()).filter(Boolean);
  }
  return arr.map((e: any) => {
    if (typeof e === "string") {
      const m = e.split(/->|→|-/).map((s) => s.trim());
      return { from: m[0], to: m[1] };
    }
    return e;
  });
}

// --- viz: node-graph (SVG; x/y are 0..100 percentages) ---
function vizNodeGraph(p: any, theme: Theme): string {
  const W = 1200, H = 620;
  const nodes = normalizeNodes(p.nodes);
  const edges = normalizeEdges(p.edges);
  // Precompute positions: honour explicit x/y, otherwise spread nodes evenly
  // across a centred row so shorthand graphs never collapse onto one point.
  const N = nodes.length;
  const posMap: Record<string, { x: number; y: number }> = {};
  nodes.forEach((n: any, i: number) => {
    const autoX = N <= 1 ? 50 : 12 + (76 * i) / (N - 1);
    const hasX = n.x !== undefined && n.x !== null && n.x !== "";
    const hasY = n.y !== undefined && n.y !== null && n.y !== "";
    const x = (hasX ? Number(n.x) : autoX) / 100 * W;
    const y = (hasY ? Number(n.y) : 50) / 100 * H;
    posMap[String(n.id)] = { x, y };
  });
  const posOf = (id: string) => posMap[String(id)] || null;
  const sizeMap: Record<string, number> = { sm: 34, md: 46, lg: 58, xl: 74 };

  // --- Reading-order assembly (Round 15) ---------------------------------
  // Interleave nodes and edges into ONE entrance sequence so the graph reads
  // node → edge → node, drawing each edge only AFTER both its endpoints have
  // appeared. Nodes enter in array order; an edge is slotted in right after the
  // LATER of its two endpoints. The resulting `data-seq` per element is what the
  // runtime spreads across the window (edges included — never dumped at once).
  const idxOf: Record<string, number> = {};
  nodes.forEach((n: any, i: number) => { idxOf[String(n.id)] = i; });
  const edgesByReady: Record<number, number[]> = {};
  edges.forEach((e: any, i: number) => {
    const fi = idxOf[String(e.from)], ti = idxOf[String(e.to)];
    const ready = (fi === undefined || ti === undefined) ? (nodes.length - 1) : Math.max(fi, ti);
    (edgesByReady[ready] = edgesByReady[ready] || []).push(i);
  });
  const nodeSeq: number[] = new Array(nodes.length);
  const edgeSeq: number[] = new Array(edges.length);
  let seq = 0;
  for (let i = 0; i < nodes.length; i++) {
    nodeSeq[i] = seq++;
    (edgesByReady[i] || []).forEach((ei) => { edgeSeq[ei] = seq++; });
  }
  edges.forEach((_e: any, i: number) => { if (edgeSeq[i] === undefined) edgeSeq[i] = seq++; });

  const edgeSvg = edges.map((e: any, i: number) => {
    const a = posOf(e.from), b = posOf(e.to);
    if (!a || !b) return "";
    const midX = (a.x + b.x) / 2, midY = (a.y + b.y) / 2 - 40;
    const dash = e.style === "dashed" ? `stroke-dasharray="10 8"` : e.style === "dotted" ? `stroke-dasharray="2 7"` : "";
    const col = resolveColor(theme, e.color ?? "gray");
    // Draw-on runs stroke-dashoffset full->0 using the real path length
    // (measured at runtime); the handler clears the override once fully drawn so
    // the resting `stroke-dasharray` (dashed/dotted) reappears untouched.
    return `<path class="stg edge-draw" data-stagger="${i}" data-seq="${edgeSeq[i]}" d="M ${a.x} ${a.y} Q ${midX} ${midY} ${b.x} ${b.y}" fill="none" stroke="${col}" stroke-width="2.5" ${dash} opacity="0.6" stroke-linecap="round"/>`;
  }).join("\n");
  const nodeSvg = nodes.map((n: any, i: number) => {
    const pos = posOf(n.id);
    if (!pos) return "";
    const r = sizeMap[String(n.size)] ?? 48;
    const col = resolveColor(theme, n.color);
    // Outer <g> holds the position; middle <g> is the pop-in target (fill-box +
    // centre origin so scale-in grows from the node's own centre); the inner
    // .node-bob <g> carries the ambient bob (a separate wrapper so the bob
    // translate composes with the pop-in scale instead of clobbering it).
    return `<g transform="translate(${pos.x},${pos.y})"><g class="stg" data-stagger="${i}" data-seq="${nodeSeq[i]}" style="transform-box:fill-box;transform-origin:center"><g class="node-bob" data-i="${i}">
        <circle r="${r * 1.35}" fill="${col}" opacity="0.12"/>
        <circle r="${r}" fill="${col}" stroke="${col}" stroke-width="2" opacity="0.92"/>
        <text text-anchor="middle" dominant-baseline="central" fill="#fff" font-family="${theme.fonts.body}" font-weight="700" font-size="${Math.max(15, r * 0.42)}">${escapeHtml(n.label ?? "")}</text>
      </g></g></g>`;
  }).join("\n");
  const annotation = p.annotation
    ? `<text x="${W / 2}" y="${H - 8}" text-anchor="middle" fill="${theme.colors.inkFaint}" font-family="${theme.fonts.body}" font-size="18">${escapeHtml(String(p.annotation))}</text>`
    : "";
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;max-height:70vh;overflow:visible">${edgeSvg}\n${nodeSvg}\n${annotation}</svg>`;
}

// --- viz: boundary-sim (packet → gate → recipient, one row per case) ---
function vizBoundarySim(p: any, theme: Theme): string {
  const cases = p.cases ? asArray(p.cases) : [{ packet: p.packet, label: p.label, recipient: p.recipient, access: p.access, result: p.result, gate: p.gate }];
  const rows = cases.map((c: any, i: number) => {
    const pass = String(c.result).toLowerCase() === "pass";
    const col = pass ? theme.colors.green : theme.colors.red;
    const gateSym = c.gate ?? "∈";
    const access = Array.isArray(c.access) ? c.access.join(", ") : String(c.access ?? "").replace(/^\[|\]$/g, "");
    return `<div class="stg" data-stagger="${i}" style="display:flex;align-items:center;justify-content:center;gap:22px;padding:18px 24px;border-radius:16px;background:${theme.colors.bg2};border:1px solid ${theme.colors.grid}">
        <div style="padding:12px 22px;border-radius:24px;background:${theme.colors.bg};border:1.5px solid ${theme.colors.inkSoft}66;font-family:${theme.fonts.mono};font-size:18px;font-weight:600;color:${theme.colors.ink}">${escapeHtml(c.packet ?? "")}</div>
        <div style="color:${theme.colors.inkSoft};font-size:26px">→</div>
        <div style="display:flex;flex-direction:column;align-items:center;gap:4px">
          <div style="width:52px;height:52px;border-radius:26px;background:${col};color:#fff;display:flex;justify-content:center;align-items:center;font-size:24px;font-weight:700">${pass ? "✓" : "✕"}</div>
          <div style="font-family:${theme.fonts.mono};font-size:12px;color:${theme.colors.inkSoft}">GATE ${escapeHtml(String(gateSym))}</div>
        </div>
        <div style="color:${theme.colors.inkSoft};font-size:26px">→</div>
        <div style="display:flex;flex-direction:column;align-items:center;gap:2px;padding:12px 20px;border-radius:14px;border:2px solid ${col}88;background:${col}14;min-width:120px">
          <div style="font-family:${theme.fonts.body};font-size:17px;font-weight:600;color:${theme.colors.ink}">${escapeHtml(c.recipient ?? "")}</div>
          ${access ? `<div style="font-family:${theme.fonts.mono};font-size:12px;color:${theme.colors.inkSoft}">${escapeHtml(access)}</div>` : ""}
        </div>
        <div style="padding:6px 16px;border-radius:14px;background:${col};color:#fff;font-family:${theme.fonts.mono};font-size:13px;font-weight:700;letter-spacing:0.08em">${pass ? "PASS" : "BLOCK"}</div>
      </div>`;
  }).join("\n");
  return `<div style="display:flex;flex-direction:column;gap:16px;width:100%;align-items:center">${rows}</div>`;
}

// --- viz: workspace (shared zone above two private zones) ---
function vizWorkspace(p: any, theme: Theme): string {
  const zones = asArray(p.zones);
  const zoneHtml = zones.map((z: any) => {
    const isLeft = String(z.side) === "left";
    const col = isLeft ? theme.colors.purple : theme.colors.green;
    return `<div style="flex:1;padding:28px;border-radius:18px;background:${col}12;border:2px dashed ${col}77">
        <div style="font-family:${theme.fonts.mono};font-size:13px;font-weight:700;letter-spacing:0.1em;color:${col};margin-bottom:10px">${escapeHtml(z.label ?? "")}</div>
        ${z.tag ? `<div style="font-family:${theme.fonts.body};font-size:15px;color:${theme.colors.inkSoft}">${escapeHtml(z.tag)}</div>` : ""}
      </div>`;
  }).join("\n");
  return `<div style="display:flex;flex-direction:column;gap:20px;width:100%">
    <div style="padding:26px;border-radius:18px;background:${theme.colors.ink}0d;border:1px solid ${theme.colors.grid};text-align:center;font-family:${theme.fonts.display};font-size:22px;font-weight:700;color:${theme.colors.ink}">${escapeHtml(String(p.shared ?? "SHARED"))}</div>
    <div style="display:flex;gap:20px">${zoneHtml}</div>
  </div>`;
}

// --- viz: protocol-compare (table with auth/data badges) ---
function vizProtocolCompare(p: any, theme: Theme): string {
  const protocols = asArray(p.protocols);
  const badge = (ok: boolean) => `<span style="display:inline-block;min-width:64px;padding:5px 12px;border-radius:10px;font-family:${theme.fonts.mono};font-size:13px;font-weight:700;color:#fff;background:${ok ? theme.colors.green : theme.colors.red}">${ok ? "✓ YES" : "✕ NO"}</span>`;
  const rows = protocols.map((pr: any, i: number) => `<div class="stg" data-stagger="${i + 1}" style="display:grid;grid-template-columns:1.4fr 1fr 1fr;align-items:center;gap:16px;padding:16px 22px;border-radius:14px;background:${theme.colors.bg2};border:1px solid ${theme.colors.grid}">
      <div style="font-family:${theme.fonts.display};font-size:22px;font-weight:700;color:${theme.colors.ink}">${escapeHtml(pr.name ?? "")}</div>
      <div style="text-align:center">${badge(isYes(pr.auth))}</div>
      <div style="text-align:center">${badge(isYes(pr.data))}</div>
    </div>`).join("\n");
  const header = `<div class="stg" data-stagger="0" style="display:grid;grid-template-columns:1.4fr 1fr 1fr;gap:16px;padding:0 22px;font-family:${theme.fonts.mono};font-size:12px;font-weight:700;letter-spacing:0.1em;color:${theme.colors.inkSoft}">
      <div>PROTOCOL</div><div style="text-align:center">AUTH</div><div style="text-align:center">DATA</div>
    </div>`;
  return `<div style="display:flex;flex-direction:column;gap:12px;width:100%;max-width:820px">${header}${rows}</div>`;
}

// --- viz: chart (bar / line / counter) --------------------------------------
// The most valuable RemoCN port: themed, frame-driven DATA CHARTS that build
// progressively via the SAME `.stg` machinery as every other viz.
//   kind: bar     (default) vertical bars, each grows up from the baseline
//                 (reveal "grow-up" scales height as f(frame)), staggered.
//   kind: line    a polyline that DRAWS ON left→right (edge-draw dashoffset),
//                 with dots + value labels appearing point-by-point.
//   kind: counter a big number that COUNTS UP 0→value over its window
//                 (.countup, driven by the count-up pass), with a label and
//                 optional prefix/suffix.
// Data comes from `data: [{label, value, color?}]` — the multi-line list form
// yields numeric values directly; a compact inline string is parsed leniently.
// Never blank: empty/short data degrades to a graceful placeholder chip.
function vizChart(p: any, theme: Theme, timing: any): string {
  const kind = String(p.kind ?? "bar").toLowerCase();
  if (kind === "counter") return chartCounter(p, theme, timing);
  if (kind === "line") return chartLine(p, theme);
  return chartBar(p, theme);
}

/** Coerce `data:` into a clean [{label, value, color?}] list. Accepts the
 *  structured multi-line list (already objects with numeric values), a compact
 *  inline string like `[{label:"A", value:30}]`, or bare "Label: 30" tokens. */
function normalizeChartData(raw: unknown): { label: string; value: number; color?: unknown }[] {
  let arr = asArray(raw);
  if (arr.length === 1 && typeof arr[0] === "string" && /[\[{]/.test(arr[0] as string)) {
    arr = parseInlineObjectString(arr[0] as string);
  }
  return arr.map((d: any) => {
    if (typeof d === "string") {
      const m = /^(.*?)[\s:=]+(-?\d[\d.]*)$/.exec(d.trim());
      if (m) return { label: m[1].trim().replace(/^["']|["']$/g, ""), value: Number(m[2]) };
      return { label: d, value: 0 };
    }
    return { label: d.label != null ? String(d.label) : "", value: Number(d.value) || 0, color: d.color };
  });
}

/** Lenient parse of a compact `[{k: v, ...}, ...]` string (the inline `data:`
 *  form the structured parser keeps as raw text). Regex-only, no eval. */
function parseInlineObjectString(s: string): any[] {
  const groups = s.match(/\{[^}]*\}/g);
  if (groups) {
    return groups.map((g) => {
      const o: Record<string, unknown> = {};
      const re = /([a-zA-Z_][\w-]*)\s*:\s*(?:"([^"]*)"|'([^']*)'|([^,}\s]+))/g;
      let m: RegExpExecArray | null;
      while ((m = re.exec(g))) o[m[1]] = m[2] ?? m[3] ?? m[4];
      return o;
    });
  }
  return s.replace(/^\[|\]$/g, "").split(",").map((x) => x.trim()).filter(Boolean);
}

/** Format a chart number (drop noise decimals) with optional prefix/suffix. */
function fmtNum(v: number, prefix = "", suffix = ""): string {
  const s = Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
  return prefix + s + suffix;
}

function chartPlaceholder(theme: Theme, kind: string): string {
  return `<div style="padding:28px 40px;border-radius:14px;background:${theme.colors.bg2};border:1px dashed ${theme.colors.inkFaint};font-family:${theme.fonts.mono};font-size:15px;color:${theme.colors.inkSoft}">${escapeHtml(kind)}: no data</div>`;
}

// Vertical bars. Each column is flex-end so its bar sits on the baseline; the
// bar is a `.stg` with reveal "grow-up" (transform-origin:bottom) so it rises
// from the axis as a pure function of frame. Value label + bar share a stagger
// slot; category labels below are static (always legible). Auto-scaled to max.
function chartBar(p: any, theme: Theme): string {
  const data = normalizeChartData(p.data);
  if (!data.length) return chartPlaceholder(theme, "bar chart");
  const prefix = p.prefix != null ? String(p.prefix) : "";
  const suffix = p.suffix != null ? String(p.suffix) : "";
  const maxVal = Math.max(1, ...data.map((d) => d.value));
  const PLOT = 340, BARMAX = 300;
  const gap = data.length > 8 ? 10 : 20;
  const cols = data.map((d, i) => {
    const col = resolveColor(theme, d.color);
    const hPx = Math.max(3, (d.value / maxVal) * BARMAX);
    const valLabel = `<div class="stg" data-stagger="${i}" data-reveal="fade" style="font-family:${theme.fonts.mono};font-size:20px;font-weight:700;color:${theme.colors.ink};margin-bottom:8px;opacity:0;white-space:nowrap">${escapeHtml(fmtNum(d.value, prefix, suffix))}</div>`;
    const bar = `<div class="stg" data-stagger="${i}" data-reveal="grow-up" style="width:100%;max-width:100px;height:${hPx.toFixed(1)}px;background:linear-gradient(180deg,${col},${col}cc);border-radius:9px 9px 0 0;transform-origin:bottom center;opacity:0;box-shadow:0 6px 20px ${col}33"></div>`;
    return `<div style="flex:1;min-width:0;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%">${valLabel}${bar}</div>`;
  }).join("");
  const cats = data.map((d) => `<div style="flex:1;min-width:0;text-align:center;font-family:${theme.fonts.body};font-size:16px;font-weight:600;color:${theme.colors.inkSoft};padding:0 4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(d.label)}</div>`).join("");
  return `<div style="width:100%;max-width:1000px;display:flex;flex-direction:column">
    <div style="display:flex;align-items:flex-end;justify-content:center;gap:${gap}px;height:${PLOT}px;border-bottom:2px solid ${theme.colors.inkSoft}55;padding:0 12px">${cols}</div>
    <div style="display:flex;justify-content:center;gap:${gap}px;padding:12px 12px 0">${cats}</div>
  </div>`;
}

// Line chart (SVG). The path DRAWS ON left→right by reusing the `.stg edge-draw`
// machinery (stroke-dashoffset by frame); dots + value labels ride later stagger
// slots so points land one-by-one along the drawn line. Light gridlines + a
// baseline axis; category labels under the axis. Auto-scaled to max.
function chartLine(p: any, theme: Theme): string {
  const data = normalizeChartData(p.data);
  if (data.length < 2) return chartPlaceholder(theme, "line chart");
  const prefix = p.prefix != null ? String(p.prefix) : "";
  const suffix = p.suffix != null ? String(p.suffix) : "";
  const W = 1200, H = 560, padL = 64, padR = 48, padT = 64, padB = 64;
  const maxVal = Math.max(1, ...data.map((d) => d.value));
  const plotW = W - padL - padR, plotH = H - padT - padB, baseY = H - padB;
  const N = data.length;
  const accent = resolveColor(theme, p.color);
  const xOf = (i: number) => (N === 1 ? padL + plotW / 2 : padL + (plotW * i) / (N - 1));
  const yOf = (v: number) => baseY - (v / maxVal) * plotH;
  let grid = "";
  for (let g = 0; g <= 4; g++) {
    const gy = baseY - (g / 4) * plotH;
    grid += `<line x1="${padL}" y1="${gy.toFixed(1)}" x2="${W - padR}" y2="${gy.toFixed(1)}" stroke="${theme.colors.inkSoft}" stroke-width="1" opacity="0.14"/>`;
  }
  grid += `<line x1="${padL}" y1="${baseY}" x2="${W - padR}" y2="${baseY}" stroke="${theme.colors.inkSoft}" stroke-width="2" opacity="0.5"/>`;
  const pts = data.map((d, i) => ({ x: xOf(i), y: yOf(d.value) }));
  const dPath = pts.map((pt, i) => `${i === 0 ? "M" : "L"} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`).join(" ");
  const line = `<path class="stg edge-draw" data-seq="0" data-stagger="0" d="${dPath}" fill="none" stroke="${accent}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>`;
  const dots = pts.map((pt, i) => {
    const dot = `<circle class="stg" data-seq="${i + 1}" data-stagger="${i + 1}" data-reveal="scale-in" cx="${pt.x.toFixed(1)}" cy="${pt.y.toFixed(1)}" r="7.5" fill="${accent}" stroke="${theme.colors.bg}" stroke-width="3" style="opacity:0;transform-box:fill-box;transform-origin:center"/>`;
    const val = `<text class="stg" data-seq="${i + 1}" data-stagger="${i + 1}" data-reveal="fade" x="${pt.x.toFixed(1)}" y="${(pt.y - 18).toFixed(1)}" text-anchor="middle" fill="${theme.colors.ink}" font-family="${theme.fonts.mono}" font-size="19" font-weight="700" style="opacity:0">${escapeHtml(fmtNum(data[i].value, prefix, suffix))}</text>`;
    return dot + val;
  }).join("");
  const cats = data.map((d, i) => `<text x="${xOf(i).toFixed(1)}" y="${(baseY + 34).toFixed(1)}" text-anchor="middle" fill="${theme.colors.inkSoft}" font-family="${theme.fonts.body}" font-size="18" font-weight="600">${escapeHtml(d.label)}</text>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;max-height:70vh;overflow:visible">${grid}${line}${dots}${cats}</svg>`;
}

// Big count-up number. The `.countup` div carries its target/window/format as
// data-* and is driven by the count-up pass in applyElementTiming (pure f(frame)
// ⇒ seek-safe). The wrapping viz element still owns the fade/scale entrance.
function chartCounter(p: any, theme: Theme, timing: any): string {
  const value = Number(p.value);
  if (isNaN(value)) return chartPlaceholder(theme, "counter");
  const startSec = timing && typeof timing.start === "number" ? timing.start : 0;
  const endSec = timing && timing.end != null ? Number(timing.end) : startSec + 3;
  const winF = Math.max(1, Math.round((endSec - startSec) * 30));
  const durF = Math.max(12, Math.round(winF * 0.7));
  const decimals = Number(p.decimals) || 0;
  const prefix = p.prefix != null ? String(p.prefix) : "";
  const suffix = p.suffix != null ? String(p.suffix) : "";
  const label = p.label != null ? String(p.label) : "";
  const init = prefix + (0).toFixed(decimals) + suffix;
  const num = `<div class="countup" data-start="${startSec}" data-dur="${durF}" data-to="${value}" data-decimals="${decimals}" data-prefix="${escapeHtml(prefix)}" data-suffix="${escapeHtml(suffix)}" style="font-family:${theme.fonts.display};font-size:150px;font-weight:800;line-height:1;letter-spacing:-0.03em;color:${theme.colors.ink}">${escapeHtml(init)}</div>`;
  const lab = label ? `<div style="font-family:${theme.fonts.body};font-size:26px;font-weight:600;color:${theme.colors.inkSoft};margin-top:16px;text-align:center">${escapeHtml(label)}</div>` : "";
  return `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center">${num}${lab}</div>`;
}

// --- viz: custom (Level-3 escape hatch) --------------------------------------
// Renders the author's RAW inline SVG (captured by the parser as props.svg /
// props.content) inside the themed viz container, scaled to fit and centred.
// It's inlined author markup at the SAME trust level as the built-in viz SVG —
// no external fetch is introduced. Reveal:
//  - Elements carrying data-animate="<reveal>" (optional data-delay="<sec>")
//    are tagged into the existing frame-driven `.stg` machinery so they ease in
//    on a stagger while the rest of the drawing is present immediately.
//  - If NO element opts in, the container-level reveal fades/scales the whole
//    SVG in (the else-branch in applyElementTiming) — never a static blank.
// Everything stays a pure function of the frame, so scrubbing is correct.
function vizCustom(p: any, theme: Theme): string {
  let svg = typeof p.svg === "string" ? p.svg : (typeof p.content === "string" ? p.content : "");
  svg = String(svg).trim();
  if (!svg) {
    return `<div style="padding:28px 36px;border-radius:14px;background:${theme.colors.bg2};border:1px solid ${theme.colors.grid};font-family:${theme.fonts.mono};font-size:14px;color:${theme.colors.inkSoft}">custom viz: no SVG content</div>`;
  }
  // Make the root <svg> responsive: scale to fit width, cap height, centre.
  svg = injectRootSvgStyle(svg, "display:block;width:100%;height:auto;max-width:1200px;max-height:74vh");
  // Opt-in per-element reveals via data-animate (+ optional data-delay).
  svg = tagAnimatedSvgElements(svg);
  return `<div style="width:100%;display:flex;align-items:center;justify-content:center">${svg}</div>`;
}

/** Merge extra CSS into the FIRST <svg …> tag's style attribute (or add one).
 *  Author styles win where they overlap (they are emitted first). */
function injectRootSvgStyle(svg: string, extra: string): string {
  return svg.replace(/<svg\b([^>]*)>/i, (full, attrs) => {
    if (/\bstyle\s*=\s*"/.test(attrs)) {
      return `<svg${attrs.replace(/\bstyle\s*=\s*"([^"]*)"/i, (_m: string, s: string) => `style="${s};${extra}"`)}>`;
    }
    return `<svg${attrs} style="${extra}">`;
  });
}

/** Wire elements with data-animate into the `.stg` reveal machinery: give each
 *  one `class="stg"`, a `data-stagger` index (or one derived from data-delay),
 *  a `data-reveal` copied from data-animate, and a fill-box transform origin so
 *  scale/slide reveals pivot about the element's own centre. Class/style are
 *  MERGED so author attributes are preserved. */
function tagAnimatedSvgElements(svg: string): string {
  const STAG = 13; // nominal frames/slot: quantizes a data-delay (secs) into a
                   // discrete stagger SLOT index; the runtime then spreads those
                   // slots across the element's window at its own dynamic pace.
  const fps = 30;
  let idx = 0;
  return svg.replace(/<([a-zA-Z][\w:-]*)\b([^>]*?\bdata-animate\s*=\s*"[^"]*"[^>]*?)(\/?)>/g,
    (full, tag: string, attrs: string, slash: string) => {
      const animM = /\bdata-animate\s*=\s*"([^"]*)"/.exec(attrs);
      const anim = animM ? animM[1] : "fade";
      const delayM = /\bdata-delay\s*=\s*"([^"]*)"/.exec(attrs);
      const stagger = delayM
        ? Math.max(0, Math.round((parseFloat(delayM[1]) || 0) * fps / STAG))
        : idx;
      idx++;
      const originStyle = "transform-box:fill-box;transform-origin:center";
      let a = attrs;
      if (/\bclass\s*=\s*"/.test(a)) a = a.replace(/\bclass\s*=\s*"([^"]*)"/i, (_m, c) => `class="${c} stg"`);
      else a += ` class="stg"`;
      if (/\bstyle\s*=\s*"/.test(a)) a = a.replace(/\bstyle\s*=\s*"([^"]*)"/i, (_m, s) => `style="${s};${originStyle}"`);
      else a += ` style="${originStyle}"`;
      a += ` data-stagger="${stagger}" data-reveal="${anim}"`;
      return `<${tag}${a}${slash}>`;
    });
}

// --- viz fallback: never blank. Shows type + any string/number props. ---
function vizFallback(vizType: string | undefined, p: any, theme: Theme): string {
  const rows = Object.entries(p || {})
    .filter(([, v]) => typeof v === "string" || typeof v === "number")
    .map(([k, v]) => `<div style="font-family:${theme.fonts.mono};font-size:15px;color:${theme.colors.inkSoft}"><b style="color:${theme.colors.ink}">${escapeHtml(k)}</b>: ${escapeHtml(String(v))}</div>`)
    .join("\n");
  return `<div style="padding:32px 40px;border-radius:16px;background:${theme.colors.bg2};border:1px solid ${theme.colors.grid};text-align:center">
      <div style="font-family:${theme.fonts.mono};font-size:13px;font-weight:700;letter-spacing:0.12em;color:${theme.colors.inkSoft};margin-bottom:12px">${escapeHtml(String(vizType ?? "viz").toUpperCase())}</div>
      ${rows}
    </div>`;
}

// --- Shared trace-log HTML (used by component + viz) ---
function traceLogHtml(theme: Theme, timing: any, reveal: string, columns: string[], entries: any[], badge?: string): string {
  const head = columns.length
    ? `<div class="stg" data-stagger="0" style="display:flex;gap:24px;padding:0 4px 8px;border-bottom:1px solid ${theme.colors.grid}">${columns.map((c) => `<div style="flex:1;font-family:${theme.fonts.mono};font-size:12px;font-weight:700;letter-spacing:0.08em;color:${theme.colors.inkSoft};text-transform:uppercase">${escapeHtml(c)}</div>`).join("")}</div>`
    : "";
  const rows = entries.map((e: any, i: number) => {
    const cells = Array.isArray(e.tokens) ? e.tokens : (Array.isArray(e) ? e : [String(e)]);
    return `<div class="stg" data-stagger="${i + 1}" style="display:flex;gap:24px;padding:8px 4px;border-bottom:1px solid ${theme.colors.grid}55">${cells.map((cell: string) => `<div style="flex:1;font-family:${theme.fonts.mono};font-size:16px;color:${theme.colors.ink}">${escapeHtml(String(cell))}</div>`).join("")}</div>`;
  }).join("\n");
  const badgeHtml = badge
    ? `<div style="align-self:flex-end;margin-bottom:10px;padding:4px 12px;border-radius:10px;background:${theme.colors.amber}22;border:1px solid ${theme.colors.amber}66;font-family:${theme.fonts.mono};font-size:11px;font-weight:700;letter-spacing:0.1em;color:${theme.colors.amber}">${escapeHtml(badge)}</div>`
    : "";
  return `<div class="vdsl-el" data-el="trace-log" data-start="${timing.start}" data-end="${timing.end ?? ""}" data-reveal="${reveal}" style="position:absolute;inset:0;display:flex;justify-content:center;align-items:center;padding:100px 160px">
    <div style="width:100%;max-width:900px;display:flex;flex-direction:column;padding:28px 32px;border-radius:16px;background:${theme.colors.bg2};border:1px solid ${theme.colors.grid};box-shadow:0 16px 44px rgba(0,0,0,0.14)">
      ${badgeHtml}${head}${rows}
    </div>
  </div>`;
}

// --- Helpers ---
function posToStyle(position: string): string {
  const base = "position:absolute;inset:0;display:flex;";
  switch (position) {
    case "upper-left": return base + "justify-content:flex-start;align-items:flex-start;padding:60px 60px";
    case "upper-right": return base + "justify-content:flex-end;align-items:flex-start;padding:60px 60px";
    case "bottom-center": return base + "justify-content:center;align-items:flex-end;padding:0 0 50px";
    case "bottom-right": return base + "justify-content:flex-end;align-items:flex-end;padding:0 60px 50px";
    default: return base + "justify-content:center;align-items:center";
  }
}
