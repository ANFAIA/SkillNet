---
title: "Sistema de diseño"
order: 16
section: "extensibility"
---

# Design System

> Tokens visuales y patrones de componentes de SkillNet. Los agentes de IA deben seguir este fichero: no inventar colores, espaciados ni patrones fuera de lo definido aquí.

---

## Principios

1. **Limpio antes que decorado.** Sin gradientes, brillos ni sombras gratuitos. El espacio en blanco es la herramienta visual principal
2. **Jerarquía mediante peso y espaciado.** Usa el peso de la fuente y el espaciado para crear jerarquía, no bloques de color ni badges
3. **Coherente, no uniforme.** Cada componente sigue los mismos tokens, pero las pantallas pueden sentirse distintas gracias al layout
4. **Funcional, no lúdico.** Esto es una herramienta de trabajo que usan empleados entre tareas. No es una app de consumo, ni un juego

## Anti-patrones (NO HACER)

- `rounded-2xl` o `rounded-3xl` en tarjetas. Usar `rounded-lg` como máximo
- `bg-gradient-to-*` en contenedores. Solo fondos planos
- Fondos de icono coloreados en cada tarjeta de métrica (el patrón `bg-blue-50` + icono azul)
- `shadow-lg` o `shadow-xl` en tarjetas. Usar solo `shadow-sm` o `border`
- Badges pastel por todas partes. Usar badges con moderación, solo para estado
- Animaciones decorativas al cargar la página. Nada de `animate-fade-in` en cada elemento
- Emojis en texto de la interfaz

---

## Tokens de color

Definidos como propiedades personalizadas de CSS en `src/styles/index.css`:

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

Uso: `text-[--color-text-secondary]` o `bg-[--color-bg-subtle]`. No usar colores arbitrarios de Tailwind fuera de estos tokens.

## Tipografía

**Fuente:** Inter (fallback del sistema: -apple-system, sans-serif)

| Uso | Clase | Tamaño |
|-----|-------|--------|
| Título de página | `text-2xl font-semibold` | 24px |
| Título de sección | `text-lg font-semibold` | 18px |
| Título de tarjeta | `text-base font-medium` | 16px |
| Cuerpo | `text-sm` | 14px |
| Caption / metadatos | `text-xs text-[--color-text-secondary]` | 12px |

- Nada de `text-3xl` o mayor para títulos de página. Mantenerlo sobrio
- Nada de `font-bold` — usar `font-semibold` para encabezados, `font-medium` para énfasis
- Interlineado: el de Tailwind por defecto (`leading-normal`)

## Espaciado

Usar la escala por defecto de Tailwind de forma consistente:

| Contexto | Valor |
|---------|-------|
| Padding de página | `p-6` (24px) |
| Espacio entre secciones | `space-y-6` (24px) |
| Padding de tarjeta | `p-5` (20px) |
| Entre elementos dentro de una tarjeta | `space-y-3` (12px) |
| Entre elementos en línea | `gap-3` (12px) |
| Entre campos de formulario | `space-y-4` (16px) |

## Radio de borde

| Elemento | Valor |
|---------|-------|
| Tarjetas, paneles | `rounded-lg` (8px) |
| Botones | `rounded-md` (6px) |
| Inputs | `rounded-md` (6px) |
| Badges | `rounded-full` (solo badges) |
| Avatares | `rounded-full` |

Nada de `rounded-xl`, `rounded-2xl` ni `rounded-3xl` en ningún sitio.

## Sombras

| Elemento | Valor |
|---------|-------|
| Tarjetas | `shadow-sm` o `border border-[--color-border]` (no ambas) |
| Dropdowns, modales | `shadow-md` |
| Todo lo demás | Sin sombra |

Preferir `border` sobre `shadow` para separar tarjetas. Sombra solo cuando importa la elevación (dropdowns, modales).

## Iconos

Lucide React. Tamaño `w-4 h-4` (16px) en línea, `w-5 h-5` (20px) independientes.

- Los iconos son `text-[--color-text-secondary]` por defecto
- Los iconos activos/primarios son `text-[--color-primary]`
- Sin círculos de fondo coloreado alrededor de los iconos (nada del patrón `bg-blue-50 rounded-full p-2`)
- Los iconos acompañan al texto, no lo sustituyen

---

## Transiciones e interacciones

Ver `motion-system.md` para las curvas de tiempo y easing. Estas son las reglas:

1. **Sin blur.** Nunca. Ni en transiciones, ni en modales, ni en overlays, ni en backdrops.
2. **Morph desde el trigger.** Todo lo que se abre (modal, panel, chat, popover) se transforma
   visualmente desde el elemento que lo abrió. Usar `layoutId` de Framer Motion.
   - Card de lista -> fullscreen: morph con layoutId
   - Pill del buddy -> card de chat: morph con layoutId
   - Botón -> panel expandido: morph con layoutId
   - NUNCA: modal centrado que aparece de la nada con backdrop
3. **Opacity + scale para entradas.** `initial={{ opacity: 0, scale: 0.97 }}` es el patrón
   base. NO blur, NO translateY grande, NO rotate.
