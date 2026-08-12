/**
 * The "Ver mas" modal (§8.6).
 *
 * Every case here is a bug that shipped: the modal was assembled from the right pieces
 * but wired so that nothing *inside* it was click-to-explain. The popover opened behind
 * the card, follow-up answers had no handler over them at all, and the card had no
 * Escape and no focus trap.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { ExplainModal } from './ExplainModal'
import { EXPLAIN_LAYER_MODAL } from './explainLayers'

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => vi.fn() }
})

const mockFetch = vi.fn()

/** An SSE body delivered one chunk per `read()`, like the real reader. */
function sse(events: string[]) {
  const encoder = new TextEncoder()
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

/** A `/chat` tutor answer as prose: no `ui` event, so the panel falls back to markdown. */
function chatProse(text: string) {
  return sse([`event: token\ndata: ${JSON.stringify({ content: text })}\n\n`])
}

function explainProse(text: string) {
  return sse([
    `event: token\ndata: ${JSON.stringify({ content: text })}\n\n`,
    `event: done\ndata: ${JSON.stringify({ explanation: text, cached: false, cacheable: true })}\n\n`,
  ])
}

const PANEL = 'La merma es el producto que se pierde antes de venderse.'
const GLOSS = 'Producto no vendible.'

function explainCalls() {
  return mockFetch.mock.calls.filter((call) => String(call[0]).includes('/explain'))
}

function lastExplainTerm(): string {
  const init = explainCalls().at(-1)?.[1] as RequestInit | undefined
  return (JSON.parse(String(init?.body)) as { term: string }).term
}

function renderModal(onClose = vi.fn()) {
  render(
    <MemoryRouter>
      <ExplainModal
        term="merma"
        context="Controlar la merma es parte del cierre de caja."
        nodeId="node-1"
        open
        onClose={onClose}
      />
    </MemoryRouter>,
  )
  return { onClose }
}

/** The card, addressed by the name only it answers to. */
function card() {
  return screen.getByRole('dialog', { name: /Explicacion ampliada de/ })
}

/** The inline gloss bubble, which is the *other* dialog on screen. */
function popover() {
  return document.querySelector('.explain-popover') as HTMLElement | null
}

beforeEach(() => {
  mockFetch.mockReset()
  mockFetch.mockImplementation((url: string) =>
    String(url).includes('/explain') ? explainProse(GLOSS) : chatProse(PANEL),
  )
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ExplainModal', () => {
  it('uses the shared tutor endpoint, never the admin-only assistant', async () => {
    renderModal()
    await screen.findByText('producto')

    const urls = mockFetch.mock.calls.map(([url]) => String(url))
    expect(urls).toContain('/api/v1/chat')
    expect(urls).not.toContain('/api/v1/chat/admin')
  })

  describe('clicking a word inside the panel', () => {
    it('opens a popover, which is the whole point of the modal', async () => {
      renderModal()

      await userEvent.click(await screen.findByText('producto'))

      await waitFor(() => expect(explainCalls()).toHaveLength(1))
      expect(lastExplainTerm()).toBe('producto')
      expect(await screen.findByText(GLOSS)).toBeInTheDocument()
    })

    /**
     * The reported bug. The popover is portaled to `body` at the stylesheet's `z-index:
     * 50`, and the card paints at `z-[101]` — so the bubble opened *behind* an opaque
     * card and clicking a word looked like it did nothing at all.
     */
    it('paints the popover above the card, not behind it', async () => {
      renderModal()

      await userEvent.click(await screen.findByText('producto'))
      await screen.findByText(GLOSS)

      const bubble = popover()
      expect(bubble).not.toBeNull()
      expect(Number(bubble!.style.zIndex)).toBe(EXPLAIN_LAYER_MODAL)
      // The card's own layer, which the bubble has to clear.
      expect(Number(bubble!.style.zIndex)).toBeGreaterThan(101)
    })

    it('does not explain the term the panel is already about', async () => {
      renderModal()
      await screen.findByText('producto')

      // "merma" is a word *in* the panel as well as the heading above it — the span,
      // not the `<h2>`, is what a reader would click.
      const span = Array.from(document.querySelectorAll<HTMLElement>('.entity')).find(
        (el) => el.textContent === 'merma',
      )
      expect(span).toBeDefined()
      await userEvent.click(span!)

      expect(explainCalls()).toHaveLength(0)
    })
  })

  describe('the follow-up thread', () => {
    /**
     * The second half of the bug: the surface used to live inside the explanation
     * panel, so a follow-up answer rendered *outside* it and every word in it was dead
     * text. One surface now covers the panel and the thread together.
     */
    it('makes words in a follow-up answer clickable too', async () => {
      renderModal()
      await screen.findByText('producto')

      await userEvent.type(
        screen.getByPlaceholderText('Pregunta algo mas...'),
        'Como se calcula?{Enter}',
      )

      // The answer uses the same prose mock, so its words are the panel's words.
      await waitFor(() => expect(screen.getAllByText('pierde').length).toBeGreaterThan(1))
      await userEvent.click(screen.getAllByText('pierde')[1])

      await waitFor(() => expect(explainCalls()).toHaveLength(1))
      expect(lastExplainTerm()).toBe('pierde')
    })

    it('drops the thread when the reader drills into a new term', async () => {
      renderModal()
      await screen.findByText('producto')

      await userEvent.type(
        screen.getByPlaceholderText('Pregunta algo mas...'),
        'Como se calcula?{Enter}',
      )
      await screen.findByText('Como se calcula?')

      // The answer repeats the panel's prose, so pick the panel's own copy.
      await userEvent.click(screen.getAllByText('producto')[0])
      await screen.findByText(GLOSS)
      await userEvent.click(screen.getByRole('button', { name: 'Ver mas' }))

      // The panel is now about "producto"; the question about "merma" is gone.
      await waitFor(() =>
        expect(screen.queryByText('Como se calcula?')).not.toBeInTheDocument(),
      )
    })
  })

  describe('"Ver mas" from inside the modal', () => {
    it('drills down in place instead of stacking a second modal', async () => {
      renderModal()

      await userEvent.click(await screen.findByText('producto'))
      await screen.findByText(GLOSS)
      await userEvent.click(screen.getByRole('button', { name: 'Ver mas' }))

      // One card, now titled with the new term, plus a breadcrumb back to the old one.
      await waitFor(() =>
        expect(screen.getAllByRole('dialog', { name: /Explicacion ampliada de/ })).toHaveLength(1),
      )
      expect(card()).toHaveAccessibleName('Explicacion ampliada de producto')
      expect(screen.getByRole('button', { name: 'Volver' })).toBeInTheDocument()
    })
  })

  describe('keyboard (§8.2)', () => {
    it('closes on Escape', async () => {
      const { onClose } = renderModal()
      await screen.findByText('producto')

      await userEvent.keyboard('{Escape}')

      expect(onClose).toHaveBeenCalledTimes(1)
    })

    /**
     * Order matters: one Escape must dismiss the bubble the reader is looking at, not
     * tear down the whole panel underneath it.
     */
    it('closes an open popover first, leaving the modal up', async () => {
      const { onClose } = renderModal()

      await userEvent.click(await screen.findByText('producto'))
      await screen.findByText(GLOSS)

      await userEvent.keyboard('{Escape}')

      await waitFor(() => expect(popover()).toBeNull())
      expect(onClose).not.toHaveBeenCalled()
      expect(card()).toBeInTheDocument()

      // The second Escape now reaches the modal.
      await userEvent.keyboard('{Escape}')
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('keeps Tab inside the card', async () => {
      renderModal()
      await screen.findByText('producto')

      // Focus starts on the close button; walking forward must never leave the card.
      for (let step = 0; step < 8; step += 1) {
        await userEvent.tab()
        expect(card().contains(document.activeElement)).toBe(true)
      }
    })
  })
})
