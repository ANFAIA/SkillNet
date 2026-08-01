# Phase 2b integration — DragOrder, HotspotImage, StepByStepReveal

Code to add to shared files after the phase 2a agent finishes.

---

## 1. `schemas.ts`

### Add prop schemas (after `markdownProps`):

```ts
export const dragOrderProps = z.object({
  instruction: z.string().describe('Enunciado de la tarea de ordenar'),
  items: z.array(z.string()).describe('Elementos a ordenar (desordenados)'),
  correctOrder: z.array(z.string()).describe('Secuencia correcta'),
})

export const hotspotImageProps = z.object({
  imageUrl: z.string().describe('URL de la imagen'),
  alt: z.string().describe('Texto alternativo'),
  hotspots: z.array(z.array(z.string())).describe('Puntos: [[x, y, label, detail], ...]'),
})

export const stepByStepRevealProps = z.object({
  title: z.string().describe('Titulo del bloque'),
  steps: z.array(z.array(z.string())).describe('Pasos: [[enunciado, explicacion], ...]'),
})
```

### Add to `KIT_COMPONENT_NAMES` array:

```ts
export const KIT_COMPONENT_NAMES = [
  'Stack',
  'TextContent',
  'Card',
  'Callout',
  'StepSequence',
  'Table',
  'CodeBlock',
  'Chart',
  'QuizItem',
  'Markdown',
  // phase 2a components here...
  'DragOrder',
  'HotspotImage',
  'StepByStepReveal',
] as const
```

### Add to `KIT_DESCRIPTIONS`:

```ts
DragOrder: 'Reordenar arrastrando',
HotspotImage: 'Imagen con zonas interactivas',
StepByStepReveal: 'Revelacion progresiva de pasos',
```

### Add to `KIT_PROP_SCHEMAS`:

```ts
DragOrder: dragOrderProps,
HotspotImage: hotspotImageProps,
StepByStepReveal: stepByStepRevealProps,
```

---

## 2. `coerce.ts`

### Add `readHotspots` function:

```ts
import type { Hotspot } from '../blocks/HotspotImageBlock'

/** Parses hotspot matrix: each row is [x, y, label, detail] with x,y as number strings. */
export function readHotspots(value: unknown): Hotspot[] {
  if (!Array.isArray(value)) return []
  return value
    .filter((entry) => Array.isArray(entry) && entry.length >= 4)
    .map((entry) => ({
      x: clampPct(Number(entry[0])),
      y: clampPct(Number(entry[1])),
      label: typeof entry[2] === 'string' ? entry[2] : String(entry[2] ?? ''),
      detail: typeof entry[3] === 'string' ? entry[3] : String(entry[3] ?? ''),
    }))
}

function clampPct(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, value))
}

/** Parses step matrix: each row is [statement, explanation]. */
export function readStepPairs(value: unknown): Array<{ statement: string; explanation: string }> {
  if (!Array.isArray(value)) return []
  return value
    .filter((entry) => Array.isArray(entry) && entry.length >= 2)
    .map((entry) => ({
      statement: typeof entry[0] === 'string' ? entry[0] : String(entry[0] ?? ''),
      explanation: typeof entry[1] === 'string' ? entry[1] : String(entry[1] ?? ''),
    }))
}
```

---

## 3. `library.tsx`

### Add imports:

```ts
import {
  DragOrderBlock,
  HotspotImageBlock,
  StepByStepRevealBlock,
} from '../blocks'
import {
  readHotspots,
  readStepPairs,
} from './coerce'
import {
  dragOrderProps,
  hotspotImageProps,
  stepByStepRevealProps,
} from './schemas'
```

### Add component definitions (before `skillnetLibrary`):

```ts
const DragOrder = defineComponent({
  name: 'DragOrder',
  description: KIT_DESCRIPTIONS.DragOrder,
  props: dragOrderProps,
  component: ({ props }: ComponentRenderProps<{ instruction: string; items: string[]; correctOrder: string[] }>) => (
    <DragOrderBlock
      instruction={readString(props.instruction)}
      items={readStringArray(props.items)}
      correctOrder={readStringArray(props.correctOrder)}
    />
  ),
})

const HotspotImage = defineComponent({
  name: 'HotspotImage',
  description: KIT_DESCRIPTIONS.HotspotImage,
  props: hotspotImageProps,
  component: ({ props }: ComponentRenderProps<{ imageUrl: string; alt: string; hotspots: string[][] }>) => (
    <HotspotImageBlock
      imageUrl={readString(props.imageUrl)}
      alt={readString(props.alt)}
      hotspots={readHotspots(props.hotspots)}
    />
  ),
})

const StepByStepReveal = defineComponent({
  name: 'StepByStepReveal',
  description: KIT_DESCRIPTIONS.StepByStepReveal,
  props: stepByStepRevealProps,
  component: ({ props }: ComponentRenderProps<{ title: string; steps: string[][] }>) => (
    <StepByStepRevealBlock
      title={readString(props.title)}
      steps={readStepPairs(props.steps)}
    />
  ),
})
```

### Add to `createLibrary` components array:

```ts
components: [
  // ...existing...
  DragOrder,
  HotspotImage,
  StepByStepReveal,
],
```

---

## 4. `blocks/index.ts`

### Add exports:

```ts
export { DragOrderBlock } from './DragOrderBlock'
export type { DragOrderBlockProps } from './DragOrderBlock'

export { HotspotImageBlock } from './HotspotImageBlock'
export type { HotspotImageBlockProps } from './HotspotImageBlock'

export { StepByStepRevealBlock } from './StepByStepRevealBlock'
export type { StepByStepRevealBlockProps } from './StepByStepRevealBlock'
```

---

## 5. Backend `kit.py`

### Add to `UI_KIT` components tuple (after `Markdown`):

```python
ComponentSpec(
    name="DragOrder",
    purpose="Reordenar arrastrando",
    props=(
        PropSpec("instruction", PropKind.STRING, "Enunciado de la tarea de ordenar"),
        PropSpec("items", PropKind.STRING_LIST, "Elementos a ordenar (desordenados)"),
        PropSpec("correctOrder", PropKind.STRING_LIST, "Secuencia correcta"),
    ),
),
ComponentSpec(
    name="HotspotImage",
    purpose="Imagen con zonas interactivas",
    props=(
        PropSpec("imageUrl", PropKind.STRING, "URL de la imagen"),
        PropSpec("alt", PropKind.STRING, "Texto alternativo"),
        PropSpec("hotspots", PropKind.STRING_MATRIX, "Puntos: [[x, y, label, detail], ...]"),
    ),
),
ComponentSpec(
    name="StepByStepReveal",
    purpose="Revelacion progresiva de pasos",
    props=(
        PropSpec("title", PropKind.STRING, "Titulo del bloque"),
        PropSpec("steps", PropKind.STRING_MATRIX, "Pasos: [[enunciado, explicacion], ...]"),
    ),
),
```
