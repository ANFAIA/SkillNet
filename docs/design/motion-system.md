# Motion System

> Sistema de animaciones para SkillNet. El objetivo es que la app se sienta como una app nativa de iOS — transiciones fluidas, elementos que se transforman unos en otros, feedback fisico al interactuar. No como una web que carga paginas, sino como una app que fluye entre estados.

**Libreria:** Framer Motion (ya integrada). No migrar a GSAP — `layoutId` de Framer Motion implementa la misma tecnica FLIP de forma nativa en React.

---

## Principios

1. **Opacity y scale, nunca blur.** Los elementos entran/salen con opacity (y opcionalmente
   scale). NUNCA blur ni backdrop-blur — ni en transiciones, ni en modales, ni en overlays.
   Blur esta prohibido en toda la app.
2. **Morph, no appear.** Cuando un elemento se convierte en otro (card -> fullscreen, pill ->
   panel, word -> popover), debe transformarse visualmente desde el trigger. Nada aparece de
   la nada. Usa `layoutId` de Framer Motion para conectar el estado colapsado con el expandido.
3. **Overshoot, no ease-in-out.** Las curvas de easing sobrepasan ligeramente el destino y
   vuelven. Nunca usar `ease`, `ease-in-out` o `linear`.
4. **Feedback rapido, estructura lenta.** Los cambios de color/estado son instantaneos (125ms).
   Los cambios de layout/posicion son lentos y fluidos (500-700ms).
5. **Spring over duration.** Preferir springs de Framer Motion sobre duraciones fijas cuando
   sea posible. Los springs no tienen duracion fija — terminan cuando la fisica lo dicta.
6. **Secuencial, no simultaneo.** Los elementos entran UNO DESPUES DE OTRO, no todos a la vez.
   Cada elemento espera a que la animacion anterior termine antes de empezar la suya. En
   secuencias de entrada (stagger), el delay entre elementos es suficiente para que no se
   solapen.
7. **Todo debe fluir.** De paso a paso, de nodo a nodo, de curso a leccion — nunca un corte.
   El usuario no debe percibir "cambio de pagina". Es una app que fluye entre estados.

---

## Curvas de easing

Definidas como constantes reutilizables. Nunca hardcodear valores inline.

```typescript
// src/lib/motion.ts

// ── Curvas base ──────────────────────────────────────────────
/** Decelerate suave. Uso general para entradas y transiciones. */
export const ease = {
  /** Curva firma — decelerate suave, aterrizaje limpio */
  base:        [0.38, 0.49, 0, 1]       as const,
  /** Bounce sutil — botones hover, scale interactivo */
  bounce:      [0.38, 0.49, 0, 1.16]    as const,
  /** Bounce medio — border-radius morphs */
  bounceMid:   [0.38, 0.49, 0, 1.5]     as const,
  /** Bounce fuerte — expansion de padding, efectos playful */
  bounceHard:  [0.38, 0.49, 0, 2]       as const,
  /** Snappy — paneles que entran (push-in) */
  snapIn:      [0.1, 0.8, 0, 1]         as const,
  /** Exit rapido — paneles que salen (push-out) */
  snapOut:     [0.1, 0, 0.7, 1]         as const,
  /** Morph de bordes — border-radius en modales */
  morph:       [0.56, 0.27, 0, 1]       as const,
} as const;
```

### Cuando usar cada curva

| Curva | Uso | Ejemplo |
|-------|-----|---------|
| `ease.base` | Default para todo | Page transitions, modal open, list entry |
| `ease.bounce` | Hover/press interactivo | Botones scale, cards hover |
| `ease.bounceMid` | Cambios de forma | Border-radius de pills, toggles |
| `ease.bounceHard` | Expansion juguetona | Padding crece al hover, chips |
| `ease.snapIn` | Paneles que entran | Sidebar push, sub-section enter |
| `ease.snapOut` | Paneles que salen | Sidebar dismiss, sub-section exit |
| `ease.morph` | Transformacion de forma | Modal pill -> fullscreen |

---

## Timing

```typescript
// src/lib/motion.ts

export const duration = {
  /** Feedback inmediato — color, background, icon state */
  instant:   0.125,
  /** Transicion rapida — tooltips, dropdowns, focus rings */
  fast:      0.2,
  /** Blur/fade de contenido */
  normal:    0.3,
  /** Page transitions, list stagger */
  medium:    0.5,
  /** Modal morph, shared element transitions */
  slow:      0.7,
  /** Border-radius morph en mobile (fullscreen modal) */
  morphSlow: 1.0,
} as const;
```

