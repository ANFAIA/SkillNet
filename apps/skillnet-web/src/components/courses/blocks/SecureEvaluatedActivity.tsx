import { useEffect, useId, useRef, useState } from 'react'
import { useIntl } from 'react-intl'

import { ActivityNotEvaluableError } from '../../../lib/didact'
import type { DidactHostPorts, EvaluationResult } from '../../../lib/didact'
import { Button } from '../../ui/Button'
import { evaluateDidactSubmission } from './didact-evaluation-adapter'
import { WorkedSolution } from './QuizItemHints'
import { useLessonFeedback, useStepperSolve } from './StepperContext'
import { usesSecureEvaluationAdapter } from './secure-evaluation-components'

type PublicProps = Readonly<Record<string, unknown>>
type Answer = string | boolean | string[] | Record<string, string>
type Choice = { id: string; content: string }
type QuizOption = { value: string; label: string }

function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item))
    : []
}

function choices(value: unknown): Choice[] {
  return records(value).flatMap((item) => (
    typeof item.id === 'string' && typeof item.content === 'string'
      ? [{ id: item.id, content: item.content }]
      : []
  ))
}

function options(value: unknown): QuizOption[] {
  return records(value).flatMap((item) => (
    typeof item.value === 'string' && typeof item.label === 'string'
      ? [{ value: item.value, label: item.label }]
      : []
  ))
}

function initialAnswer(componentId: string, props: PublicProps): Answer {
  if (componentId === 'didact.sort') return choices(props.items).map((item) => item.id)
  if (componentId === 'didact.quiz.multi-select') return []
  if (componentId === 'didact.quiz.true-false') return ''
  if (
    componentId === 'didact.matching'
    || componentId === 'didact.categorize'
    || componentId === 'didact.completion-problem'
    || componentId === 'didact.word-bank'
  ) return {}
  return ''
}

function titleFor(componentId: string, props: PublicProps): string {
  const value = componentId.startsWith('didact.quiz.')
    ? props.question
    : componentId === 'didact.completion-problem'
      ? props.problem
      : componentId === 'didact.numeric-question'
        ? props.prompt
        : props.title
  return typeof value === 'string' ? value : ''
}

function Result({ result, closed }: { result: EvaluationResult; closed: boolean }) {
  // A graded miss is a wrong answer, not a broken grader. The previous copy ("la respuesta
  // necesita revisión") read as "the system could not correct this", which is what made a
  // plain failed attempt look like a bug to the learner.
  //
  // `closed` changes what a miss is allowed to promise. Once the server has handed over
  // the solution there is no retry left, so "vuelve a intentarlo" would be a lie printed
  // directly above the answer.
  const copy = result.outcome === 'correct'
    ? 'Respuesta correcta.'
    : result.outcome === 'unscored'
      ? 'Respuesta enviada para revisión.'
      : closed
        ? 'La respuesta no es correcta. Aquí tienes la solución.'
        : result.outcome === 'partial'
          ? 'Respuesta parcialmente correcta. Puedes volver a intentarlo.'
          : 'La respuesta no es correcta. Vuelve a intentarlo.'
  return (
    <div className="rounded-lg border border-border bg-bg-subtle p-3 text-sm" role="status" aria-live="polite">
      <p className="font-medium text-text">{copy}</p>
      {typeof result.feedback === 'string' && result.feedback && (
        <p className="mt-1 text-text-secondary">{result.feedback}</p>
      )}
    </div>
  )
}

// A written gap inside a sentence: a run of two or more underscores, or an explicit
// `{{blank}}` / `[blank]` marker. The authoring prompt asks for `____`
// (`src/agents/runtime/assessment.py`), and shorter runs plus the bracket forms show up in
// real generations, so all of them are accepted here.
const BLANK_MARKER = /_{2,}|\{\{\s*blank\s*\}\}|\[\s*blank\s*\]/i

function splitOnBlank(sentence: string): { before: string; after: string } | undefined {
  const match = BLANK_MARKER.exec(sentence)
  if (!match) return undefined
  return {
    before: sentence.slice(0, match.index).trimEnd(),
    after: sentence.slice(match.index + match[0].length).trimStart(),
  }
}

