import type { DidactHostCapability } from './host-ports'

/**
 * SkillNet-owned description of a Didact component adapter.
 *
 * `llmExposure` is intentionally independent from renderer availability: a
 * component must be explicitly reviewed before OpenUI may emit it.
 */
export type DidactAdapterDescriptor = {
  componentId: string
  adapterVersion: string
  didactVersion?: string
  rendererAvailable: boolean
  llmExposure: 'enabled' | 'disabled'
  requiredPorts?: readonly DidactHostCapability[]
  optionalPorts?: readonly DidactHostCapability[]
}
