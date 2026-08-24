---
title: "Motion system"
order: 43
section: "extensibility"
---

# Motion System

> Animation system for SkillNet. The goal is for the app to feel like a native iOS app — fluid transitions, elements that morph into one another, physical feedback when interacting. Not like a website loading pages, but like an app that flows between states.

**Library:** Framer Motion (already integrated). Do not migrate to GSAP — Framer Motion's `layoutId` implements the same FLIP technique natively in React.

---

## Principles

1. **Opacity and scale, never blur.** Elements enter/exit with opacity (and optionally
   scale). NEVER blur or backdrop-blur — not in transitions, not in modals, not in overlays.
   Blur is banned across the whole app.
2. **Morph, not appear.** When one element becomes another (card -> fullscreen, pill ->
   panel, word -> popover), it must visually transform from the trigger. Nothing appears out of
   thin air. Use Framer Motion's `layoutId` to connect the collapsed state with the expanded one.
3. **Overshoot, not ease-in-out.** Easing curves slightly overshoot the destination and
   settle back. Never use `ease`, `ease-in-out`, or `linear`.
4. **Fast feedback, slow structure.** Color/state changes are instant (125ms).
   Layout/position changes are slow and fluid (500-700ms).
5. **Spring over duration.** Prefer Framer Motion springs over fixed durations whenever
   possible. Springs don't have a fixed duration — they finish when the physics dictates.
6. **Sequential, not simultaneous.** Elements enter ONE AFTER ANOTHER, not all at once.
   Each element waits for the previous animation to finish before starting its own. In
   entry sequences (stagger), the delay between elements is enough that they don't
   overlap.
7. **Everything must flow.** From step to step, from node to node, from course to lesson — never a cut.
   The user should never perceive a "page change." It's an app that flows between states.

---

## Easing curves

Defined as reusable constants. Never hardcode inline values.

```typescript
// src/lib/motion.ts

// ── Base curves ──────────────────────────────────────────────
/** Smooth decelerate. General use for entries and transitions. */
export const ease = {
  /** Signature curve — smooth decelerate, clean landing */
  base:        [0.38, 0.49, 0, 1]       as const,
  /** Subtle bounce — hover buttons, interactive scale */
  bounce:      [0.38, 0.49, 0, 1.16]    as const,
  /** Medium bounce — border-radius morphs */
  bounceMid:   [0.38, 0.49, 0, 1.5]     as const,
  /** Strong bounce — padding expansion, playful effects */
  bounceHard:  [0.38, 0.49, 0, 2]       as const,
  /** Snappy — panels entering (push-in) */
  snapIn:      [0.1, 0.8, 0, 1]         as const,
  /** Fast exit — panels leaving (push-out) */
  snapOut:     [0.1, 0, 0.7, 1]         as const,
  /** Border morph — border-radius in modals */
  morph:       [0.56, 0.27, 0, 1]       as const,
} as const;
```

### When to use each curve

| Curve | Use | Example |
|-------|-----|---------|
| `ease.base` | Default for everything | Page transitions, modal open, list entry |
| `ease.bounce` | Interactive hover/press | Scale buttons, hover cards |
| `ease.bounceMid` | Shape changes | Pill border-radius, toggles |
| `ease.bounceHard` | Playful expansion | Padding grows on hover, chips |
| `ease.snapIn` | Panels entering | Sidebar push, sub-section enter |
| `ease.snapOut` | Panels leaving | Sidebar dismiss, sub-section exit |
| `ease.morph` | Shape transformation | Pill modal -> fullscreen |

---

## Timing

```typescript
// src/lib/motion.ts

export const duration = {
  /** Immediate feedback — color, background, icon state */
  instant:   0.125,
  /** Fast transition — tooltips, dropdowns, focus rings */
  fast:      0.2,
  /** Content blur/fade */
  normal:    0.3,
  /** Page transitions, list stagger */
  medium:    0.5,
  /** Modal morph, shared element transitions */
  slow:      0.7,
  /** Border-radius morph on mobile (fullscreen modal) */
  morphSlow: 1.0,
} as const;
```

### Dual timing rule

**Decorative** changes (color, background, icon opacity) use `instant` or `fast`.
**Structural** changes (layout, position, size, border-radius) use `medium` or `slow`.

Never mix: a button changes color in 125ms but its scale is 300ms.

