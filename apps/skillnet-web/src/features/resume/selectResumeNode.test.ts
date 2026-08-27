import { describe, it, expect } from 'vitest'
import { hasStartedCourse, selectResumeNode } from './selectResumeNode'
import type { LearningNode } from '../../types'

/**
 * The rule that decides which node "Continuar" opens.
 *
 * Every case here is one the chain of `find`s it replaced got wrong, and they all come
 * from the same place: `state` cannot say where the learner is. `learning` needs a graded
 * answer (rule 0 of §7.3), and the `learner_node_states` row exists either way because a
 * prefetch creates it too — so "the first `not_started` unlocked node" was, in practice,
 * always node one.
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
    locked: false,
    locked_by: [],
    needs_practice: false,
    estimated_minutes: 6,
    first_seen_at: null,
    completed_at: null,
    ...overrides,
  }
}

describe('selectResumeNode', () => {
  it('picks the most recently seen node, not the first one', () => {
    const nodes = [
      node({ id: 'n1', position: 1, first_seen_at: '2026-08-20T09:00:00Z' }),
      node({ id: 'n2', position: 2, first_seen_at: '2026-08-24T18:00:00Z' }),
      node({ id: 'n3', position: 3, first_seen_at: '2026-08-22T12:00:00Z' }),
    ]
    expect(selectResumeNode(nodes)?.id).toBe('n2')
  })

  it('ignores the state column, which says `not_started` for a node read end to end', () => {
    const nodes = [
      node({ id: 'n1', position: 1, state: 'not_started', first_seen_at: null }),
      node({ id: 'n2', position: 2, state: 'not_started', first_seen_at: '2026-08-24T18:00:00Z' }),
    ]
    expect(selectResumeNode(nodes)?.id).toBe('n2')
  })

  it('starts at the first unlocked node when nothing has been seen', () => {
    const nodes = [
      node({ id: 'n1', position: 1 }),
      node({ id: 'n2', position: 2 }),
    ]
    expect(selectResumeNode(nodes)?.id).toBe('n1')
  })

  it('never returns a locked node', () => {
    const nodes = [
      node({ id: 'n1', position: 1, locked: true, first_seen_at: '2026-08-24T18:00:00Z' }),
      node({ id: 'n2', position: 2 }),
    ]
    expect(selectResumeNode(nodes)?.id).toBe('n2')
  })

  it('moves forward past a node that was seen and then mastered', () => {
    const nodes = [
      node({ id: 'n1', position: 1, state: 'mastered', mastery: 1, first_seen_at: '2026-08-24T18:00:00Z' }),
      node({ id: 'n2', position: 2 }),
    ]
    expect(selectResumeNode(nodes)?.id).toBe('n2')
  })

  it('falls back to the last unlocked node when the whole course is mastered', () => {
    const nodes = [
      node({ id: 'n1', position: 1, state: 'mastered', mastery: 1, first_seen_at: '2026-08-20T09:00:00Z' }),
      node({ id: 'n2', position: 2, state: 'mastered', mastery: 1, first_seen_at: '2026-08-24T18:00:00Z' }),
    ]
    expect(selectResumeNode(nodes)?.id).toBe('n2')
  })

  it('is undefined when nothing is unlocked, which is what disables the button', () => {
    expect(selectResumeNode([node({ locked: true })])).toBeUndefined()
    expect(selectResumeNode([])).toBeUndefined()
  })

  it('treats an unparsable timestamp as never seen rather than as NaN', () => {
    const nodes = [
      node({ id: 'n1', position: 1, first_seen_at: 'no es una fecha' }),
      node({ id: 'n2', position: 2, first_seen_at: '2026-08-24T18:00:00Z' }),
    ]
    expect(selectResumeNode(nodes)?.id).toBe('n2')
  })
})

describe('hasStartedCourse', () => {
  it('is true for a node that was only read — the case `mastery === 0` missed', () => {
    expect(hasStartedCourse([node({ mastery: 0, first_seen_at: '2026-08-24T18:00:00Z' })])).toBe(true)
  })

  it('is false for a fresh course, so the course intro still shows once', () => {
    expect(hasStartedCourse([node(), node({ id: 'n2', position: 2 })])).toBe(false)
  })

  it('is true on mastery alone, for progress made before the stamp existed', () => {
    expect(hasStartedCourse([node({ mastery: 0.4, first_seen_at: null })])).toBe(true)
  })
})
