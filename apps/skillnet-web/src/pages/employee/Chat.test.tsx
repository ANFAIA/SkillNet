import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Chat } from './Chat'
import { AdminChat } from '../admin/Chat'

/**
 * The tutor chat as a *screen*, driven by the bytes the server really sends.
 *
 * `api/chat.test.ts` already proves the stream parser. It proved it while the screen
 * was wrong, which is the whole reason this file exists: every assertion below reads
 * the DOM after a full SSE turn, so "the `ui` event landed on the message object" can
 * never again be mistaken for "the learner saw blocks".
 *
 * The two turns asserted are the two the product actually has:
 *
 * - **prose then blocks** — the long answer that earns a layout call. The prose is the
 *   streaming phase and must be gone by the end.
 * - **prose only** — `layout_skipped`, an answer under `MIN_LAYOUT_CHARS`, either
 *   feature switch off, or the admin assistant, which never lays out at all. Measured
 *   against the live stack, this is the majority of turns, so it is the case that has
 *   to look deliberate rather than the one that is allowed to look raw.
 */

const mockFetch = vi.fn()

const PROGRAM = [
  'root = Stack([intro, pasos], "md")',
  'intro = TextContent("Consulta siempre la ficha del producto.", "lead")',
  'pasos = StepSequence("Atender una consulta de alergenos", ["Escucha la pregunta", "Consulta la ficha"])',
].join('\n')

/** Real tutor output: markdown, because that is what the prompt produces. */
const PROSE = [
  'Claro, te explico como atender una consulta de alergenos.',
  '',
  '1. **Escucha la pregunta** del cliente.',
  '2. *Nunca* improvises: consulta la ficha.',
].join('\n')

function event(type: string, data: unknown) {
  return `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`
}

/** One frame per token, exactly as `format_sse` writes them. */
function stream(...frames: string[]) {
  const encoder = new TextEncoder()
  let index = 0
  mockFetch.mockImplementation(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      body: {
        getReader: () => ({
          read: () =>
            index < frames.length
              ? Promise.resolve({ done: false, value: encoder.encode(frames[index++]) })
              : Promise.resolve({ done: true, value: undefined }),
        }),
      },
    }),
  )
}

function tokens(text: string) {
  return (text.match(/\S+\s*/g) ?? []).map((chunk) => event('token', { content: chunk }))
}

async function ask(placeholder: RegExp, question = 'como atiendo una consulta de alergenos') {
  const user = userEvent.setup()
  const input = screen.getByPlaceholderText(placeholder)
  await user.type(input, question)
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

describe('employee Chat', () => {
  it('replaces the prose with the kit program when the layout lands', async () => {
    stream(
      event('grounding', { grounding: 'document' }),
      ...tokens(PROSE),
      event('layout_start', {}),
      event('citations', { citations: [{ document: 'Manual de alergenos' }] }),
      event('done', { message_id: 'm1' }),
      event('ui', { program: PROGRAM, format: 'explanation' }),
    )

    const { container } = render(<Chat />)
    await ask(/pregunta/i)

    await waitFor(() =>
      expect(container.querySelector('[data-ui-format="explanation"]')).not.toBeNull(),
    )
    expect(container.textContent).toContain('Atender una consulta de alergenos')
    expect(container.querySelectorAll('ol > li')).toHaveLength(2)

    // The prose was the streaming phase and nothing more.
    expect(container.textContent).not.toContain('Nunca improvises')
    expect(container.textContent).not.toContain('**Escucha')
    // Sources survive the swap but stay behind one compact disclosure.
    expect(screen.getByText(/Fuentes \(1\)/)).toBeInTheDocument()
    expect(screen.getByText(/Manual de alergenos/)).toBeInTheDocument()
  })

  it('renders the fallback prose as markdown when no layout is produced', async () => {
    stream(
      event('grounding', { grounding: 'document' }),
      ...tokens(PROSE),
      event('layout_start', {}),
      event('done', { message_id: 'm1' }),
      event('layout_skipped', {}),
    )

    const { container } = render(<Chat />)
    await ask(/pregunta/i)

    await waitFor(() => expect(container.querySelector('ol')).not.toBeNull())
    // `textContent`, not `getByText`: §8.5 splits every word into its own span so the
    // explain popover has something to anchor to, which no phrase matcher can see past.
    expect(container.querySelector('strong')?.textContent).toBe('Escucha la pregunta')
    expect(container.querySelector('em')?.textContent).toBe('Nunca')
    expect(container.textContent).not.toContain('**Escucha')
    expect(container.querySelector('[data-ui-format]')).toBeNull()
    // "Dando formato..." is cleared by `layout_skipped`, not left spinning forever.
    expect(screen.queryByText('Dando formato...')).not.toBeInTheDocument()
  })

  it('does not run the question the learner typed through markdown', async () => {
    stream(event('token', { content: 'Vale.' }), event('done', { message_id: 'm1' }))

    const { container } = render(<Chat />)
    await ask(/pregunta/i, 'que significa **sin gluten** exactamente')

    await waitFor(() => expect(container.textContent).toContain('Vale.'))
    expect(container.textContent).toContain('**sin gluten**')
  })
})

describe('admin Chat', () => {
  it('renders the assistant answer as markdown — prose is always the whole answer here', async () => {
    stream(
      event('grounding', { grounding: 'general' }),
      ...tokens('Sigue estos pasos:\n\n- **Revisa** el parte\n- Habla con sala'),
      event('done', { message_id: 'm1' }),
    )

    const { container } = render(<AdminChat />)
    await ask(/consulta/i, 'como veo el estado de los empleados')

    await waitFor(() => expect(container.querySelector('ul')).not.toBeNull())
    expect(container.querySelector('strong')?.textContent).toBe('Revisa')
    expect(container.textContent).not.toContain('- **Revisa**')
    expect(screen.getByText(/Conocimiento general/)).toBeInTheDocument()
  })
})