---

## Springs

For physical interactions, use springs instead of fixed durations:

```typescript
// src/lib/motion.ts

export const spring = {
  /** Default — responsive, settles quickly */
  default:  { type: "spring", stiffness: 400, damping: 30 } as const,
  /** Bouncy — for playful interactive elements */
  bouncy:   { type: "spring", stiffness: 500, damping: 25 } as const,
  /** Stiff — for snapping and precise positioning */
  stiff:    { type: "spring", stiffness: 500, damping: 35, mass: 0.5 } as const,
  /** Gentle — for large layout shifts */
  gentle:   { type: "spring", stiffness: 200, damping: 25 } as const,
} as const;
```

---

## Animation patterns

### 1. Page transitions

Every route change animates with blur + fade + subtle scale.

```tsx
// In the layout that wraps <Outlet />
<AnimatePresence mode="wait">
  <motion.div
    key={location.pathname}
    initial={{ opacity: 0, filter: "blur(8px)", scale: 0.98 }}
    animate={{ opacity: 1, filter: "blur(0px)", scale: 1 }}
    exit={{ opacity: 0, filter: "blur(8px)", scale: 0.98 }}
    transition={{ duration: duration.medium, ease: ease.base }}
  >
    <Outlet />
  </motion.div>
</AnimatePresence>
```

**Before (what we had):** `opacity: 0, y: 8` with `duration: 0.2`
**Now:** blur + scale creates depth, not just a flat fade.

---

### 2. Morph modals (shared element transitions)

The most important pattern. An element in a list visually transforms into the modal/detail view.

```tsx
// In the list — the source element
<motion.div
  layoutId={`card-${item.id}`}
  onClick={() => setSelected(item)}
  className="border rounded-lg p-5 cursor-pointer"
  whileHover={{ scale: 1.02 }}
  transition={{ layout: { duration: duration.slow, ease: ease.base } }}
>
  <motion.h3 layoutId={`title-${item.id}`}>{item.name}</motion.h3>
  <motion.p layoutId={`desc-${item.id}`}>{item.description}</motion.p>
</motion.div>

// The modal — the target element (same layoutId)
<AnimatePresence>
  {selected && (
    <>
      {/* Backdrop */}
      <motion.div
        className="fixed inset-0 bg-black/10 backdrop-blur-sm"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: duration.fast }}
        onClick={() => setSelected(null)}
      />
      {/* Modal that morphs from the card */}
      <motion.div
        layoutId={`card-${selected.id}`}
        className="fixed inset-4 md:inset-12 bg-white rounded-lg p-6 overflow-auto"
        transition={{ layout: { duration: duration.slow, ease: ease.base } }}
      >
        <motion.h3 layoutId={`title-${selected.id}`}>{selected.name}</motion.h3>
        <motion.p layoutId={`desc-${selected.id}`}>{selected.description}</motion.p>
        {/* Extra modal content with blur-in */}
        <motion.div
          initial={{ opacity: 0, filter: "blur(8px)" }}
          animate={{ opacity: 1, filter: "blur(0px)" }}
          transition={{ delay: 0.2, duration: duration.normal, ease: ease.base }}
        >
          {/* expanded content */}
        </motion.div>
      </motion.div>
    </>
  )}
</AnimatePresence>
```

**Backdrop:** Only `bg-black/10` (10% opacity). Heavy backdrops are from 2015. Combine with `backdrop-blur-sm` for a subtle frosted glass.

---

### 3. Staggered lists

List items appear sequentially with blur.

```tsx
// Container
<motion.ul
  initial="hidden"
  animate="visible"
  variants={{
    visible: { transition: { staggerChildren: 0.06 } },
  }}
>
  {items.map((item) => (
    <motion.li
      key={item.id}
      variants={{
        hidden: { opacity: 0, y: 12, filter: "blur(6px)" },
        visible: {
          opacity: 1,
          y: 0,
          filter: "blur(0px)",
          transition: { duration: duration.normal, ease: ease.base },
        },
      }}
    >
      {/* content */}
    </motion.li>
  ))}
</motion.ul>
```

**Stagger:** 0.06s between items (fast, not dramatic). Max 8-10 animated items — if there are more, only animate the ones visible in the viewport.

**Item exit** (when removed from a list):

