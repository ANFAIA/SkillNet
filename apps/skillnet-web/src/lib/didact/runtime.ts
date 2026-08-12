import { DIDACT_COMPONENT_BY_ID } from './generated-registry'
import type { DidactHostPorts } from './host-ports'
import { deriveDidactAvailability, type DidactAdapterAvailability } from './availability'
import { didactPolicyFor, type DidactComponentPolicy } from './policy'

export type DidactMountResolution = {
  availability: DidactAdapterAvailability
  policy?: DidactComponentPolicy
}

export function resolveDidactMount(
  componentId: string,
  ports: DidactHostPorts,
): DidactMountResolution {
  const registryEntry = DIDACT_COMPONENT_BY_ID.get(componentId)
  const policy = didactPolicyFor(componentId)
  const rendererAvailable = registryEntry?.adapter.rendererAvailable === true && policy !== undefined

  return {
    policy,
    availability: deriveDidactAvailability(
      {
        componentId,
        adapterVersion: '1',
        didactVersion: registryEntry?.didactVersion,
        rendererAvailable,
        llmExposure: 'disabled',
        requiredPorts: policy?.requiredPorts,
        optionalPorts: policy?.optionalPorts,
      },
      ports,
    ),
  }
}

const PROTECTED_ANSWER_KEYS = new Set([
  'acceptedanswer',
  'acceptedanswers',
  'answerkey',
  'correctanswer',
  'correctanswers',
  'correctcategories',
  'correctitemids',
  'correctmatches',
  'correctoption',
  'correctoptionid',
  'correctoptionids',
  'correctorder',
  'correctregionids',
  'correctvalue',
  'expectedanswer',
  'expectedanswers',
  'grading',
])

function normalizedKey(key: string): string {
  return key.replaceAll(/[^a-zA-Z]/g, '').toLowerCase()
}

/**
 * Defense in depth for generated/public props. Correctness data belongs behind
 * EvaluationPort and must never be mounted into the learner-visible React tree.
 */
export function withoutProtectedAnswerKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(withoutProtectedAnswerKeys)
  if (value === null || typeof value !== 'object') return value

  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => !PROTECTED_ANSWER_KEYS.has(normalizedKey(key)))
      .map(([key, nested]) => [key, withoutProtectedAnswerKeys(nested)]),
  )
}
