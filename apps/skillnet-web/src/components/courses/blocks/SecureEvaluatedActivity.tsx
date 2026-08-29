import { useEffect, useId, useRef, useState } from 'react'
import { useIntl } from 'react-intl'

import {
  activityHintPath,
  useActivitySolution,
  useActivitySolutionRevealed,
  useActivityFailures,
} from '../../../api/activities'
import { ActivityNotEvaluableError } from '../../../lib/didact'
import type { DidactHostPorts, EvaluationResult, EvaluationSolution } from '../../../lib/didact'
import { Button } from '../../ui/Button'
import { evaluateDidactSubmission } from './didact-evaluation-adapter'
import { HintLadder, WorkedSolution } from './QuizItemHints'
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

function Result({
  result,
  closed,
  solutionShown,
}: {
  result: EvaluationResult
  closed: boolean
  solutionShown: boolean
}) {
  const intl = useIntl()
  // A graded miss is a wrong answer, not a broken grader. The previous copy ("the answer
  // needs review") read as "the system could not correct this", which is what made a
  // plain failed attempt look like a bug to the learner.
  //
  // `closed` changes what a miss is allowed to promise: once the server has closed the
  // item there is no retry left, so "try again" would be a lie printed directly above the
  // answer.
  //
  // `solutionShown` decides which of the two closing sentences it gets, and it is a
  // separate question. `show_worked_solution: true` can arrive with `solution: null` —
  // `render_solution` returns `None` for an evaluation mode it does not know how to write
  // out — and announcing "here is the solution" above a panel that then renders nothing
  // promises something that never comes. The honest line says so and still lets the
  // learner out; the step opens either way, from `submit`.
  const copy = intl.formatMessage({
    id: result.outcome === 'correct'
      ? 'activity.result.correct'
      : result.outcome === 'unscored'
        ? 'activity.result.unscored'
        : closed
          ? solutionShown
            ? 'activity.result.incorrectWithSolution'
            : 'activity.result.incorrectNoSolution'
          : result.outcome === 'partial'
            ? 'activity.result.partial'
            : 'activity.result.incorrect',
  })
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
 * generic "your answer" field and the gap was nowhere on screen.
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
  const intl = useIntl()
  const missingWord = intl.formatMessage({ id: 'activity.missingWord' })
  const gap = splitOnBlank(sentence)
  const input = (
    <input
      className="min-w-40 rounded-lg border border-border bg-bg px-3 py-1 text-text"
      aria-label={missingWord}
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
        <span className="font-medium text-text">{missingWord}</span>
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
  const intl = useIntl()
  return (
    <fieldset className="space-y-3" disabled={disabled}>
      <legend className="sr-only">{intl.formatMessage({ id: 'activity.assign.legend' })}</legend>
      {items.map((item) => (
        <label className="grid gap-1 text-sm" key={item.id}>
          <span className="font-medium text-text">{item.content}</span>
          <select
            className="rounded-lg border border-border bg-bg px-3 py-2 text-text"
            aria-label={intl.formatMessage({ id: 'activity.assign.itemLabel' }, { item: item.content })}
            value={value[item.id] ?? ''}
            onChange={(event) => onChange({ ...value, [item.id]: event.target.value })}
          >
            <option value="">{intl.formatMessage({ id: 'activity.assign.placeholder' })}</option>
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
  const intl = useIntl()
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
      <ol className="space-y-2" aria-label={intl.formatMessage({ id: 'activity.sort.listLabel' })}>
        {order.map((id, index) => (
          <li className="flex items-center gap-2 rounded-lg border border-border p-2" key={id}>
            <span className="min-w-0 flex-1 text-sm text-text">{itemById.get(id)?.content}</span>
            <Button type="button" variant="secondary" size="sm" disabled={disabled || index === 0} aria-label={intl.formatMessage({ id: 'activity.sort.moveUp' }, { item: itemById.get(id)?.content ?? '' })} onClick={() => move(index, -1)}>↑</Button>
            <Button type="button" variant="secondary" size="sm" disabled={disabled || index === order.length - 1} aria-label={intl.formatMessage({ id: 'activity.sort.moveDown' }, { item: itemById.get(id)?.content ?? '' })} onClick={() => move(index, 1)}>↓</Button>
          </li>
        ))}
      </ol>
    )
  }
  if (componentId === 'didact.quiz.single-choice') {
    return (
      <fieldset disabled={disabled} className="space-y-2">
        <legend className="sr-only">{intl.formatMessage({ id: 'activity.legend.singleChoice' })}</legend>
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
        <legend className="sr-only">{intl.formatMessage({ id: 'activity.legend.multiSelect' })}</legend>
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
        <legend className="sr-only">{intl.formatMessage({ id: 'activity.legend.trueFalse' })}</legend>
        {[['true', 'hints.true'], ['false', 'hints.false']].map(([value, labelId]) => (
          <label className="flex items-center gap-2 text-sm text-text" key={value}>
            <input type="radio" name={groupName} checked={typeof answer === 'boolean' && answer === (value === 'true')} onChange={() => onChange(value === 'true')} />
            {intl.formatMessage({ id: labelId })}
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
      <span className="font-medium text-text">
        {unit?.policy === 'required'
          ? intl.formatMessage({ id: 'activity.answerWithUnit' }, { unit: String(unit.symbol) })
          : intl.formatMessage({ id: 'quiz.yourAnswer' })}
      </span>
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
  /**
   * The learner asking to see the solution rather than waiting for the fourth failure.
   *
   * `null` is "never asked". A value is "asked and answered", and the answer inside it
   * may still be `null`: the server does not know how to write every evaluation mode out
   * and says so by sending nothing. The two are kept apart because the second one closes
   * the activity and the first does not — the same distinction `show_worked_solution`
   * arriving with `solution: null` already forced on this component.
   */
  const [revealed, setRevealed] = useState<{ solution: EvaluationSolution | null } | null>(null)
  const solutionRequest = useActivitySolution(activityId)
  // The reveal, as the server remembers it. Without this the closure lived only in the
  // state above: a reload put the activity back as if it were still open, in front of
  // somebody who had already been given the answer. The written solution is not re-sent
  // — knowing it was shown is enough to keep the activity closed.
  const revealedBefore = useActivitySolutionRevealed(activityId)
  // Failures the server has recorded, plus the one this component just saw. The local half
  // matters because the server count arrives on the next fetch, and the help has to appear
  // the instant the verdict lands — not one refetch later.
  const failuresOnServer = useActivityFailures(activityId)
  const [failedHere, setFailedHere] = useState(false)
  const hasFailed = failedHere || failuresOnServer > 0

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
    return <div role="status" data-didact-status="blocked">{intl.formatMessage({ id: 'activity.missingPublicDefinition' })}</div>
  }

  const submit = async () => {
    setPending(true)
    setError(false)
    try {
      const evaluated = await evaluateDidactSubmission(activityId, componentId, ports, answer)
      setResult(evaluated)
      if (evaluated.outcome !== 'correct') setFailedHere(true)
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
        // learner out immediately, instead of the "try again" that could only ever be
        // answered by trying again.
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
    // A failed reveal left its red line on screen across the whole next attempt, so a
    // learner who then answered correctly was told the solution could not be shown.
    solutionRequest.reset()
    setAnswer(initialAnswer(componentId, componentProps))
    setAttemptNonce((nonce) => nonce + 1)
  }

  /**
   * Show me the answer.
   *
   * It closes the activity — there is nothing left to demonstrate once the answer is on
   * screen — so it calls `solveStep`, for exactly the reason the fourth failure does: the
   * step this block sits in is born closed, and if nothing opens it the learner is shut
   * in with the solution they just asked for.
   *
   * No `feedback.report`: the mascot's red is for a verdict the learner received, and
   * asking for help is not one. The evidence is untouched too — nothing is graded here.
   */
  const reveal = () => {
    solutionRequest.mutate(undefined, {
      onSuccess: (solution) => {
        setRevealed({ solution })
        solveStep?.()
      },
    })
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
  //
  // A solution the learner asked for closes it too, and that is the one closing the
  // client is allowed to decide: it did not decide the answer was earned, it only knows
  // the answer is now on screen.
  const closed =
    result?.outcome === 'correct'
    || result?.showWorkedSolution === true
    || revealed !== null
    || revealedBefore
  const canRetry = Boolean(result) && !closed
  // Whether there is anything to *show*, which is not the same as whether the item closed.
  // `WorkedSolution` prints nothing without a written solution (this call site passes no
  // `correctAnswer`), so gating the panel on `showWorkedSolution` alone rendered an empty
  // element under a sentence promising the answer.
  //
  // Either road can end in nothing to print, so the panel is gated on there being a
  // solution and never on the activity being closed.
  const solution =
    revealed?.solution
    ?? (result?.showWorkedSolution === true ? result.solution ?? null : null)
  const solutionShown = Boolean(solution)
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
          disabled={pending || closed || Boolean(result) || unevaluable}
          onChange={setAnswer}
          groupName={`${groupName}:${attemptNonce}`}
        />
      </div>
      <div className="mt-4 space-y-3">
        {unevaluable ? (
          <p className="text-sm text-text-secondary" role="status">
            {intl.formatMessage({ id: 'activity.notEvaluable' })}
          </p>
        ) : (
          <>
            {result ? <Result result={result} closed={closed} solutionShown={solutionShown} /> : null}
            {/* One row for every action still on the table. A closed activity has none:
                no answer to send, no attempt to repeat, and the solution already out. */}
            {!closed && (
              <div className="flex flex-wrap items-center gap-2">
                {result ? (
                  canRetry && (
                    <Button type="button" variant="secondary" onClick={retry}>{intl.formatMessage({ id: 'quiz.retry' })}</Button>
                  )
                ) : (
                  <Button type="button" disabled={pending || !canSubmit(componentId, componentProps, answer)} onClick={() => void submit()}>
                    {intl.formatMessage({ id: pending ? 'activity.checking' : 'activity.check' })}
                  </Button>
                )}
                {/* The way out the owner asked for, next to the automatic one: four
                    failures still hand the solution over on their own, and this is the
                    same exit taken on purpose instead of by exhaustion.
                    Held back until the learner has got it wrong once. Offering the answer
                    to somebody who has not tried is not an escape hatch, it is a shortcut
                    past the exercise — and the exercise is the lesson. The automatic
                    hand-over at the fourth failure is unaffected: it never needed a button. */}
                {hasFailed && (
                <Button type="button" variant="ghost" disabled={solutionRequest.isPending} onClick={reveal}>
                  {solutionRequest.isPending
                    ? intl.formatMessage({ id: 'hints.revealing' })
                    : intl.formatMessage({ id: 'hints.reveal' })}
                </Button>
                )}
              </div>
            )}
            {solutionRequest.isError && (
              <p className="text-sm text-danger" role="alert">
                {intl.formatMessage({ id: 'hints.revealError' })}
              </p>
            )}
          </>
        )}
        {error && (
          <p className="text-sm text-danger" role="alert">
            {intl.formatMessage({ id: 'activity.evaluateError' })}
          </p>
        )}
      </div>
      {/* The ladder itself is the quiz item's, endpoint and all — only the URL differs
          (`api/activities.activityHintPath`). It stays mounted once the activity closes so
          the hints already earned sit next to the solution; only the "ask for another"
          affordance goes away. */}
      {unevaluable || !hasFailed ? null : (
        <HintLadder endpoint={activityHintPath(activityId)} disabled={closed} />
      )}
      {solutionShown ? <WorkedSolution solution={solution} /> : null}
      {/* Asked, and there was nothing to write out. Said plainly rather than left as an
          empty panel under a button that promised an answer — and the step is already
          open, so the learner is not held here by it. */}
      {revealed && !solutionShown && !result ? (
        <p className="mt-4 text-sm text-text-secondary" role="status">
          {/* Deliberately the tail of the sentence `Result` prints when the item closes
              with nothing to show (`activity.result.incorrectNoSolution`): one situation,
              one wording. */}
          {intl.formatMessage({ id: 'activity.solutionUnavailable' })}
        </p>
      ) : null}
    </section>
  )
}
