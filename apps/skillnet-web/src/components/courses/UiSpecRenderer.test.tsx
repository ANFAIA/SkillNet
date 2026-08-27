/**
 * `UiSpecRenderer` over OpenUI's real runtime.
 *
 * The input is now the **dialect**, not the JSON IR, so the corpus is the same
 * `.openui` set the backend parser is tested against
 * (`apps/skillnet-api/tests/fixtures/dsl/`) — see `src/test/fixtures/dsl.ts`.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactElement } from 'react'

import { UiSpecRenderer } from './UiSpecRenderer'
import {
  FALLBACK_MARKDOWN_PROGRAM,
  brokenPrograms,
  dslFixtures,
  hasDslCorpus,
  validPrograms,
} from '../../test/fixtures/dsl'
import type { StaticViolation } from './kit/assertStaticOnly'

vi.mock('../../api/client', () => ({
  post: vi.fn(),
}))

// Imported after the mock so the test grabs the mocked binding.
import { post } from '../../api/client'

const mockedPost = vi.mocked(post)

function renderWithQuery(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

/**
 * `ClickableText` (§8.5) splits prose into one `<span>` per word, and
 * `getByText` only ever sees an element's *direct* text nodes — so a phrase that
 * spans several word spans has no single element to match. Content assertions
 * therefore run against the subtree's rendered text.
 */
function expectText(container: HTMLElement, text: string | RegExp) {
  expect(container).toHaveTextContent(text)
}

let warnSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
  mockedPost.mockReset()
})

afterEach(() => {
  warnSpy.mockRestore()
})

describe('the dialect corpus', () => {
  it('is the backend fixture set, read in place', () => {
    expect(hasDslCorpus).toBe(true)
    expect(Object.keys(dslFixtures)).toHaveLength(17)
    expect(Object.keys(validPrograms)).toHaveLength(11)
    expect(Object.keys(brokenPrograms)).toHaveLength(6)
  })
})

