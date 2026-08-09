import { useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useIntl } from 'react-intl'
import { post } from '../../../api/client'
import { Button } from '../../ui'
import { HintLadder, WorkedSolution } from './QuizItemHints'
import { duration, ease } from '../../../lib/motion'
import { BLOCK_TITLE, INLINE_SURFACE } from './rhythm'
import { useNodeRenderTarget } from '../kit/NodeRenderContext'
import { useStepperAdvance, useStepperSolve } from './StepperContext'
import type { ExerciseType } from '../../../types'
import type { BloomLevel } from '../kit/schemas'
import type {
  NodeAnswerPayload,
  NodeAnswerRequest,
  NodeAttemptResult,
} from '../../../types/node-render'

export interface QuizItemBlockProps {
  item_id: string
  item_type: ExerciseType
  bloom_level: BloomLevel
  question: string
  options?: string[]
  /** Target of `POST /nodes/{nodeId}/answer`. Injected by `UiSpecRenderer`. */
  nodeId: string
  /**
   * The render this item belongs to. Absent only when a spec is previewed
   * outside a persisted render (Storybook, admin preview of a raw spec) — the
   * item then renders read-only instead of posting an ungradeable attempt.
   */
  renderId?: string
}

// §5.3: this block is AUTONOMOUS. It is deliberately NOT a bridge to v1's
// `ExerciseRenderer` — those six components each build their own mutations and
// key off a real `exercises` row id, so reusing them would mean refactoring six
// v1 files. ~120 lines of duplicated UI is the accepted price of not touching
// `src/components/exercises/`.

/** Item types answered by picking one option. Everything else is a constructed answer. */
const SINGLE_CHOICE_TYPES: readonly ExerciseType[] = ['test', 'true_false']

const TRUE_FALSE_OPTIONS = ['Verdadero', 'Falso']

function buildAnswer(
  itemType: ExerciseType,
  selected: number | null,
  text: string,
): NodeAnswerPayload | null {
  if (itemType === 'true_false') {
    return selected === null ? null : { answer: selected === 0 }
  }
  if (itemType === 'test') {
    return selected === null ? null : { selected }
  }
  const trimmed = text.trim()
  if (!trimmed) return null
  // `fill_blank` is graded against a list of blanks; the rest are open text.
  return itemType === 'fill_blank' ? { answers: [trimmed] } : { response: trimmed }
}

