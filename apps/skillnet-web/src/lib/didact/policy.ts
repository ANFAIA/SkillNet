import { DIDACT_COMPONENT_REGISTRY } from './generated-registry'
import type { DidactHostCapability } from './host-ports'
import type { DidactRegistryEntry } from './registry-types'

/** What the host may do when a capability is absent. */
export type DidactFallbackMode =
  | 'static-content'
  | 'local-interaction'
  | 'host-assisted'
  | 'host-required'

/** Data classes that must stay behind an explicit SkillNet boundary. */
export type DidactProtectedData =
  | 'answer-key'
  | 'model-answer'
  | 'learner-response'
  | 'learner-progress'
  | 'learner-artifact'
  | 'source-media'
  | 'executable-code'

export type DidactComponentPolicy = {
  requiredPorts: readonly DidactHostCapability[]
  optionalPorts: readonly DidactHostCapability[]
  fallbackMode: DidactFallbackMode
  protectedData: readonly DidactProtectedData[]
}

type ManifestPolicy = DidactComponentPolicy

const STATIC = {
  requiredPorts: [],
  optionalPorts: [],
  fallbackMode: 'static-content',
  protectedData: [],
} as const satisfies ManifestPolicy

const LOCAL = {
  requiredPorts: [],
  optionalPorts: ['events'],
  fallbackMode: 'local-interaction',
  protectedData: ['learner-response'],
} as const satisfies ManifestPolicy

/**
 * Host-owned policy keyed by Didact manifest, not by React export.
 *
 * Variant type IDs inherit their manifest policy below. This keeps policy
 * exhaustive over the generated registry without copying its 34 identifiers.
 */
