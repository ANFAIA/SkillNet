import { describe, expect, it } from 'vitest'
import { nodeStatus } from './nodeStatus'
import type { LearningNode } from '../../types'

/**
 * The one question every node list asks, and the one it must stop asking.
 *
 * "Is it finished?" is `done`. It was `state === 'mastered'`, and `mastered` needs 0.90
 * mastery plus three consecutive correct answers on **graded** items — so a node with
 * nothing to answer can never reach it. The index drew the hollow "not started" circle on
 * a lesson the learner had completed while the bar above said 100%.
 */

function node(overrides: Partial<LearningNode> = {}): LearningNode {
  return {
    id: 'n1',
    title: 'Nodo',
    summary: null,
    criticality: 'recommended',
    position: 1,
    state: 'not_started',
    mastery: 0,
    done: false,
    available: true,
    first_seen_at: null,
    completed_at: null,
    ...overrides,
  }
}

describe('nodeStatus', () => {
  it('calls an expository node finished, though its state never leaves `not_started`', () => {
    expect(
      nodeStatus(node({ state: 'not_started', done: true, completed_at: '2026-08-28T10:00:00Z' })),
    ).toBe('completed')
  })

  it('keeps `state` to say HOW it was finished: demonstrated, not just walked through', () => {
    expect(nodeStatus(node({ state: 'mastered', mastery: 1, done: true }))).toBe('mastered')
  })

  it('is `learning` for a node answered but not finished — done is not mastery', () => {
    expect(nodeStatus(node({ state: 'learning', mastery: 0.4, done: false }))).toBe('learning')
  })

  it('is `not_started` for a node nobody has opened', () => {
    expect(nodeStatus(node())).toBe('not_started')
  })
})
