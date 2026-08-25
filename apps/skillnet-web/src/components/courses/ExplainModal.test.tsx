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
function chatProse(text: string, sessionId = 'session-1') {
  return sse([
    `event: token\ndata: ${JSON.stringify({ content: text })}\n\n`,
    `event: done\ndata: ${JSON.stringify({ session_id: sessionId })}\n\n`,
  ])
}

function explainProse(text: string) {
  return sse([
    `event: token\ndata: ${JSON.stringify({ content: text })}\n\n`,
    `event: done\ndata: ${JSON.stringify({ explanation: text, cached: false, cacheable: true })}\n\n`,
  ])
}

/**
 * A `/chat` tutor answer that lays out: the DSL streams as `token` events and the
 * compiled program lands in a trailing `ui` event — the shape the modal must render.
 */
function chatProgram(program: string, sessionId = 'session-1') {
  return sse([
    `event: token\ndata: ${JSON.stringify({ content: program })}\n\n`,
    `event: done\ndata: ${JSON.stringify({ session_id: sessionId })}\n\n`,
    `event: ui\ndata: ${JSON.stringify({ program })}\n\n`,
  ])
}

/**
 * The reported-bug shape: the DSL streams as tokens but the `ui` event never lands
 * (layout skipped, the program failed the gate, connection dropped). The accumulated
 * tokens are raw OpenUI Lang — they must never be shown as raw DSL, but their string
 * literals are the prose the model wrote, so the modal degrades to that plain text.
 */
function chatRawDsl(program: string) {
  return sse([`event: token\ndata: ${JSON.stringify({ content: program })}\n\n`])
}

/** A `/chat` answer that streams nothing at all: no tokens, no `ui` event. */
function chatNothing() {
  return sse([])
}

const PROGRAM = [
  'root = Stack([intro, pasos], "md")',
  'intro = TextContent("Consulta siempre la ficha del producto.", "lead")',
  'pasos = StepSequence("Atender una consulta de alergenos", ["Escucha la pregunta", "Consulta la ficha"])',
].join('\n')

const PANEL = 'La merma es el producto que se pierde antes de venderse.'
const GLOSS = 'Producto no vendible.'
const RETRY = 'No se pudo generar la explicacion. Prueba de nuevo.'

function explainCalls() {
  return mockFetch.mock.calls.filter((call) => String(call[0]).includes('/explain'))
}

/** A prose answer whose `done` event is held back to exercise the session-ready gate. */
function chatProseWithDelayedDone(text: string, sessionId: string) {
  const encoder = new TextEncoder()
  let readIndex = 0
  let releaseDone!: () => void
  const doneGate = new Promise<void>((resolve) => {
    releaseDone = resolve
  })
  return {
    response: Promise.resolve({
      ok: true,
      status: 200,
      body: {
        getReader: () => ({
          read: async () => {
            if (readIndex === 0) {
              readIndex += 1
              return {
                done: false,
                value: encoder.encode(
                  `event: token\ndata: ${JSON.stringify({ content: text })}\n\n`,
                ),
              }
            }
            if (readIndex === 1) {
              readIndex += 1
              await doneGate
              return {
                done: false,
                value: encoder.encode(
                  `event: done\ndata: ${JSON.stringify({ session_id: sessionId })}\n\n`,
                ),
              }
            }
            return { done: true, value: undefined }
          },
        }),
      },
    }),
    releaseDone,
  }
}

