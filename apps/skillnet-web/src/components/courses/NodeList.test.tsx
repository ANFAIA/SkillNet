/**
 * The node map when the course is walked in order.
 *
 * `available` used to arrive `true` for every node and nothing read it, so a server that
 * started saying `false` would have changed nothing on screen: the row stayed a link and
 * opening it bought a 403 with no sentence attached. What the list owes the learner is
 * the two things it could not say — this one is not open yet, and here is what opens it.
 *
 * The rule itself is never reproduced here. `available` is the server's answer (see
 * `nodeIsAvailable`), which is exactly what the padlocks removed on 2026-08-28 got wrong
 * by deriving it client-side.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { NodeList } from './NodeList'
import { es } from '../../i18n/es'
import type { LearningNode, NodeList as NodeListRead } from '../../types'

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

function renderList(nodes: LearningNode[], at = '/empleado/curso/c1') {
  const data: NodeListRead = {
    course_id: 'c1',
    delivery_mode: 'dynamic',
    schema_version: 1,
    nodes,
    next_node_id: nodes[0]?.id ?? null,
    can_complete: false,
    blocked_by: [],
    progress_percent: 50,
  }
  return render(
    <MemoryRouter initialEntries={[at]}>
      <NodeList data={data} />
    </MemoryRouter>,
  )
}

describe('<NodeList> and `available`', () => {
  it('links every node while the course is navigated freely', () => {
    renderList([
      node({ id: 'n1', title: 'Primera', position: 1 }),
      node({ id: 'n2', title: 'Segunda', position: 2 }),
    ])

    expect(screen.getAllByRole('link')).toHaveLength(2)
    expect(screen.queryByText(es['nodelist.unavailable'])).not.toBeInTheDocument()
  })

  it('does not offer a way into a node the server has not opened, and says why', () => {
    renderList([
      node({ id: 'n1', title: 'Primera', position: 1, done: true }),
      node({ id: 'n2', title: 'Segunda', position: 2, available: false }),
    ])

    // The row is still there — a hidden lesson makes the course look shorter than it is.
    expect(screen.getByText('Segunda')).toBeInTheDocument()
    expect(screen.getByText(es['nodelist.unavailable'])).toBeInTheDocument()

    // And it is not a link: an anchor that goes nowhere is still announced as a way in.
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(1)
    expect(links[0]).toHaveAttribute('href', '/empleado/curso/c1/nodo/n1')
    expect(screen.getByTestId('node-row-unavailable')).toHaveAttribute('aria-disabled', 'true')
  })

  it('treats a payload with no `available` field as available, not as closed', () => {
    const legacy = node({ id: 'n1', title: 'Primera' })
    delete (legacy as Partial<LearningNode>).available

    renderList([legacy])

    expect(screen.getAllByRole('link')).toHaveLength(1)
    expect(screen.queryByText(es['nodelist.unavailable'])).not.toBeInTheDocument()
  })
})

/**
 * The map is the same component on the course screen and inside a lesson, and it used to
 * build its links by trimming the current URL — which is the course only on the first of
 * those two. From a lesson every row pointed at `.../nodo/<open>/nodo/<wanted>`, no route
 * matched, and the catch-all took the learner to their dashboard.
 */
describe('<NodeList> links, from wherever it is opened', () => {
  const two = [
    node({ id: 'n1', title: 'Primera', position: 1, done: true }),
    node({ id: 'n2', title: 'Segunda', position: 2 }),
  ]

  it('points at the lesson from the course screen', () => {
    renderList(two)

    expect(screen.getAllByRole('link').map((a) => a.getAttribute('href'))).toEqual([
      '/empleado/curso/c1/nodo/n1',
      '/empleado/curso/c1/nodo/n2',
    ])
  })

  it('points at the lesson from inside another lesson', () => {
    renderList(two, '/empleado/curso/c1/nodo/n1')

    expect(screen.getAllByRole('link').map((a) => a.getAttribute('href'))).toEqual([
      '/empleado/curso/c1/nodo/n1',
      '/empleado/curso/c1/nodo/n2',
    ])
  })

  it('stays on the admin test drive, from the course and from inside a lesson', () => {
    const { unmount } = renderList(two, '/admin/probar-curso/c1')
    expect(screen.getAllByRole('link')[1]).toHaveAttribute(
      'href',
      '/admin/probar-curso/c1/nodo/n2',
    )
    unmount()

    renderList(two, '/admin/probar-curso/c1/nodo/n1')
    expect(screen.getAllByRole('link')[1]).toHaveAttribute(
      'href',
      '/admin/probar-curso/c1/nodo/n2',
    )
  })
})