/**
 * `didact.quiz.fill-in-the-blank` publishes only the sentence (`question`), never the
 * accepted answers, so the sentence itself is the interaction: the gap is replaced by a real
 * input in the position the author wrote it. Without this the component fell through to the
 * generic "Tu respuesta" field and the gap was nowhere on screen.
 */
function FillInTheBlank({
  sentence,
  value,
  disabled,
  onChange,
}: {
  sentence: string
  value: string
  disabled: boolean
  onChange: (value: string) => void
}) {
  const gap = splitOnBlank(sentence)
  const input = (
    <input
      className="min-w-40 rounded-lg border border-border bg-bg px-3 py-1 text-text"
      aria-label="Palabra que falta"
      disabled={disabled}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  )
  // No written gap: the sentence stays the heading above and the field carries the label,
  // so the learner still knows a single missing word is what is being asked for.
  if (!gap) {
    return (
      <label className="grid gap-1 text-sm">
        <span className="font-medium text-text">Palabra que falta</span>
        {input}
      </label>
    )
  }
  return (
    <p className="flex flex-wrap items-baseline gap-x-2 gap-y-2 text-lg text-text">
      {gap.before && <span>{gap.before}</span>}
      {input}
      {gap.after && <span>{gap.after}</span>}
    </p>
  )
}

function SelectAssignments({
  items,
  destinations,
  value,
  disabled,
  onChange,
}: {
  items: Choice[]
  destinations: Choice[]
  value: Record<string, string>
  disabled: boolean
  onChange: (value: Record<string, string>) => void
}) {
  return (
    <fieldset className="space-y-3" disabled={disabled}>
      <legend className="sr-only">Asigna cada elemento a una opción</legend>
      {items.map((item) => (
        <label className="grid gap-1 text-sm" key={item.id}>
          <span className="font-medium text-text">{item.content}</span>
          <select
            className="rounded-lg border border-border bg-bg px-3 py-2 text-text"
            aria-label={`Asignación para ${item.content}`}
            value={value[item.id] ?? ''}
            onChange={(event) => onChange({ ...value, [item.id]: event.target.value })}
          >
            <option value="">Selecciona una opción</option>
            {destinations.map((destination) => (
              <option key={destination.id} value={destination.id}>{destination.content}</option>
            ))}
          </select>
        </label>
      ))}
    </fieldset>
  )
}