### Regla de timing dual

Los cambios **decorativos** (color, background, opacity de iconos) usan `instant` o `fast`.
Los cambios **estructurales** (layout, posicion, tamanio, border-radius) usan `medium` o `slow`.

Nunca mezclar: un boton cambia de color en 125ms pero su scale es 300ms.

---

## Springs

Para interacciones fisicas, usar springs en lugar de duraciones fijas:

```typescript
// src/lib/motion.ts

export const spring = {
  /** Default — responsive, settling rapido */
  default:  { type: "spring", stiffness: 400, damping: 30 } as const,
  /** Bouncy — para elementos interactivos playful */
  bouncy:   { type: "spring", stiffness: 500, damping: 25 } as const,
  /** Stiff — para snapping y posicionamiento preciso */
  stiff:    { type: "spring", stiffness: 500, damping: 35, mass: 0.5 } as const,
  /** Gentle — para layout shifts grandes */
  gentle:   { type: "spring", stiffness: 200, damping: 25 } as const,
} as const;
```

---

## Patrones de animacion

### 1. Page transitions

Cada cambio de ruta anima con blur + fade + scale sutil.

```tsx
// En el layout que wrappea <Outlet />
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

**Antes (lo que teniamos):** `opacity: 0, y: 8` con `duration: 0.2`
**Ahora:** blur + scale crea profundidad, no solo un fade plano.

---

### 2. Morph modals (shared element transitions)

El patron mas importante. Un elemento en una lista se transforma visualmente en el modal/detail view.

```tsx
// En la lista — el elemento origen
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

// El modal — el elemento destino (mismos layoutId)
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
      {/* Modal que morfa desde la card */}
      <motion.div
        layoutId={`card-${selected.id}`}
        className="fixed inset-4 md:inset-12 bg-white rounded-lg p-6 overflow-auto"
        transition={{ layout: { duration: duration.slow, ease: ease.base } }}
      >
        <motion.h3 layoutId={`title-${selected.id}`}>{selected.name}</motion.h3>
        <motion.p layoutId={`desc-${selected.id}`}>{selected.description}</motion.p>
        {/* Contenido extra del modal con blur-in */}
        <motion.div
          initial={{ opacity: 0, filter: "blur(8px)" }}
          animate={{ opacity: 1, filter: "blur(0px)" }}
          transition={{ delay: 0.2, duration: duration.normal, ease: ease.base }}
        >
          {/* contenido expandido */}
        </motion.div>
      </motion.div>
    </>
  )}
</AnimatePresence>
```

**Backdrop:** Solo `bg-black/10` (10% opacidad). Los backdrops pesados son de 2015. Combinar con `backdrop-blur-sm` para frosted glass sutil.

---

### 3. Staggered lists

Los items de listas aparecen secuencialmente con blur.

```tsx
// Contenedor
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
      {/* contenido */}
    </motion.li>
  ))}
</motion.ul>
```

**Stagger:** 0.06s entre items (rapido, no dramatico). Maximo 8-10 items animados — si hay mas, animar solo los visibles en viewport.

**Exit de items** (al borrar de lista):

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

Items salen hacia la izquierda con blur. No se desvanecen en su sitio.

---

### 4. Sub-section panels (push navigation)

Navegacion tipo iOS dentro de una seccion — panel entra desde la derecha.

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

**Asimetria enter/exit:** Enter es lento (400ms, snapIn). Exit es rapido (200ms, snapOut). Esto imita el iOS navigation controller.

---

### 5. Micro-interactions

#### Botones

```tsx
<motion.button
  whileHover={{ scale: 1.03 }}
  whileTap={{ scale: 0.97 }}
  transition={{ type: "spring", stiffness: 500, damping: 30 }}
>
  Accion
</motion.button>
```

- Hover: scale sutil (1.03), no exagerado
- Tap: squish (0.97) — feedback de presion
- Spring para que el retorno sea organico

#### Cards hover

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

#### Inputs focus

```css
/* CSS puro — no necesita Framer Motion */
input:focus {
  box-shadow: 0 0 0 3px var(--color-primary-subtle),
              0 1px 3px rgba(0,0,0,0.08);
  transition: box-shadow 0.3s cubic-bezier(0.38, 0.49, 0, 1);
}
```

#### Active nav indicator

```tsx
// Pill que sigue al item activo en el sidebar
<motion.div
  className="absolute left-0 bg-[--color-bg-muted] rounded-md"
  layoutId="nav-indicator"
  transition={spring.stiff}
  style={{ width: "100%", height: itemHeight }}