```tsx
<motion.li
  exit={{
    opacity: 0,
    filter: "blur(16px)",
    x: -64,
    transition: { duration: duration.normal, ease: ease.snapOut },
  }}
/>
```

Items exit to the left with blur. They don't fade out in place.

---

### 4. Sub-section panels (push navigation)

iOS-style navigation within a section — panel enters from the right.

```tsx
<AnimatePresence mode="wait">
  {activeSection === "detail" ? (
    <motion.div
      key="detail"
      initial={{ opacity: 0, x: "100%" }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: "100%" }}
      transition={{
        enter: { duration: 0.4, ease: ease.snapIn },
        exit: { duration: 0.2, ease: ease.snapOut },
      }}
    >
      <DetailView />
    </motion.div>
  ) : (
    <motion.div
      key="list"
      initial={{ opacity: 0, x: "-30%" }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: "-30%" }}
      transition={{ duration: 0.3, ease: ease.base }}
    >
      <ListView />
    </motion.div>
  )}
</AnimatePresence>
```

**Enter/exit asymmetry:** Enter is slow (400ms, snapIn). Exit is fast (200ms, snapOut). This mimics the iOS navigation controller.

---

### 5. Micro-interactions

#### Buttons

```tsx
<motion.button
  whileHover={{ scale: 1.03 }}
  whileTap={{ scale: 0.97 }}
  transition={{ type: "spring", stiffness: 500, damping: 30 }}
>
  Action
</motion.button>
```

- Hover: subtle scale (1.03), not exaggerated
- Tap: squish (0.97) — pressure feedback
- Spring so the return feels organic

#### Card hover

```tsx
<motion.div
  whileHover={{
    scale: 1.02,
    boxShadow: "0 8px 32px -8px rgba(0,0,0,0.12)",
  }}
  transition={{
    scale: { type: "spring", stiffness: 400, damping: 25 },
    boxShadow: { duration: duration.normal, ease: ease.base },
  }}
>
  <Card />
</motion.div>
```

#### Input focus

```css
/* Pure CSS — doesn't need Framer Motion */
input:focus {
  box-shadow: 0 0 0 3px var(--color-primary-subtle),
              0 1px 3px rgba(0,0,0,0.08);
  transition: box-shadow 0.3s cubic-bezier(0.38, 0.49, 0, 1);
}
```

#### Active nav indicator

```tsx
// Pill that follows the active item in the sidebar
<motion.div
  className="absolute left-0 bg-[--color-bg-muted] rounded-md"
  layoutId="nav-indicator"
  transition={spring.stiff}
  style={{ width: "100%", height: itemHeight }}
/>
```

Uses `layoutId` — the pill moves with spring physics between nav items.

---

### 6. Frosted glass surfaces

```css
/* iOS-style translucent panels */
.glass-panel {
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(24px) saturate(1.2);
}

/* Dark mode */
@media (prefers-color-scheme: dark) {
  .glass-panel {
    background: rgba(0, 0, 0, 0.8);
  }
}

/* Mobile bottom bar */
.mobile-bar {
  backdrop-filter: blur(16px);
  background: rgba(255, 255, 255, 0.85);
}
```

Use for: mobile bottom nav, modal backdrops, sticky headers, floating action bars.

---

### 7. Toasts / Notifications

```tsx
<motion.div
  initial={{ y: -60, opacity: 0, filter: "blur(8px)" }}
  animate={{ y: 0, opacity: 1, filter: "blur(0px)" }}
  exit={{ y: -60, opacity: 0, filter: "blur(8px)" }}
  transition={{
    enter: { type: "spring", stiffness: 300, damping: 20 },
    exit: { duration: 0.2, ease: ease.snapOut },
  }}
>
  <Toast />
</motion.div>
```

Toasts enter from the top with a spring (subtle bounce). They exit fast, without bounce.

---

## Properties that get animated

Ordered by frequency of use:

| Property | Pattern | Notes |
|-----------|--------|-------|
| `opacity` | 0 -> 1 (enter), 1 -> 0 (exit) | Always paired with blur |
| `filter: blur()` | 8-16px -> 0 (enter), 0 -> 16-32px (exit) | Main motion primitive |
| `scale` | 0.96-0.98 -> 1 (enter), 1.02-1.03 (hover) | Always subtle |
| `x, y` | translate for slides and pushes | Y for vertical, X for push navigation |
| `borderRadius` | Shape morph (card -> fullscreen) | Via automatic `layout` prop |
| `boxShadow` | Hover elevation | Slow transition (300ms) |
| `backgroundColor` | Active/hover state | Fast transition (125ms) |

