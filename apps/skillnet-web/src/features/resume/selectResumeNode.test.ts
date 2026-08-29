import { describe, it, expect } from 'vitest'
import { hasStartedCourse, selectResumeNode } from './selectResumeNode'
import type { LearningNode } from '../../types'

/**
 * The rule that decides which node "Continuar" opens.
 *
 * Every case here is one the chain of `find`s it replaced got wrong, and they all come
 * from the same place: `state` cannot say where the learner is. `learning` needs a graded
 * answer (rule 0 of §7.3), and the `learner_node_states` row exists either way because a
 * prefetch creates it too — so "the first `not_started` node" was, in practice, always
 * node one. `state` cannot say whether a node is *finished* either, which is why "not yet
 * done" is `done` and never `state !== 'mastered'`.
 *
 * The fixtures set `done` alongside `state: 'mastered'` because that is what the server
 * sends: `node_is_done` is `mastered` **or** stamped with `completed_at`.
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

describe('selectResumeNode', () => {
  it('picks the most recently seen node, not the first one', () => {
    const nodes = [
      node({ id: 'n1', position: 1, first_seen_at: '2026-08-20T09:00:00Z' }),
      node({ id: 'n2', position: 2, first_seen_at: '2026-08-24T18:00:00Z' }),
      node({ id: 'n3', position: 3, first_seen_at: '2026-08-22T12:00:00Z' }),
    ]
    expect(selectResumeNode(nodes, 'n1')?.id).toBe('n2')
  })

  it('ignores the state column, which says `not_started` for a node read end to end', () => {
    const nodes = [
      node({ id: 'n1', position: 1, state: 'not_started', first_seen_at: null }),
      node({ id: 'n2', position: 2, state: 'not_started', first_seen_at: '2026-08-24T18:00:00Z' }),
    ]
    expect(selectResumeNode(nodes, 'n1')?.id).toBe('n2')
  })

  it('takes the node the server calls next when nothing has been seen', () => {
    const nodes = [
      node({ id: 'n1', position: 1 }),
      node({ id: 'n2', position: 2 }),
    ]
    expect(selectResumeNode(nodes, 'n1')?.id).toBe('n1')
  })

  it('returns the deepest node seen, ahead of what the server says is missing', () => {
    // "Where did I leave off" and "what is left" are different questions, and they
    // disagree the moment somebody skips ahead. Rung 1 wins.
    const nodes = [
      node({ id: 'n1', position: 1, first_seen_at: '2026-08-24T18:00:00Z' }),
      node({ id: 'n2', position: 2 }),
    ]
    expect(selectResumeNode(nodes, 'n1')?.id).toBe('n1')
  })

  it('moves forward past a node that was seen and then mastered', () => {
    const nodes = [
      node({ id: 'n1', position: 1, state: 'mastered', mastery: 1, done: true, first_seen_at: '2026-08-24T18:00:00Z' }),
      node({ id: 'n2', position: 2 }),
    ]
    expect(selectResumeNode(nodes, 'n2')?.id).toBe('n2')
  })

  it('moves forward past an expository node read to the end, which is never `mastered`', () => {
    // The case `state !== 'mastered'` got wrong: nothing in this node can be answered, so
    // it stays `not_started` for ever and "Continuar" kept reopening it.
    const nodes = [
      node({
        id: 'n1',
        position: 1,
        state: 'not_started',
        done: true,
        first_seen_at: '2026-08-24T18:00:00Z',
        completed_at: '2026-08-24T18:20:00Z',
      }),
      node({ id: 'n2', position: 2 }),
    ]
    expect(selectResumeNode(nodes, 'n2')?.id).toBe('n2')
  })

  it('falls back to the last node when the whole course is done', () => {
    const nodes = [
      node({ id: 'n1', position: 1, state: 'mastered', mastery: 1, done: true, first_seen_at: '2026-08-20T09:00:00Z' }),
      node({ id: 'n2', position: 2, state: 'mastered', mastery: 1, done: true, first_seen_at: '2026-08-24T18:00:00Z' }),
    ]
    expect(selectResumeNode(nodes, null)?.id).toBe('n2')
  })

  it('falls back to the last node when `next_node_id` names one this list does not carry', () => {
    const nodes = [
      node({ id: 'n1', position: 1 }),
      node({ id: 'n2', position: 2 }),
    ]
    expect(selectResumeNode(nodes, 'archivado')?.id).toBe('n2')
  })

  it('is undefined only for an empty course', () => {
    expect(selectResumeNode([], null)).toBeUndefined()
  })

  it('treats an unparsable timestamp as never seen rather than as NaN', () => {
    const nodes = [
      node({ id: 'n1', position: 1, first_seen_at: 'no es una fecha' }),
      node({ id: 'n2', position: 2, first_seen_at: '2026-08-24T18:00:00Z' }),
    ]
    expect(selectResumeNode(nodes, 'n1')?.id).toBe('n2')
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