function SecureInteraction({
  componentId,
  props,
  answer,
  disabled,
  onChange,
  groupName,
}: {
  componentId: string
  props: PublicProps
  answer: Answer
  disabled: boolean
  onChange: (answer: Answer) => void
  groupName: string
}) {
  if (componentId === 'didact.matching') {
    return <SelectAssignments items={choices(props.sources)} destinations={choices(props.targets)} value={answer as Record<string, string>} disabled={disabled} onChange={onChange} />
  }
  if (componentId === 'didact.categorize') {
    return <SelectAssignments items={choices(props.items)} destinations={choices(props.categories)} value={answer as Record<string, string>} disabled={disabled} onChange={onChange} />
  }
  if (componentId === 'didact.word-bank') {
    const gaps = records(props.gaps).map((gap) => ({
      id: String(gap.id ?? ''),
      content: [gap.before, gap.prompt, '____', gap.after].filter((part) => typeof part === 'string' && part).join(' '),
    })).filter((gap) => gap.id)
    return <SelectAssignments items={gaps} destinations={choices(props.options)} value={answer as Record<string, string>} disabled={disabled} onChange={onChange} />
  }
  if (componentId === 'didact.sort') {
    const itemById = new Map(choices(props.items).map((item) => [item.id, item]))
    const order = answer as string[]
    const move = (index: number, offset: number) => {
      const next = [...order]
      const target = index + offset
      if (target < 0 || target >= next.length) return
      ;[next[index], next[target]] = [next[target], next[index]]
      onChange(next)
    }
    return (
      <ol className="space-y-2" aria-label="Elementos en el orden actual">
        {order.map((id, index) => (
          <li className="flex items-center gap-2 rounded-lg border border-border p-2" key={id}>
            <span className="min-w-0 flex-1 text-sm text-text">{itemById.get(id)?.content}</span>
            <Button type="button" variant="secondary" size="sm" disabled={disabled || index === 0} aria-label={`Subir ${itemById.get(id)?.content}`} onClick={() => move(index, -1)}>↑</Button>
            <Button type="button" variant="secondary" size="sm" disabled={disabled || index === order.length - 1} aria-label={`Bajar ${itemById.get(id)?.content}`} onClick={() => move(index, 1)}>↓</Button>
          </li>
        ))}
      </ol>
    )
  }
  if (componentId === 'didact.quiz.single-choice') {
    return (
      <fieldset disabled={disabled} className="space-y-2">
        <legend className="sr-only">Elige una respuesta</legend>
        {options(props.options).map((option) => (
          <label className="flex items-center gap-2 text-sm text-text" key={option.value}>
            <input type="radio" name={groupName} value={option.value} checked={answer === option.value} onChange={() => onChange(option.value)} />
            {option.label}
          </label>
        ))}
      </fieldset>
    )
  }
  if (componentId === 'didact.quiz.multi-select') {
    const selected = answer as string[]
    return (
      <fieldset disabled={disabled} className="space-y-2">
        <legend className="sr-only">Elige todas las respuestas aplicables</legend>
        {options(props.options).map((option) => (
          <label className="flex items-center gap-2 text-sm text-text" key={option.value}>
            <input
              type="checkbox"
              checked={selected.includes(option.value)}
              onChange={(event) => onChange(event.target.checked ? [...selected, option.value] : selected.filter((value) => value !== option.value))}
            />
            {option.label}
          </label>
        ))}
      </fieldset>
    )
  }
  if (componentId === 'didact.quiz.true-false') {
    return (
      <fieldset disabled={disabled} className="space-y-2">
        <legend className="sr-only">Indica si es verdadero o falso</legend>
        {[['true', 'Verdadero'], ['false', 'Falso']].map(([value, label]) => (
          <label className="flex items-center gap-2 text-sm text-text" key={value}>
            <input type="radio" name={groupName} checked={typeof answer === 'boolean' && answer === (value === 'true')} onChange={() => onChange(value === 'true')} />
            {label}
          </label>
        ))}
      </fieldset>
    )
  }
  if (componentId === 'didact.completion-problem') {
    const values = answer as Record<string, string>
    return (
      <div className="space-y-3">
        {records(props.steps).map((step) => {
          const id = String(step.id ?? '')
          if (step.kind === 'worked') return <p className="rounded-lg bg-bg-subtle p-3 text-sm text-text" key={id}>{String(step.content ?? '')}</p>
          return (
            <label className="grid gap-1 text-sm" key={id}>
              <span className="font-medium text-text">{String(step.prompt ?? '')}</span>
              <input className="rounded-lg border border-border bg-bg px-3 py-2 text-text" disabled={disabled} value={values[id] ?? ''} onChange={(event) => onChange({ ...values, [id]: event.target.value })} />
            </label>
          )
        })}
      </div>
    )
  }
  if (componentId === 'didact.quiz.fill-in-the-blank') {
    return (
      <FillInTheBlank
        sentence={typeof props.question === 'string' ? props.question : ''}
        value={String(answer)}
        disabled={disabled}
        onChange={onChange}
      />
    )
  }
  const multiline = componentId === 'didact.quiz.short-answer'
  const unit = props.unit && typeof props.unit === 'object' && !Array.isArray(props.unit)
    ? props.unit as Record<string, unknown>
    : undefined
  const input = multiline ? (
    <textarea className="min-h-28 w-full rounded-lg border border-border bg-bg px-3 py-2 text-text" disabled={disabled} value={String(answer)} onChange={(event) => onChange(event.target.value)} />
  ) : (
    <input
      className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-text"
      inputMode={componentId === 'didact.numeric-question' ? 'decimal' : 'text'}
      disabled={disabled}
      value={String(answer)}
      onChange={(event) => onChange(event.target.value)}
    />
  )
  return (
    <label className="grid gap-1 text-sm">
      <span className="font-medium text-text">Tu respuesta{unit?.policy === 'required' ? ` (incluye ${String(unit.symbol)})` : ''}</span>
      <span className="flex items-center gap-2">{input}{unit?.policy === 'display' && <span>{String(unit.symbol)}</span>}</span>
    </label>
  )
}

