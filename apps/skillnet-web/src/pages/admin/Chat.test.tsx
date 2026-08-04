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
 * `frames` stream immediately; `tail` is held until the returned function is called.
 *
 * The layout call takes real seconds against a real provider, and that gap is where
 * the interesting states live — the composer is already back, the notice is up, the
 * program has not landed. Holding it makes those states assertable instead of a race
 * against the reader draining and clearing `isLayingOut` on its own.
 */
function stream(frames: string[], tail: string[] = []) {
  const encoder = new TextEncoder()
  let release: () => void = () => {}
  const held = new Promise<void>((resolve) => {
    release = resolve
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
            return { done: true, value: undefined }
          },
        }),
      },
    }),
  )
  return () => release()
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
    const release = stream(
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
        event('layout_start', {}),
      ],
      [event('ui', { program: PROGRAM, format: 'explanation' })],
    )

    const { container } = render(<AdminChat />)
    await ask()

    // Mid-turn: the answer is complete, the layout is not. The admin reads prose.
    await waitFor(() => expect(screen.getByText('Dando formato...')).toBeInTheDocument())
    // `textContent`, not `getByText().tagName`: §8.5 wraps every word in its own span so
    // the explain popover has an anchor, so the emphasised run is no longer a text node.
    expect(container.querySelector('strong')?.textContent).toBe('Noa')
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
    expect(screen.queryByText('Dando formato...')).not.toBeInTheDocument()
  })

  it('renders the fallback prose as markdown when no layout is produced', async () => {
    stream([
      event('grounding', { grounding: 'general' }),
      ...tokens(PROSE),
      event('done', { message_id: 'm1' }),
      event('layout_start', {}),
      event('layout_skipped', {}),
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
    // Cleared by `layout_skipped`, not left spinning forever.
    expect(screen.queryByText('Dando formato...')).not.toBeInTheDocument()
  })

  it('keeps the prose when the browser gate refuses the program', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const release = stream(
      [...tokens(PROSE), event('done', { message_id: 'm1' }), event('layout_start', {})],
      [event('ui', { program: REACTIVE_PROGRAM, format: 'explanation' })],
    )

    const { container } = render(<AdminChat />)
    await ask()

    await waitFor(() => expect(screen.getByText('Dando formato...')).toBeInTheDocument())
    release()
    // The notice clearing is the `ui` event having been applied to the message.
    await waitFor(() => expect(screen.queryByText('Dando formato...')).not.toBeInTheDocument())

    // Not a blank bubble: the server validated this program and our stricter gate
    // still refused it, so the answer the admin was already reading stays put.
    expect(container.querySelector('[data-ui-format]')).toBeNull()
    expect(container.textContent).not.toContain('Datos del equipo')
    expect(container.querySelector('strong')?.textContent).toBe('Noa')
  })

  it('does not run the question the admin typed through markdown', async () => {
    stream([event('token', { content: 'Vale.' }), event('done', { message_id: 'm1' })])

    const { container } = render(<AdminChat />)
    await ask('que empleados llevan **cero** cursos')

    await waitFor(() => expect(container.textContent).toContain('Vale.'))
    expect(container.textContent).toContain('**cero**')
  })
})
