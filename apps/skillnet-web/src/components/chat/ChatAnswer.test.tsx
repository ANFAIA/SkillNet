import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ChatAnswer } from './ChatAnswer'
import { ChatMarkdown } from './ChatMarkdown'
import type { ChatMessage } from '../../types'

/**
 * The bubble, from the angle the unit tests were blind to.
 *
 * The regression that shipped is instructive: `api/chat.ts` was fully covered, the
 * `ui` event was parsed correctly, `program` landed on the message — and the screen
 * was still wrong, because nothing asserted what the *bubble* did with either half of
 * the answer. So the three claims here are all about pixels, not state:
 *
 * 1. Prose is **rendered as markdown**. `**Escucha**` reaching the DOM as four literal
 *    characters is the reported bug, and it is invisible to any test that only reads
 *    `message.content`.
 * 2. The program **replaces** the prose. Not "is also present": the prose must be gone.
 * 3. A program the browser's gate refuses falls back to the prose. This is the case
 *    that turns a stricter client gate into a blank bubble, and the server cannot
 *    prevent it — its validator and this one are deliberately not the same check.
 */

const PROGRAM = [
  'root = Stack([intro, pasos], "md")',
  'intro = TextContent("Consulta siempre la ficha del producto.", "lead")',
  'pasos = StepSequence("Atender una consulta de alergenos", ["Escucha la pregunta", "Consulta la ficha"])',
].join('\n')

/** Reactivity: what the gate exists to refuse, and what the server would never emit. */
const REACTIVE_PROGRAM = [
  'root = Stack([intro], "md")',
  'intro = TextContent("Texto", "lead")',
  'z = Query("leak_everything", {})',
].join('\n')

const PROSE = [
  'Para atender una consulta de alergenos:',
  '',
  '1. **Escucha la pregunta** del cliente.',
  '2. *Nunca* improvises.',
  '',
  '| Turno | Responsable |',
  '| --- | --- |',
  '| Mañana | Noa |',
].join('\n')

function answer(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: 'a1',
    role: 'assistant',
    content: PROSE,
    grounding: 'document',
    ...overrides,
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

/**
 * The text of the first `selector` in the bubble.
 *
 * `getByText` cannot be used for a *phrase* anywhere in this file any more: §8.5 splits
 * every word into its own span for the explain popover, and since `ChatMarkdown` began
 * emitting those spans — without them no word in a chat answer was clickable at all —
 * that applies to markdown as well as to the kit blocks. The element is still asserted;
 * only the way its text is read changes.
 */
function textOf(container: HTMLElement, selector: string): string | null | undefined {
  return container.querySelector(selector)?.textContent
}

describe('ChatAnswer', () => {
  it('renders the prose as markdown, not as the characters the model typed', () => {
    const { container } = render(<ChatAnswer message={answer()} />)

    // The literal source must not survive anywhere in the bubble's text.
    expect(container.textContent).not.toContain('**Escucha')
    expect(container.textContent).not.toContain('| Turno |')

    expect(textOf(container, 'strong')).toBe('Escucha la pregunta')
    expect(textOf(container, 'em')).toBe('Nunca')
    expect(container.querySelector('ol')).not.toBeNull()
    // GFM: the table only exists because `remark-gfm` is applied.
    expect(container.querySelector('table')).not.toBeNull()
    expect(Array.from(container.querySelectorAll('th')).map((th) => th.textContent)).toContain(
      'Responsable',
    )
  })

  it('lets the kit program replace the prose once it arrives', () => {
    const { container, rerender } = render(<ChatAnswer message={answer()} />)
    expect(textOf(container, 'strong')).toBe('Escucha la pregunta')

    rerender(<ChatAnswer message={answer({ program: PROGRAM })} />)

    // The blocks are the answer. `textContent` rather than `getByText` because §8.5
    // splits every kit string into per-word spans for the explain popover.
    expect(container.textContent).toContain('Atender una consulta de alergenos')
    expect(container.textContent).toContain('Consulta siempre la ficha del producto.')
    expect(container.querySelector('[data-ui-format="explanation"]')).not.toBeNull()
    // A StepSequence, which is the shape the question asked for.
    expect(container.querySelectorAll('ol > li')).toHaveLength(2)
    // ...and the prose is gone rather than pushed underneath them.
    expect(container.textContent).not.toContain('Nunca')
    expect(container.querySelector('table')).toBeNull()
  })

  it('keeps the prose when the browser gate refuses the program', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { container } = render(<ChatAnswer message={answer({ program: REACTIVE_PROGRAM })} />)

    // Not a blank bubble: the answer the learner was already reading is still there.
    expect(textOf(container, 'strong')).toBe('Escucha la pregunta')
    expect(container.querySelector('[data-ui-format]')).toBeNull()
    expect(container.textContent).not.toContain('Texto')
  })

  it('shows the caret while tokens arrive and drops it at done', () => {
    const { container, rerender } = render(
      <ChatAnswer message={answer({ content: 'Los alergenos', isStreaming: true })} />,
    )
    expect(container.textContent).toContain('▍')

    rerender(<ChatAnswer message={answer({ content: 'Los alergenos son 14.' })} />)
    expect(container.textContent).not.toContain('▍')
    expect(container.textContent).toContain('Los alergenos son 14.')
  })

  it('says it is writing before the first token', () => {
    render(<ChatAnswer message={answer({ content: '', isStreaming: true })} />)
    expect(screen.getByText('Escribiendo...')).toBeInTheDocument()
  })
})

describe('ChatMarkdown', () => {
  it('leaves a one-paragraph answer without a trailing margin', () => {
    const { container } = render(<ChatMarkdown content="Los alergenos son 14." />)
    const p = container.querySelector('p')
    expect(p).not.toBeNull()
    // `last:mb-0` is what keeps the common case pixel-identical to the plain <p> it
    // replaced; without it every short answer grows a gap inside its own bubble.
    expect(p?.className).toContain('last:mb-0')
  })

  it('does not paint an image the model asked for', () => {
    const { container } = render(
      <ChatMarkdown content="Mira esto ![pixel](https://tracker.example/p.gif) y ya." />,
    )
    // An image is the one construct that calls out to an arbitrary host unattended,
    // and this text is downstream of a document anybody can upload.
    expect(container.querySelector('img')).toBeNull()
    expect(container.textContent).toContain('Mira esto')
    expect(container.textContent).toContain('y ya.')
  })

  it('does not let raw HTML out of the text', () => {
    const { container } = render(
      <ChatMarkdown content={'Cuidado <script>alert(1)</script> y <b>esto</b>.'} />,
    )
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
    expect(container.textContent).toContain('<b>esto</b>')
  })
})
