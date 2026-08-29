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
import { es } from '../../i18n/es'
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

/**
 * Sequential navigation, as the index has to show it.
 *
 * The server is the only one that decides: `available: false` arrives already computed,
 * and the row's job is to stop pretending the lesson is reachable and to name what opens
 * it. The old padlocks did the deciding themselves and got it wrong; this row does not
 * decide anything.
 */
describe('<CourseIndex> when the course is walked in order', () => {
  it('dims a node the server has not opened yet, and says what opens it', () => {
    renderIndex([
      node({ id: 'n1', title: 'Primera', position: 1, done: true, available: true }),
      node({ id: 'n2', title: 'Segunda', position: 2, available: false }),
    ])

    expect(screen.getByText(es['nodelist.unavailable'])).toBeInTheDocument()
    // Still listed: the course does not look shorter than it is.
    expect(screen.getByText('Segunda')).toBeInTheDocument()
    expect(screen.getByText('Segunda').closest('li')).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByText('Primera').closest('li')).not.toHaveAttribute('aria-disabled')
  })

  it('says nothing at all while every node is available', () => {
    renderIndex([node({ id: 'n1', title: 'Primera', available: true })])

    expect(screen.queryByText(es['nodelist.unavailable'])).not.toBeInTheDocument()
  })
})
