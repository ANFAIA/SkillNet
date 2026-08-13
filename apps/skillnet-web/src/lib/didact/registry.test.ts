import { describe, expect, it } from 'vitest'

import { exposedComponentIds } from './exposure'
import {
  DIDACT_COMPONENT_BY_ID,
  DIDACT_COMPONENT_REGISTRY,
  DIDACT_REGISTRY_SOURCE,
} from './generated-registry'

describe('generated Didact registry', () => {
  it('covers every authoritative available type exactly once', () => {
    const ids = DIDACT_COMPONENT_REGISTRY.map((entry) => entry.componentId)
    const expectedCount = DIDACT_REGISTRY_SOURCE.authoritativeTypeCount

    expect(ids).toHaveLength(expectedCount)
    expect(new Set(ids).size).toBe(expectedCount)
    expect(DIDACT_COMPONENT_BY_ID.size).toBe(expectedCount)
    expect(ids.every((id) => id.startsWith('didact.'))).toBe(true)
  })

  it('retains identity, provenance, maturity and lazy-module metadata', () => {
    expect(DIDACT_REGISTRY_SOURCE.repository).toBe('https://github.com/JoseEstevez520/Didact')
    expect(DIDACT_REGISTRY_SOURCE.commit).toMatch(/^[a-f0-9]{40}$/)
    expect(DIDACT_REGISTRY_SOURCE.contentSha256).toMatch(/^[a-f0-9]{64}$/)

    for (const entry of DIDACT_COMPONENT_REGISTRY) {
      expect(entry.manifestId).toMatch(/^didact\./)
      expect(entry.exportName).not.toBe('')
      expect(entry.registryItem).not.toBe('')
      expect(entry.didactVersion).toMatch(/^\d+\.\d+\.\d+$/)
      expect(['experimental', 'beta', 'stable', 'deprecated']).toContain(entry.maturity)
      expect(entry.lazyModule).toEqual({
        strategy: 'vendor-export',
        exportName: entry.exportName,
        registryItem: entry.registryItem,
        sourceModule: entry.registryItem === 'progress-indicators'
          ? 'progress-indicator'
          : entry.registryItem,
      })
    }
  })

  it('records all vendored renderers as available without importing them eagerly', () => {
    const rendererReady = DIDACT_COMPONENT_REGISTRY.filter(
      (entry) => entry.adapter.rendererAvailable,
    )

    expect(rendererReady).toHaveLength(DIDACT_REGISTRY_SOURCE.authoritativeTypeCount)
    expect(rendererReady.every((entry) => entry.adapter.rendererSymbol === entry.exportName)).toBe(true)
  })

  it('projects the backend operational contract without conflating vendor exports', () => {
    const emittable = DIDACT_COMPONENT_REGISTRY.filter(
      (entry) => entry.operations.emission === 'enabled',
    )
    const blocked = DIDACT_COMPONENT_REGISTRY.filter(
      (entry) => entry.operations.rendererMode === 'blocked',
    )

    expect(DIDACT_REGISTRY_SOURCE.operationalSchemaVersion).toBe(1)
    expect(emittable).toHaveLength(29)
    expect(blocked).toHaveLength(5)
    expect(emittable.every((entry) => entry.operations.rendererSymbol !== null)).toBe(true)
  })

  it('keeps generation exposure separate from the installed catalogue', () => {
    const before = DIDACT_COMPONENT_REGISTRY.length
    const exposed = exposedComponentIds(DIDACT_COMPONENT_REGISTRY, [
      {
        componentId: 'didact.flashcard',
        exposed: true,
        experimentArm: 'shortlist-1',
        reasons: ['semantic match'],
      },
      {
        componentId: 'didact.hint-reveal',
        exposed: false,
        experimentArm: 'shortlist-1',
        reasons: ['not selected'],
      },
    ])

    expect(exposed).toEqual(['didact.flashcard'])
    expect(DIDACT_COMPONENT_REGISTRY).toHaveLength(before)
    expect(DIDACT_COMPONENT_BY_ID.size).toBe(DIDACT_REGISTRY_SOURCE.authoritativeTypeCount)
  })
})