function chatCalls() {
  return mockFetch.mock.calls.filter((call) => String(call[0]) === '/api/v1/chat')
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

  it('marks the expanded Curio request and sends node plus selection context', async () => {
    renderModal()
    await screen.findByText('producto')

    const init = chatCalls()[0][1] as RequestInit
    const body = JSON.parse(String(init.body)) as {
      message: string
      context: Record<string, unknown>
    }

    expect(body.message).not.toContain('Hazlo visual')
    expect(body.context).toEqual({
      surface: 'curio_explain',
      selected_term: 'merma',
      selection_context: 'Controlar la merma es parte del cierre de caja.',
      node_id: 'node-1',
    })
  })

  /**
   * The reported bug: the panel streams an OpenUI program from `/chat` and must RENDER
   * the compiled blocks (the same `UiSpecRenderer` gate path chat and lessons use), never
   * print the raw `root = Stack(...)` DSL as text.
   */
  describe('rendering the OpenUI program', () => {
    it('renders the compiled blocks and never leaks the raw DSL', async () => {
      mockFetch.mockImplementation((url: string) =>
        String(url).includes('/explain') ? explainProse(GLOSS) : chatProgram(PROGRAM),
      )
      renderModal()

      // The kit blocks paint through the shared renderer.
      await waitFor(() =>
        expect(document.querySelector('[data-ui-format="explanation"]')).not.toBeNull(),
      )
      expect(card().textContent).toContain('Atender una consulta de alergenos')
      expect(card().textContent).toContain('Consulta siempre la ficha del producto.')
      // The StepSequence the program asked for, as a real list.
      expect(card().querySelectorAll('ol > li').length).toBeGreaterThanOrEqual(2)
      // The raw DSL must not survive anywhere in the card.
      expect(card().textContent).not.toContain('root = Stack')
    })

    it('degrades to the salvaged prose without leaking the DSL when no valid program lands', async () => {
      mockFetch.mockImplementation((url: string) =>
        String(url).includes('/explain') ? explainProse(GLOSS) : chatRawDsl(PROGRAM),
      )
      renderModal()

      // The human text the DSL literals carried is shown as a real answer...
      await screen.findByText('Atender')
      expect(card().textContent).toContain('Escucha')
      expect(card().textContent).toContain('ficha')
      // ...but never the raw scaffolding, and never the error.
      expect(card().textContent).not.toContain('root = Stack')
      expect(card().textContent).not.toContain('StepSequence')
      expect(card().textContent).not.toContain(RETRY)
      expect(document.querySelector('[data-ui-format]')).toBeNull()
    })

    it('shows the error only when the answer is genuinely empty', async () => {
      mockFetch.mockImplementation((url: string) =>
        String(url).includes('/explain') ? explainProse(GLOSS) : chatNothing(),
      )
      renderModal()

      // Nothing streamed and no program: the retry fallback is the honest outcome.
      await screen.findByText(RETRY)
      expect(document.querySelector('[data-ui-format]')).toBeNull()
    })
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
    it('blocks the composer until the initial done event provides a session', async () => {
      const delayed = chatProseWithDelayedDone(PANEL, 'delayed-session')
      let chatRequest = 0
      mockFetch.mockImplementation((url: string) => {
        if (String(url).includes('/explain')) return explainProse(GLOSS)
        chatRequest += 1
        return chatRequest === 1
          ? delayed.response
          : chatProse(PANEL, 'delayed-session')
      })
      renderModal()
      await waitFor(() => expect(chatCalls()).toHaveLength(1))

      const waitingComposer = screen.getByPlaceholderText('Generando explicacion')
      expect(waitingComposer).toBeDisabled()
      await userEvent.type(waitingComposer, 'Esto no debe enviarse{Enter}')
      expect(chatCalls()).toHaveLength(1)

      delayed.releaseDone()
      const composer = await screen.findByPlaceholderText('Pregunta algo mas...')
      await waitFor(() => expect(composer).not.toBeDisabled())
      await userEvent.type(composer, 'Ahora si{Enter}')
      await waitFor(() => expect(chatCalls()).toHaveLength(2))

      const body = JSON.parse(String((chatCalls()[1][1] as RequestInit).body)) as {
        session_id?: string
      }
      expect(body.session_id).toBe('delayed-session')
    })

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

      const lastChatCall = chatCalls().at(-1)
      expect(lastChatCall).toBeDefined()
      const followUp = JSON.parse(String((lastChatCall![1] as RequestInit).body)) as {
        context: Record<string, unknown>
      }
      expect(followUp.context).toMatchObject({
        surface: 'curio_explain',
        selected_term: 'merma',
        node_id: 'node-1',
      })
      expect(
        JSON.parse(String((lastChatCall![1] as RequestInit).body)).session_id,
      ).toBe('session-1')
    })

    it('renders follow-up GenUI and never exposes its streamed DSL', async () => {
      let chatRequest = 0
      mockFetch.mockImplementation((url: string) => {
        if (String(url).includes('/explain')) return explainProse(GLOSS)
        chatRequest += 1
        return chatRequest === 1
          ? chatProse(PANEL, 'curio-session')
          : chatProgram(PROGRAM, 'curio-session')
      })
      renderModal()
      await screen.findByText('producto')

      await userEvent.type(
        screen.getByPlaceholderText('Pregunta algo mas...'),
        'Puedes explicarlo por pasos?{Enter}',
      )

      await waitFor(() =>
        expect(card().querySelectorAll('[data-ui-format="explanation"]')).toHaveLength(1),
      )
      expect(card().textContent).toContain('Atender una consulta de alergenos')
      expect(card().textContent).not.toContain('root = Stack')
      expect(card().textContent).not.toContain('StepSequence(')

      const followUpCall = chatCalls()[1]
      const body = JSON.parse(String((followUpCall[1] as RequestInit).body)) as {
        session_id?: string
      }
      expect(body.session_id).toBe('curio-session')
    })

    it('drops the prior session when drilling into another term', async () => {
      let chatRequest = 0
      mockFetch.mockImplementation((url: string) => {
        if (String(url).includes('/explain')) return explainProse(GLOSS)
        chatRequest += 1
        return chatProse(PANEL, chatRequest === 1 ? 'session-merma' : 'session-producto')
      })
      renderModal()
      await screen.findByText('producto')

      await userEvent.click(screen.getAllByText('producto')[0])
      await screen.findByText(GLOSS)
      await userEvent.click(screen.getByRole('button', { name: 'Ver mas' }))
      await waitFor(() => expect(chatCalls()).toHaveLength(2))

      await userEvent.type(
        screen.getByPlaceholderText('Pregunta algo mas...'),
        'Y esto como encaja?{Enter}',
      )
      await waitFor(() => expect(chatCalls()).toHaveLength(3))

      const body = JSON.parse(String((chatCalls()[2][1] as RequestInit).body)) as {
        session_id?: string
      }
      expect(body.session_id).toBe('session-producto')
      expect(body.session_id).not.toBe('session-merma')
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

    /**
     * El bug reportado: "si intentas continuar la conversacion, la respuesta que te da la
     * IA no se renderiza". Una respuesta que llega vacia —el modelo escribio un programa,
     * el validador lo rechazo y entonces no hay ni programa ni prosa de la que tirar— no
     * puede quedarse en una burbuja en blanco, que es indistinguible de "no ha llegado".
     */
    it('nunca deja la burbuja en blanco cuando la respuesta llega vacia', async () => {
      let chatRequest = 0
      mockFetch.mockImplementation((url: string) => {
        if (String(url).includes('/explain')) return explainProse(GLOSS)
        chatRequest += 1
        return chatRequest === 1 ? chatProse(PANEL) : chatNothing()
      })
      renderModal()
      await screen.findByText('producto')

      await userEvent.type(
        screen.getByPlaceholderText('Pregunta algo mas...'),
        'Y esto?{Enter}',
      )
      await waitFor(() => expect(chatCalls()).toHaveLength(2))

      await waitFor(() => expect(screen.getByText(RETRY)).toBeInTheDocument())
    })

    /**
     * La otra mitad: preguntar otra vez aborta el stream anterior, y ese mensaje sigue en
     * pantalla. Si el abort no lo cierra, se queda con los tres puntos para siempre.
     */
    it('cierra la respuesta anterior cuando una pregunta nueva la aborta', async () => {
      const delayed = chatProseWithDelayedDone(PANEL, 'session-1')
      let chatRequest = 0
      mockFetch.mockImplementation((url: string) => {
        if (String(url).includes('/explain')) return explainProse(GLOSS)
        chatRequest += 1
        if (chatRequest === 1) return chatProse(PANEL)
        if (chatRequest === 2) return delayed.response
        return chatProse('la segunda respuesta')
      })
      renderModal()
      await screen.findByText('producto')

      const composer = screen.getByPlaceholderText('Pregunta algo mas...')
      await userEvent.type(composer, 'Primera?{Enter}')
      await waitFor(() => expect(chatCalls()).toHaveLength(2))

      // La segunda pregunta aborta el stream de la primera.
      await userEvent.type(composer, 'Segunda?{Enter}')
      await waitFor(() => expect(chatCalls()).toHaveLength(3))
      delayed.releaseDone()

      // Como maximo una respuesta puntea a la vez: la que de verdad esta en vuelo.
      await waitFor(() =>
        expect(card().querySelectorAll('.typing-dots').length).toBeLessThanOrEqual(1),
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