### Properties that are NOT animated

- `width` / `height` directly — use Framer Motion's `layout` prop
- `margin` / `padding` — except for very specific micro-interactions
- `border-color` — instant change, don't transition
- `font-size` / `font-weight` — don't animate typography

---

## GPU acceleration

```css
/* Apply to elements that animate frequently */
a, button {
  will-change: transform;
}

/* Force a compositing layer on elements with backdrop-filter */
.glass-panel {
  transform: translateZ(0);
}
```

Framer Motion already handles `will-change` automatically in its `motion.*` components. Only add manual hints for pure CSS elements.

---

## Anti-patterns (do NOT do)

- `ease-in-out` or `linear` as easing — always custom curves with overshoot
- Fade without blur — flat fades feel "web," not "native"
- Uniform durations — each type of change has its own timing
- Animating everything — only animate meaningful state changes, not decoration
- Tailwind's `animate-bounce` or `animate-pulse` — too generic and an infinite loop
- Long delays (>300ms) — the user shouldn't have to wait on the animation
- Animating on page load — the initial content appears immediately, without stagger

---

## Presets file

All constants in this document are exported from `src/lib/motion.ts`. Import from there, never define values inline.

```typescript
// Usage in components
import { ease, duration, spring } from '@/lib/motion';

<motion.div
  transition={{ duration: duration.medium, ease: ease.base }}
/>
```

---

## Current state

### Already done

- [x] `src/lib/motion.ts` — centralized presets (ease, duration, spring, transition, variants)
- [x] `src/pages/dev/MotionDemo.tsx` — interactive demo page at `/dev/motion` with all patterns
- [x] `/dev/motion` route registered in `App.tsx`
- [x] This document

### Demo page

At `/dev/motion` there's a page with interactive demos of each pattern: page transitions, morph modals, staggered lists, push navigation, micro-interactions, wizard steps, sidebar overlay, content swap, and a before/after comparison. Use it as a visual reference for what we're aiming for.

---

## What we want to achieve

Right now the app feels like a website: pages appear and disappear with a flat fade, modals pop out of nowhere, lists appear all at once. We want it to feel like a native app — like when you use an app on the iPhone and everything flows, things transform into each other, there's depth in the transitions, and buttons respond physically when you touch them.

Below is what we want to improve, in order of importance. There are presets already prepared in `src/lib/motion.ts` that can be used directly.

---

### 1. The sidebar and page transitions

This is the most important change because it's what the user sees constantly.

**How the layout works:** The app has an "L-frame" design — the sidebar and header are blue (a gradient with texture, `frame-surface` class in `index.css`) and the main content is white with a rounded corner at the top left (`rounded-tl-xl`). It's as if the white area sits "on top" of the blue frame.

**The active pill effect:** The active page in the nav has a white background that extends all the way to the right edge of the sidebar, blending with the main content's white. There's no separation — the nav's white and the content's white are one. This creates the illusion that the content "enters" the sidebar to mark where you are.

```
SIDEBAR (blue)  │  MAIN (white)
                │╭─────────────────
  Home          ││
  ■■■■■■■■■■■■■■██  ← the white blends with the main content
  Courses       ││
  Skills        ││
                │╰─────────────────
```

**What's wrong now:** In AdminSidebar there's a pill animated with a spring, but it has a gap to the right edge (`right-4`) that breaks the fusion with the main content. In the employee Sidebar there isn't even an animated pill — it's a static background. And when you change pages, the content does a flat fade that feels like a web page loading.

**What we want:** When you click a nav item, the white pill should slide smoothly to the new item (with a spring, like an actual spring), and the main content should transition with blur and scale so it feels fluid, like switching tabs in an app. The main content's white frame never moves — only what's inside it changes. The feeling should be of "sliding" between sections, not "loading" a new page.

**Relevant files:** `Sidebar.tsx`, `AdminSidebar.tsx`, `AppLayout.tsx`, `AdminLayout.tsx`

---

### 2. Modals that transform instead of appearing

Right now there are several interactions where forms or detail views open abruptly. A good example is the Employees page (`Employees.tsx`):

