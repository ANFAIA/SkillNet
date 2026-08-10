/**
 * The SkillNet UI Kit — prop schemas (§5.3).
 *
 * These zod objects are the frontend's declaration of the frozen catalogue: the
 * component names, the prop names, the closed enums, and — crucially — the
 * **positional order** of the dialect. `@openuidev/lang-core` builds its
 * positional-to-named mapping from `Object.keys(z.object({...}).properties)`,
 * so *the key order in each object below IS the argument order of the dialect*
 * (§5.4). Reordering a key silently reinterprets every generated program.
 *
 * The order mirrors `apps/skillnet-api/src/render/kit.py::UI_KIT`, which stays
 * the source of truth for the prompt and for validation. This file is the same
 * table expressed in the vendor's own vocabulary.
 *
 * ## What these schemas do and do not enforce
 *
 * MEASURED, and the reason the adapters in `library.tsx` still coerce every
 * prop: **OpenUI's parser does not evaluate zod.** `compileSchema()` keeps only
 * `{ name, required, defaultValue }` per prop, so the parser checks *arity* and
 * *presence* and nothing else. `Stack([a], "enorme")` and `TextContent(42, …)`
 * both parse with `meta.errors == []`. The enums and value types below are
 * therefore:
 *
 *   1. the contract, in one place, next to the names;
 *   2. the input to `library.prompt()` signatures (unused today — the Spanish
 *      prompt with the seven contract rules is generated in Python);
 *   3. the source of the TypeScript types the presentational blocks use.
 *
 * Enforcement happens in three other places: the backend Pydantic validator
 * (`src/render/spec.py`, all seven rules of §5.2), the structural gate
 * (`assertStaticOnly.ts`), and the per-prop coercion of `coerce.ts`.
 */

import { z } from 'zod'

// ── Closed enums ─────────────────────────────────────────────
// Exported as const arrays because the runtime coercion needs the members and
// the blocks need the union type. `z.enum()` is fed from them so a value can
// never be in one list and not the other.

export const STACK_GAPS = ['sm', 'md', 'lg'] as const
export const TEXT_VARIANTS = ['body', 'lead', 'caption'] as const
export const CALLOUT_TONES = ['info', 'warn', 'success'] as const
export const CHART_KINDS = ['bar', 'line'] as const
export const VOICE_STYLES = ['neutral', 'warm', 'formal'] as const

/** The six `exercise_type` values (§5.3). Same list as `ExerciseType` in `src/types/index.ts`. */
export const ITEM_TYPES = [
  'test',
  'true_false',
  'fill_blank',
  'order_steps',
  'practical_case',
  'dialogue',
] as const

/** Bloom taxonomy — mirrors `BLOOM_LEVELS` in `src/models/node_attempt.py`. */
export const BLOOM_LEVELS = [
  'remember',
  'understand',
  'apply',
  'analyze',
  'evaluate',
  'create',
] as const

export type StackGap = (typeof STACK_GAPS)[number]
export type TextVariant = (typeof TEXT_VARIANTS)[number]
export type CalloutTone = (typeof CALLOUT_TONES)[number]
export type ChartKind = (typeof CHART_KINDS)[number]
export type VoiceStyle = (typeof VOICE_STYLES)[number]
export type ItemType = (typeof ITEM_TYPES)[number]
export type BloomLevel = (typeof BLOOM_LEVELS)[number]

// ── Prop schemas, one per kit component ──────────────────────
// KEY ORDER = POSITIONAL ARGUMENT ORDER. See the header.
//
// `children` is `z.array(z.any())` rather than a component union: what arrives
// at render time is an array of already-resolved `ElementNode`s (or the empty
// array, for references that have not streamed in yet). Typing it as the union
// would be a lie the runtime does not honour.

export const stackProps = z.object({
  children: z.array(z.any()).describe('Ids de los bloques hijos, en orden'),
  gap: z.enum(STACK_GAPS).describe('Separacion vertical'),
})

