# Design System

> Visual tokens and component patterns for SkillNet. AI agents must follow this file — do not invent colors, spacing, or patterns outside of what's defined here.

---

## Principles

1. **Clean over decorated.** No gratuitous gradients, glows, or shadows. White space is the primary visual tool
2. **Hierarchy through weight and spacing.** Use font weight and spacing to create hierarchy, not color blocks and badges
3. **Consistent, not uniform.** Every component follows the same tokens but screens can feel different through layout
4. **Functional, not playful.** This is a work tool used by employees between tasks. Not a consumer app, not a game

## Anti-patterns (DO NOT)

- `rounded-2xl` or `rounded-3xl` on cards. Use `rounded-lg` max
- `bg-gradient-to-*` on containers. Flat backgrounds only
- Colored icon backgrounds on every metric card (the `bg-blue-50` + blue icon pattern)
- `shadow-lg` or `shadow-xl` on cards. Use `shadow-sm` or `border` only
- Pastel badges everywhere. Use badges sparingly, only for status
- Decorative animations on page load. No `animate-fade-in` on every element
- Emoji in UI text

---

## Color tokens

Defined as CSS custom properties in `src/styles/index.css`:

```css
@theme {
  /* Background */
  --color-bg: #ffffff;
  --color-bg-subtle: #f8fafc;         /* slate-50 */
  --color-bg-muted: #f1f5f9;          /* slate-100 */

  /* Text */
  --color-text: #0f172a;              /* slate-900 */
  --color-text-secondary: #64748b;    /* slate-500 */
  --color-text-muted: #94a3b8;        /* slate-400 */

  /* Border */
  --color-border: #e2e8f0;            /* slate-200 */
  --color-border-strong: #cbd5e1;     /* slate-300 */

  /* Primary — brand blue (spider) */
  --color-primary: #3661A5;
  --color-primary-hover: #2B4F8A;
  --color-primary-subtle: #EBF0F7;

  /* Accent — brand green (web) */
  --color-accent: #4BA862;
  --color-accent-hover: #3D8C51;
  --color-accent-subtle: #EDF7EF;

  /* Status */
  --color-success: #4BA862;           /* brand green */
  --color-warning: #d97706;           /* amber-600 */
  --color-danger: #dc2626;            /* red-600 */

  /* Skill levels */
  --color-skill-high: #4BA862;        /* brand green */
  --color-skill-medium: #d97706;      /* amber-600 */
  --color-skill-low: #dc2626;         /* red-600 */
  --color-skill-none: #e2e8f0;        /* slate-200 */
}
```

Usage: `text-[--color-text-secondary]` or `bg-[--color-bg-subtle]`. Do not use arbitrary Tailwind colors outside these tokens.

## Typography

**Font:** Inter (system fallback: -apple-system, sans-serif)

| Use | Class | Size |
|-----|-------|------|
| Page title | `text-2xl font-semibold` | 24px |
| Section title | `text-lg font-semibold` | 18px |
| Card title | `text-base font-medium` | 16px |
| Body | `text-sm` | 14px |
| Caption / metadata | `text-xs text-[--color-text-secondary]` | 12px |

- No `text-3xl` or larger for page titles. Keep it calm
- No `font-bold` — use `font-semibold` for headings, `font-medium` for emphasis
- Line height: default Tailwind (`leading-normal`)

## Spacing

Use Tailwind's default scale consistently:

| Context | Value |
|---------|-------|
| Page padding | `p-6` (24px) |
| Section gap | `space-y-6` (24px) |
| Card padding | `p-5` (20px) |
| Between elements inside card | `space-y-3` (12px) |
| Between inline items | `gap-3` (12px) |
| Between form fields | `space-y-4` (16px) |

## Border radius

| Element | Value |
|---------|-------|
| Cards, panels | `rounded-lg` (8px) |
| Buttons | `rounded-md` (6px) |
| Inputs | `rounded-md` (6px) |
| Badges | `rounded-full` (only badges) |
| Avatars | `rounded-full` |

No `rounded-xl`, `rounded-2xl`, or `rounded-3xl` anywhere.

## Shadows

| Element | Value |
|---------|-------|
| Cards | `shadow-sm` or `border border-[--color-border]` (not both) |
| Dropdowns, modals | `shadow-md` |
| Everything else | No shadow |

Prefer `border` over `shadow` for card separation. Shadow only when elevation matters (dropdowns, modals).

## Icons

Lucide React. Size `w-4 h-4` (16px) for inline, `w-5 h-5` (20px) for standalone.

- Icons are `text-[--color-text-secondary]` by default
- Active/primary icons are `text-[--color-primary]`
- No colored background circles around icons (no `bg-blue-50 rounded-full p-2` pattern)
- Icons accompany text, they don't replace it

---

## Transitions and interactions

See `motion-system.md` for timing and easing curves. These are the rules:

1. **No blur.** Nunca. Ni en transiciones, ni en modales, ni en overlays, ni en backdrops.
2. **Morph from trigger.** Todo lo que se abre (modal, panel, chat, popover) se transforma
   visualmente desde el elemento que lo abrio. Usar `layoutId` de Framer Motion.
   - Card de lista -> fullscreen: morph con layoutId
   - Pill del buddy -> card de chat: morph con layoutId
   - Boton -> panel expandido: morph con layoutId
   - NUNCA: modal centrado que aparece de la nada con backdrop
3. **Opacity + scale para entradas.** `initial={{ opacity: 0, scale: 0.97 }}` es el patron
   base. NO blur, NO translateY grande, NO rotate.
4. **Secuencial.** Los elementos entran uno despues de otro. El siguiente espera a que el
   anterior termine. `delay` suficiente para que no se solapen.