- The "Add employee" button makes a form appear below with no animation at all. It would be much better if the button transformed into the form — growing smoothly until it becomes the form's Card. And on close, it should shrink back into the button.

- When you click an employee in the list, the whole page is replaced by the employee's detail view. Context of where you came from is completely lost. It would be better to have a modal that opens from the employee's row/card — the list item visually transforming into the modal. With a subtle background (not heavy black, but a frosted-glass-style blur). And the extra modal content (assigned courses, etc.) should appear with blur once the morph finishes.

- The reset password modal uses a 40% black background with no blur — it looks dated. It should have backdrop-blur.

This "morph modal" pattern applies in many places across the app, not just Employees. It's a general pattern: whenever something expands into a detail view, it should transform, not appear out of nowhere.

There's an interactive demo of this pattern at `/dev/motion`, "Morph Modals" section.

**Relevant files:** `Employees.tsx` as the first case, but the pattern applies throughout the app.

---

### 3. Lists that appear with rhythm

Lists of employees, courses, and content all appear at once right now. They should appear item by item with a slight stagger, each one entering with a bit of blur that resolves. Not dramatic — fast and subtle, to give rhythm without slowing the user down.

When an item is deleted, it should slide out to the left with blur, not disappear abruptly.

**Where to apply:** employee lists, admin courses, employee courses, lessons within a course.

---

### 4. Buttons and cards that respond to touch

Buttons currently only change color on hover. They should have a slight scale on hover (grow a bit) and a "squish" on click (shrink a bit, as if physically pressed). Spring physics so the return feels organic, not linear.

Interactive cards should lift slightly on hover (a bit of shadow and scale).

Nothing exaggerated — micro-interactions, almost imperceptible but together they make the app feel alive.

---

### 5. Lesson change in CourseView

When the employee switches lessons, the content does a flat fade. It should do a transition with blur. And if possible, it should be directional: if you move to the next lesson, the content exits to the left and enters from the right. If you go back, the opposite.

**Relevant files:** `CourseView.tsx`

---

### 6. Create-course wizard

The 5-step wizard already has a directional slide, but with no blur and a generic easing that feels mechanical. It should use the motion system's presets (blur on enter/exit, signature curve, and asymmetry: enter slow, exit fast).

**Relevant files:** `CreateCourse.tsx`

---

### 7. Mobile sidebar

The sidebar overlay on mobile uses a 50% black background (too heavy) and the sidebar enters with a generic easing. It should use backdrop-blur (a subtle frosted glass) and the sidebar should enter with spring physics.

**Relevant files:** `Sidebar.tsx`, `AdminSidebar.tsx`

---

### 8. CSS utilities

Add easing custom properties to `index.css` so they can be used in pure CSS (not everything needs Framer Motion). Also a `.glass-panel` class for frosted-glass surfaces (backdrop-blur), and `will-change: transform` on buttons/links for GPU acceleration.

**Relevant files:** `index.css`

---

## Motion design research — findings

An in-depth analysis was done of reference web apps that achieve a native feel. Below are the technical findings used to define this document's presets.

### Easing curves found

These curves are the ones that give the "native" feel — all are variants of an aggressive decelerate with different degrees of overshoot:

| Curve | Character | Typical use |
|---|---|---|
| `cubic-bezier(0.38, 0.49, 0, 1)` | Smooth decelerate, clean landing | Main curve for everything |
| `cubic-bezier(0.38, 0.49, 0, 1.16)` | Subtle overshoot | Hover buttons, interactive scale |
| `cubic-bezier(0.38, 0.49, 0, 1.5)` | Medium overshoot | Border-radius morphs, toggles |
| `cubic-bezier(0.38, 0.49, 0, 2)` | Strong overshoot | Padding expansion, bouncy |
| `cubic-bezier(0.1, 0.8, 0, 1)` | Snappy, fast at the start | Panels entering (push-in) |
| `cubic-bezier(0.1, 0, 0.7, 1)` | Acceleration for exits | Panels leaving (push-out) |
| `cubic-bezier(0.56, 0.27, 0, 1)` | Emphasized decelerate | Border-radius morph in modals |

**Key point:** `ease`, `ease-in-out`, or `linear` are never used. Everything is custom with some degree of overshoot.

### Recurring animation patterns