export const textContentProps = z.object({
  text: z.string().describe('Texto plano o marcado inline'),
  variant: z.enum(TEXT_VARIANTS).describe('Rol del texto'),
})

export const cardProps = z.object({
  title: z.string().describe('Titulo del grupo'),
  children: z.array(z.any()).describe('Ids de los bloques agrupados'),
})

export const calloutProps = z.object({
  tone: z.enum(CALLOUT_TONES).describe('Intencion del aviso'),
  text: z.string().describe('Texto del aviso'),
})

export const stepSequenceProps = z.object({
  title: z.string().describe('Nombre del procedimiento'),
  steps: z.array(z.string()).describe('Un paso por elemento'),
})

export const tableProps = z.object({
  headers: z.array(z.string()).describe('Cabeceras de columna'),
  rows: z.array(z.array(z.string())).describe('Filas: array de arrays de texto'),
})

export const codeBlockProps = z.object({
  language: z.string().describe('Lenguaje, en minusculas'),
  code: z.string().describe('Codigo, con \\n para los saltos'),
})

export const chartProps = z.object({
  kind: z.enum(CHART_KINDS).describe('Tipo de grafico'),
  title: z.string().describe('Titulo del grafico'),
  labels: z.array(z.string()).describe('Etiqueta por valor'),
  values: z.array(z.number()).describe('Un numero por etiqueta'),
})

/**
 * No `correct` and no `explanation`: contract rule 5 (§5.2) keeps the answer key
 * server-side. Adding either here would put it in the prompt and in the program
 * text the browser receives.
 */
export const quizItemProps = z.object({
  item_id: z.string().describe('Id corto y unico dentro del spec'),
  item_type: z.enum(ITEM_TYPES).describe('Tipo de ejercicio'),
  bloom_level: z.enum(BLOOM_LEVELS).describe('Nivel cognitivo'),
  question: z.string().describe('Enunciado'),
  options: z.array(z.string()).describe('Opciones; [] si no aplica'),
})

export const beforeAfterProps = z.object({
  title: z.string().describe('Titulo de la comparacion'),
  beforeLabel: z.string().describe('Etiqueta del estado anterior'),
  beforeContent: z.string().describe('Contenido del estado anterior'),
  afterLabel: z.string().describe('Etiqueta del estado posterior'),
  afterContent: z.string().describe('Contenido del estado posterior'),
})

export const markdownProps = z.object({
  content: z.string().describe('Contenido de la leccion semilla'),
})

export const dragOrderProps = z.object({
  instruction: z.string().describe('Enunciado de la tarea de ordenar'),
  items: z.array(z.string()).describe('Elementos a ordenar (desordenados)'),
  correctOrder: z.array(z.string()).describe('Secuencia correcta'),
})

export const audioExplanationProps = z.object({
  text: z.string().describe('Texto que se leera en voz alta'),
  voice: z.enum(VOICE_STYLES).describe('Estilo de voz'),
})

export const pronunciationExerciseProps = z.object({
  targetText: z.string().describe('Texto objetivo para practicar'),
  language: z.string().describe('Codigo de idioma, p.ej. "es"'),
})

/** The frozen names, in the order of the §5.3 table. */
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
  'BeforeAfter',
  'Markdown',
  'DragOrder',
  'AudioExplanation',
  'PronunciationExercise',
] as const

export type KitComponentName = (typeof KIT_COMPONENT_NAMES)[number]

/**
 * The nine the model may emit. `Markdown` is reachable through `fallback_seed`
 * only (§5.3), so it is registered for rendering and absent from the prompt.
 */
export const LLM_COMPONENT_NAMES = KIT_COMPONENT_NAMES.filter(
  (name): name is Exclude<KitComponentName, 'Markdown'> => name !== 'Markdown',
)

