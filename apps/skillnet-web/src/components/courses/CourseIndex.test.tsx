/**
 * The index of a course, and the disagreement it used to print.
 *
 * The row branched on `state`, so a node the learner had worked through to the end drew
 * the empty "sin empezar" circle — right under a progress bar reading 100%, because the
 * bar counts `done`. One screen, two answers to "is this finished?". The tick is `done`
 * now; `state` only chooses the word next to it.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { CourseIndex } from './CourseIndex'
import type { LearningNode, NodeList } from '../../types'

const useCourseNodes = vi.fn()
vi.mock('../../api/nodes', () => ({
  useCourseNodes: (courseId: string | undefined) => useCourseNodes(courseId),
}))

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

function renderIndex(nodes: LearningNode[]) {
  useCourseNodes.mockReturnValue({
    isLoading: false,
    data: {
      course_id: 'c1',
      delivery_mode: 'dynamic',
      schema_version: 1,
      nodes,
      next_node_id: null,
      can_complete: false,
      blocked_by: [],
      progress_percent: 100,
    } satisfies NodeList,
  })
  return render(<CourseIndex courseId="c1" />)
}

describe('<CourseIndex>', () => {
  it('marks an expository node read to the end as finished, not as "sin empezar"', () => {
    renderIndex([
      node({
        id: 'n1',
        title: 'Qué es un sesgo',
        state: 'not_started',
        done: true,
        first_seen_at: '2026-08-28T09:00:00Z',
        completed_at: '2026-08-28T09:20:00Z',
      }),
    ])

    expect(screen.getByText('Completado')).toBeInTheDocument()
    expect(screen.queryByText('Sin empezar')).not.toBeInTheDocument()
  })

  it('still says "Dominado" for a node the learner demonstrated', () => {
    renderIndex([node({ id: 'n1', state: 'mastered', mastery: 1, done: true })])

    expect(screen.getByText('Dominado')).toBeInTheDocument()
  })

  it('leaves a node nobody has finished alone', () => {
    renderIndex([node({ id: 'n1', state: 'learning', mastery: 0.4 })])

    expect(screen.getByText('En curso')).toBeInTheDocument()
  })
})