describe('UiSpecRenderer — valid programs', () => {
  it.each(Object.keys(validPrograms))('renders the %s program cleanly', (name) => {
    const violations: StaticViolation[] = []
    const { container } = renderWithQuery(
      <UiSpecRenderer
        program={validPrograms[name]}
        nodeId="node-1"
        renderId="render-1"
        onViolations={(found) => violations.push(...found)}
      />,
    )

    // Something was painted, and the gate found nothing to say about it.
    expect(container.firstElementChild).not.toBeNull()
    expect(container.textContent?.trim().length ?? 0).toBeGreaterThan(0)
    expect(violations).toEqual([])
    expect(warnSpy).not.toHaveBeenCalled()
  })

  it('tags the wrapper with the declared ui_format', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer program={validPrograms.chart_data} nodeId="node-1" format="chart" />,
    )
    expect(container.firstElementChild).toHaveAttribute('data-ui-format', 'chart')
  })

  it('renders TextContent variants as prose', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer program={validPrograms.explanation_basic} nodeId="node-1" />,
    )
    expectText(container, 'Las devoluciones se aceptan durante 30 dias naturales.')
    // `lead` is the §5.2 rule 7 slot; `body`/`caption` are the other two variants.
    expect(container.querySelectorAll('p')).not.toHaveLength(0)
  })

  it('renders inline markdown as real elements and leaves code unclickable', () => {
    // No fixture carries inline markup, so the §5.2-rule-6 case gets its own
    // program rather than a hand-edited copy of B1's.
    const program = [
      'root = Stack([intro], "md")',
      'intro = TextContent("Aplica la **garantia** del fabricante. El codigo interno es `GAR-FAB`.", "lead")',
    ].join('\n')

    const { container } = renderWithQuery(<UiSpecRenderer program={program} nodeId="node-1" />)

    expect(container.querySelector('strong')).toHaveTextContent('garantia')
    expectText(container, 'Aplica la garantia del fabricante.')
    expect(container.textContent).not.toContain('**')
    // §8.5: `code` is in OPAQUE_TAGS, so it stays one unclickable run.
    const code = screen.getByText('GAR-FAB')
    expect(code.tagName).toBe('CODE')
    expect(code.querySelector('.entity')).toBeNull()
  })

  it('renders a Card title and its resolved children', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer program={validPrograms.card_nested} nodeId="node-1" />,
    )
    const heading = container.querySelector('h3')
    expect(heading).not.toBeNull()
    expectText(heading as HTMLElement, 'Comprobacion del plazo')
    expectText(container, 'Compara la fecha del ticket con la de hoy.')
    expectText(container, 'dias = (hoy - ticket).days')
  })

  it('renders Callout tones with a text label, not colour alone', () => {
    renderWithQuery(
      <UiSpecRenderer program={validPrograms.explanation_callout_first} nodeId="node-1" />,
    )
    expect(screen.getByRole('note', { name: 'Atención' })).toBeInTheDocument()

    renderWithQuery(<UiSpecRenderer program={validPrograms.deep_stack} nodeId="node-1" />)
    expect(screen.getByRole('note', { name: 'Importante' })).toBeInTheDocument()
  })

  it('renders StepSequence as an ordered list', () => {
    renderWithQuery(<UiSpecRenderer program={validPrograms.explanation_basic} nodeId="node-1" />)
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(4)
    expect(items[0]).toHaveTextContent('Verificar el producto')
    expect(items[3]).toHaveTextContent('Emitir el reembolso')
  })

  it('renders Didact Flashcard with reveal-before-rate behavior', async () => {
    const program = [
      'root = Stack([card], "md")',
      'card = Flashcard("Que debe hacerse antes de abrir?", "Comprobar y registrar el fondo de caja.")',
    ].join('\n')
    const user = userEvent.setup()

    renderWithQuery(<UiSpecRenderer program={program} nodeId="node-1" />)

    expect(screen.getByRole('button', { name: 'Mostrar respuesta' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Lo sabía' })).toBeNull()
    await user.click(await screen.findByRole('button', { name: 'Mostrar respuesta' }))
    expect(screen.getByRole('button', { name: 'Lo sabía' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Necesito repasarlo' })).toBeInTheDocument()
  })

  it('renders Didact HintReveal progressively', async () => {
    const program = [
      'root = Stack([help], "md")',
      'help = HintReveal("Comprueba tu decision", ["Mira el importe.", "Comprueba si hay riesgo para la salud."], "Escala antes de comprometer una solucion.")',
    ].join('\n')
    const user = userEvent.setup()

    renderWithQuery(<UiSpecRenderer program={program} nodeId="node-1" />)

    expect(screen.queryByText('Mira el importe.')).toBeNull()
    await user.click(await screen.findByRole('button', { name: 'Mostrar siguiente pista' }))
    expect(document.body).toHaveTextContent('Mira el importe.')
    expect(screen.getByText('Pista 1 de 2')).toBeInTheDocument()
  })

  it('renders Table headers as column scopes and every cell', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer program={validPrograms.table_nested} nodeId="node-1" />,
    )
    expect(screen.getAllByRole('columnheader')).toHaveLength(3)
    expect(screen.getAllByRole('row')).toHaveLength(4) // header + 3 data rows
    expectText(container, 'Coste del envio')
    expectText(container, '3,95 EUR')
  })

  it('renders CodeBlock inside a pre and excludes it from click-to-explain', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer program={validPrograms.card_nested} nodeId="node-1" />,
    )
    const pre = container.querySelector('pre')
    expect(pre).not.toBeNull()
    expect(pre?.textContent).toContain('if dias <= 30:')
    // §8.5: ClickableSurface hit-tests with closest('[data-no-explain]').
    expect(pre?.closest('[data-no-explain]')).not.toBeNull()
  })

  it('renders a Chart without a chart library', () => {
    const { container } = renderWithQuery(<UiSpecRenderer program={validPrograms.chart_data} nodeId="node-1" />)
    // The chart title is rendered via ClickableText, which splits into entity spans.
    expectText(container, 'Variacion mensual de devoluciones')
    expect(screen.getByText('Febrero')).toBeInTheDocument()
  })

  it('renders the line kind as hand-rolled SVG', () => {
    // The chart fixture is a bar chart, so `kind: "line"` needs its own program.
    const program = validPrograms.chart_data.replace('Chart("bar"', 'Chart("line"')

    const { container } = renderWithQuery(<UiSpecRenderer program={program} nodeId="node-1" />)
    expect(container.querySelector('svg polyline')).not.toBeNull()
    expect(
      screen.getByRole('img', { name: /Variacion mensual de devoluciones/ }),
    ).toBeInTheDocument()
  })

  it('renders the fallback_seed Markdown through LessonContent', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer program={FALLBACK_MARKDOWN_PROGRAM} nodeId="node-1" />,
    )
    expect(screen.getByRole('heading', { name: 'Devoluciones' })).toBeInTheDocument()
    expectText(container, '30 dias naturales')
  })

  it('keeps escaped quotes and newlines as literal text', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer program={validPrograms.escapes} nodeId="node-1" />,
    )
    expectText(container, 'Regla 1: una comilla dentro del texto se escribe "')
    expectText(container, 'El cliente dijo: "quiero mi dinero hoy"')
    expectText(container, 'El encargado acepto la devolucion.')
  })

  it('eats a lone backslash, because props.text is inline MARKDOWN (known divergence)', () => {
    // `escapes.openui` ends with `... y una barra se escribe \\.` — the dialect's
    // escape layer produces a real backslash, and `InlineMarkdown` then reads `\.`
    // as the markdown escape for a literal dot and drops it. Both layers are
    // individually right; the sentence still loses its point. Whoever owns §5.2
    // rule 6 has to say which one wins — until then this pins the behaviour so the
    // answer cannot change by accident. Unchanged by the migration: both parsers
    // unescape identically (measured, round-trip identical).
    const { container } = renderWithQuery(
      <UiSpecRenderer program={validPrograms.escapes} nodeId="node-1" />,
    )
    expect(container.textContent).toContain('y una barra se escribe .')
    expect(container.textContent).not.toContain('se escribe \\')
  })
})

