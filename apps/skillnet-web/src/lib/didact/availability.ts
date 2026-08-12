import type { DidactAdapterDescriptor } from './adapter'
import type { DidactHostCapability, DidactHostPorts } from './host-ports'

export type DidactAvailabilityStatus = 'ready' | 'degraded' | 'blocked'

export type DidactAdapterAvailability = {
  status: DidactAvailabilityStatus
  rendererAvailable: boolean
  llmEmittable: boolean
  missingRequiredPorts: readonly DidactHostCapability[]
  missingOptionalPorts: readonly DidactHostCapability[]
  reasons: readonly (
    | 'renderer_unavailable'
    | 'missing_required_ports'
    | 'missing_optional_ports'
    | 'llm_exposure_disabled'
  )[]
}

function unique(capabilities: readonly DidactHostCapability[]): DidactHostCapability[] {
  return [...new Set(capabilities)]
}

function missingPorts(
  capabilities: readonly DidactHostCapability[],
  ports: DidactHostPorts,
): DidactHostCapability[] {
  return unique(capabilities).filter((capability) => ports[capability] === undefined)
}

/** Pure readiness derivation. It does not register renderers or mutate ports. */
export function deriveDidactAvailability(
  descriptor: DidactAdapterDescriptor,
  ports: DidactHostPorts,
): DidactAdapterAvailability {
  const missingRequiredPorts = missingPorts(descriptor.requiredPorts ?? [], ports)
  const missingOptionalPorts = missingPorts(descriptor.optionalPorts ?? [], ports)

  const status: DidactAvailabilityStatus = !descriptor.rendererAvailable || missingRequiredPorts.length > 0
    ? 'blocked'
    : missingOptionalPorts.length > 0
      ? 'degraded'
      : 'ready'

  const llmEmittable = status !== 'blocked' && descriptor.llmExposure === 'enabled'
  const reasons: DidactAdapterAvailability['reasons'][number][] = []

  if (!descriptor.rendererAvailable) reasons.push('renderer_unavailable')
  if (missingRequiredPorts.length > 0) reasons.push('missing_required_ports')
  if (missingOptionalPorts.length > 0) reasons.push('missing_optional_ports')
  if (descriptor.llmExposure === 'disabled') reasons.push('llm_exposure_disabled')

  return {
    status,
    rendererAvailable: descriptor.rendererAvailable,
    llmEmittable,
    missingRequiredPorts,
    missingOptionalPorts,
    reasons,
  }
}
