import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AdminChat } from './Chat'

/**
 * The admin assistant as a *screen*, driven by the bytes the server really sends.
 *
 * This surface used to render `ChatMarkdown` directly, on the grounds that
 * `_should_lay_out` in `chat_service.py` excluded `admin` turns outright. That
 * exclusion is gone: an admin turn now emits a `ui` event exactly like a tutor turn,
 * and the strongest case for blocks in the whole product lives here — *"como van mis
 * empleados"* is five people and four columns, which is a table in every other tool
 * an administrator uses.
 *
 * `api/chat.ts` never needed a change for that (one hook, one parser, the endpoint is
 * only a URL fragment) — which is precisely the failure mode this file exists to
 * catch. The `ui` event landing on the message object was already true while the
 * bubble threw it away, so every assertion below reads the DOM after a full SSE turn.
 *
 * ## One phase, no notice
 *
 * The admin turn used to be two-phase like the tutor's: prose, `layout_start`, a second
 * LLM call, `ui`. `7a48fa5` made it **single-phase** — the admin prompt writes OpenUI
 * Lang itself, and `chat_service.py` only validates what already streamed, so
 * `_should_lay_out` is now gated on `agent_type == "tutor"` and this endpoint never
 * emits `layout_start` again. The "Dando formato..." notice these tests used to wait on
 * went with it (`cad48aa`), and rightly: there is no second call to wait for. The frames
 * below are therefore the ones the server really writes, and the mid-turn sync point is
 * the prose itself.
 */

const mockFetch = vi.fn()

/** The shape the question asks for: an admin turn that earns a table. */
const PROGRAM = [
  'root = Stack([intro, tabla], "md")',
  'intro = TextContent("Tres de cinco empleados van con retraso.", "lead")',
  'tabla = Table(["Empleado", "Curso", "Progreso"], [["Noa", "Alergenos", "80%"], ["Iker", "Alergenos", "20%"]])',
].join('\n')

/** What the gate exists to refuse, and what the server would never emit. */
const REACTIVE_PROGRAM = [
  'root = Stack([intro], "md")',
  'intro = TextContent("Datos del equipo", "lead")',
  'z = Query("leak_everything", {})',
].join('\n')

/** Real admin output: markdown, because that is what the prompt produces. */
const PROSE = [
  'Asi va tu equipo ahora mismo:',
  '',
  '- **Noa** va por el 80% de Alergenos.',
  '- *Iker* se ha quedado en el 20%.',
].join('\n')

function event(type: string, data: unknown) {
  return `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`
}

function tokens(text: string) {
  return (text.match(/\S+\s*/g) ?? []).map((chunk) => event('token', { content: chunk }))
}

/**
 * `frames` stream immediately; `tail` is held until `release()` is called.
 *
 * Validating the streamed text and persisting the program still costs a round trip after
 * `done`, and that gap is where the interesting states live — the composer is already
 * back, the admin is reading prose, the program has not landed. Holding it makes those
 * states assertable instead of a race against the reader draining on its own.
 *
 * `drained` resolves once the reader has been told the body is over, which is the only
 * honest sync point for a `ui` event that changes **nothing** on screen: a program our
 * gate refuses leaves the same prose in place, so waiting for a DOM change would wait
 * forever and asserting immediately would pass before the event was ever read.
 */
function stream(frames: string[], tail: string[] = []) {
  const encoder = new TextEncoder()
  let release: () => void = () => {}
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  let markDrained: () => void = () => {}
  const drained = new Promise<void>((resolve) => {
    markDrained = resolve
  })
  let index = 0
  mockFetch.mockImplementation(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      body: {
        getReader: () => ({
          read: async () => {
            if (index < frames.length) {
              return { done: false, value: encoder.encode(frames[index++]) }
            }
            if (tail.length > 0 && index === frames.length) {
              await held
              index += 1
              return { done: false, value: encoder.encode(tail.join('')) }
            }
            markDrained()
            return { done: true, value: undefined }
          },
        }),
      },
    }),
  )
  return { release: () => release(), drained }
}