/**
 * The `purpose` column of the §5.3 table, verbatim from `src/render/kit.py`.
 *
 * Kept here rather than inline in `library.tsx` because two consumers need it and
 * neither may own a second copy: the React library, and `prompt-catalog.mjs`,
 * which the build step imports from Node to generate the prompt artefacts the
 * Python backend reads. `catalog-drift.test.ts` fails if a string diverges from
 * the backend's own catalogue.
 */
export const KIT_DESCRIPTIONS = {
  Stack: 'Contenedor vertical. Envuelve la pantalla entera; siempre es el root',
  TextContent: 'Prosa breve: el gancho inicial o una transicion. No vuelques aqui el contenido',
  Card: 'Agrupa bajo un titulo propio un caso practico o un ejemplo cerrado',
  Callout: 'Una regla critica o excepcion que no se puede pasar por alto. Uno por pantalla',
  StepSequence: 'Pasos en orden que se entienden solos. Prefierelo con 3-7 pasos cortos',
  Table: 'Varios elementos comparados por varios atributos. Si solo contrastas DOS estados usa BeforeAfter',
  CodeBlock: 'Fragmento de codigo de ejemplo',
  Chart: 'Cifras comparables entre categorias. Solo si las cifras estan en la fuente',
  QuizItem: 'Pregunta de evaluacion sobre un caso concreto',
  BeforeAfter: 'Contrasta exactamente DOS estados: correcto frente a incorrecto, antes frente a despues. Prefierelo a Table cuando la comparacion es de dos',
  Markdown: 'Solo para fallback_seed; el modelo no puede emitirlo',
  DragOrder: 'Evaluar reordenando pasos o prioridades arrastrando',
  AudioExplanation: 'Texto leido en voz alta con resaltado de palabras',
  PronunciationExercise: 'Escuchar y practicar la pronunciacion de un termino',
} satisfies Record<KitComponentName, string>

/** Name → prop schema, so a consumer can walk the catalogue without React. */
export const KIT_PROP_SCHEMAS = {
  Stack: stackProps,
  TextContent: textContentProps,
  Card: cardProps,
  Callout: calloutProps,
  StepSequence: stepSequenceProps,
  Table: tableProps,
  CodeBlock: codeBlockProps,
  Chart: chartProps,
  QuizItem: quizItemProps,
  BeforeAfter: beforeAfterProps,
  Markdown: markdownProps,
  DragOrder: dragOrderProps,
  AudioExplanation: audioExplanationProps,
  PronunciationExercise: pronunciationExerciseProps,
} satisfies Record<KitComponentName, z.ZodObject>

/**
 * The two container components (contract rule 1, §5.2: `root` must be one of
 * them). `Stack` is the library root, so the parser resolves a bare program
 * against it.
 */
export const CONTAINER_NAMES = ['Stack', 'Card'] as const

/** Contract rule 4 (§5.2), the only one of the seven checkable from a ParseResult. */
export const MAX_COMPONENTS = 12

/**
 * Contract rule 4's painting half, and the budget the hand-written renderer used to
 * carry as `MAX_RENDERED`.
 *
 * `statementCount` counts *components*, and the flat list is a DAG: the same id may
 * appear several times inside one `children` array and inside several parents, while
 * only the ROOT fan-out is capped. MEASURED with lang-core 0.2.10 — twelve components
 * of the shape `a{i} = Card("n{i}", [a{i+1} x W])` expand to 1 025 elements from 334
 * bytes and 29 526 from 370, all with `statementCount === 12`, so the check above sees
 * nothing wrong. `src/render/spec.py` enforces the same cap server-side and is the one
 * that matters (at W=8 the parse itself dies of a V8 heap OOM, which no `try/catch` can
 * intercept, so by the time a ParseResult exists the tab is already safe or already
 * gone). This is the fail-closed half, for text that reached the browser some other
 * way. The ten valid fixtures expand to 5 elements at most.
 */
export const MAX_RENDERED_ELEMENTS = 64