function ResultPanel({
  result,
  onRetry,
}: {
  result: NodeAttemptResult
  onRetry?: () => void
}) {
  const intl = useIntl()
  return (
    <motion.div
      role="status"
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: duration.normal, ease: [...ease.base] }}
      className={`mt-4 rounded-lg border p-4 ${
        result.passed ? 'border-accent bg-accent-subtle' : 'border-danger bg-danger/5'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span
          className={`text-sm font-medium ${result.passed ? 'text-accent' : 'text-danger'}`}
        >
          {result.passed ? intl.formatMessage({ id: 'quiz.correct' }) : intl.formatMessage({ id: 'quiz.incorrect' })}
        </span>
        <span className="text-xs text-text-secondary tabular-nums">
          {intl.formatMessage({ id: 'quiz.mastery' }, { pct: Math.round((result.mastery ?? 0) * 100) })}
        </span>
      </div>
      {result.feedback ? <p className="text-sm text-text mt-2">{result.feedback}</p> : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 text-sm font-medium text-primary hover:text-primary/80 transition-colors"
        >
          {intl.formatMessage({ id: 'quiz.retry' })}
        </button>
      ) : null}
    </motion.div>
  )
}

function SingleChoiceItem({
  name,
  options,
  selected,
  disabled,
  onSelect,
}: {
  name: string
  options: string[]
  selected: number | null
  disabled: boolean
  onSelect: (index: number) => void
}) {
  return (
    <div className="space-y-2">
      {options.map((option, idx) => (
        <label
          key={idx}
          className={`flex items-center gap-3 p-3 border rounded-lg transition-colors ${
            disabled ? 'cursor-default' : 'cursor-pointer'
          } ${selected === idx && !disabled ? 'border-2 border-primary' : 'border border-border'}`}
        >
          <input
            type="radio"
            name={name}
            checked={selected === idx}
            onChange={() => !disabled && onSelect(idx)}
            disabled={disabled}
            className="accent-primary"
          />
          <span className="text-sm text-text break-words min-w-0">{option}</span>
        </label>
      ))}
    </div>
  )
}

function ConstructedAnswerItem({
  value,
  disabled,
  rows,
  onChange,
}: {
  value: string
  disabled: boolean
  rows: number
  onChange: (value: string) => void
}) {
  const intl = useIntl()
  return (
    <textarea
      value={value}
      disabled={disabled}
      rows={rows}
      onChange={(e) => onChange(e.target.value)}
      placeholder={intl.formatMessage({ id: 'quiz.answerPlaceholder' })}
      aria-label={intl.formatMessage({ id: 'quiz.yourAnswer' })}
      className="w-full px-3 py-2 text-sm text-text border border-border rounded-lg bg-bg placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors disabled:opacity-60 resize-y"
    />
  )
}

export function QuizItemBlock({
  item_id,
  item_type,
  question,
  options,
  nodeId,
  renderId,
}: QuizItemBlockProps) {
  const intl = useIntl()
  const [selected, setSelected] = useState<number | null>(null)
  const [text, setText] = useState('')
  const queryClient = useQueryClient()
  const { recordEvent } = useNodeRenderTarget()
  const stepperAdvance = useStepperAdvance()
  // El paso ya nace cerrado por llevar este bloque dentro (`kit/solvableSteps.ts`), asi
  // que aqui no hay nada que cerrar: solo se avisa de que se ha abierto. Si este bloque
  // deja de llamar a `useStepperSolve`, o aparece otro que lo llame, hay que mover
  // `SOLVABLE_COMPONENTS` con el — `solvableSteps.test.ts` lo comprueba.
  const solveStep = useStepperSolve()

  // Latency is measured from mount, which is when the item became visible.
  const openedAt = useRef(Date.now())

  const submit = useMutation({
    mutationFn: (body: NodeAnswerRequest) =>
      post<NodeAttemptResult>(`/nodes/${nodeId}/answer`, body),
    onSuccess: (result) => {
      // Mastery moved server-side; the node list and the enrollment progress
      // that depend on it are now stale.
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })

      // §3.3: emit quiz_correct / quiz_wrong so the format_vector learns that
      // this learner engages with exercises. The element is always `ejercicio`
      // because a quiz item is an exercise component regardless of the lesson's
      // overall ui_format.
      if (recordEvent) {
        recordEvent({
          type: result.passed ? 'quiz_correct' : 'quiz_wrong',
          element: 'ejercicio',
          element_id: item_id,
        })
      }

      // Acertar abre el paso; fallar lo deja cerrado para que se reintente.
      //
      // `show_worked_solution` tambien lo abre, y no es un detalle: el servidor lo manda
      // cuando se acaban los intentos y le enseña la solucion al aprendiz. Ahi el item
      // queda bloqueado SIN haber pasado nunca por `passed`, asi que sin esta rama no hay
      // quien abra el paso y el aprendiz se queda encerrado en el nodo, sin nada que
      // pulsar. Solo avanza solo cuando acierta: si esta leyendo la solucion, que decida
      // el cuando pasar.
      if (result.passed) {
        solveStep?.()
        stepperAdvance?.()
      } else if (result.show_worked_solution === true) {
        solveStep?.()
      }
    },
  })

  const result = submit.data ?? null
  const isSingleChoice = SINGLE_CHOICE_TYPES.includes(item_type)
  const choices =
    item_type === 'true_false' && (!options || options.length === 0)
      ? TRUE_FALSE_OPTIONS
      : (options ?? [])

  // A passed item is final. So is one the server just closed with the worked solution
  // (§7.4 rule 8): the node has moved to `needs_review` and re-answering the same item
  // with the solution on screen would record an attempt that measures nothing. Everything
  // else can be retried, which is what `next === 'retry'` asks for.
  //
  // `workedSolution` is read from the server's flag and never inferred here. See
  // `QuizItemHints`: a client that decided when the solution appears could decide to see
  // it on the first attempt.
  const workedSolution = result?.show_worked_solution === true
  const locked = result?.passed === true || workedSolution
  const answer = buildAnswer(item_type, selected, text)
  const readOnly = !renderId

  function retry() {
    submit.reset()
    setSelected(null)
    setText('')
    openedAt.current = Date.now()
  }

  function send() {
    if (!answer || !renderId) return
    submit.mutate({
      render_id: renderId,
      item_id,
      answer,
      // Always zero, even though `HintLadder` below now spends real hints.
      //
      // The number is INFORMATIVE and the server must treat it as such: it is what
      // decides whether `correct_answer` comes back, and a field the client fills in
      // cannot govern revealing the answer — `hints_used: 3` would otherwise be a
      // free answer key for anyone with the network tab open. The count of record is
      // `node_attempts.hints_used` for this `(user, node, item)`, incremented only by
      // the hint endpoint. See `NodeAnswerRequest.hints_used` and §11.3 (B5).
      hints_used: 0,
      latency_ms: Math.max(0, Date.now() - openedAt.current),
    })
  }

  return (
    <div
      // §8.5: the WHOLE item is excluded from click-to-explain — statement AND
      // options. Explaining a word inside the correct option leaks the answer.
      data-no-explain=""
      className={`${INLINE_SURFACE} bg-bg-subtle`}
    >
      {/* The stem is a block title, not a heavier thing: it used to sit on `mb-4`
          while every other block's title sat on `mb-3`, so a quiz next to a
          StepSequence was visibly on a different grid. */}
      <p className={BLOCK_TITLE}>{question}</p>

      {isSingleChoice ? (
        <SingleChoiceItem
          // Scoped by node so two renders of the same item on one page keep
          // independent radio groups.
          name={`${nodeId}:${item_id}`}
          options={choices}
          selected={selected}
          disabled={locked || readOnly || submit.isPending}
          onSelect={setSelected}
        />
      ) : (
        <ConstructedAnswerItem
          value={text}
          rows={item_type === 'fill_blank' ? 2 : 5}
          disabled={locked || readOnly || submit.isPending}
          onChange={setText}
        />
      )}

      {readOnly ? (
        <p className="mt-4 text-xs text-text-muted">
          {intl.formatMessage({ id: 'quiz.previewOnly' })}
        </p>
      ) : (
        !locked && (
          <Button
            size="sm"
            className="mt-4"
            disabled={!answer || submit.isPending}
            onClick={send}
          >
            {submit.isPending ? intl.formatMessage({ id: 'quiz.checking' }) : intl.formatMessage({ id: 'quiz.check' })}
          </Button>
        )
      )}

      {renderId ? (
        <HintLadder
          nodeId={nodeId}
          renderId={renderId}
          itemId={item_id}
          // Kept mounted once the item closes so the hints already earned stay on
          // screen next to the solution; only the "pedir otra" affordance goes away.
          disabled={locked}
        />
      ) : null}

      {submit.isError ? (
        <p className="mt-3 text-sm text-danger">{intl.formatMessage({ id: 'quiz.submitError' })}</p>
      ) : null}

      {result ? <ResultPanel result={result} onRetry={locked ? undefined : retry} /> : null}

      {workedSolution ? (
        <WorkedSolution
          itemType={item_type}
          correctAnswer={result?.correct_answer ?? null}
          options={choices}
        />
      ) : null}
    </div>
  )
}