async function ask(question = 'como van mis empleados') {
  const user = userEvent.setup()
  await user.type(screen.getByPlaceholderText(/consulta/i), question)
  await user.keyboard('{Enter}')
}

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
  Element.prototype.scrollIntoView = vi.fn()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('admin Chat', () => {
  it('replaces the prose with the kit program when the layout lands', async () => {
    const { release } = stream(
      [
        event('grounding', { grounding: 'document' }),
        event('org_data', {
          employees: 5,
          courses: 2,
          documents: 9,
          generated_at: '2026-07-27T10:00:00Z',
        }),
        ...tokens(PROSE),
        event('done', { message_id: 'm1' }),
      ],
      [event('ui', { program: PROGRAM, format: 'explanation' })],
    )

    const { container } = render(<AdminChat />)
    await ask()

    // Mid-turn: the answer is complete, the program has not landed. The admin reads prose.
    // `textContent`, not `getByText().tagName`: §8.5 wraps every word in its own span so
    // the explain popover has an anchor, so the emphasised run is no longer a text node.
    await waitFor(() => expect(container.querySelector('strong')?.textContent).toBe('Noa'))
    expect(container.querySelector('[data-ui-format]')).toBeNull()
    // `org_data` is parsed by nobody and breaks nothing — the handler ignores it.
    expect(container.textContent).not.toContain('generated_at')

    release()

    await waitFor(() =>
      expect(container.querySelector('[data-ui-format="explanation"]')).not.toBeNull(),
    )
    // A real table, not four paragraphs pretending to be one.
    expect(container.querySelectorAll('table thead th')).toHaveLength(3)
    expect(container.querySelectorAll('table tbody tr')).toHaveLength(2)
    expect(container.textContent).toContain('Tres de cinco empleados van con retraso.')

    // The prose was the streaming phase and nothing more: blocks or prose, never both.
    expect(container.textContent).not.toContain('se ha quedado en el 20%')
    expect(container.textContent).not.toContain('**Noa**')
  })

  it('renders the fallback prose as markdown when no `ui` event is produced', async () => {
    stream([
      event('grounding', { grounding: 'general' }),
      ...tokens(PROSE),
      event('done', { message_id: 'm1' }),
    ])

    const { container } = render(<AdminChat />)
    await ask()

    await waitFor(() => expect(container.querySelector('ul')).not.toBeNull())
    expect(container.querySelector('strong')?.textContent).toBe('Noa')
    expect(container.querySelector('em')?.textContent).toBe('Iker')
    expect(container.textContent).not.toContain('- **Noa**')
    expect(container.querySelector('[data-ui-format]')).toBeNull()
    // The honesty note survives either way — it is not the answer.
    expect(screen.getByText(/Conocimiento general/)).toBeInTheDocument()
    // Prose is the answer, so it is click-to-explain like any other answer. Bare markdown
    // here painted every word as pointer-cursored `.entity` with no handler behind it.
    expect(container.querySelector('[data-explain-surface] .entity')).not.toBeNull()
  })

  it('keeps the prose when the browser gate refuses the program', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { release, drained } = stream(
      [...tokens(PROSE), event('done', { message_id: 'm1' })],
      [event('ui', { program: REACTIVE_PROGRAM, format: 'explanation' })],
    )

    const { container } = render(<AdminChat />)
    await ask()

    await waitFor(() => expect(container.querySelector('strong')?.textContent).toBe('Noa'))
    release()
    // The `ui` event has now been read. It changes nothing on screen, which is the point.
    await drained

    // Not a blank bubble: the server validated this program and our stricter gate
    // still refused it, so the answer the admin was already reading stays put.
    await waitFor(() => expect(container.querySelector('strong')?.textContent).toBe('Noa'))
    expect(container.querySelector('[data-ui-format]')).toBeNull()
    expect(container.textContent).not.toContain('Datos del equipo')
  })

  it('does not run the question the admin typed through markdown', async () => {
    stream([event('token', { content: 'Vale.' }), event('done', { message_id: 'm1' })])

    const { container } = render(<AdminChat />)
    await ask('que empleados llevan **cero** cursos')

    await waitFor(() => expect(container.textContent).toContain('Vale.'))
    expect(container.textContent).toContain('**cero**')
  })
})