function canSubmit(componentId: string, props: PublicProps, answer: Answer): boolean {
  if (typeof answer === 'string') return answer.trim().length > 0
  if (typeof answer === 'boolean') return true
  if (Array.isArray(answer)) return answer.length > 0
  const expectedCount = componentId === 'didact.matching'
    ? choices(props.sources).length
    : componentId === 'didact.categorize'
      ? choices(props.items).length
      : componentId === 'didact.word-bank'
        ? records(props.gaps).length
        : componentId === 'didact.completion-problem'
          ? records(props.steps).filter((step) => step.kind === 'completion').length
          : 0
  return expectedCount > 0 && Object.values(answer).filter((value) => value.trim()).length === expectedCount
}

export function SecureEvaluatedActivity({
  activityId,
  componentId,
  componentProps,
  ports,
}: {
  activityId: string
  componentId: string
  componentProps: PublicProps
  ports: DidactHostPorts
}) {
  const intl = useIntl()
  const titleId = useId()
  const groupName = useId()
  const startedEventId = useRef(crypto.randomUUID())
  const title = titleFor(componentId, componentProps)
  // The step holding this activity is born closed (`kit/solvableSteps.ts`), so this call
  // is the only thing that opens it. If this block stops calling `useStepperSolve`, or
  // another one starts, `SOLVABLE_COMPONENTS` has to move with it —
  // `solvableSteps.test.ts` checks exactly that.
  const solveStep = useStepperSolve()
  // Ambient feedback (ResultGlow + mascot). Independent of whether the step opens.
  const feedback = useLessonFeedback()
  const [answer, setAnswer] = useState<Answer>(() => initialAnswer(componentId, componentProps))
  const [result, setResult] = useState<EvaluationResult>()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(false)
  // The third dead end: the server says this activity cannot be graded at all. Separate
  // from `error`, which is a request that failed and is worth trying again.
  const [unevaluable, setUnevaluable] = useState(false)
  // Bumped on every explicit learner retry. It keys the interaction so the controls are torn
  // down and rebuilt from scratch: clearing `answer` and `result` already re-enables them,
  // but in a real browser a graded attempt leaves a checked+disabled radio whose reset
  // depends on a re-render landing in the same tick. Remounting makes "empty and enabled
  // again" unconditional instead of derived. Same reasoning as `QuizItemBlock.attemptNonce`.
  const [attemptNonce, setAttemptNonce] = useState(0)

  useEffect(() => {
    void ports.events?.emit({
      version: 1,
      eventId: startedEventId.current,
      activityId,
      type: 'started',
      occurredAt: new Date().toISOString(),
      scope: { organizationId: '', courseId: '' },
      componentId,
      payload: {},
    }).catch(() => undefined)
  }, [activityId, componentId, ports.events])

  const blocked = !usesSecureEvaluationAdapter(componentId) || !title

  // Nothing here will ever be answered, and the step that contains it is already closed.
  // Opening it is not a claim that anything was learned — it is refusing to hold the
  // learner behind an activity that never rendered.
  useEffect(() => {
    if (blocked) solveStep?.()
  }, [blocked, solveStep])

  if (blocked) {
    return <div role="status" data-didact-status="blocked">La actividad no tiene una definición pública válida.</div>
  }

  const submit = async () => {
    setPending(true)
    setError(false)
    try {
      const evaluated = await evaluateDidactSubmission(activityId, componentId, ports, answer)
      setResult(evaluated)
      // Same three reports as `QuizItemBlock`, so the glow and the mascot behave
      // identically in both families: a win, a definitive miss (the solution is out and
      // there is no retry), and a miss with an attempt still left. `unscored` is nobody's
      // verdict yet, so it reports nothing.
      //
      // Both closing branches call `solveStep`. Without the second one the learner who
      // ran out of attempts is handed the solution and then held in the step by it: the
      // item never passed, so nothing else would ever open the gate.
      if (evaluated.outcome === 'correct') {
        feedback?.report('acierto')
        solveStep?.()
      } else if (evaluated.showWorkedSolution === true) {
        feedback?.report('fallo', { definitivo: true })
        solveStep?.()
      } else if (evaluated.outcome !== 'unscored') {
        feedback?.report('fallo')
      }
    } catch (failure) {
      if (failure instanceof ActivityNotEvaluableError) {
        // Broken activity: no attempt of it will ever be scored. Say so once and let the
        // learner out immediately, instead of the "inténtalo de nuevo" that could only
        // ever be answered by trying again.
        setUnevaluable(true)
        solveStep?.()
      } else {
        setError(true)
      }
    } finally {
      setPending(false)
    }
  }

  // Every submission mints its own `attemptId` inside `evaluateDidactSubmission`, so a retry
  // is already a separate attempt on the server (`attempted`/`answered`/`completed` carry the
  // new id) and there is no idempotency key to rotate here. `started` stays emitted once per
  // mount: it marks the activity being opened, not an attempt.
  const retry = () => {
    setResult(undefined)
    setError(false)
    setAnswer(initialAnswer(componentId, componentProps))
    setAttemptNonce((nonce) => nonce + 1)
  }

  // The same rule as `QuizItemBlock`. A correct answer is final: re-answering it would
  // only overwrite evidence the learner already earned. So is an item the server just
  // closed with the worked solution (§7.4 rule 8) — re-answering it with the answer on
  // screen would record an attempt that measures nothing. Everything else can be tried
  // again: `partial` because the learner can still complete it, and `unscored` because
  // nothing was graded, so a second attempt adds information instead of replacing a
  // verdict.
  //
  // `showWorkedSolution` is read from the server's flag and never inferred here. A client
  // that decided when the solution appears could decide to see it on the first attempt.
  const closed = result?.outcome === 'correct' || result?.showWorkedSolution === true
  const canRetry = Boolean(result) && !closed
  // A written gap makes the sentence itself the interaction (see `FillInTheBlank`), so the
  // heading keeps the accessible name and stops repeating the same sentence on screen.
  const sentenceIsInteraction = componentId === 'didact.quiz.fill-in-the-blank' && BLANK_MARKER.test(title)

  return (
    <section className="w-full max-w-2xl rounded-lg border border-border bg-bg p-5" aria-labelledby={titleId} data-didact-secure-adapter={componentId}>
      <h3 className={sentenceIsInteraction ? 'sr-only' : 'mb-1 text-lg font-semibold text-text'} id={titleId}>{title}</h3>
      {typeof componentProps.instructions === 'string' && <p className="mb-4 text-sm text-text-secondary">{componentProps.instructions}</p>}
      <div className="mt-4">
        <SecureInteraction
          // Fresh subtree per attempt (see `attemptNonce`). The radio group name carries the
          // nonce too so a discarded attempt cannot share a group with the new one.
          key={attemptNonce}
          componentId={componentId}
          props={componentProps}
          answer={answer}
          disabled={pending || Boolean(result) || unevaluable}
          onChange={setAnswer}
          groupName={`${groupName}:${attemptNonce}`}
        />
      </div>
      <div className="mt-4 space-y-3">
        {unevaluable ? (
          <p className="text-sm text-text-secondary" role="status">
            {intl.formatMessage({ id: 'activity.notEvaluable' })}
          </p>
        ) : result ? (
          <>
            <Result result={result} closed={closed} />
            {canRetry && (
              <Button type="button" variant="secondary" onClick={retry}>Reintentar</Button>
            )}
          </>
        ) : (
          <Button type="button" disabled={pending || !canSubmit(componentId, componentProps, answer)} onClick={() => void submit()}>
            {pending ? 'Comprobando…' : 'Comprobar respuesta'}
          </Button>
        )}
        {error && <p className="text-sm text-danger" role="alert">No se pudo evaluar la respuesta. Inténtalo de nuevo.</p>}
      </div>
      {result?.showWorkedSolution === true ? (
        <WorkedSolution solution={result.solution ?? null} />
      ) : null}
    </section>
  )
}
