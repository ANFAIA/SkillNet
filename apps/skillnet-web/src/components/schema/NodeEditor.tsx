import type { NodeCriticality } from '../../types'
import type { UiFormat } from '../../types/node-render'

/**
 * One node of the draft schema, edited locally until the creator saves.
 *
 * `key` exists because a brand-new node has no `id` until the first `PUT`, and React
 * still needs stable identity while it is being typed into.
 */
export interface DraftNode {
  key: string
  id: string | null
  title: string
  summary: string
  outcome: string
  criticality: NodeCriticality
  masteryThreshold: number
  defaultUiFormat: UiFormat
  skillId: string | null
  seedLessonId: string | null
  sourceDocumentId: string | null
  sourceHeadings: string[]
  prerequisiteNodeIds: string[]
  archived: boolean
}

/**
 * The formats a creator may pick.
 *
 * `simulation` is deliberately absent: the value exists in the `ui_format` enum but is
 * reserved and never emitted (§1.3 — a `Simulation` component needs data binding the
 * IR does not have). Offering it would let a creator pin a node to a format the
 * renderer cannot produce.
 *
 * The table is module-level, outside any component, so it stores message ids and the
 * consumer formats them at render time.
 */
export const SELECTABLE_UI_FORMATS: { value: UiFormat; labelKey: string; hintKey: string }[] = [
  { value: 'explanation', labelKey: 'schemaNode.format.explanation', hintKey: 'schemaNode.format.explanationHint' },
  { value: 'exercise', labelKey: 'schemaNode.format.exercise', hintKey: 'schemaNode.format.exerciseHint' },
  { value: 'chart', labelKey: 'schemaNode.format.chart', hintKey: 'schemaNode.format.chartHint' },
  { value: 'mixed', labelKey: 'schemaNode.format.mixed', hintKey: 'schemaNode.format.mixedHint' },
]
