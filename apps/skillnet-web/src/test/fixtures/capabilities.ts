/**
 * Capability fixtures for tests and stories.
 *
 * `Capabilities` stopped being a bag of booleans, and spelling `{ status: 'ready' }`
 * six times per seed drowns the one entry a test actually cares about. `caps({ images:
 * blocked('missing_api_key') })` says it in one line.
 */

import {
  DEFAULT_CAPABILITIES,
  type Capabilities,
  type CapabilityName,
  type CapabilityReason,
} from '../../api/setup'

export const ready = { status: 'ready' } as const

export function degraded(reason: CapabilityReason) {
  return { status: 'degraded', reason } as const
}

export function blocked(reason?: CapabilityReason) {
  return { status: 'blocked', reason: reason ?? null } as const
}

/** Everything ready (including `google_login`), overridden by `overrides`. */
export function caps(overrides: Partial<Capabilities> = {}): Capabilities {
  const all = {} as Capabilities
  for (const name of Object.keys(DEFAULT_CAPABILITIES) as CapabilityName[]) {
    all[name] = ready
  }
  return { ...all, ...overrides }
}