5. **Chevrones, no flechas.** Los iconos de navegacion son chevrones (`<` / `>`), no flechas
   (`←` / `→`). Coherente en toda la app.
6. **Sin decoracion de carga.** No spinners, no "Cargando...", no barras de progreso
   genericas. Si hay espera, mostrar el esqueleto del contenido (shimmer) o pasos con nombre.

### Anti-patterns de transicion (DO NOT)

- `backdrop-blur-sm` o cualquier blur en scrim/overlay
- Modal que aparece centrado sin conexion visual con su trigger
- `animate-spin` como indicador de carga
- Fade-in en page load (animar lo que ya estaba ahi)
- Elementos que entran todos a la vez (sin stagger)
- Transicion de salida mas larga que la de entrada

---

## Component patterns

### Card

```tsx
<div className="border border-[--color-border] rounded-lg p-5">
  <h3 className="text-base font-medium text-[--color-text]">Title</h3>
  <p className="text-sm text-[--color-text-secondary] mt-1">Description</p>
</div>
```

No shadow. Border only. No gradient backgrounds.

### Button

```tsx
// Primary
<button className="bg-[--color-primary] hover:bg-[--color-primary-hover] text-white text-sm font-medium px-4 py-2 rounded-md">
  Action
</button>

// Secondary
<button className="border border-[--color-border] hover:bg-[--color-bg-muted] text-sm font-medium px-4 py-2 rounded-md">
  Cancel
</button>

// Ghost
<button className="hover:bg-[--color-bg-muted] text-sm text-[--color-text-secondary] px-3 py-1.5 rounded-md">
  Optional
</button>
```

### Input

```tsx
<input
  className="w-full border border-[--color-border] rounded-md px-3 py-2 text-sm focus:outline-none focus:border-[--color-primary] focus:ring-1 focus:ring-[--color-primary]"
  placeholder="Email"
/>
```

### Badge (status only)

```tsx
// Skill levels
<span className="text-xs font-medium px-2 py-0.5 rounded-full bg-green-50 text-green-700">High</span>
<span className="text-xs font-medium px-2 py-0.5 rounded-full bg-amber-50 text-amber-700">Medium</span>
<span className="text-xs font-medium px-2 py-0.5 rounded-full bg-red-50 text-red-700">Low</span>

// Content status
<span className="text-xs font-medium px-2 py-0.5 rounded-full bg-[--color-bg-muted] text-[--color-text-secondary]">Draft</span>
<span className="text-xs font-medium px-2 py-0.5 rounded-full bg-green-50 text-green-700">Published</span>
```

Badges are for status. Not for decorating every metric.

### Skeleton (loading)

```tsx
<div className="space-y-3">
  <ShimmerSkeleton className="h-4 w-1/3" />
  <ShimmerSkeleton className="h-4 w-full" />
  <ShimmerSkeleton className="h-4 w-2/3" />
</div>
```

Skeleton shape should match the content it replaces. No generic spinners.

`ShimmerSkeleton` (`components/ui/ShimmerSkeleton.tsx`) is the one to use in new code: a
transform-based shimmer sweep rather than `animate-pulse`. Under `prefers-reduced-motion` it
drops the sweep entirely and renders a static muted block — a slower animation is not the
accessible degradation, no animation is.

The older `components/ui/Skeleton.tsx` still exists and still uses `animate-pulse`. It was
deliberately **not** changed: it is re-exported as `SkeletonText` / `SkeletonCard` /
`SkeletonRow` across v1 pages, so editing it would have been a visible v1 change with the v2
flag off. Leave it alone; reach for `ShimmerSkeleton` in anything new.

### Empty state

```tsx
<div className="text-center py-12">
  <p className="text-sm text-[--color-text-secondary]">No courses assigned yet</p>
  <button className="mt-3 text-sm text-[--color-primary] hover:underline">
    Ask your admin to assign one
  </button>
</div>
```

Centered, minimal. One line of explanation + one action if applicable. No large illustrations or decorative icons.

### Progress bar

```tsx
<div className="h-1.5 bg-[--color-bg-muted] rounded-full overflow-hidden">
  <div className="h-full bg-[--color-primary] rounded-full" style={{ width: '40%' }} />
</div>
```

Thin (`h-1.5`), not chunky. Color matches primary.

### Skills matrix cell

```tsx
// In admin skills matrix table
<td className="px-3 py-2">
  <span className="inline-block w-3 h-3 rounded-full bg-[--color-skill-high]" />
</td>
```

Small colored dot. Not a full colored cell background.

---

## Layout

### Page

```tsx
<main className="max-w-6xl mx-auto p-6">
  <h1 className="text-2xl font-semibold text-[--color-text]">Page Title</h1>
  <p className="text-sm text-[--color-text-secondary] mt-1">Subtitle or context</p>
  <div className="mt-6">
    {/* Page content */}
  </div>
</main>
```

### Sidebar

- Width: `w-60` expanded, `w-16` collapsed (icons only)
- Background: `bg-[--color-bg]` with right border `border-r border-[--color-border]`
- Nav items: `text-sm`, active = `bg-[--color-bg-muted] text-[--color-text] font-medium`, inactive = `text-[--color-text-secondary]`
- No colored backgrounds for active items. Subtle highlight only

### Responsive

- Desktop: sidebar + content
- Tablet: collapsed sidebar (icons) + content
- Mobile: no sidebar, hamburger menu. Content full width with `p-4`

---

## Motion & Animations

See [`motion-system.md`](motion-system.md) for the complete animation specification — easing curves, timing, patterns (morph modals, blur transitions, staggered lists, micro-interactions).

---

## What this system does NOT define

- Dark mode (not planned)
- Marketing pages (this is for the app only)