4. **Secuencial.** Los elementos entran uno después de otro. El siguiente espera a que el
   anterior termine. `delay` suficiente para que no se solapen.
5. **Chevrones, no flechas.** Los iconos de navegación son chevrones (`<` / `>`), no flechas
   (`←` / `→`). Coherente en toda la app.
6. **Sin decoración de carga.** No spinners, no "Cargando...", no barras de progreso
   genéricas. Si hay espera, mostrar el esqueleto del contenido (shimmer) o pasos con nombre.

### Anti-patrones de transición (NO HACER)

- `backdrop-blur-sm` o cualquier blur en scrim/overlay
- Modal que aparece centrado sin conexión visual con su trigger
- `animate-spin` como indicador de carga
- Fade-in en el load de la página (animar lo que ya estaba ahí)
- Elementos que entran todos a la vez (sin stagger)
- Transición de salida más larga que la de entrada

---

## Patrones de componente

### Card

```tsx
<div className="border border-[--color-border] rounded-lg p-5">
  <h3 className="text-base font-medium text-[--color-text]">Title</h3>
  <p className="text-sm text-[--color-text-secondary] mt-1">Description</p>
</div>
```

Sin sombra. Solo border. Sin fondos degradados.

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

### Badge (solo estado)

```tsx
// Skill levels
<span className="text-xs font-medium px-2 py-0.5 rounded-full bg-green-50 text-green-700">High</span>
<span className="text-xs font-medium px-2 py-0.5 rounded-full bg-amber-50 text-amber-700">Medium</span>
<span className="text-xs font-medium px-2 py-0.5 rounded-full bg-red-50 text-red-700">Low</span>

// Content status
<span className="text-xs font-medium px-2 py-0.5 rounded-full bg-[--color-bg-muted] text-[--color-text-secondary]">Draft</span>
<span className="text-xs font-medium px-2 py-0.5 rounded-full bg-green-50 text-green-700">Published</span>
```

Los badges son para estado. No para decorar cada métrica.

### Skeleton (carga)

```tsx
<div className="space-y-3">
  <ShimmerSkeleton className="h-4 w-1/3" />
  <ShimmerSkeleton className="h-4 w-full" />
  <ShimmerSkeleton className="h-4 w-2/3" />
</div>
```

La forma del skeleton debe coincidir con el contenido que sustituye. Sin spinners genéricos.

`ShimmerSkeleton` (`components/ui/ShimmerSkeleton.tsx`) es el que hay que usar en código nuevo: un
barrido shimmer basado en transform en lugar de `animate-pulse`. Bajo `prefers-reduced-motion`
elimina el barrido por completo y renderiza un bloque estático apagado — una animación más lenta no
es la degradación accesible, ninguna animación lo es.

El `components/ui/Skeleton.tsx` más antiguo sigue existiendo y sigue usando `animate-pulse`. Se
dejó **deliberadamente** sin cambiar: se re-exporta como `SkeletonText` / `SkeletonCard` /
`SkeletonRow` en las páginas de v1, así que editarlo habría sido un cambio visible de v1 con el flag
de v2 apagado. Déjalo tal cual; usa `ShimmerSkeleton` en todo lo nuevo.

### Empty state

```tsx
<div className="text-center py-12">
  <p className="text-sm text-[--color-text-secondary]">No courses assigned yet</p>
  <button className="mt-3 text-sm text-[--color-primary] hover:underline">
    Ask your admin to assign one
  </button>
</div>
```

Centrado, minimal. Una línea de explicación + una acción si aplica. Sin ilustraciones grandes ni iconos decorativos.

### Progress bar

```tsx
<div className="h-1.5 bg-[--color-bg-muted] rounded-full overflow-hidden">
  <div className="h-full bg-[--color-primary] rounded-full" style={{ width: '40%' }} />
</div>
```

Fina (`h-1.5`), no gruesa. El color coincide con el primario.

### Celda de la matriz de skills

```tsx
// In admin skills matrix table
<td className="px-3 py-2">
  <span className="inline-block w-3 h-3 rounded-full bg-[--color-skill-high]" />
</td>
```

Un punto de color pequeño. No un fondo de celda completo coloreado.

---

## Layout

### Página

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

- Ancho: `w-60` expandido, `w-16` colapsado (solo iconos)
- Fondo: `bg-[--color-bg]` con borde derecho `border-r border-[--color-border]`
- Elementos de navegación: `text-sm`, activo = `bg-[--color-bg-muted] text-[--color-text] font-medium`, inactivo = `text-[--color-text-secondary]`
- Sin fondos coloreados para elementos activos. Solo un resaltado sutil

### Responsive

- Escritorio: sidebar + contenido
- Tablet: sidebar colapsado (iconos) + contenido
- Móvil: sin sidebar, menú hamburguesa. Contenido a ancho completo con `p-4`

---

## Motion & Animations

Ver [`motion-system.md`](/docs/motion-system) para la especificación completa de animación — curvas de easing, tiempos, patrones (modales morph, transiciones con blur, listas escalonadas, micro-interacciones).

---

## Lo que este sistema NO define

- Modo oscuro (no planificado)
- Páginas de marketing (esto es solo para la app)
</content>