**Blur as a primitive:** Every element entry/exit uses `filter: blur()` in addition to opacity. Typical values are 8-16px blur on enter and 16-32px on exit. This creates a depth-of-field effect, like the eye focusing and unfocusing.

**Shared-element transitions (FLIP):** Modals don't appear out of nowhere — they transform from their source element (a button, a card, a table row). The FLIP technique (First, Last, Invert, Play) captures the initial position, calculates the final one, and animates between them. In Framer Motion this is done with `layoutId`.

**Border-radius morphing:** Modals on mobile go from a pill shape (border-radius 64px) to fullscreen (border-radius 0), animated over ~1s with `cubic-bezier(0.56, 0.27, 0, 1)` easing. This gives the iOS "sheet" effect.

**Frosted glass:** Surfaces with `backdrop-filter: blur(24-64px) saturate(1.2)` and a semi-transparent background. Modal backdrops are subtle (10% black, not 40-50%).

**Dual timing:** State changes (color, background, icons) are fast (~125ms). Structural changes (position, size, layout) are slow (~500-700ms). This difference creates the sense that the app responds instantly to input but transitions are fluid.

**Enter/exit asymmetry:** Entries are slower (~400ms) than exits (~200ms). This mimics iOS navigation, where pushing a view is deliberate but going back is fast.

**Stagger with blur:** List items appear sequentially (~60ms between items), each with blur that resolves. It's fast and subtle — it doesn't slow perceived loading.

### Animated properties (by frequency)

1. `opacity` — always paired with blur
2. `filter: blur()` — the main primitive
3. `transform: scale()` — subtle, 0.96-0.98 on enter, 1.02-1.03 on hover
4. `transform: translate()` — for slides and push navigation
5. `border-radius` — shape morph
6. `box-shadow` — hover elevation
7. `background-color` — fast state transition
8. `backdrop-filter` — translucent panels

### Properties that are NOT animated

- `width` / `height` directly
- `margin` / `padding` (except micro-interactions)
- `border-color`
- `font-size` / `font-weight`

### Anti-patterns observed (what native apps do NOT do)

- `ease-in-out` or `linear` as easing
- Flat fades without blur
- Uniform durations for everything
- `animate-bounce` or `animate-pulse` in a loop
- Long delays (>300ms) that make the user wait
- Decorative animations on page load

---

## Appendix: raw data from the reference app audit

Data extracted from an in-depth analysis of web apps with a native feel. Use as technical reference when implementing.

### CSS keyframes found

