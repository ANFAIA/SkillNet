import { describe, expect, it } from 'vitest'

import { DIDACT_COMPONENT_REGISTRY } from './generated-registry'
import { DIDACT_COMPONENT_LOADERS, loadDidactExport } from './generated-loaders'

describe('Didact lazy component loaders', () => {
  it('has one loader entry for every installed educational type', () => {
    expect(Object.keys(DIDACT_COMPONENT_LOADERS)).toHaveLength(34)
    expect(new Set(Object.keys(DIDACT_COMPONENT_LOADERS))).toEqual(
      new Set(DIDACT_COMPONENT_REGISTRY.map((entry) => entry.componentId)),
    )
  })

  it('groups exports from the same registry module behind one lazy loader', () => {
    expect(DIDACT_COMPONENT_LOADERS['didact.matching'].loadModule).toBe(
      DIDACT_COMPONENT_LOADERS['didact.sort'].loadModule,
    )
    expect(DIDACT_COMPONENT_LOADERS['didact.sort'].loadModule).toBe(
      DIDACT_COMPONENT_LOADERS['didact.categorize'].loadModule,
    )
    expect(DIDACT_COMPONENT_LOADERS['didact.quiz.single-choice'].loadModule).toBe(
      DIDACT_COMPONENT_LOADERS['didact.quiz.short-answer'].loadModule,
    )
  })

  it('resolves every educational export from its lazy vendor module', async () => {
    const exports = await Promise.all(
      DIDACT_COMPONENT_REGISTRY.map((entry) => loadDidactExport(entry.componentId)),
    )

    expect(exports).toHaveLength(34)
    expect(exports.every((component) => typeof component === 'function' || typeof component === 'object'))
      .toBe(true)
  }, 20_000)

  it('keeps loader metadata independent from per-generation exposure', () => {
    for (const entry of Object.values(DIDACT_COMPONENT_LOADERS)) {
      expect(entry).not.toHaveProperty('llmExposure')
      expect(entry).not.toHaveProperty('selected')
      expect(typeof entry.loadModule).toBe('function')
    }
  })
})
