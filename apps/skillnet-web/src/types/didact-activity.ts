import type { DidactValue } from '../lib/didact/host-ports'

/**
 * Public, learner-safe projection of a server-owned ActivityDefinition.
 *
 * The complete definition (answer keys, rubrics and execution configuration)
 * never crosses this boundary. This deliberately stays independent from the
 * Python model so both sides may evolve without importing generated clients.
 */
export interface PublicActivityDefinition {
  activity_id: string
  component_id: `didact.${string}`
  family: 'assessment' | 'artifact' | 'media' | 'simulation' | 'execution'
  schema_version: number
  public_definition: Readonly<Record<string, DidactValue>>
  required_ports: readonly string[]
  provenance: Readonly<Record<string, DidactValue>>
  status: 'ready' | 'declined'
  decline_reason: string | null
}

export type DidactActivityReference = {
  activityId: string
  componentId: `didact.${string}`
}