/>
```

Usa `layoutId` — la pill se mueve con spring physics entre items del nav.

---

### 6. Frosted glass surfaces

```css
/* Paneles translucidos tipo iOS */
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

Usar para: mobile bottom nav, modal backdrops, sticky headers, floating action bars.

---

### 7. Toasts / Notificaciones

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

Toasts entran desde arriba con spring (bounce sutil). Salen rapido sin bounce.

---

## Propiedades que se animan

Ordenadas por frecuencia de uso:

| Propiedad | Patron | Notas |
|-----------|--------|-------|
| `opacity` | 0 -> 1 (enter), 1 -> 0 (exit) | Siempre acompanado de blur |
| `filter: blur()` | 8-16px -> 0 (enter), 0 -> 16-32px (exit) | Primitiva de motion principal |
| `scale` | 0.96-0.98 -> 1 (enter), 1.02-1.03 (hover) | Siempre sutil |
| `x, y` | translate para slides y pushes | Y para vertical, X para push navigation |
| `borderRadius` | Morph de formas (card -> fullscreen) | Via `layout` prop automatico |
| `boxShadow` | Hover elevation | Transicion lenta (300ms) |
| `backgroundColor` | Estado activo/hover | Transicion rapida (125ms) |

### Propiedades que NO se animan

- `width` / `height` directamente — usar `layout` prop de Framer Motion
- `margin` / `padding` — excepto micro-interactions muy especificas
- `border-color` — cambio instantaneo, no transicionar
- `font-size` / `font-weight` — no animar tipografia

---

## GPU acceleration

```css
/* Aplicar a elementos que se animan frecuentemente */
a, button {
  will-change: transform;
}

/* Forzar compositing layer en elementos con backdrop-filter */
.glass-panel {
  transform: translateZ(0);
}
```

Framer Motion ya maneja `will-change` automaticamente en sus `motion.*` components. Solo anadir hints manuales para elementos CSS puros.

---

## Anti-patrones (NO hacer)

- `ease-in-out` o `linear` como easing — siempre custom curves con overshoot
- Fade sin blur — los fades planos se sienten "web", no "native"
- Duraciones uniformes — cada tipo de cambio tiene su propio timing
- Animar todo — solo animar cambios de estado significativos, no decoracion
- `animate-bounce` o `animate-pulse` de Tailwind — demasiado generic y loop infinito
- Delays largos (>300ms) — el usuario no debe esperar a la animacion
- Animar en page load — el contenido inicial aparece inmediatamente, sin stagger

---

## Archivo de presets

Todas las constantes de este documento se exportan desde `src/lib/motion.ts`. Importar desde ahi, nunca definir valores inline.

```typescript
// Uso en componentes
import { ease, duration, spring } from '@/lib/motion';

<motion.div
  transition={{ duration: duration.medium, ease: ease.base }}
/>
```

---

## Estado actual

### Ya hecho

- [x] `src/lib/motion.ts` — presets centralizados (ease, duration, spring, transition, variants)
- [x] `src/pages/dev/MotionDemo.tsx` — pagina de demo interactiva en `/dev/motion` con todos los patrones
- [x] Ruta `/dev/motion` registrada en `App.tsx`
- [x] Este documento

### Pagina de demo

En `/dev/motion` hay una pagina con demos interactivas de cada patron: page transitions, morph modals, staggered lists, push navigation, micro-interactions, wizard steps, sidebar overlay, content swap, y una comparacion antes/ahora. Usala como referencia visual de lo que se busca.

---

## Que queremos conseguir

La app ahora mismo se siente como una web: las paginas aparecen y desaparecen con un fade plano, los modales saltan de la nada, las listas aparecen de golpe. Queremos que se sienta como una app nativa — como cuando usas una app en el iPhone y todo fluye, las cosas se transforman unas en otras, hay profundidad en las transiciones, y los botones responden fisicamente cuando los tocas.

A continuacion se describe lo que queremos mejorar, en orden de importancia. Hay presets ya preparados en `src/lib/motion.ts` que se pueden usar directamente.

---

### 1. El sidebar y las transiciones entre paginas

Este es el cambio mas importante porque es lo que el usuario ve constantemente.

