import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactElement } from 'react'

import { UiSpecRenderer } from './UiSpecRenderer'
import { brokenSpecs, goldenSpecs } from '../../test/fixtures/ui-specs'
import type { UiSpec } from '../../types/ui-spec'

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

describe('UiSpecRenderer — golden specs', () => {
  it.each(Object.keys(goldenSpecs))('renders the %s golden spec without warnings', (name) => {
    const spec = goldenSpecs[name]
    const { container } = renderWithQuery(
      <UiSpecRenderer spec={spec} nodeId="node-1" renderId="render-1" />,
    )

    // Something was painted, and nothing was reported as broken.
    expect(container.firstElementChild).not.toBeNull()
    expect(container.textContent?.trim().length ?? 0).toBeGreaterThan(0)
    expect(warnSpy).not.toHaveBeenCalled()
  })

  it('tags the wrapper with the declared ui_format', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer spec={goldenSpecs.chart_data} nodeId="node-1" />,
    )
    expect(container.firstElementChild).toHaveAttribute('data-ui-format', 'chart')
  })

  it('renders TextContent variants as prose', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer spec={goldenSpecs.explanation_basic} nodeId="node-1" />,
    )
    expectText(container, 'Las devoluciones se aceptan durante 30 dias naturales.')
    // `lead` is the §5.2 rule 7 slot; `body`/`caption` are the other two variants.
    expect(container.querySelectorAll('p')).not.toHaveLength(0)
  })

  it('renders inline markdown as real elements and leaves code unclickable', () => {
    // No golden fixture carries inline markup, so the §5.2-rule-6 case gets its
    // own spec rather than a hand-edited copy of B1's.
    const spec = {
      version: 'skillnet-ui/1',
      format: 'explanation',
      root: 'root',
      components: [
        { id: 'root', type: 'Stack', props: { gap: 'md' }, children: ['intro'] },
        {
          id: 'intro',
          type: 'TextContent',
          props: {
            text: 'Aplica la **garantia** del fabricante. El codigo interno es `GAR-FAB`.',
            variant: 'lead',
          },
          children: [],
        },
      ],
    } as unknown as UiSpec

    const { container } = renderWithQuery(<UiSpecRenderer spec={spec} nodeId="node-1" />)

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
      <UiSpecRenderer spec={goldenSpecs.card_nested} nodeId="node-1" />,
    )
    const heading = container.querySelector('h3')
    expect(heading).not.toBeNull()
    expectText(heading as HTMLElement, 'Comprobacion del plazo')
    expectText(container, 'Compara la fecha del ticket con la de hoy.')
    expectText(container, 'dias = (hoy - ticket).days')
  })

  it('renders Callout tones with a text label, not colour alone', () => {
    renderWithQuery(
      <UiSpecRenderer spec={goldenSpecs.explanation_callout_first} nodeId="node-1" />,
    )
    expect(screen.getByRole('note', { name: 'Atencion' })).toBeInTheDocument()

    renderWithQuery(<UiSpecRenderer spec={goldenSpecs.deep_stack} nodeId="node-1" />)
    expect(screen.getByRole('note', { name: 'Importante' })).toBeInTheDocument()
  })

  it('renders StepSequence as an ordered list', () => {
    renderWithQuery(<UiSpecRenderer spec={goldenSpecs.explanation_basic} nodeId="node-1" />)
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(4)
    expect(items[0]).toHaveTextContent('Verificar el producto')
    expect(items[3]).toHaveTextContent('Emitir el reembolso')
  })

  it('renders Table headers as column scopes and every cell', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer spec={goldenSpecs.table_nested} nodeId="node-1" />,
    )
    expect(screen.getAllByRole('columnheader')).toHaveLength(3)
    expect(screen.getAllByRole('row')).toHaveLength(4) // header + 3 data rows
    expectText(container, 'Coste del envio')
    expectText(container, '3,95 EUR')
  })

  it('renders CodeBlock inside a pre and excludes it from click-to-explain', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer spec={goldenSpecs.card_nested} nodeId="node-1" />,
    )
    const pre = container.querySelector('pre')
    expect(pre).not.toBeNull()
    expect(pre?.textContent).toContain('if dias <= 30:')
    // §8.5: ClickableSurface hit-tests with closest('[data-no-explain]').
    expect(pre?.closest('[data-no-explain]')).not.toBeNull()
  })

  it('renders a Chart without a chart library', () => {
    renderWithQuery(<UiSpecRenderer spec={goldenSpecs.chart_data} nodeId="node-1" />)
    expect(screen.getByText('Variacion mensual de devoluciones')).toBeInTheDocument()
    expect(screen.getByText('Febrero')).toBeInTheDocument()
  })

  it('renders the line kind as hand-rolled SVG', () => {
    // B1's chart fixture is a bar chart, so `kind: "line"` needs its own spec.
    const spec = {
      ...goldenSpecs.chart_data,
      components: goldenSpecs.chart_data.components.map((component) =>
        component.type === 'Chart'
          ? { ...component, props: { ...component.props, kind: 'line' } }
          : component,
      ),
    } as unknown as UiSpec

    const { container } = renderWithQuery(<UiSpecRenderer spec={spec} nodeId="node-1" />)
    expect(container.querySelector('svg polyline')).not.toBeNull()
    expect(
      screen.getByRole('img', { name: /Variacion mensual de devoluciones/ }),
    ).toBeInTheDocument()
  })

  it('renders Markdown fallback content through LessonContent', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer spec={goldenSpecs.fallback_markdown} nodeId="node-1" />,
    )
    expect(screen.getByRole('heading', { name: 'Devoluciones' })).toBeInTheDocument()
    expectText(container, '30 dias naturales')
  })

  it('keeps escaped quotes and newlines as literal text', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer spec={goldenSpecs.escapes} nodeId="node-1" />,
    )
    expectText(container, 'Regla 1: una comilla dentro del texto se escribe "')
    expectText(container, 'El cliente dijo: "quiero mi dinero hoy"')
    expectText(container, 'El encargado acepto la devolucion.')
  })

  it('eats a lone backslash, because props.text is inline MARKDOWN (known divergence)', () => {
    // B1's `escapes.json` ends with `... y una barra se escribe \.` — the
    // dialect's escape layer produced a real backslash, and `InlineMarkdown`
    // then reads `\.` as the markdown escape for a literal dot and drops it.
    // Both layers are individually right; the sentence still loses its point.
    // Whoever owns §5.2 rule 6 has to say which one wins — until then this test
    // pins the behaviour so the answer cannot change by accident.
    const { container } = renderWithQuery(
      <UiSpecRenderer spec={goldenSpecs.escapes} nodeId="node-1" />,
    )
    expect(container.textContent).toContain('y una barra se escribe .')
    expect(container.textContent).not.toContain('se escribe \\')
  })
})