```css
/* Blur entrance — the most used pattern */
@keyframes blur-in {
  from { filter: blur(32px); }
  to   { filter: blur(0); }
  /* 300ms, cubic-bezier(.37, .35, 0, 1) */
}

/* Blur exit */
@keyframes blur-out {
  from { filter: blur(0); }
  to   { filter: blur(32px); }
  /* 500ms, cubic-bezier(.37, .35, 0, 1) */
}

/* General entrance — blur + scale */
@keyframes general-in {
  from { opacity: 0; filter: blur(16px); transform: scale(0.96); }
  to   { opacity: 1; filter: blur(0);    transform: scale(1); }
}

/* Intense entrance — strong blur + aggressive scale */
@keyframes general-in-2 {
  from { opacity: 0; filter: blur(32px); transform: scale(0.7); }
  to   { opacity: 1; filter: blur(0);    transform: scale(1); }
}

/* Mobile modal: pill -> fullscreen */
@keyframes window-border-radius {
  from { border-radius: 64px; }
  to   { border-radius: 0; }
  /* 1000ms, cubic-bezier(.56, .27, 0, 1) */
}

/* Modal close: card -> super-pill */
@keyframes window-border-radius-close {
  from { border-radius: 32px; }
  to   { border-radius: 400px; }
  /* 500ms */
}

/* Modal slide-up (iOS sheet) */
@keyframes window-in {
  from { transform: translateY(100%); }
  to   { transform: translateY(0); }
}

/* Push navigation enter */
@keyframes move-in {
  from { opacity: 0; transform: translateX(100%); }
  to   { opacity: 1; transform: translateX(0); }
  /* 400ms, cubic-bezier(0.1, 0.8, 0, 1) */
}

/* Push navigation exit */
@keyframes move-out {
  to { transform: translateX(100%); opacity: 0; }
  /* 200ms, cubic-bezier(.1, 0, .7, 1) */
}

/* Search result item entry — blur + slide */
@keyframes search-item-in {
  from { opacity: 0; filter: blur(16px); transform: translateY(-20px); }
  to   { opacity: 1; filter: blur(0);    transform: translateY(0); }
}

/* Item exit — blur + slide left */
@keyframes item-out-left {
  from { opacity: 1; filter: blur(0);    transform: translateX(0); }
  to   { opacity: 0; filter: blur(16px); transform: translateX(-64px); }
}

/* Button squish on click */
@keyframes button-click {
  0%   { transform: scaleX(1) scaleY(1); }
  50%  { transform: scaleX(0.95) scaleY(0.9); }
  100% { transform: scaleX(1) scaleY(1); }
  /* 500ms, cubic-bezier(.37, 1.42, .37, 1) */
}

/* Toast slide-down */
@keyframes message-in {
  from { transform: translateY(-80px); }
  to   { transform: translateY(0); }
}

/* Error shake */
@keyframes error-shake {
  0%   { transform: translateX(0); }
  25%  { transform: translateX(-2px); }
  50%  { transform: translateX(2px); }
  75%  { transform: translateX(-2px); }
  100% { transform: translateX(0); }
}

/* Entry wipe — gradient mask sweep */
@keyframes entry-wipe {
  from { transform: scaleX(1.4) translateX(0%); }
  to   { transform: scaleX(1.4) translateX(100%); }
  /* 700ms, cubic-bezier(0.38, 0.49, 0, 1) — uses a pseudo-element with gradient mask */
}

/* Perspective tilt-in (3D) */
@keyframes perspective-in {
  from { transform: perspective(400px) rotateX(-15deg); }
  to   { transform: perspective(400px) rotateX(0deg); }
}

/* Icon fill morph (Material Symbols variable font) */
@keyframes icon-fill {
  from { font-variation-settings: 'FILL' 0; }
  to   { font-variation-settings: 'FILL' 1; }
  /* 125ms, cubic-bezier(.48, 0, 0, 1) */
}

/* Blur fade — 3-phase midpoint blur */
@keyframes blur-fade {
  0%   { filter: blur(0px); }
  50%  { filter: blur(4px); }
  100% { filter: blur(0px); }
}
```

### GSAP CustomEase curves (SVG paths)

These are advanced easing curves defined as SVG paths, used for FLIP animations and modals:

```
/* Main curve for modals and FLIP transitions */
M0,0 C0.308,0.19 0.107,0.633 0.288,0.866 0.382,0.987 0.656,1 1,1
/* Character: aggressive ease-out, reaches 86% of the path at 29% of the time */

/* Modal open with subtle bounce at the end */
M0,0 C0.249,-0.124 0.04,0.951 0.335,1 0.684,1.057 0.614,0.964 1,1

/* Modal close (reverse) */
M0,0 C0.28,0.08 0.10,0.55 0.28,0.78 0.38,0.95 0.64,1 1,1
```

### CSS transitions found (by pattern)

```css
/* Transform transitions with overshoot */
button.hover-scale    { transition: transform 0.3s cubic-bezier(0, 0, 0.5, 1); }
button.style-bounce   { transition: transform 0.3s cubic-bezier(0.38, 0.49, 0, 1.16); }
nav.floating-dock     { transition: transform 500ms cubic-bezier(0, 1, 0, 1); }

/* Border-radius morphs */
nav-button            { transition: border-radius 500ms cubic-bezier(0.38, 0.49, 0, 1.2); }
menu.mobile           { transition: border-radius 2000ms cubic-bezier(.56, .27, 0, 1); }
/* Note: 2s for border-radius on mobile — extra slow, smooth morph */

/* Multi-property button with strong bounce */
button.rounded:hover {
  transition:
    padding 400ms cubic-bezier(0.38, 0.49, 0, 2),
    background 125ms,
    color 125ms,
    border-radius 200ms cubic-bezier(0.38, 0.49, 0, 1.5);
}

/* Input focus ring */
input.focus { transition: box-shadow 0.5s, background 0.5s; }

/* Nav icon font-weight morph */
nav-icon { transition: font-variation-settings 500ms; }

/* Generic content transitions */
editor-elements { transition: opacity 0.7s cubic-bezier(0.38, 0.49, 0, 1.1); }
editor-toolbar  { transition: all 0.5s cubic-bezier(0.38, 0.49, 0, 1.16); }

/* Folder expand */
folder-parent { transition: max-width 0.7s cubic-bezier(0.1, 0.8, 0, 1); }
```