**Como funciona el layout:** La app tiene un diseno "L-frame" — el sidebar y el header son azules (un gradiente con textura, clase `frame-surface` en `index.css`) y el contenido principal es blanco con una esquina redondeada arriba a la izquierda (`rounded-tl-xl`). Es como si la zona blanca estuviera "encima" del marco azul.

**El efecto de la pill activa:** La pagina activa en el nav tiene un fondo blanco que se extiende hasta el borde derecho del sidebar, fundiendose con el blanco del main. No hay separacion — el blanco del nav y el blanco del contenido son uno solo. Esto crea la ilusion de que el contenido "entra" en el sidebar para marcar donde estas.

```
SIDEBAR (azul)  │  MAIN (blanco)
                │╭─────────────────
  Inicio        ││
  ■■■■■■■■■■■■■■██  ← el blanco se funde con el main
  Cursos        ││
  Skills        ││
                │╰─────────────────
```

**Que esta mal ahora:** En el AdminSidebar hay una pill animada con spring, pero tiene un gap al borde derecho (`right-4`) que rompe la fusion con el main. En el Sidebar del empleado ni siquiera hay pill animada — es un fondo estatico. Y cuando cambias de pagina, el contenido hace un fade plano que se siente a pagina web cargando.

**Lo que queremos:** Que al hacer click en un item del nav, la pill blanca se deslice suavemente al nuevo item (con spring, como un muelle), y que el contenido del main haga una transicion con blur y scale que se sienta fluida, como cambiar de tab en una app. El marco blanco del main nunca se mueve — solo cambia lo de dentro. La sensacion debe ser de "deslizar" entre secciones, no de "cargar" una pagina nueva.

**Archivos relevantes:** `Sidebar.tsx`, `AdminSidebar.tsx`, `AppLayout.tsx`, `AdminLayout.tsx`

---

### 2. Modales que se transforman en vez de aparecer

Ahora mismo hay varias interacciones donde se abren formularios o vistas de detalle de forma brusca. Un buen ejemplo es la pagina de Empleados (`Employees.tsx`):

- El boton "Agregar empleado" hace aparecer un formulario debajo sin ninguna animacion. Seria mucho mejor que el boton se transformara en el formulario — que creciera suavemente hasta convertirse en la Card del form. Y al cerrar, que se contraiga de vuelta al boton.

- Cuando haces click en un empleado de la lista, se reemplaza toda la pagina por el detalle del empleado. Se pierde completamente el contexto de donde venias. Seria mejor un modal que se abra desde la fila/card del empleado — que el elemento de la lista se transforme visualmente en el modal. Con un fondo sutil (no negro pesado, sino con un blur tipo cristal esmerilado). Y el contenido extra del modal (cursos asignados, etc.) que aparezca con blur una vez que el morph termina.

- El modal de restablecer contraseña usa un fondo negro al 40% sin blur — se ve antiguo. Deberia tener backdrop-blur.

Este patron de "morph modal" se aplica en muchos sitios de la app, no solo en Empleados. Es un patron general: siempre que algo se expanda a un detalle, deberia transformarse, no aparecer de la nada.

Hay una demo interactiva de este patron en `/dev/motion` seccion "Morph Modals".

**Archivos relevantes:** `Employees.tsx` como primer caso, pero el patron aplica en toda la app.

---

### 3. Listas que aparecen con ritmo

Las listas de empleados, cursos y contenido aparecen todas de golpe. Deberian aparecer item por item con un ligero desfase (stagger), cada uno entrando con un poquito de blur que se resuelve. No dramatico — rapido y sutil, para dar ritmo sin frenar al usuario.

Cuando se elimina un item, deberia salir deslizandose hacia la izquierda con blur, no desaparecer de golpe.

**Donde aplicar:** listas de empleados, cursos del admin, cursos del empleado, lecciones dentro de un curso.

---

### 4. Botones y cards que responden al toque

Los botones ahora solo cambian de color al hover. Deberian tener un ligero scale al hover (crecer un poquito) y un "squish" al hacer click (achicarse un poco, como si lo presionaras fisicamente). Spring physics para que el retorno sea organico, no lineal.

Las cards interactivas deberian elevarse sutilmente al hover (un poquito de sombra y scale).

Nada exagerado — micro-interactions, casi imperceptibles pero que sumadas hacen que la app se sienta viva.

---

### 5. Cambio de leccion en CourseView