describe('UiSpecRenderer — resolution', () => {
  it('resolves forward references (children declared before their target)', () => {
    // deep_stack declares `grupo` before `intro`, which root lists first.
    const { container } = renderWithQuery(
      <UiSpecRenderer spec={goldenSpecs.deep_stack} nodeId="node-1" />,
    )
    expectText(container, 'Tres cosas que recordar antes de atender una devolucion.')
    expectText(container, 'Primera: comprueba la fecha del ticket.')
    expectText(container, 'Segunda: revisa el estado del producto.')
  })

  it('keeps the first declaration when an id is duplicated', () => {
    const spec = {
      version: 'skillnet-ui/1',
      format: 'explanation',
      root: 'b0',
      components: [
        { id: 'b0', type: 'Stack', props: { gap: 'md' }, children: ['b1'] },
        { id: 'b1', type: 'TextContent', props: { text: 'primero', variant: 'lead' } },
        { id: 'b1', type: 'TextContent', props: { text: 'segundo', variant: 'body' } },
      ],
    } as unknown as UiSpec

    const { container } = renderWithQuery(<UiSpecRenderer spec={spec} nodeId="node-1" />)
    expectText(container, 'primero')
    expect(container.textContent).not.toContain('segundo')
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('duplicate component id'))
  })

  it('renders nothing when root does not exist, and does not throw', () => {
    const spec = {
      version: 'skillnet-ui/1',
      format: 'explanation',
      root: 'nope',
      components: [{ id: 'b0', type: 'Stack', props: {}, children: [] }],
    } as unknown as UiSpec

    const { container } = renderWithQuery(<UiSpecRenderer spec={spec} nodeId="node-1" />)
    expect(container).toBeEmptyDOMElement()
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('unknown component id "nope"'))
  })

  it('renders nothing for an empty component list', () => {
    const spec = {
      version: 'skillnet-ui/1',
      format: 'explanation',
      root: 'b0',
      components: [],
    } as unknown as UiSpec

    const { container } = renderWithQuery(<UiSpecRenderer spec={spec} nodeId="node-1" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('survives a spec object that is not a spec at all', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer spec={undefined as unknown as UiSpec} nodeId="node-1" />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})

describe('UiSpecRenderer — robustness', () => {
  it('drops a dangling child reference and keeps its siblings', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer spec={brokenSpecs.danglingRef} nodeId="node-1" />,
    )
    expectText(container, 'Primer bloque, si se ve.')
    expectText(container, 'Segundo bloque, tambien se ve.')
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('unknown component id "b_ausente"'),
    )
  })

  it('breaks a cycle instead of recursing forever', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer spec={brokenSpecs.cycle} nodeId="node-1" />,
    )
    expectText(container, 'Bloque valido antes del ciclo.')
    expectText(container, 'Hermano del ciclo, se sigue viendo.')
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('cycle detected'))
    // The self-referencing card is rendered exactly once.
    expect(container.querySelectorAll('h3')).toHaveLength(1)
  })

  it('renders null for an unknown component type and keeps the rest of the screen', () => {
    const { container } = renderWithQuery(
      <UiSpecRenderer spec={brokenSpecs.unknownType} nodeId="node-1" />,
    )
    expectText(container, 'Bloque conocido.')
    expectText(container, 'Otro bloque conocido, detras del desconocido.')
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('unsupported component type "Timeline"'),
    )
  })

  it('warns on a version mismatch but still renders', () => {
    const spec = { ...goldenSpecs.explanation_basic, version: 'skillnet-ui/99' }
    const { container } = renderWithQuery(<UiSpecRenderer spec={spec} nodeId="node-1" />)
    expectText(container, '30 dias naturales')
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('skillnet-ui/99'))
  })

  it('coerces malformed props instead of throwing', () => {
    const spec = {
      version: 'skillnet-ui/1',
      format: 'explanation',
      root: 'b0',
      components: [
        { id: 'b0', type: 'Stack', props: { gap: 'enormous' }, children: ['b1', 'b2', 'b3'] },
        { id: 'b1', type: 'TextContent', props: { text: 42, variant: 'shouting' } },
        { id: 'b2', type: 'Table', props: { headers: 'nope', rows: [null, ['a']] } },
        { id: 'b3', type: 'Chart', props: { kind: 'pie', title: 'T', labels: ['a'], values: ['x'] } },
      ],
    } as unknown as UiSpec

    expect(() =>
      renderWithQuery(<UiSpecRenderer spec={spec} nodeId="node-1" />),
    ).not.toThrow()
    expect(screen.getByText('T')).toBeInTheDocument()
  })

  it('stops at the depth guard on a deeply nested spec', () => {
    const depth = 20
    const components = Array.from({ length: depth }, (_, i) => ({
      id: `s${i}`,
      type: 'Stack',
      props: { gap: 'sm' },
      children: [`s${i + 1}`],
    }))
    components.push({
      id: `s${depth}`,
      type: 'Stack',
      props: { gap: 'sm' },
      children: [],
    })
    const spec = {
      version: 'skillnet-ui/1',
      format: 'explanation',
      root: 's0',
      components,
    } as unknown as UiSpec

    expect(() =>
      renderWithQuery(<UiSpecRenderer spec={spec} nodeId="node-1" />),
    ).not.toThrow()
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('max depth'))
  })
})

