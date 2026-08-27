/**
 * The §8.5 boundary, wired end to end: `ClickableSurface` + `UiSpecRenderer` +
 * the real blocks, over B1's dialect fixtures — now rendered by OpenUI's own
 * runtime, which is exactly why this file has to keep passing unchanged in
 * substance: the hit-test must not care who built the DOM.
 *
 * `ClickableSurface.test.tsx` proves the hit-test in isolation, with hand-built
 * markup. This file proves the thing that actually ships: that the five prose
 * blocks put `.entity` spans on screen, and that `QuizItemBlock` and
 * `CodeBlockBlock` do not — which is the difference between an explanation and a
 * free, uncounted hint on the correct answer.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactElement } from 'react'

import { ClickableSurface } from './ClickableSurface'
import { UiSpecRenderer } from './UiSpecRenderer'
import { validPrograms } from '../../test/fixtures/dsl'

vi.mock('../../api/client', () => ({
  post: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number
    constructor(status: number) {
      super(String(status))
      this.status = status
    }
  },
}))

const mockFetch = vi.fn()

function sseResponse(text: string) {
  const encoder = new TextEncoder()
  const events = [
    `event: token\ndata: ${JSON.stringify({ content: text })}\n\n`,
    `event: done\ndata: ${JSON.stringify({ explanation: text, cached: false })}\n\n`,
  ]
  let index = 0
  return Promise.resolve({
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: () =>
          index < events.length
            ? Promise.resolve({ done: false, value: encoder.encode(events[index++]) })
            : Promise.resolve({ done: true, value: undefined }),
      }),
    },
  })
}

function explainCalls() {
  return mockFetch.mock.calls.filter((call) => String(call[0]).includes('/explain'))
}

function lastExplainBody(): Record<string, unknown> {
  const init = explainCalls().at(-1)?.[1] as RequestInit | undefined
  return JSON.parse(String(init?.body)) as Record<string, unknown>
}

function renderLesson(program: string, ui?: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <ClickableSurface nodeId="node-1">
          {ui ?? <UiSpecRenderer program={program} nodeId="node-1" renderId="render-1" />}
        </ClickableSurface>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mockFetch.mockReset()
  mockFetch.mockImplementation(() => sseResponse('Devolver un producto comprado.'))
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('click-to-explain inside the kit blocks (§8.5)', () => {
  it('explains a word clicked in a TextContentBlock, with the paragraph as context', async () => {
    renderLesson(validPrograms.mixed_quiz)

    await userEvent.click(screen.getByText('devoluciones'))

    await waitFor(() => expect(explainCalls()).toHaveLength(1))
    const body = lastExplainBody()
    expect(body.term).toBe('devoluciones')
    expect(body.context).toBe('Las devoluciones se aceptan durante 30 dias naturales.')
    expect(body.node_id).toBe('node-1')
  })

  it('does NOT explain a word clicked in a quiz option', async () => {
    renderLesson(validPrograms.mixed_quiz)

    const option = screen.getByText('Ofrecer garantia del fabricante')
    // The option is inside the item's `data-no-explain`, and it was never
    // decorated in the first place: no `.entity`, so nothing hints otherwise.
    expect(option.closest('[data-no-explain]')).not.toBeNull()
    expect(option.querySelector('.entity')).toBeNull()

    await userEvent.click(option)

    expect(explainCalls()).toHaveLength(0)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('does NOT explain the quiz statement either', async () => {
    renderLesson(validPrograms.mixed_quiz)

    await userEvent.click(screen.getByText(/Un cliente vuelve el dia 32/))

    expect(explainCalls()).toHaveLength(0)
  })

  it('explains a step of a StepSequenceBlock, scoped to its own <li>', async () => {
    renderLesson(validPrograms.explanation_basic)

    await userEvent.click(screen.getByText('Escanear'))

    await waitFor(() => expect(explainCalls()).toHaveLength(1))
    expect(lastExplainBody().context).toBe('Escanear el ticket')
  })

  it('does NOT turn the step number into a term', async () => {
    const { container } = renderLesson(validPrograms.explanation_basic)

    // Matched by the opt-out rather than by position: `b0a4b93` moved the number into a
    // timeline column, so it is no longer a direct child of its `<li>`. Reading the text
    // back is what keeps this honest — the elements found have to *be* the four numbers.
    const markers = Array.from(container.querySelectorAll('li [data-no-explain]'))
    expect(markers.map((marker) => marker.textContent)).toEqual(['1', '2', '3', '4'])
    for (const marker of markers) {
      expect(marker.querySelector('.entity')).toBeNull()
      expect(marker).toHaveAttribute('aria-hidden', 'true')
    }
  })

  it('explains a table cell, scoped to that cell', async () => {
    renderLesson(validPrograms.table_nested)

    await userEvent.click(screen.getByText('Telefono'))

    await waitFor(() => expect(explainCalls()).toHaveLength(1))
    expect(lastExplainBody().context).toBe('Telefono')
  })

  it('explains a Callout, but not its tone label', async () => {
    const { container } = renderLesson(validPrograms.explanation_callout_first)

    const label = screen.getByText('Atención')
    expect(label.querySelector('.entity')).toBeNull()

    await userEvent.click(screen.getByText('garantia'))
    await waitFor(() => expect(explainCalls()).toHaveLength(1))
    expect(lastExplainBody().context).toBe(
      'Pasados 30 dias aplica la garantia del fabricante, no la devolucion.',
    )
    expect(container).toBeTruthy()
  })

  it('explains a Card title (§8.5: "titulos incluidos") and not the code inside it', async () => {
    renderLesson(validPrograms.card_nested)

    // The code sample is one opaque run, inside `data-no-explain`.
    const code = screen.getByText(/dias = \(hoy - ticket\)\.days/)
    expect(code.querySelector('.entity')).toBeNull()
    expect(code.closest('[data-no-explain]')).not.toBeNull()

    await userEvent.click(screen.getByText('Comprobacion'))

    await waitFor(() => expect(explainCalls()).toHaveLength(1))
    expect(lastExplainBody().term).toBe('Comprobacion')
    expect(lastExplainBody().context).toBe('Comprobacion del plazo')
  })

  it('gives each block exactly one tab stop, not one per word', () => {
    renderLesson(validPrograms.explanation_basic)

    // TextContent + StepSequence = two groups, and no word is tabbable (§8.2).
    const groups = screen.getAllByRole('group')
    expect(groups).toHaveLength(2)
    for (const group of groups) expect(group).toHaveAttribute('tabindex', '0')
    expect(screen.getByText('devoluciones')).not.toHaveAttribute('tabindex')
  })
})
