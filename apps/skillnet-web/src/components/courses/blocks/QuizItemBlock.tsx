import { useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useIntl } from 'react-intl'
import { post } from '../../../api/client'
import { Button } from '../../ui'
import { HintLadder, WorkedSolution } from './QuizItemHints'
import { duration, ease } from '../../../lib/motion'
import { INLINE_SURFACE } from './rhythm'
import { useNodeRenderTarget } from '../kit/NodeRenderContext'
import { useLessonFeedback, useStepperSolve } from './StepperContext'
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
      className={`mt-4 rounded-xl border p-4 ${
        result.passed ? 'border-accent bg-accent-subtle' : 'border-danger bg-danger/5'
      }`}
    >
      <div className="flex items-center gap-2">
        <span
          className={`text-lesson-body font-medium ${result.passed ? 'text-accent' : 'text-danger'}`}
        >
          {result.passed ? intl.formatMessage({ id: 'quiz.correct' }) : intl.formatMessage({ id: 'quiz.incorrect' })}
        </span>
      </div>
      {result.feedback ? <p className="text-lesson-body text-text mt-2">{result.feedback}</p> : null}
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

/**
 * Lo que una respuesta YA graduada dice de las opciones.
 *
 * `null` mientras no hay nota. El componente no juzga nada: `passed` y `correctIndex`
 * salen del servidor (`correctIndex` solo cuando el servidor decide revelar la solucion),
 * asi que la opcion correcta no se puede leer del DOM antes de fallar.
 */
interface ChoiceOutcome {
  passed: boolean
  correctIndex: number | null
}

/**
 * El indice de la opcion correcta tal y como lo entiende esta lista de opciones, o `null`.
 *
 * Espeja `buildAnswer`: en `true_false` la primera opcion es "Verdadero", asi que
 * `correct: true` es el indice 0. Si los dos lados dejan de coincidir, el aprendiz ve
 * marcada en verde la opcion contraria a la que acerto, que es peor que no marcar nada.
 */
function revealedCorrectIndex(
  itemType: ExerciseType,
  correctAnswer: Record<string, unknown> | null,
): number | null {
  if (!correctAnswer) return null
  if (itemType === 'true_false') {
    return typeof correctAnswer.correct === 'boolean' ? (correctAnswer.correct ? 0 : 1) : null
  }
  if (itemType === 'test') {
    return typeof correctAnswer.correct === 'number' ? correctAnswer.correct : null
  }
  return null
}