const MANIFEST_POLICY = {
  'didact.flashcard': {
    ...LOCAL,
    optionalPorts: ['events', 'persistence', 'progress'],
  },
  'didact.quiz': {
    requiredPorts: ['evaluation'],
    optionalPorts: ['events', 'progress'],
    fallbackMode: 'host-required',
    protectedData: ['answer-key', 'model-answer', 'learner-response'],
  },
  'didact.matching-exercises': {
    requiredPorts: ['evaluation'],
    optionalPorts: ['events', 'progress'],
    fallbackMode: 'host-required',
    protectedData: ['answer-key', 'learner-response'],
  },
  'didact.glossary': STATIC,
  'didact.hint-reveal': {
    ...LOCAL,
    protectedData: ['model-answer', 'learner-response'],
  },
  'didact.progress': {
    requiredPorts: ['progress'],
    optionalPorts: [],
    fallbackMode: 'host-required',
    protectedData: ['learner-progress'],
  },
  'didact.mastery-badge': {
    requiredPorts: ['progress'],
    optionalPorts: [],
    fallbackMode: 'host-required',
    protectedData: ['learner-progress'],
  },
  'didact.rubric': {
    requiredPorts: [],
    optionalPorts: ['events', 'persistence', 'evaluation', 'progress'],
    fallbackMode: 'host-assisted',
    protectedData: ['learner-response', 'learner-progress'],
  },
  'didact.timeline': STATIC,
  'didact.practice-set': {
    requiredPorts: ['evaluation', 'persistence', 'progress'],
    optionalPorts: ['events'],
    fallbackMode: 'host-required',
    protectedData: ['answer-key', 'model-answer', 'learner-response', 'learner-progress'],
  },
  'didact.retrieval-practice-session': {
    requiredPorts: ['persistence', 'progress', 'clock', 'scheduler'],
    optionalPorts: ['events'],
    fallbackMode: 'host-required',
    protectedData: ['model-answer', 'learner-response', 'learner-progress'],
  },
  'didact.self-explanation-prompt': {
    requiredPorts: ['persistence'],
    optionalPorts: ['events', 'progress'],
    fallbackMode: 'host-assisted',
    protectedData: ['model-answer', 'learner-response'],
  },
  'didact.worked-example': {
    requiredPorts: [],
    optionalPorts: ['events', 'persistence'],
    fallbackMode: 'local-interaction',
    protectedData: [],
  },
  'didact.completion-problem': {
    requiredPorts: ['evaluation'],
    optionalPorts: ['events', 'progress'],
    fallbackMode: 'host-required',
    protectedData: ['answer-key', 'model-answer', 'learner-response'],
  },
  'didact.numeric-question': {
    requiredPorts: ['evaluation'],
    optionalPorts: ['events', 'progress'],
    fallbackMode: 'host-required',
    protectedData: ['answer-key', 'learner-response'],
  },
  'didact.word-bank': {
    requiredPorts: ['evaluation'],
    optionalPorts: ['events', 'progress'],
    fallbackMode: 'host-required',
    protectedData: ['answer-key', 'learner-response'],
  },
  'didact.hotspot': {
    requiredPorts: ['assets', 'evaluation'],
    optionalPorts: ['events', 'progress'],
    fallbackMode: 'host-required',
    protectedData: ['answer-key', 'learner-response', 'source-media'],
  },
  'didact.label-diagram': {
    requiredPorts: ['assets', 'evaluation'],
    optionalPorts: ['events', 'progress'],
    fallbackMode: 'host-required',
    protectedData: ['answer-key', 'learner-response', 'source-media'],
  },
  'didact.concept-map': {
    requiredPorts: ['persistence'],
    optionalPorts: ['events', 'evaluation', 'progress'],
    fallbackMode: 'host-assisted',
    protectedData: ['learner-artifact', 'learner-response'],
  },
  'didact.drawing-response': {
    requiredPorts: ['persistence'],
    optionalPorts: ['events', 'evaluation', 'progress'],
    fallbackMode: 'host-assisted',
    protectedData: ['learner-artifact', 'learner-response'],
  },
  'didact.equation-workbench': {
    requiredPorts: ['evaluation'],
    optionalPorts: ['events', 'persistence', 'progress'],
    fallbackMode: 'host-required',
    protectedData: ['answer-key', 'learner-artifact', 'learner-response'],
  },
  'didact.evidence-annotation': {
    requiredPorts: ['persistence'],
    optionalPorts: ['events', 'evaluation', 'progress'],
    fallbackMode: 'host-assisted',
    protectedData: ['learner-artifact', 'learner-response'],
  },
  'didact.measurement-lab': {
    requiredPorts: ['evaluation'],
    optionalPorts: ['events', 'progress'],
    fallbackMode: 'host-required',
    protectedData: ['answer-key', 'learner-response'],
  },
  'didact.interactive-media': {
    requiredPorts: ['assets'],
    optionalPorts: ['media', 'events', 'persistence', 'progress'],
    fallbackMode: 'host-assisted',
    protectedData: ['source-media', 'learner-response', 'learner-progress'],
  },
  'didact.data-explorer': {
    ...LOCAL,
    optionalPorts: ['events', 'evaluation', 'persistence', 'progress'],
    fallbackMode: 'host-assisted',
  },
  'didact.branching-scenario': {
    requiredPorts: ['simulation'],
    optionalPorts: ['events', 'persistence', 'progress'],
    fallbackMode: 'host-required',
    protectedData: ['learner-response', 'learner-progress'],
  },
  'didact.simulation-lab': {
    requiredPorts: ['simulation', 'clock'],
    optionalPorts: ['events', 'persistence', 'progress'],
    fallbackMode: 'host-required',
    protectedData: ['learner-response', 'learner-progress'],
  },
  'didact.code-exercise': {
    requiredPorts: ['execution', 'evaluation'],
    optionalPorts: ['events', 'persistence', 'progress'],
    fallbackMode: 'host-required',
    protectedData: ['answer-key', 'learner-artifact', 'learner-response', 'executable-code'],
  },
} as const satisfies Readonly<Record<string, ManifestPolicy>>

function policyForEntry(entry: DidactRegistryEntry): DidactComponentPolicy {
  const policy = MANIFEST_POLICY[entry.manifestId as keyof typeof MANIFEST_POLICY]
  if (!policy) throw new Error(`Missing Didact host policy for manifest ${entry.manifestId}`)
  return policy
}

export const DIDACT_COMPONENT_POLICY: ReadonlyMap<string, DidactComponentPolicy> = new Map(
  DIDACT_COMPONENT_REGISTRY.map((entry) => [entry.componentId, policyForEntry(entry)]),
)

export function didactPolicyFor(componentId: string): DidactComponentPolicy | undefined {
  return DIDACT_COMPONENT_POLICY.get(componentId)
}
