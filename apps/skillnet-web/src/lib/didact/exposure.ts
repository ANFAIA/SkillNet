import type { DidactRegistryEntry } from './registry-types'

/**
 * A generation-specific decision over the installed catalogue.
 *
 * Registry entries never disappear when an experiment chooses a smaller shortlist.
 * Keeping this type in its own module makes that boundary hard to blur accidentally.
 */
export type DidactExposureDecision = {
  componentId: DidactRegistryEntry['componentId']
  exposed: boolean
  experimentArm: string
  reasons: readonly string[]
}

export function exposedComponentIds(
  registry: readonly DidactRegistryEntry[],
  decisions: readonly DidactExposureDecision[],
): readonly DidactRegistryEntry['componentId'][] {
  const installed = new Set(registry.map((entry) => entry.componentId))
  return decisions
    .filter((decision) => decision.exposed && installed.has(decision.componentId))
    .map((decision) => decision.componentId)
}