describe('UiSpecRenderer — resolution', () => {
  it('resolves forward references (children declared before their target)', () => {
    // deep_stack declares `grupo` before `intro`, which root lists first.
    const { container } = renderWithQuery(
      <UiSpecRenderer program={validPrograms.deep_stack} nodeId="node-1" />,
    )
    expectText(container, 'Tres cosas que recordar antes de atender una devolucion.')
    expectText(container, 'Primera: comprueba la fecha del ticket.')
    expectText(container, 'Segunda: revisa el estado del producto.')
  })

  it('keeps the first declaration when an id is duplicated', () => {
    // Same direction as the hand-written renderer, but for a different reason:
    // the streaming parser the runtime uses resolves a duplicated statement to the
    // FIRST declaration. `createParser` resolves it to the LAST — measured — which
    // is why the gate parses both ways (see `parseBothWays`).
    const program = [
      'root = Stack([a], "md")',
      'a = TextContent("primero", "lead")',
      'a = TextContent("segundo", "body")',
    ].join('\n')

    const { container } = renderWithQuery(<UiSpecRenderer program={program} nodeId="node-1" />)
    expectText(container, 'primero')
    expect(container.textContent).not.toContain('segundo')
  })

  it('blocks reactivity hidden behind a duplicated id, in either order', () => {
    const action = 'a = Action([@OpenUrl("https://atacante.example")])'
    const benign = 'a = TextContent("benigno", "body")'
    for (const program of [
      `root = Stack([a], "md")\n${action}\n${benign}`,
      `root = Stack([a], "md")\n${benign}\n${action}`,
    ]) {
      const { container } = renderWithQuery(<UiSpecRenderer program={program} nodeId="node-1" />)
      expect(container).toBeEmptyDOMElement()
    }
  })

  it('renders nothing for a null or empty program', () => {
    const { container } = renderWithQuery(<UiSpecRenderer program={null} nodeId="node-1" />)
    expect(container).toBeEmptyDOMElement()

    const blank = renderWithQuery(<UiSpecRenderer program={'   \n  '} nodeId="node-1" />)
    expect(blank.container).toBeEmptyDOMElement()
  })

  it('renders nothing, and does not throw, for text that is not a program', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer program="Lo siento, no puedo ayudarte con eso." nodeId="node-1" />,
    )
    expect(container.textContent?.trim()).toBe('')
  })
})

