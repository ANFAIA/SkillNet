import { describe, expect, it } from 'vitest'

import { DIDACT_COMPONENT_REGISTRY } from './generated-registry'
import { DIDACT_COMPONENT_POLICY, didactPolicyFor } from './policy'

describe('Didact host policy', () => {
  it('covers all 34 installed type IDs exactly once', () => {
    const installedIds = DIDACT_COMPONENT_REGISTRY.map((entry) => entry.componentId)
    const policyIds = [...DIDACT_COMPONENT_POLICY.keys()]

    expect(installedIds).toHaveLength(34)
    expect(new Set(installedIds)).toHaveLength(34)
    expect(policyIds).toEqual(installedIds)
    expect(policyIds).toHaveLength(34)
  })

  it.each(DIDACT_COMPONENT_REGISTRY)('declares a complete policy for $componentId', (entry) => {
    const policy = didactPolicyFor(entry.componentId)

    expect(policy).toBeDefined()
    if (!policy) throw new Error(`Missing policy for ${entry.componentId}`)
    expect(policy.fallbackMode).toMatch(/^(static-content|local-interaction|host-assisted|host-required)$/)
    expect(policy.requiredPorts).toEqual([...new Set(policy.requiredPorts)])
    expect(policy.optionalPorts).toEqual([...new Set(policy.optionalPorts)])
    expect(policy.requiredPorts.filter((port) => policy.optionalPorts.includes(port))).toEqual([])
    expect(policy.protectedData).toEqual([...new Set(policy.protectedData)])
  })

  it('inherits one reviewed manifest policy across manifest variants', () => {
    const quizPolicies = DIDACT_COMPONENT_REGISTRY
      .filter((entry) => entry.manifestId === 'didact.quiz')
      .map((entry) => didactPolicyFor(entry.componentId))

    expect(quizPolicies).toHaveLength(5)
    expect(new Set(quizPolicies)).toHaveLength(1)
  })

  it('protects executable code and requires both execution and evaluation', () => {
    const policy = didactPolicyFor('didact.code-exercise')

    expect(policy?.requiredPorts).toEqual(['execution', 'evaluation'])
    expect(policy?.protectedData).toContain('executable-code')
    expect(policy?.fallbackMode).toBe('host-required')
  })

  it('keeps pure presentation components independent from host state', () => {
    expect(didactPolicyFor('didact.timeline-steps')).toEqual({
      requiredPorts: [],
      optionalPorts: [],
      fallbackMode: 'static-content',
      protectedData: [],
    })
  })

  it('does not claim a self-explanation response can survive without persistence', () => {
    const policy = didactPolicyFor('didact.self-explanation-prompt')

    expect(policy?.requiredPorts).toEqual(['persistence'])
    expect(policy?.protectedData).toContain('learner-response')
    expect(policy?.optionalPorts).not.toContain('evaluation')
  })

  it('keeps worked examples usable locally while declaring resume telemetry as optional', () => {
    const policy = didactPolicyFor('didact.worked-example')

    expect(policy?.requiredPorts).toEqual([])
    expect(policy?.optionalPorts).toEqual(['events', 'persistence'])
    expect(policy?.fallbackMode).toBe('local-interaction')
  })
})