Cuando el empleado cambia de leccion, el contenido hace un fade plano. Deberia hacer una transicion con blur. Y si es posible, que sea direccional: si vas a la leccion siguiente, el contenido sale hacia la izquierda y entra desde la derecha. Si vuelves atras, al reves.

**Archivos relevantes:** `CourseView.tsx`

---

### 6. Wizard de crear curso

El wizard de 5 pasos ya tiene slide direccional, pero sin blur y con un easing generico que se siente mecanico. Deberia usar los presets del motion system (blur en enter/exit, curva firma, y asimetria: entrar lento, salir rapido).

**Archivos relevantes:** `CreateCourse.tsx`

---

### 7. Sidebar mobile

El overlay del sidebar en movil usa un fondo negro al 50% (muy pesado) y el sidebar entra con un easing generico. Deberia usar backdrop-blur (cristal esmerilado sutil) y el sidebar deberia entrar con spring physics.

**Archivos relevantes:** `Sidebar.tsx`, `AdminSidebar.tsx`

---

### 8. Utilidades CSS

Anadir custom properties de easing a `index.css` para poder usarlas en CSS puro (no todo necesita Framer Motion). Tambien una clase `.glass-panel` para superficies con efecto cristal esmerilado (backdrop-blur), y `will-change: transform` en botones/links para GPU acceleration.

**Archivos relevantes:** `index.css`

---

## Research de motion design — hallazgos

Se hizo un analisis profundo de apps web de referencia que consiguen un feel nativo. A continuacion estan los hallazgos tecnicos que se usaron para definir los presets de este documento.

### Curvas de easing encontradas

Estas curvas son las que dan el feel "nativo" — todas son variantes de un decelerate agresivo con distintos grados de overshoot:

| Curva | Caracter | Uso tipico |
|---|---|---|
| `cubic-bezier(0.38, 0.49, 0, 1)` | Decelerate suave, aterrizaje limpio | Curva principal para todo |
| `cubic-bezier(0.38, 0.49, 0, 1.16)` | Overshoot sutil | Botones hover, scale interactivo |
| `cubic-bezier(0.38, 0.49, 0, 1.5)` | Overshoot medio | Border-radius morphs, toggles |
| `cubic-bezier(0.38, 0.49, 0, 2)` | Overshoot fuerte | Expansion de padding, bouncy |
| `cubic-bezier(0.1, 0.8, 0, 1)` | Snappy, rapido al principio | Paneles que entran (push-in) |
| `cubic-bezier(0.1, 0, 0.7, 1)` | Aceleracion para salidas | Paneles que salen (push-out) |
| `cubic-bezier(0.56, 0.27, 0, 1)` | Decelerate enfatizado | Morph de border-radius en modales |

**Clave:** Nunca se usa `ease`, `ease-in-out` o `linear`. Todo es custom con algun grado de overshoot.

### Patrones de animacion recurrentes

**Blur como primitiva:** Cada entrada/salida de elementos usa `filter: blur()` ademas de opacity. Los valores tipicos son blur 8-16px al entrar y 16-32px al salir. Esto crea un efecto de profundidad de campo, como cuando el ojo enfoca y desenfoca.

**Shared-element transitions (FLIP):** Los modales no aparecen de la nada — se transforman desde su elemento origen (un boton, una card, una fila de tabla). La tecnica FLIP (First, Last, Invert, Play) captura la posicion inicial, calcula la final, y anima entre ambas. En Framer Motion esto se hace con `layoutId`.

**Border-radius morphing:** Los modales en mobile van de una forma pill (border-radius 64px) a fullscreen (border-radius 0), animado en ~1s con easing `cubic-bezier(0.56, 0.27, 0, 1)`. Esto da el efecto de "sheet" de iOS.

**Frosted glass:** Superficies con `backdrop-filter: blur(24-64px) saturate(1.2)` y fondo semi-transparente. Los backdrops de modales son sutiles (10% negro, no 40-50%).

**Timing dual:** Los cambios de estado (color, background, iconos) son rapidos (~125ms). Los cambios estructurales (posicion, tamanio, layout) son lentos (~500-700ms). Esta diferencia crea la sensacion de que la app responde instantaneamente al input pero las transiciones son fluidas.

**Asimetria enter/exit:** Las entradas son mas lentas (~400ms) que las salidas (~200ms). Esto imita la navegacion de iOS donde empujar una vista es deliberado pero volver es rapido.