function SingleChoiceItem({
  name,
  options,
  selected,
  disabled,
  outcome,
  onSelect,
}: {
  name: string
  options: string[]
  selected: number | null
  disabled: boolean
  /** `null` hasta que hay nota; entonces pinta el acierto y el fallo. */
  outcome: ChoiceOutcome | null
  onSelect: (index: number) => void
}) {
  return (
    <div className="space-y-3">
      {options.map((option, idx) => {
        // Seleccionada es seleccionada, tambien con los controles congelados. El `&&
        // !disabled` que habia aqui borraba el resaltado en el instante de responder: la
        // opcion elegida se quedaba igual que las demas y la correccion no se veia por
        // ninguna parte — ni verde ni roja, que es exactamente lo que se reporto.
        const active = selected === idx
        return (
          <label
            key={idx}
            // Each option is a full-width, tappable hairline panel. The selected
            // state is a full border in the primary colour plus a restrained tint
            // (`bg-primary-subtle`) — never a left edge, never a heavier ring. The
            // border width stays 1px in every state so selecting one never nudges
            // the layout.
            // Ya graduada: la elegida se pinta del color de su suerte (verde si acerto,
            // rojo si no) y, cuando el servidor revela la solucion, la correcta se marca
            // en verde aunque no se haya elegido. Sin nota, el estado seleccionado sigue
            // siendo el de siempre. El borde mide 1px en todos los casos para que
            // corregir no mueva la maquetacion.
            className={`flex w-full items-center gap-3 rounded-xl border p-4 transition-colors ${
              disabled ? 'cursor-default' : 'cursor-pointer'
            } ${
              outcome
                ? active
                  ? outcome.passed
                    ? 'border-accent bg-accent-subtle'
                    : 'border-danger bg-danger/5'
                  : outcome.correctIndex === idx
                    ? 'border-accent bg-accent-subtle'
                    : 'border-border'
                : active
                  ? 'border-primary bg-primary-subtle'
                  : `border-border ${disabled ? '' : 'hover:border-border-strong'}`
            }`}
          >
            <input
              type="radio"
              name={name}
              checked={selected === idx}
              onChange={() => !disabled && onSelect(idx)}
              disabled={disabled}
              className="accent-primary"
            />
            <span className="text-lesson-body text-text break-words min-w-0">{option}</span>
          </label>
        )
      })}
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
      className="w-full p-4 text-lesson-body text-text border border-border rounded-xl bg-bg placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors disabled:opacity-60 resize-y"
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
  // El paso ya nace cerrado por llevar este bloque dentro (`kit/solvableSteps.ts`), asi
  // que aqui no hay nada que cerrar: solo se avisa de que se ha abierto. Si este bloque
  // deja de llamar a `useStepperSolve`, o aparece otro que lo llame, hay que mover
  // `SOLVABLE_COMPONENTS` con el — `solvableSteps.test.ts` lo comprueba.
  const solveStep = useStepperSolve()
  // Feedback ambiental (ResultGlow + mascota). Independiente de si abre el paso.
  const feedback = useLessonFeedback()

  // Latency is measured from mount, which is when the item became visible.
  const openedAt = useRef(Date.now())
  // Keep one idempotency key for every logical submission. Transport retries reuse
  // it; the explicit learner retry below rotates it for the next attempt.
  const attemptId = useRef(crypto.randomUUID())
  // The graded result lives in local state, not `submit.data`. `useMutation`'s reset()
  // clears its own state through the query client's notify manager, which in a real
  // browser (unlike RTL's `act()`-wrapped test runs) can land a render tick apart from
  // the `setSelected(null)` right next to it in `retry()` — the radios re-enable but
  // `submit.data` is still the stale result for one paint, and the click that follows
  // races it. Owning `result` directly means `retry()` clears it in the same state
  // update as everything else, with no dependency on when the mutation's own
  // subscribers get notified.
  const [result, setResult] = useState<NodeAttemptResult | null>(null)
  // Bumped on every explicit learner retry. It keys the answer region so the radios /
  // textarea are torn down and rebuilt from scratch each attempt. Clearing `result` and
  // `selected` already re-enables them through `attemptFinished`, but in the real browser
  // a graded attempt leaves a checked+disabled radio whose reset depended on a re-render
  // landing in the same tick; remounting the subtree makes "unchecked and enabled again"
  // unconditional instead of derived, which is what the RTL harness could not surface.
  const [attemptNonce, setAttemptNonce] = useState(0)

  const submit = useMutation({
    mutationFn: (body: NodeAnswerRequest) =>
      post<NodeAttemptResult>(`/nodes/${nodeId}/answer`, body),
    onSuccess: (result) => {
      setResult(result)
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

      // Acertar abre el paso (aparece el boton de avanzar); fallar lo deja cerrado
      // para que se reintente. Abrir el paso NO avanza solo: el aprendiz pulsa el
      // boton cuando quiere — antes auto-avanzaba a 1.2s y ademas salia el boton, que
      // quedaba raro.
      //
      // `show_worked_solution` tambien lo abre, y no es un detalle: el servidor lo manda
      // cuando se acaban los intentos y le enseña la solucion al aprendiz. Ahi el item
      // queda bloqueado SIN haber pasado nunca por `passed`, asi que sin esta rama no hay
      // quien abra el paso y el aprendiz se queda encerrado en el nodo, sin nada que pulsar.
      if (result.passed) {
        feedback?.report('acierto')
        solveStep?.()
      } else if (result.show_worked_solution === true) {
        // Se acabaron los intentos: fallo sin reintento -> rojo reservado + mascota ups.
        feedback?.report('fallo', { definitivo: true })
        solveStep?.()
      } else {
        // Fallo con reintento: ambar "todavia no", no rojo.
        feedback?.report('fallo')
      }
    },
  })

  const isSingleChoice = SINGLE_CHOICE_TYPES.includes(item_type)
  const choices =
    item_type === 'true_false' && (!options || options.length === 0)
      ? TRUE_FALSE_OPTIONS
      : (options ?? [])

  // A passed item is final. So is one the server just closed with the worked solution
  // (§7.4 rule 8): the item is done with — the learner has the solution and moves on, and
  // re-answering it with the answer on screen would record an attempt that measures
  // nothing. Everything else can be retried, which is what `next === 'retry'` asks for.
  //
  // `workedSolution` is read from the server's flag and never inferred here. See
  // `QuizItemHints`: a client that decided when the solution appears could decide to see
  // it on the first attempt.
  const workedSolution = result?.show_worked_solution === true
  const locked = result?.passed === true || workedSolution
  // Once the server has graded an attempt, freeze its controls until the learner
  // explicitly starts a new attempt. Previously a failed result left the radios and
  // "Comprobar" enabled: choosing another option reused the old idempotency key, the
  // server correctly rejected it as a conflicting payload, and the UI made every
  // subsequent option look wrong. `retry()` rotates that key and clears the result.
  const attemptFinished = result !== null
  const answer = buildAnswer(item_type, selected, text)
  const readOnly = !renderId

  function retry() {
    setResult(null)
    submit.reset()
    setSelected(null)
    setText('')
    openedAt.current = Date.now()
    attemptId.current = crypto.randomUUID()
    setAttemptNonce((n) => n + 1)
  }

  function send() {
    if (!answer || !renderId) return
    submit.mutate({
      attempt_id: attemptId.current,
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
      {/* The question stem leads the exercise, so it is the lead of the lesson
          scale — a step up from a block title — with generous room before the
          options. Full contrast, medium weight; hierarchy from size, not dimming. */}
      <p className="text-lesson-lead font-medium text-text mb-5">{question}</p>

      {isSingleChoice ? (
        <SingleChoiceItem
          // `attemptNonce` forces a fresh subtree per attempt (see `retry`). Scoped by
          // node so two renders of the same item on one page keep independent radio
          // groups.
          key={`choice-${attemptNonce}`}
          name={`${nodeId}:${item_id}:${attemptNonce}`}
          options={choices}
          selected={selected}
          disabled={attemptFinished || readOnly || submit.isPending}
          outcome={
            result
              ? {
                  passed: result.passed,
                  correctIndex: revealedCorrectIndex(item_type, result.correct_answer),
                }
              : null
          }
          onSelect={setSelected}
        />
      ) : (
        <ConstructedAnswerItem
          key={`text-${attemptNonce}`}
          value={text}
          rows={item_type === 'fill_blank' ? 2 : 5}
          disabled={attemptFinished || readOnly || submit.isPending}
          onChange={setText}
        />
      )}

      {readOnly ? (
        <p className="mt-4 text-xs text-text-muted">
          {intl.formatMessage({ id: 'quiz.previewOnly' })}
        </p>
      ) : (
        !attemptFinished && (
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