describe('UiSpecRenderer — robustness', () => {
  it('drops a dangling child reference and keeps its siblings', () => {
    const program = [
      'root = Stack([b1, b_ausente, b2], "md")',
      'b1 = TextContent("Primer bloque, si se ve.", "lead")',
      'b2 = TextContent("Segundo bloque, tambien se ve.", "body")',
    ].join('\n')

    const violations: StaticViolation[] = []
    const { container } = renderWithQuery(
      <UiSpecRenderer
        program={program}
        nodeId="node-1"
        onViolations={(found) => violations.push(...found)}
      />,
    )

    expectText(container, 'Primer bloque, si se ve.')
    expectText(container, 'Segundo bloque, tambien se ve.')
    // Reported, never fatal: a missing reference costs a block, not the lesson.
    expect(violations.map((violation) => violation.severity)).toEqual(['structural'])
    expect(violations[0].message).toContain('b_ausente')
  })

  it('breaks a cycle instead of recursing forever', () => {
    const program = [
      'root = Stack([antes, ciclo, despues], "md")',
      'antes = TextContent("Bloque valido antes del ciclo.", "lead")',
      'ciclo = Card("Se referencia a si mismo", [ciclo])',
      'despues = TextContent("Hermano del ciclo, se sigue viendo.", "body")',
    ].join('\n')

    const { container } = renderWithQuery(<UiSpecRenderer program={program} nodeId="node-1" />)
    expectText(container, 'Bloque valido antes del ciclo.')
    expectText(container, 'Hermano del ciclo, se sigue viendo.')
    // The self-referencing card is rendered exactly once.
    expect(container.querySelectorAll('h3')).toHaveLength(1)
  })

  it('does not paint a component that is not in the catalogue', () => {
    // `invalid_unknown_component.openui`: `linea = Timeline("Hitos", [...])`.
    const { container } = renderWithQuery(
      <UiSpecRenderer program={brokenPrograms.invalid_unknown_component} nodeId="node-1" />,
    )
    expectText(container, 'Los hitos del proceso de devolucion.')
    expect(container.textContent).not.toContain('Hitos')
    expect(container.textContent).not.toContain('Reembolso')
  })

  it.each(Object.keys(brokenPrograms))('survives the %s fixture', (name) => {
    expect(() =>
      renderWithQuery(<UiSpecRenderer program={brokenPrograms[name]} nodeId="node-1" />),
    ).not.toThrow()
  })

  it('coerces malformed props instead of throwing', () => {
    // OpenUI's parser checks arity, never types: measured, `gap: "enorme"` and a
    // number where a string belongs both parse with `meta.errors == []`. The
    // coercion in `kit/coerce.ts` is what keeps them harmless.
    const program = [
      'root = Stack([b1, b2, b3], "enorme")',
      'b1 = TextContent(42, "gritando")',
      'b2 = Table("nope", ["a"])',
      'b3 = Chart("pie", "T", ["a"], ["x"])',
    ].join('\n')

    expect(() =>
      renderWithQuery(<UiSpecRenderer program={program} nodeId="node-1" />),
    ).not.toThrow()
    expect(screen.getByText('T')).toBeInTheDocument()
  })

  it('renders the deepest nesting the contract still allows', () => {
    // Depth is bounded by the 12-statement limit of rule 4, which the gate does
    // enforce — so the old MAX_DEPTH guard has nothing left to protect against.
    // 10 nested Stacks + the text + root = exactly 12 statements.
    const depth = 10
    const program = [
      'root = Stack([s0], "md")',
      ...Array.from({ length: depth }, (_, i) =>
        i === depth - 1 ? `s${i} = Stack([fondo], "sm")` : `s${i} = Stack([s${i + 1}], "sm")`,
      ),
      'fondo = TextContent("fondo", "body")',
    ].join('\n')

    const { container } = renderWithQuery(<UiSpecRenderer program={program} nodeId="node-1" />)
    expectText(container, 'fondo')
  })

  it('refuses a program past the 12-statement contract limit instead of rendering it', () => {
    const ids = Array.from({ length: 13 }, (_, index) => `b${index}`)
    const program = [
      `root = Stack([${ids.join(', ')}], "md")`,
      ...ids.map((id) => `${id} = TextContent("bloque ${id}", "body")`),
    ].join('\n')

    const { container } = renderWithQuery(<UiSpecRenderer program={program} nodeId="node-1" />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('UiSpecRenderer — progressive rendering', () => {
  const program = validPrograms.mixed_quiz ?? ''

  it.each([1, 8, 20, 34, 60, 90, 140, 200, 300, 400])(
    'never throws with the program truncated at %i characters',
    (cut) => {
      expect(() =>
        renderWithQuery(
          <UiSpecRenderer program={program.slice(0, cut)} nodeId="node-1" isStreaming />,
        ),
      ).not.toThrow()
    },
  )

  it('paints the blocks that have arrived and nothing it has not read yet', () => {
    const lines = program.split('\n')
    const partial = `${lines[0]}\n${lines[1]}`
    const { container } = renderWithQuery(
      <UiSpecRenderer program={partial} nodeId="node-1" isStreaming />,
    )
    expectText(container, 'Las devoluciones se aceptan durante 30 dias naturales.')
    expect(container.textContent).not.toContain('Verificar el producto')
  })

  it('says nothing about the references a half-written program is missing', () => {
    const violations: StaticViolation[] = []
    renderWithQuery(
      <UiSpecRenderer
        program={program.slice(0, 60)}
        nodeId="node-1"
        isStreaming
        onViolations={(found) => violations.push(...found)}
      />,
    )
    expect(violations).toEqual([])
  })

  it('ends up with the whole lesson once the stream closes', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer program={program} nodeId="node-1" isStreaming={false} />,
    )
    expectText(container, 'Las devoluciones se aceptan durante 30 dias naturales.')
    expectText(container, 'Emitir el reembolso')
    expectText(container, 'Un cliente vuelve el dia 32')
  })
})

describe('UiSpecRenderer — the static-only gate', () => {
  const reactive = [
    'root = Stack([a, veredicto], "md")',
    'a = TextContent("Elige una opcion.", "lead")',
    '$elegida = -1',
    'veredicto = Callout($elegida == 1 ? "success" : "warn", "Respuesta")',
  ].join('\n')

  it('renders nothing at all when the program carries reactivity', () => {
    const { container } = renderWithQuery(<UiSpecRenderer program={reactive} nodeId="node-1" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('reports the incident instead of swallowing it', () => {
    const violations: StaticViolation[] = []
    renderWithQuery(
      <UiSpecRenderer
        program={reactive}
        nodeId="node-1"
        onViolations={(found) => violations.push(...found)}
      />,
    )
    expect(violations.some((violation) => violation.severity === 'blocking')).toBe(true)
    expect(violations.map((violation) => violation.code)).toContain('state')
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('blocking state'))
  })

  it('blocks a Mutation even while streaming', () => {
    const program = [
      'root = Stack([a], "md")',
      'a = TextContent("x", "body")',
      'z = Mutation("delete_all_users", { confirm: true })',
    ].join('\n')
    const { container } = renderWithQuery(
      <UiSpecRenderer program={program} nodeId="node-1" isStreaming />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})

describe('UiSpecRenderer — autonomous QuizItemBlock', () => {
  it('excludes the whole quiz item from click-to-explain, statement and options', () => {
    renderWithQuery(
      <UiSpecRenderer program={validPrograms.mixed_quiz} nodeId="node-1" renderId="render-1" />,
    )
    const statement = screen.getByText(/Un cliente vuelve el dia 32/)
    expect(statement.closest('[data-no-explain]')).not.toBeNull()

    for (const option of screen.getAllByRole('radio')) {
      expect(option.closest('[data-no-explain]')).not.toBeNull()
    }
  })

  it('renders single-choice and constructed-answer items from the same program', () => {
    // exercise_only: a true_false item (radios) next to a fill_blank one (textarea).
    renderWithQuery(
      <UiSpecRenderer program={validPrograms.exercise_only} nodeId="node-1" renderId="render-1" />,
    )
    expect(screen.getAllByRole('radio')).toHaveLength(2)
    expect(screen.getByRole('textbox', { name: 'Tu respuesta' })).toBeInTheDocument()
  })

  it('renders all four item types of the fenced quiz_types fixture', () => {
    // The fixture arrives wrapped in a ```openui fence; the parser ignores it.
    renderWithQuery(
      <UiSpecRenderer program={validPrograms.quiz_types} nodeId="node-1" renderId="render-1" />,
    )
    expect(screen.getAllByRole('textbox', { name: 'Tu respuesta' })).toHaveLength(3)
    expect(screen.getByText(/Ordena los pasos de la devolucion/)).toBeInTheDocument()
  })

  it('posts the answer to /nodes/{id}/answer and shows the graded result', async () => {
    mockedPost.mockResolvedValue({
      score: 1,
      passed: true,
      feedback: 'Exacto: pasados 30 dias aplica la garantia.',
      correct_answer: { selected: 1 },
      mastery: 0.82,
      state: 'mastered',
      consecutive_correct: 1,
      consecutive_failed: 0,
      next: 'next_item',
    })

    const user = userEvent.setup()
    renderWithQuery(
      <UiSpecRenderer program={validPrograms.mixed_quiz} nodeId="node-7" renderId="render-9" />,
    )

    await user.click(await screen.findByRole('radio', { name: 'Ofrecer garantia del fabricante' }))
    await user.click(await screen.findByRole('button', { name: 'Comprobar' }))

    await waitFor(() => expect(mockedPost).toHaveBeenCalledTimes(1))
    const [path, body] = mockedPost.mock.calls[0]
    expect(path).toBe('/nodes/node-7/answer')
    expect(body).toMatchObject({
      render_id: 'render-9',
      item_id: 'q1',
      answer: { selected: 1 },
      hints_used: 0,
    })
    expect((body as { latency_ms: number }).latency_ms).toBeGreaterThanOrEqual(0)

    // `findByRole('status')` resuelve en cuanto EXISTE el nodo, que es antes de que
    // llegue el feedback corregido; y al repintar, React sustituye el elemento, asi que
    // una referencia capturada aqui puede quedarse huerfana. Se espera al TEXTO concreto,
    // reconsultando, y solo despues se afirma sobre el nodo ya asentado.
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('pasados 30 dias')
    })
    const status = screen.getByRole('status')
    expect(within(status).getByText('Correcto')).toBeInTheDocument()
    // El panel de resultado NO muestra el dominio bruto: se quito a proposito
    // (ce909d6, "don't show the raw 'Dominio: X%' mastery score to the learner").
    // La asercion se invierte para que sirva de guardia de esa decision.
    expect(status).not.toHaveTextContent('Dominio')
  })

  it('offers a retry after a failed attempt', async () => {
    mockedPost.mockResolvedValue({
      score: 0,
      passed: false,
      feedback: 'No: el plazo son 30 dias.',
      correct_answer: null,
      mastery: 0.2,
      state: 'learning',
      consecutive_correct: 0,
      consecutive_failed: 1,
      next: 'retry',
    })

    const user = userEvent.setup()
    renderWithQuery(
      <UiSpecRenderer program={validPrograms.mixed_quiz} nodeId="node-7" renderId="render-9" />,
    )

    await user.click(await screen.findByRole('radio', { name: 'Aceptar la devolucion' }))
    await user.click(await screen.findByRole('button', { name: 'Comprobar' }))

    expect(await screen.findByText('Incorrecto')).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'Reintentar' }))
    expect(screen.queryByText('Incorrecto')).not.toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Aceptar la devolucion' })).not.toBeChecked()
  })

  it('fully resets the item on retry: result gone, radio unchecked and re-enabled, next attempt gets a fresh id', async () => {
    // Regression: `retry()` used to clear the graded result by calling only
    // `submit.reset()`. Deriving `result` from `submit.data` meant the radios'
    // `disabled` state and the result panel both depended on the mutation
    // observer's own notification timing, which is not guaranteed to land in the
    // same tick as the sibling `setSelected(null)` outside of `act()`-flushed
    // tests. This asserts the whole post-retry state in one attempt: no result
    // text, radio unchecked AND enabled, and the next submission carries a
    // different `attempt_id`.
    mockedPost
      .mockResolvedValueOnce({
        score: 0,
        passed: false,
        feedback: null,
        correct_answer: null,
        mastery: 0.2,
        state: 'learning',
        consecutive_correct: 0,
        consecutive_failed: 1,
        next: 'retry',
      })
      .mockResolvedValueOnce({
        score: 1,
        passed: true,
        feedback: null,
        correct_answer: { selected: 1 },
        mastery: 0.8,
        state: 'mastered',
        consecutive_correct: 1,
        consecutive_failed: 0,
        next: 'next_item',
      })

    const user = userEvent.setup()
    renderWithQuery(
      <UiSpecRenderer program={validPrograms.mixed_quiz} nodeId="node-7" renderId="render-9" />,
    )

    await user.click(await screen.findByRole('radio', { name: 'Aceptar la devolucion' }))
    await user.click(await screen.findByRole('button', { name: 'Comprobar' }))
    expect(await screen.findByText('Incorrecto')).toBeInTheDocument()

    await user.click(await screen.findByRole('button', { name: 'Reintentar' }))

    expect(screen.queryByText('Incorrecto')).not.toBeInTheDocument()
    const radio = screen.getByRole('radio', { name: 'Aceptar la devolucion' })
    expect(radio).not.toBeChecked()
    expect(radio).toBeEnabled()

    await user.click(radio)
    await user.click(await screen.findByRole('button', { name: 'Comprobar' }))
    expect(await screen.findByText('Correcto')).toBeInTheDocument()

    expect(mockedPost).toHaveBeenCalledTimes(2)
    expect((mockedPost.mock.calls[1][1] as { attempt_id: string }).attempt_id)
      .not.toBe((mockedPost.mock.calls[0][1] as { attempt_id: string }).attempt_id)
  })

  it('does not reuse a finished attempt when the learner changes option', async () => {
    mockedPost
      .mockResolvedValueOnce({
        score: 0,
        passed: false,
        feedback: null,
        correct_answer: null,
        mastery: 0.2,
        state: 'learning',
        consecutive_correct: 0,
        consecutive_failed: 1,
        next: 'retry',
      })
      .mockResolvedValueOnce({
        score: 1,
        passed: true,
        feedback: null,
        correct_answer: { selected: 1 },
        mastery: 0.8,
        state: 'mastered',
        consecutive_correct: 1,
        consecutive_failed: 0,
        next: 'next_item',
      })

    const program = [
      'root = Stack([q], "md")',
      'q = QuizItem("q1", "test", "understand", "Un cliente se queja de un producto defectuoso. ¿Cuál es el primer paso?", ["Ofrecer una solución inmediata", "Disculparte y reconocer la queja", "Registrar la incidencia", "Escalar al encargado"])',
    ].join('\n')
    const user = userEvent.setup()
    renderWithQuery(<UiSpecRenderer program={program} nodeId="node-7" renderId="render-9" />)

    await user.click(await screen.findByRole('radio', { name: 'Registrar la incidencia' }))
    await user.click(await screen.findByRole('button', { name: 'Comprobar' }))
    expect(await screen.findByText('Incorrecto')).toBeInTheDocument()

    // A graded payload cannot be silently mutated under the same attempt id.
    expect(screen.getByRole('radio', { name: 'Disculparte y reconocer la queja' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Comprobar' })).not.toBeInTheDocument()

    await user.click(await screen.findByRole('button', { name: 'Reintentar' }))
    await user.click(await screen.findByRole('radio', { name: 'Disculparte y reconocer la queja' }))
    await user.click(await screen.findByRole('button', { name: 'Comprobar' }))

    expect(await screen.findByText('Correcto')).toBeInTheDocument()
    expect(mockedPost).toHaveBeenCalledTimes(2)
    expect(mockedPost.mock.calls[1][1]).toMatchObject({ answer: { selected: 1 } })
    expect((mockedPost.mock.calls[1][1] as { attempt_id: string }).attempt_id)
      .not.toBe((mockedPost.mock.calls[0][1] as { attempt_id: string }).attempt_id)
  })

  it('reproduces the browser retry: wrong → Reintentar leaves the old choice unchecked and enabled, a different choice then grades correct', async () => {
    // The exact sequence the real-browser check exercised (and the RTL harness had not):
    // fail on one option, press Reintentar, and confirm the *previously chosen* radio is
    // no longer checked and no longer disabled — then pick a DIFFERENT option and pass.
    // `retry()` remounts the answer region (keyed by `attemptNonce`), so "unchecked and
    // enabled" is a fresh DOM fact, not a re-derivation racing the graded result.
    mockedPost
      .mockResolvedValueOnce({
        score: 0,
        passed: false,
        feedback: null,
        correct_answer: null,
        mastery: 0.2,
        state: 'learning',
        consecutive_correct: 0,
        consecutive_failed: 1,
        next: 'retry',
      })
      .mockResolvedValueOnce({
        score: 1,
        passed: true,
        feedback: null,
        correct_answer: { selected: 1 },
        mastery: 0.9,
        state: 'mastered',
        consecutive_correct: 1,
        consecutive_failed: 0,
        next: 'next_item',
      })

    const program = [
      'root = Stack([q], "md")',
      'q = QuizItem("q1", "test", "understand", "Un cliente devuelve un producto. Primer paso?", ["Registrar la incidencia", "Disculparte y reconocer la queja", "Escalar al encargado", "Ofrecer un vale"])',
    ].join('\n')
    const user = userEvent.setup()
    renderWithQuery(<UiSpecRenderer program={program} nodeId="node-7" renderId="render-9" />)

    const wrongFirst = () => screen.getByRole('radio', { name: 'Registrar la incidencia' })
    await user.click(wrongFirst())
    await user.click(await screen.findByRole('button', { name: 'Comprobar' }))
    expect(await screen.findByText('Incorrecto')).toBeInTheDocument()
    expect(wrongFirst()).toBeChecked()
    expect(wrongFirst()).toBeDisabled()

    await user.click(await screen.findByRole('button', { name: 'Reintentar' }))

    // The browser symptom, asserted directly: old choice cleared, all radios usable.
    expect(screen.queryByText('Incorrecto')).not.toBeInTheDocument()
    expect(wrongFirst()).not.toBeChecked()
    expect(wrongFirst()).toBeEnabled()
    const right = screen.getByRole('radio', { name: 'Disculparte y reconocer la queja' })
    expect(right).toBeEnabled()

    await user.click(right)
    await user.click(await screen.findByRole('button', { name: 'Comprobar' }))
    expect(await screen.findByText('Correcto')).toBeInTheDocument()

    expect(mockedPost).toHaveBeenCalledTimes(2)
    expect(mockedPost.mock.calls[1][1]).toMatchObject({ answer: { selected: 1 } })
    expect((mockedPost.mock.calls[1][1] as { attempt_id: string }).attempt_id).not.toBe(
      (mockedPost.mock.calls[0][1] as { attempt_id: string }).attempt_id,
    )
  })

  it('never reports a client-side hint count, not even across retries', async () => {
    // §11.3: the server uses `hints_used` to decide whether it reveals
    // `correct_answer`, so a number this client picks must never grow. The count of
    // record is `node_attempts.hints_used`, incremented only by the hint endpoint;
    // this block grants no hints and therefore always reports 0.
    mockedPost.mockResolvedValue({
      score: 0,
      passed: false,
      feedback: 'No: el plazo son 30 dias.',
      correct_answer: null,
      mastery: 0.2,
      state: 'learning',
      consecutive_correct: 0,
      consecutive_failed: 1,
      next: 'retry',
    })

    const user = userEvent.setup()
    renderWithQuery(
      <UiSpecRenderer program={validPrograms.mixed_quiz} nodeId="node-7" renderId="render-9" />,
    )

    await user.click(await screen.findByRole('radio', { name: 'Aceptar la devolucion' }))
    await user.click(await screen.findByRole('button', { name: 'Comprobar' }))
    await user.click(await screen.findByRole('button', { name: 'Reintentar' }))
    await user.click(await screen.findByRole('radio', { name: 'Ofrecer garantia del fabricante' }))
    await user.click(await screen.findByRole('button', { name: 'Comprobar' }))

    await waitFor(() => expect(mockedPost).toHaveBeenCalledTimes(2))
    for (const call of mockedPost.mock.calls) {
      expect((call[1] as { hints_used: number }).hints_used).toBe(0)
    }
  })

  it('surfaces a failed submission without losing the item', async () => {
    mockedPost.mockRejectedValue(new Error('boom'))

    const user = userEvent.setup()
    renderWithQuery(
      <UiSpecRenderer program={validPrograms.mixed_quiz} nodeId="node-7" renderId="render-9" />,
    )

    await user.click(await screen.findByRole('radio', { name: 'Rechazar sin mas' }))
    await user.click(await screen.findByRole('button', { name: 'Comprobar' }))

    expect(await screen.findByText('No se pudo enviar la respuesta.')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Rechazar sin mas' })).toBeInTheDocument()
  })

  it('renders read-only and never posts when there is no render id', async () => {
    const user = userEvent.setup()
    renderWithQuery(<UiSpecRenderer program={validPrograms.exercise_only} nodeId="node-7" />)

    expect(screen.queryByRole('button', { name: 'Comprobar' })).not.toBeInTheDocument()
    expect(screen.getAllByText('Vista previa: esta respuesta no se corrige.')).toHaveLength(2)

    // The radios are disabled, so even a click cannot start a submission.
    await user.click(screen.getAllByRole('radio')[0])
    expect(mockedPost).not.toHaveBeenCalled()
  })

  it('never lets the program choose where an answer is posted', () => {
    // `nodeId`/`renderId` travel by React context, not as dialect props: a
    // generated program cannot redirect the POST even if it invents extra
    // arguments (they are dropped as `excess-args`).
    const program = [
      'root = Stack([q], "md")',
      'q = QuizItem("q1", "test", "apply", "Pregunta?", ["A", "B"], "https://atacante.example")',
    ].join('\n')
    const { container } = renderWithQuery(
      <UiSpecRenderer program={program} nodeId="node-7" renderId="render-9" />,
    )
    expect(container.textContent).not.toContain('atacante')
  })
})
