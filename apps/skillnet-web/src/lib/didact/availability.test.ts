import { describe, expect, it } from 'vitest'

import type { DidactAdapterDescriptor } from './adapter'
import { deriveDidactAvailability } from './availability'
import type { DidactHostPorts } from './host-ports'

const eventPort: NonNullable<DidactHostPorts['events']> = {
  emit: async () => undefined,
}

const persistencePort: NonNullable<DidactHostPorts['persistence']> = {
  load: async () => undefined,
  save: async () => undefined,
  remove: async () => undefined,
}

function descriptor(overrides: Partial<DidactAdapterDescriptor> = {}): DidactAdapterDescriptor {
  return {
    componentId: 'didact/example',
    adapterVersion: '1',
    rendererAvailable: true,
    llmExposure: 'enabled',
    ...overrides,
  }
}

describe('deriveDidactAvailability', () => {
  it('is ready when renderer and every requested port are available', () => {
    const result = deriveDidactAvailability(
      descriptor({ requiredPorts: ['events'], optionalPorts: ['persistence'] }),
      { events: eventPort, persistence: persistencePort },
    )

    expect(result).toEqual({
      status: 'ready',
      rendererAvailable: true,
      llmEmittable: true,
      missingRequiredPorts: [],
      missingOptionalPorts: [],
      reasons: [],
    })
  })

  it('is degraded when only optional ports are missing', () => {
    const result = deriveDidactAvailability(
      descriptor({ requiredPorts: ['events'], optionalPorts: ['persistence', 'progress'] }),
      { events: eventPort },
    )

    expect(result.status).toBe('degraded')
    expect(result.llmEmittable).toBe(true)
    expect(result.missingOptionalPorts).toEqual(['persistence', 'progress'])
    expect(result.reasons).toContain('missing_optional_ports')
  })

  it('is blocked when a required port is missing', () => {
    const result = deriveDidactAvailability(
      descriptor({ requiredPorts: ['evaluation', 'events'] }),
      { events: eventPort },
    )

    expect(result.status).toBe('blocked')
    expect(result.llmEmittable).toBe(false)
    expect(result.missingRequiredPorts).toEqual(['evaluation'])
    expect(result.reasons).toContain('missing_required_ports')
  })

  it('is blocked when no renderer exists even if all ports exist', () => {
    const result = deriveDidactAvailability(
      descriptor({ rendererAvailable: false, requiredPorts: ['events'] }),
      { events: eventPort },
    )

    expect(result.status).toBe('blocked')
    expect(result.llmEmittable).toBe(false)
    expect(result.reasons).toContain('renderer_unavailable')
  })

  it('does not infer LLM emission from renderer availability', () => {
    const result = deriveDidactAvailability(
      descriptor({ rendererAvailable: true, llmExposure: 'disabled' }),
      {},
    )

    expect(result.status).toBe('ready')
    expect(result.rendererAvailable).toBe(true)
    expect(result.llmEmittable).toBe(false)
    expect(result.reasons).toContain('llm_exposure_disabled')
  })

  it('deduplicates repeated capability declarations', () => {
    const result = deriveDidactAvailability(
      descriptor({ requiredPorts: ['simulation', 'simulation'] }),
      {},
    )

    expect(result.missingRequiredPorts).toEqual(['simulation'])
  })
})
