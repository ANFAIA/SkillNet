import { DIDACT_COMPONENT_BY_ID } from './generated-registry'
import type { DidactValue } from './host-ports'
import { withoutProtectedAnswerKeys } from './runtime'
import type { PublicActivityDefinition } from '../../types/didact-activity'

export type ActivityDefinitionValidation =
  | { ok: true; componentProps: Readonly<Record<string, DidactValue>> }
  | { ok: false; reason: 'invalid_envelope' | 'activity_mismatch' | 'component_mismatch' | 'unknown_component' | 'declined' }

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

/** Validate identity before any server data reaches a vendored component. */
export function validatePublicActivityDefinition(
  value: unknown,
  expectedActivityId: string,
  expectedComponentId: string,
): ActivityDefinitionValidation {
  if (!isRecord(value) || !isRecord(value.public_definition)) return { ok: false, reason: 'invalid_envelope' }
  if (value.status === 'declined') return { ok: false, reason: 'declined' }
  if (value.activity_id !== expectedActivityId) return { ok: false, reason: 'activity_mismatch' }
  if (value.component_id !== expectedComponentId) return { ok: false, reason: 'component_mismatch' }
  if (!DIDACT_COMPONENT_BY_ID.has(expectedComponentId)) return { ok: false, reason: 'unknown_component' }

  // Defense in depth. The server projection is authoritative, but a cache or
  // proxy regression must still not mount protected correctness data.
  const safe = withoutProtectedAnswerKeys(value.public_definition)
  if (!isRecord(safe)) return { ok: false, reason: 'invalid_envelope' }
  return { ok: true, componentProps: safe as Record<string, DidactValue> }
}

export function isPublicActivityDefinition(value: unknown): value is PublicActivityDefinition {
  if (!isRecord(value)) return false
  return typeof value.activity_id === 'string'
    && typeof value.component_id === 'string'
    && Number.isInteger(value.schema_version)
    && isRecord(value.public_definition)
}