### Backdrop-filter patterns

```css
/* Mobile bottom action bar */
.mobile-bar { backdrop-filter: blur(16px); }

/* Frosted glass panel — standard */
.glass-8 {
  background: rgba(255, 255, 255, 0.64);
  backdrop-filter: blur(8px);
}
@media (prefers-color-scheme: dark) {
  .glass-8 { background: rgba(0, 0, 0, 0.80); }
}

/* iOS-style sheet — heavy blur */
.sheet-panel {
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(64px);
}
@media (prefers-color-scheme: dark) {
  .sheet-panel { background: rgba(0, 0, 0, 0.88); }
}

/* Floating glass navbar */
nav.glass {
  background: rgba(255, 255, 255, 0.24);
  backdrop-filter: blur(8px);
}

/* Translucent modal */
.modal-translucent {
  background: rgba(var(--neutral-bg), 0);
  backdrop-filter: blur(24px) saturate(2);
  box-shadow:
    inset 1px 1px 1px rgba(255, 255, 255, 0.6),
    inset -1px -1px 1px rgba(255, 255, 255, 0.6),
    0 0 16px rgba(0, 0, 0, 0.16);
}
```

### GSAP stagger patterns (text and lists)

```js
/* Word-by-word entrance */
gsap.from(words, {
  y: 16,
  autoAlpha: 0,
  stagger: 0.1,
  ease: "back.out(1)",
  duration: 0.25,
  filter: "blur(6px)",
});

/* Character-by-character entrance */
gsap.from(chars, {
  opacity: 0,
  yPercent: 40,
  filter: "blur(4px)",
  duration: 0.4,
  ease: "power2.out",
  stagger: 0.02,
});

/* Toast snap-back (elastic) */
gsap.to(toast, {
  x: 0, y: 0, scale: 1,
  duration: 0.5,
  ease: "elastic.out(0.5, 0.5)",
});
```

### FLIP animation pattern (modal morph)

```js
/* Capture the initial state of the source element */
const state = Flip.getState(originElement);

/* Move/transform the element to its final position */
modalContainer.appendChild(originElement);

/* Animate from the captured state to the new one */
Flip.from(state, {
  targets: modalElement,
  duration: 0.7,
  scale: false,
  absolute: false,
  ease: CustomEase.create("custom",
    "M0,0 C0.308,0.19 0.107,0.633 0.288,0.866 0.382,0.987 0.656,1 1,1"),
});

/* In Framer Motion, this is achieved with layoutId — same FLIP technique, declarative API */
```

### Macbook-dock nav effect (CSS only)

```css
/* Neighbor scaling — items near hover grow proportionally */
nav button:has(+ * + *:hover) { transform: scale(1.03); }
nav button:has(+ *:hover)     { transform: scale(1.09); }
nav button:hover               { transform: scale(1.2); }
nav button:hover + *            { transform: scale(1.09); }
nav button:hover + * + *        { transform: scale(1.03); }
/* Uses :has() selector for cascade effect */
```

### Hover glow effects

```css
/* Shimmer sweep on hover */
.card::before {
  background: linear-gradient(to right, transparent, rgba(255,255,255,0.1), transparent);
  transform: translateX(-100%);
  animation: shimmer 2s infinite;
}
.card:hover {
  transform: scale(1.03);
  box-shadow: 0 24px 64px -32px var(--primary-container);
}

/* Radial glow on hover */
.card::after {
  background: var(--secondary-container);
  opacity: 0;
  transform: translate3d(-30%, -30%, 0);
  border-radius: 200px;
  filter: blur(100px);
  transition: all 0.3s cubic-bezier(0, 0, 0.5, 1);
}
.card:hover::after { opacity: 1; }
```

### GPU acceleration hints

```css
/* Global — pre-promote interactive elements */
a, button { will-change: transform; }

/* Force compositing for glow pseudo-elements */
.glow::after { transform: translate3d(-30%, -30%, 0); }

/* 3D perspective for tilt effects */
.tilt { transform: perspective(400px) rotateX(0deg); }
```
