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
  estimatedMinutes: number | null
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
 */
export const SELECTABLE_UI_FORMATS: { value: UiFormat; label: string; hint: string }[] = [
  { value: 'explanation', label: 'Explicación', hint: 'Texto y ejemplos' },
  { value: 'exercise', label: 'Ejercicio', hint: 'Práctica con corrección' },
  { value: 'chart', label: 'Gráfico', hint: 'Datos o comparativa visual' },
  { value: 'mixed', label: 'Mixto', hint: 'Explicación y práctica en el mismo nodo' },
]