describe('UiSpecRenderer — autonomous QuizItemBlock', () => {
  it('excludes the whole quiz item from click-to-explain, statement and options', () => {
    renderWithQuery(
      <UiSpecRenderer spec={goldenSpecs.mixed_quiz} nodeId="node-1" renderId="render-1" />,
    )
    const statement = screen.getByText(/Un cliente vuelve el dia 32/)
    expect(statement.closest('[data-no-explain]')).not.toBeNull()

    for (const option of screen.getAllByRole('radio')) {
      expect(option.closest('[data-no-explain]')).not.toBeNull()
    }
  })

  it('renders single-choice and constructed-answer items from the same spec', () => {
    // exercise_only: a true_false item (radios) next to a fill_blank one (textarea).
    renderWithQuery(
      <UiSpecRenderer spec={goldenSpecs.exercise_only} nodeId="node-1" renderId="render-1" />,
    )
    expect(screen.getAllByRole('radio')).toHaveLength(2)
    expect(screen.getByRole('textbox', { name: 'Tu respuesta' })).toBeInTheDocument()
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
      <UiSpecRenderer spec={goldenSpecs.mixed_quiz} nodeId="node-7" renderId="render-9" />,
    )

    await user.click(screen.getByRole('radio', { name: 'Ofrecer garantia del fabricante' }))
    await user.click(screen.getByRole('button', { name: 'Comprobar' }))

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

    const status = await screen.findByRole('status')
    expect(within(status).getByText('Correcto')).toBeInTheDocument()
    expect(status).toHaveTextContent('pasados 30 dias')
    expect(status).toHaveTextContent('Dominio: 82%')
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
      <UiSpecRenderer spec={goldenSpecs.mixed_quiz} nodeId="node-7" renderId="render-9" />,
    )

    await user.click(screen.getByRole('radio', { name: 'Aceptar la devolucion' }))
    await user.click(screen.getByRole('button', { name: 'Comprobar' }))

    expect(await screen.findByText('Incorrecto')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(screen.queryByText('Incorrecto')).not.toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Aceptar la devolucion' })).not.toBeChecked()
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
      <UiSpecRenderer spec={goldenSpecs.mixed_quiz} nodeId="node-7" renderId="render-9" />,
    )

    await user.click(screen.getByRole('radio', { name: 'Aceptar la devolucion' }))
    await user.click(screen.getByRole('button', { name: 'Comprobar' }))
    await user.click(await screen.findByRole('button', { name: 'Reintentar' }))
    await user.click(screen.getByRole('radio', { name: 'Ofrecer garantia del fabricante' }))
    await user.click(screen.getByRole('button', { name: 'Comprobar' }))

    await waitFor(() => expect(mockedPost).toHaveBeenCalledTimes(2))
    for (const call of mockedPost.mock.calls) {
      expect((call[1] as { hints_used: number }).hints_used).toBe(0)
    }
  })

  it('surfaces a failed submission without losing the item', async () => {
    mockedPost.mockRejectedValue(new Error('boom'))

    const user = userEvent.setup()
    renderWithQuery(
      <UiSpecRenderer spec={goldenSpecs.mixed_quiz} nodeId="node-7" renderId="render-9" />,
    )

    await user.click(screen.getByRole('radio', { name: 'Rechazar sin mas' }))
    await user.click(screen.getByRole('button', { name: 'Comprobar' }))

    expect(await screen.findByText('No se pudo enviar la respuesta.')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Rechazar sin mas' })).toBeInTheDocument()
  })

  it('renders read-only and never posts when there is no render id', async () => {
    const user = userEvent.setup()
    renderWithQuery(<UiSpecRenderer spec={goldenSpecs.exercise_only} nodeId="node-7" />)

    expect(screen.queryByRole('button', { name: 'Comprobar' })).not.toBeInTheDocument()
    expect(screen.getAllByText('Vista previa: esta respuesta no se corrige.')).toHaveLength(2)

    // The radios are disabled, so even a click cannot start a submission.
    await user.click(screen.getAllByRole('radio')[0])
    expect(mockedPost).not.toHaveBeenCalled()
  })
})
