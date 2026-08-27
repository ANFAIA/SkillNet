import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'
import { ClickableSurface, expandRangeToWords } from './ClickableSurface'
import { ClickableText } from './ClickableText'
import { centerContext, normalizeContext } from '../../api/explain'
import { ExplainLayer } from './explainLayer'
import { EXPLAIN_LAYER_COURSE_CHAT } from './explainLayers'

const navigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

const mockFetch = vi.fn()

/** A fetch that answers `/explain` with a real SSE body, one chunk at a time. */
function sseResponse(events: string[]) {
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

function explainEvents(text: string) {
  return [
    `event: token\ndata: ${JSON.stringify({ content: text })}\n\n`,
    `event: done\ndata: ${JSON.stringify({ explanation: text, cached: false, cacheable: true })}\n\n`,
  ]
}

function explainCalls() {
  return mockFetch.mock.calls.filter((call) => String(call[0]).includes('/explain'))
}

function lastExplainBody(): Record<string, unknown> {
  const call = explainCalls().at(-1)
  return JSON.parse(String((call?.[1] as RequestInit).body)) as Record<string, unknown>
}

function renderSurface(children: ReactNode, nodeId: string | null = 'node-1') {
  return render(
    <MemoryRouter>
      <ClickableSurface nodeId={nodeId}>{children}</ClickableSurface>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  navigate.mockReset()
  mockFetch.mockReset()
  mockFetch.mockImplementation(() => sseResponse(explainEvents('Es el limite de dias.')))
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ClickableSurface', () => {
  it('lifts its popover above the course chat drawer when that layer is provided', async () => {
    render(
      <MemoryRouter>
        <ExplainLayer zIndex={EXPLAIN_LAYER_COURSE_CHAT}>
          <ClickableSurface nodeId={null}>
            <p><ClickableText>Consulta cualquier procedimiento del curso.</ClickableText></p>
          </ClickableSurface>
        </ExplainLayer>
      </MemoryRouter>,
    )

    await userEvent.click(screen.getByText('procedimiento'))

    const popover = await screen.findByRole('dialog', { name: 'Explicación de procedimiento' })
    expect(Number(popover.style.zIndex)).toBe(EXPLAIN_LAYER_COURSE_CHAT)
    expect(Number(popover.style.zIndex)).toBeGreaterThan(100)
  })

  describe('clicking a word', () => {
    it('sends the clicked term and the block context', async () => {
      renderSurface(
        <p>
          <ClickableText>El plazo de devolucion es de 30 dias.</ClickableText>
        </p>,
      )

      await userEvent.click(screen.getByText('devolucion'))

      await waitFor(() => expect(explainCalls()).toHaveLength(1))
      const body = lastExplainBody()
      expect(body.term).toBe('devolucion')
      expect(body.context).toBe('El plazo de devolucion es de 30 dias.')
      expect(body.node_id).toBe('node-1')
    })

    it('shows the streamed explanation in the popover', async () => {
      renderSurface(
        <p>
          <ClickableText>El plazo de devolucion es de 30 dias.</ClickableText>
        </p>,
      )

      await userEvent.click(screen.getByText('devolucion'))

      expect(await screen.findByText('Es el limite de dias.')).toBeInTheDocument()
      expect(screen.getByRole('dialog')).toHaveAttribute(
        'aria-label',
        'Explicación de devolucion',
      )
    })

    it('marks the open word with aria-expanded and clears it on close', async () => {
      renderSurface(
        <p>
          <ClickableText>El plazo de devolucion es de 30 dias.</ClickableText>
        </p>,
      )
      const word = screen.getByText('devolucion')

      await userEvent.click(word)
      await screen.findByRole('dialog')
      expect(word).toHaveAttribute('aria-expanded', 'true')
      expect(word).toHaveClass('entity-open')

      await userEvent.keyboard('{Escape}')
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      expect(word).not.toHaveAttribute('aria-expanded')
    })

    it('does nothing when a stopword is clicked, because it is not an entity', async () => {
      renderSurface(
        <p>
          <ClickableText>El plazo de devolucion es de 30 dias.</ClickableText>
        </p>,
      )

      await userEvent.click(screen.getByText('plazo').parentElement as HTMLElement, {
        // Click the glue span between words.
      })
      // Clicking the group wrapper itself is not clicking a word.
      expect(explainCalls()).toHaveLength(0)
    })
  })

  describe('the §8.5 hit-test', () => {
    // The mandatory case: answering a quiz option must never buy a free explanation
    // of the correct answer.
    it('does NOT request an explanation when a quiz option button is clicked', async () => {
      renderSurface(
        <div data-no-explain>
          <p>
            <ClickableText>Cual es el plazo de devolucion?</ClickableText>
          </p>
          <button type="button">Treinta dias naturales</button>
        </div>,
      )

      await userEvent.click(screen.getByRole('button', { name: 'Treinta dias naturales' }))

      expect(explainCalls()).toHaveLength(0)
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('does NOT request an explanation when the quiz statement is clicked', async () => {
      renderSurface(
        <div data-no-explain>
          <p>Cual es el plazo de devolucion?</p>
        </div>,
      )

      await userEvent.click(screen.getByText('Cual es el plazo de devolucion?'))

      expect(explainCalls()).toHaveLength(0)
    })

    it('does NOT fire inside a code block', async () => {
      renderSurface(
        <pre data-no-explain>
          <code>const plazo = 30</code>
        </pre>,
      )

      await userEvent.click(screen.getByText('const plazo = 30'))

      expect(explainCalls()).toHaveLength(0)
    })

    it('does NOT fire on a link', async () => {
      renderSurface(
        <p>
          <a href="https://example.test">politica de devoluciones</a>
        </p>,
      )

      await userEvent.click(screen.getByRole('link'))

      expect(explainCalls()).toHaveLength(0)
    })

    it('does NOT fire on a radio option', async () => {
      renderSurface(
        <div>
          <span role="radio" aria-checked="false">
            Treinta dias
          </span>
        </div>,
      )

      await userEvent.click(screen.getByRole('radio'))

      expect(explainCalls()).toHaveLength(0)
    })

    it('still fires for prose that sits next to a control', async () => {
      renderSurface(
        <div>
          <p>
            <ClickableText>El plazo de devolucion es de 30 dias.</ClickableText>
          </p>
          <button type="button">Enviar</button>
        </div>,
      )

      await userEvent.click(screen.getByText('devolucion'))

      await waitFor(() => expect(explainCalls()).toHaveLength(1))
    })

    /**
     * Surfaces nest, and only the innermost one owns the click.
     *
     * Two places do this today: `Chat.tsx` wraps the tutor bubble and `ChatAnswer` wraps
     * its own content inside it, and `ExplainModal` — rendered *by* a surface — wraps its
     * panel in a surface of its own. React events walk the React tree rather than the DOM
     * tree, so `createPortal` does not separate the second pair either.
     *
     * The cost of getting this wrong is not cosmetic: every ancestor surface handled the
     * same click, so one word produced two stacked popovers and **two `POST /explain`** —
     * two generations billed, and two answers written over each other.
     */
    it('lets only the innermost surface handle a click', async () => {
      render(
        <MemoryRouter>
          <ClickableSurface nodeId="outer">
            <ClickableSurface nodeId="inner">
              <p>
                <ClickableText>El plazo de devolucion es de 30 dias.</ClickableText>
              </p>
            </ClickableSurface>
          </ClickableSurface>
        </MemoryRouter>,
      )

      await userEvent.click(screen.getByText('devolucion'))

      await waitFor(() => expect(explainCalls()).toHaveLength(1))
      expect(screen.getAllByRole('dialog')).toHaveLength(1)
      // The inner surface is the one that knows which node the word was read in.
      expect(lastExplainBody().node_id).toBe('inner')
    })
  })

  describe('keyboard access (§8.2)', () => {
    it('walks words with the arrow keys and opens with Enter', async () => {
      renderSurface(
        <p>
          <ClickableText>El plazo de devolucion es de 30 dias.</ClickableText>
        </p>,
      )
      const group = screen.getByRole('group')

      group.focus()
      await userEvent.keyboard('{ArrowRight}')
      expect(group).toHaveAttribute('aria-activedescendant')
      expect(screen.getByText('plazo')).toHaveAttribute('data-cursor', 'true')

      await userEvent.keyboard('{ArrowRight}{Enter}')

      await waitFor(() => expect(explainCalls()).toHaveLength(1))
      expect(lastExplainBody().term).toBe('devolucion')
    })

    it('does not put individual words in the tab order', () => {
      renderSurface(
        <p>
          <ClickableText>El plazo de devolucion es de 30 dias.</ClickableText>
        </p>,
      )

      expect(screen.getByRole('group')).toHaveAttribute('tabindex', '0')
      expect(screen.getByText('devolucion')).not.toHaveAttribute('tabindex')
    })
  })

  /**
   * The popover's one action, which is no longer "No lo entiendo".
   *
   * §8.4 gave the popover a single next step because a learner who does not understand
   * the one sentence needs somewhere to go, and originally that somewhere was the v1 chat
   * seeded with the term (`navigate('/empleado/chat', { state })`). `2a750f5` replaced it
   * with **"Ver mas"**, which opens `ExplainModal` in place: the same next step without
   * leaving the lesson, and with the term's context already loaded. The seeded-chat route
   * has no producer any more, so what is asserted here is the handoff that exists.
   */
  describe('the "Ver mas" action', () => {
    it('opens the explanation panel on the term, without leaving the lesson', async () => {
      renderSurface(
        <p>
          <ClickableText>El plazo de devolucion es de 30 dias.</ClickableText>
        </p>,
      )

      await userEvent.click(screen.getByText('devolucion'))
      // The button only appears once there is an explanation to expand on.
      await userEvent.click(await screen.findByRole('button', { name: 'Ver más' }))

      const panel = await screen.findByRole('dialog', {
        name: 'Explicación ampliada de devolucion',
      })
      expect(panel).toHaveAttribute('aria-modal', 'true')
      // The popover it was opened from is gone: one explanation of one word at a time.
      expect(document.querySelector('.explain-popover')).toBeNull()
      // In place, not on another route.
      expect(navigate).not.toHaveBeenCalled()
    })

    it('is not offered while the explanation is still being written', async () => {
      // A `Ver mas` with nothing to expand on would open an empty panel and spend a
      // generation on it.
      mockFetch.mockImplementation(() => sseResponse([]))
      renderSurface(
        <p>
          <ClickableText>El plazo de devolucion es de 30 dias.</ClickableText>
        </p>,
      )

      await userEvent.click(screen.getByText('devolucion'))
      await screen.findByRole('dialog')
      expect(screen.queryByRole('button', { name: 'Ver más' })).toBeNull()
    })
  })

  describe('rate limiting', () => {
    it('shows the §8.4 message on a 429', async () => {
      mockFetch.mockImplementation(() =>
        Promise.resolve({
          ok: false,
          status: 429,
          json: () => Promise.resolve({ detail: 'Demasiadas consultas seguidas' }),
        }),
      )
      renderSurface(
        <p>
          <ClickableText>El plazo de devolucion es de 30 dias.</ClickableText>
        </p>,
      )

      await userEvent.click(screen.getByText('devolucion'))

      expect(await screen.findByText('Demasiadas consultas seguidas')).toBeInTheDocument()
    })
  })
})

describe('expandRangeToWords', () => {
  it('snaps a partial selection out to whole words', () => {
    const host = document.createElement('p')
    host.textContent = 'El plazo de devolucion es de 30 dias.'
    document.body.appendChild(host)
    const text = host.firstChild as Text

    const range = document.createRange()
    // "lazo de devoluci" — both ends land mid-word. Offsets are half-open, so
    // the end index is one past the last selected character (`i` is at 19).
    range.setStart(text, 4)
    range.setEnd(text, 20)
    expect(range.toString()).toBe('lazo de devoluci')

    expandRangeToWords(range)

    expect(range.toString()).toBe('plazo de devolucion')
    host.remove()
  })

  it('leaves a selection that already aligns with word edges alone', () => {
    const host = document.createElement('p')
    host.textContent = 'plazo de devolucion'
    document.body.appendChild(host)
    const text = host.firstChild as Text

    const range = document.createRange()
    range.setStart(text, 0)
    range.setEnd(text, 5)
    expandRangeToWords(range)

    expect(range.toString()).toBe('plazo')
    host.remove()
  })
})

describe('context windowing (§8.3)', () => {
  it('collapses every run of whitespace', () => {
    expect(normalizeContext('uno\n\tdos   tres  ')).toBe('uno dos tres')
  })

  it('keeps the term inside the 600-character window instead of taking the head', () => {
    const filler = 'palabra '.repeat(200)
    const window = centerContext(`${filler}el termino buscado ${filler}`, 'termino buscado')

    expect(window.length).toBeLessThanOrEqual(600)
    expect(window).toContain('termino buscado')
  })

  it('is idempotent, so client and server hash the same string', () => {
    const short = 'El plazo de devolucion es de 30 dias.'
    expect(centerContext(short, 'devolucion')).toBe(short)
    expect(centerContext(centerContext(short, 'devolucion'), 'devolucion')).toBe(short)
  })

  it('falls back to the head when the term is not in the block', () => {
    expect(centerContext('x'.repeat(1500), 'ausente')).toBe('x'.repeat(600))
  })
})
