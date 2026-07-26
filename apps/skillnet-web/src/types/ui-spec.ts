// UISpec — the canonical render IR (v2 dynamic courses, §5.2 / §5.3).
//
// The LLM never emits HTML: it emits a dialect that the backend parses and
// validates into this JSON. The browser only ever receives already-validated
// specs, so these types describe a *contract*, not user input.
//
// The component list is FROZEN (§5.3). Adding a type here without adding it to
// `src/render/kit.py` on the backend is a bug on both sides.

import type { ExerciseType } from './index'

/** Contract version string carried by every spec. */
export const UI_SPEC_VERSION = 'skillnet-ui/1'

/** Contract limits from §5.2 rule 4. Enforced by the backend; the renderer only guards against runaway specs. */
export const MAX_SPEC_COMPONENTS = 12
export const MAX_ROOT_CHILDREN = 5

/** `ui_format` enum — mirrors `UiFormat` in `src/models/node_render.py`. */
export type UiFormat = 'explanation' | 'simulation' | 'exercise' | 'chart' | 'mixed'

/** Bloom taxonomy levels — mirrors `BLOOM_LEVELS` in `src/models/node_attempt.py`. */
export type BloomLevel = 'remember' | 'understand' | 'apply' | 'analyze' | 'evaluate' | 'create'

export type StackGap = 'sm' | 'md' | 'lg'
export type TextVariant = 'body' | 'lead' | 'caption'
export type CalloutTone = 'info' | 'warn' | 'success'
export type ChartKind = 'bar' | 'line'

/** The 10 component names of the SkillNet UI Kit. `Markdown` is `fallback_seed` only. */
export type UiComponentType =
  | 'Stack'
  | 'TextContent'
  | 'Card'
  | 'Callout'
  | 'StepSequence'
  | 'Table'
  | 'CodeBlock'
  | 'Chart'
  | 'QuizItem'
  | 'Markdown'

// ── Per-component props ──────────────────────────────────────
// `children` is a sibling of `props` in the IR (§5.2), not a prop, because it
// carries *ids* and the renderer — not the block — resolves them.
//
// Every prop below is REQUIRED, because every `value_props` entry of
// `src/render/kit.py` is: `Component._validate_against_kit` emits
// "missing prop 'x'" for any declared prop that is absent. There are no
// optional props in the kit — `gap`, `variant`, `tone` and `options` all have
// to be written out, `options` as `[]` when the item type takes none.

export interface StackProps {
  gap: StackGap
}

export interface TextContentProps {
  text: string
  variant: TextVariant
}

export interface CardPropsSpec {
  title: string
}

export interface CalloutProps {
  tone: CalloutTone
  text: string
}

export interface StepSequenceProps {
  title: string
  steps: string[]
}

export interface TableProps {
  headers: string[]
  rows: string[][]
}

export interface CodeBlockProps {
  language: string
  code: string
}

export interface ChartProps {
  kind: ChartKind
  title: string
  labels: string[]
  values: number[]
}

/** No correct answer and no explanation — those live in `answer_key`, server-side (§5.2 rule 5). */
export interface QuizItemProps {
  item_id: string
  item_type: ExerciseType
  bloom_level: BloomLevel
  question: string
  /** `[]` when the item type takes no options; never absent (kit: "Opciones; [] si no aplica"). */
  options: string[]
}

export interface MarkdownProps {
  content: string
}

// ── Discriminated component union ────────────────────────────

interface UiComponentBase<T extends UiComponentType, P> {
  /** `[A-Za-z_][A-Za-z0-9_]*` — the dialect's `ident` production (§5.4). Never kebab-case. */
  id: string
  type: T
  props: P
  /**
   * The backend always serializes `children` (`Component.children` defaults to
   * `[]`), and rejects a non-empty array on anything but a container — "X takes
   * no children". So it is present and empty here, not absent.
   */
  children?: never[]
}

interface UiContainerBase<T extends UiComponentType, P>
  extends Omit<UiComponentBase<T, P>, 'children'> {
  /** Ids of child components. Forward references are legal (§5.2 rule 2). */
  children?: string[]
}

export type StackComponent = UiContainerBase<'Stack', StackProps>
export type CardComponent = UiContainerBase<'Card', CardPropsSpec>
export type TextContentComponent = UiComponentBase<'TextContent', TextContentProps>
export type CalloutComponent = UiComponentBase<'Callout', CalloutProps>
export type StepSequenceComponent = UiComponentBase<'StepSequence', StepSequenceProps>
export type TableComponent = UiComponentBase<'Table', TableProps>
export type CodeBlockComponent = UiComponentBase<'CodeBlock', CodeBlockProps>
export type ChartComponent = UiComponentBase<'Chart', ChartProps>
export type QuizItemComponent = UiComponentBase<'QuizItem', QuizItemProps>
export type MarkdownComponent = UiComponentBase<'Markdown', MarkdownProps>

export type UiComponent =
  | StackComponent
  | TextContentComponent
  | CardComponent
  | CalloutComponent
  | StepSequenceComponent
  | TableComponent
  | CodeBlockComponent
  | ChartComponent
  | QuizItemComponent
  | MarkdownComponent

/**
 * Loose shape the renderer actually works with. A spec that reached the browser
 * was validated by the backend, but a mismatched deploy (new kit entry on the
 * server, old bundle in the tab) must degrade, never crash — so the dispatch
 * narrows from this, not from `UiComponent`.
 */
export interface RawUiComponent {
  id: string
  type: string
  props?: Record<string, unknown>
  children?: string[]
}

export interface UiSpec {
  version: string
  format: UiFormat
  /** Id of the root component. Must be a `Stack` or a `Card` (§5.2 rule 1). */
  root: string
  components: UiComponent[]
}

// ── Runtime answer contract for the autonomous QuizItemBlock ──
// `POST /nodes/{node_id}/answer` (§11.3). Lives here rather than in
// `src/types/index.ts` because `QuizItemBlock` is the only consumer in B6 and
// `src/api/nodes.ts` (B9) owns the query hooks.

/** Type-specific answer payloads accepted by `POST /nodes/{node_id}/answer`. */
export type NodeAnswerPayload =
  | { selected: number }
  | { answer: boolean }
  | { answers: string[] }
  | { response: string }

export interface NodeAnswerRequest {
  render_id: string
  item_id: string
  answer: NodeAnswerPayload
  /**
   * INFORMATIVE ONLY — the server must not trust this number (§7.4, §11.3).
   *
   * It decides whether the correct answer is revealed (`correct_answer` below is
   * populated once the hint quota is spent), so a value the client chooses cannot
   * govern it: anybody can POST `hints_used: 3` and be handed the answer without
   * having asked for a single hint. The count of record is
   * `node_attempts.hints_used` for `(user_id, node_id, item_id)`, which only
   * `POST /nodes/{id}/hint` increments. B5/B9 must derive the number server-side
   * and treat this field as telemetry (or drop it from the contract).
   *
   * `QuizItemBlock` grants no hints, so it always reports `0`.
   */
  hints_used: number
  latency_ms: number
}

export interface NodeAttemptResult {
  score: number
  passed: boolean
  feedback: string
  /**
   * Only present once the item is passed or the hint quota is spent. "Spent" is
   * counted from `node_attempts.hints_used` on the server, never from the
   * `hints_used` this client sent — see `NodeAnswerRequest.hints_used`.
   */
  correct_answer: Record<string, unknown> | null
  mastery: number
  state: string
  consecutive_correct: number
  consecutive_failed: number
  next: 'retry' | 'next_item' | 'next_node'
}