**Stagger con blur:** Los items de listas aparecen secuencialmente (~60ms entre items), cada uno con blur que se resuelve. Es rapido y sutil — no ralentiza la carga percibida.

### Propiedades animadas (por frecuencia)

1. `opacity` — siempre acompanado de blur
2. `filter: blur()` — la primitiva principal
3. `transform: scale()` — sutil, 0.96-0.98 al entrar, 1.02-1.03 al hover
4. `transform: translate()` — para slides y push navigation
5. `border-radius` — morph de formas
6. `box-shadow` — elevacion al hover
7. `background-color` — transicion rapida de estado
8. `backdrop-filter` — paneles translucidos

### Propiedades que NO se animan

- `width` / `height` directamente
- `margin` / `padding` (excepto micro-interactions)
- `border-color`
- `font-size` / `font-weight`

### Anti-patrones observados (lo que NO hacen las apps nativas)

- `ease-in-out` o `linear` como easing
- Fades planos sin blur
- Duraciones uniformes para todo
- `animate-bounce` o `animate-pulse` en loop
- Delays largos (>300ms) que hacen esperar al usuario
- Animaciones decorativas en page load

---

## Apendice: datos crudos del audit de apps de referencia

Datos extraidos de un analisis profundo de apps web con feel nativo. Usar como referencia tecnica al implementar.

### Keyframes CSS encontrados

```css
/* Entrada con blur — el patron mas usado */
@keyframes blur-in {
  from { filter: blur(32px); }
  to   { filter: blur(0); }
  /* 300ms, cubic-bezier(.37, .35, 0, 1) */
}

/* Salida con blur */
@keyframes blur-out {
  from { filter: blur(0); }
  to   { filter: blur(32px); }
  /* 500ms, cubic-bezier(.37, .35, 0, 1) */
}

/* Entrada general — blur + scale */
@keyframes general-in {
  from { opacity: 0; filter: blur(16px); transform: scale(0.96); }
  to   { opacity: 1; filter: blur(0);    transform: scale(1); }
}

/* Entrada intensa — blur fuerte + scale agresivo */
@keyframes general-in-2 {
  from { opacity: 0; filter: blur(32px); transform: scale(0.7); }
  to   { opacity: 1; filter: blur(0);    transform: scale(1); }
}

/* Modal mobile: pill -> fullscreen */
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

Estas son curvas de easing avanzadas definidas como paths SVG, usadas para animaciones FLIP y modales:

```
/* Curva principal para modales y transiciones FLIP */
M0,0 C0.308,0.19 0.107,0.633 0.288,0.866 0.382,0.987 0.656,1 1,1
/* Caracter: ease-out agresivo, alcanza 86% del recorrido al 29% del tiempo */

/* Modal open con bounce sutil al final */
M0,0 C0.249,-0.124 0.04,0.951 0.335,1 0.684,1.057 0.614,0.964 1,1

/* Modal close (reversa) */
M0,0 C0.28,0.08 0.10,0.55 0.28,0.78 0.38,0.95 0.64,1 1,1
```

### CSS transitions encontradas (por patron)

```css
/* Transiciones de transform con overshoot */
button.hover-scale    { transition: transform 0.3s cubic-bezier(0, 0, 0.5, 1); }
button.style-bounce   { transition: transform 0.3s cubic-bezier(0.38, 0.49, 0, 1.16); }
nav.floating-dock     { transition: transform 500ms cubic-bezier(0, 1, 0, 1); }

/* Border-radius morphs */
nav-button            { transition: border-radius 500ms cubic-bezier(0.38, 0.49, 0, 1.2); }
menu.mobile           { transition: border-radius 2000ms cubic-bezier(.56, .27, 0, 1); }
/* Nota: 2s para border-radius en mobile — extra lento, morph suave */

/* Multi-property button con bounce fuerte */
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

### GSAP stagger patterns (texto y listas)

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
/* Capturar estado inicial del elemento origen */
const state = Flip.getState(originElement);

/* Mover/transformar el elemento a su posicion final */
modalContainer.appendChild(originElement);

/* Animar desde el estado capturado al nuevo */
Flip.from(state, {
  targets: modalElement,
  duration: 0.7,
  scale: false,
  absolute: false,
  ease: CustomEase.create("custom",
    "M0,0 C0.308,0.19 0.107,0.633 0.288,0.866 0.382,0.987 0.656,1 1,1"),
});

/* En Framer Motion, esto se logra con layoutId — misma tecnica FLIP, API declarativa */
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
