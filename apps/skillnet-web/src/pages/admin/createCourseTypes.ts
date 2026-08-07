// Shared types for the CreateCourse flow and its extracted sub-components.

export type SourceType = 'importar' | 'crear' | null
export type DeliveryChoice = 'dynamic' | 'static'
export type Phase = 'choose' | 'details' | 'schema' | 'created' | 'generating' | 'review' | 'assign'

export interface ProposedNode {
  _key: number
  title: string
  summary: string
  outcome: string | null
  criticality: string
  default_ui_format: string
  estimated_minutes: number
  source_headings: string[]
  prerequisites: number[]
}
