import { useState } from 'react'
import { useIntl } from 'react-intl'
import { useMutation } from '@tanstack/react-query'
import { ApiError, post } from '../../../api/client'
import type { EvaluationSolution } from '../../../lib/didact/host-ports'
import type { ExerciseType, NodeHintResult } from '../../../types'

/**
 * The scaffolding ladder of §7.4, and the learner's way out of an item they cannot solve.
 *
 * ## Why this exists
 *
 * `POST /nodes/{id}/hint` is the **only** writer of `node_attempts.hints_used`, so with
 * nothing calling the endpoint the ladder existed on the server and was dead. This is the
 * client half.
 *
 * It is no longer the *only* way out of an item, and that matters for what this component
 * promises: rule 8 of §7.3 — fourth failure of the same item -> worked solution, and the
 * learner carries on — used to demand the hint quota be spent too, which made the exit
 * depend on the learner asking for help. It reads the failure count alone now. What
 * `hints_used` still governs is `correct_answer` being revealed *early*, before those four
 * failures.
 *
 * ## The one rule that is not negotiable
 *
 * **The count belongs to the server.** Every number shown here comes out of a
 * `NodeHintResult` the server just sent (`hints_used`, `hints_remaining`); nothing is
 * derived from how many times this component was clicked, and nothing here decides
 * whether a hint may be served. The two refusals — "try once first" and "quota spent" —
 * are `409`s from the endpoint, printed verbatim, because they are the server's rules and
 * a local copy of them would be a second source of truth that drifts.
 *
 * That matters beyond tidiness: `hints_used` is what governs whether `correct_answer` is
 * revealed on the next answer. A client that could count its own hints could ask for
 * zero, claim three, and be handed the key.
 *
 * ## What the learner sees
 *
 * The hints accumulate on screen rather than replacing each other — the escalation *is*
 * the help (idea of the node -> structural nudge -> worked reasoning), and hiding step 1
 * when step 2 arrives throws away the part that was still true. The remaining count is
 * always visible, so "one more and that is all" is never a surprise.
 */

/** §7.4, mirrored from `HINT_LIMIT` in `src/services/mastery_service.py`. */
export const HINT_LIMIT = 3

export interface HintLadderProps {
  /**
   * Where to ask for the next hint. A `POST` here answers with a `NodeHintResult`, or
   * refuses with a `409` carrying the sentence to print.
   *
   * It is a prop and not a `nodeId` because the ladder itself is not about nodes: the
   * quiz item asks `/nodes/{id}/hint` and a Didact activity asks
   * `/activities/{id}/hint`, and everything else on screen — the escalation, the
   * server-owned count, the two refusals — is the same rule for both. The URL was the
   * only thing tying this component to `QuizItem`, so the URL is what moved out.
   */
  endpoint: string
  /**
   * What that endpoint needs to find the item. The node ladder addresses one item inside
   * one render; the activity ladder addresses the activity in the path and sends nothing.
   */
  body?: Record<string, unknown>
  /** True once the item is closed (passed, or the worked solution is out). */
  disabled?: boolean
}

export function HintLadder({ endpoint, body, disabled = false }: HintLadderProps) {
  const intl = useIntl()
  const [hints, setHints] = useState<NodeHintResult[]>([])
  const [refusal, setRefusal] = useState<string | null>(null)

  const ask = useMutation({
    mutationFn: () => post<NodeHintResult>(endpoint, body ?? {}),
    onSuccess: (result) => {
      setRefusal(null)
      setHints((prev) => [...prev, result])
    },
    onError: (error: unknown) => {
      // A `409` is an answer, not a failure: "intentalo una vez antes" and "ya has usado
      // las tres pistas" are both rules of §7.4 and both arrive with the sentence to show.
      setRefusal(
        error instanceof ApiError
          ? error.body.detail
          : intl.formatMessage({ id: 'hints.requestError' }),
      )
    },
  })

  const last = hints.length > 0 ? hints[hints.length - 1] : null
  // Server-sourced, always. `hints.length` is what *this session* saw; a learner who
  // spent a hint yesterday has a smaller quota than that number suggests, and only the
  // server knows it — which is why the button stays enabled until the server says no.
  const exhausted = last !== null && last.hints_remaining <= 0

  return (
    <div className="mt-4 space-y-2">
      {hints.map((entry, index) => (
        <div
          key={`${entry.hints_used}-${index}`}
          className="rounded-lg border border-border bg-bg px-3 py-2"
        >
          <p className="text-xs font-medium text-text-secondary">
            {intl.formatMessage({ id: 'hints.hintOf' }, { used: entry.hints_used, total: entry.hints_used + entry.hints_remaining })}
          </p>
          <p className="mt-1 text-sm text-text">{entry.hint}</p>
        </div>
      ))}

      {refusal ? <p className="text-sm text-text-secondary">{refusal}</p> : null}

      {!disabled &&
        (exhausted ? (
          <p className="text-xs text-text-muted">
            {intl.formatMessage({ id: 'hints.exhausted' }, { limit: HINT_LIMIT })}
          </p>
        ) : (
          <div className="flex flex-wrap items-baseline gap-2">
            <button
              type="button"
              onClick={() => ask.mutate()}
              disabled={ask.isPending}
              className="text-sm font-medium text-primary hover:text-primary/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {ask.isPending ? intl.formatMessage({ id: 'hints.requesting' }) : intl.formatMessage({ id: 'hints.request' })}
            </button>
            <span className="text-xs text-text-muted">
              {last
                ? intl.formatMessage({ id: 'hints.remaining' }, { count: last.hints_remaining })
                : intl.formatMessage({ id: 'hints.available' }, { limit: HINT_LIMIT })}
            </span>
          </div>
        ))}
    </div>
  )
}

// ------------------------------------------------------------------------------- //
// The worked solution (§7.4)
// ------------------------------------------------------------------------------- //

export interface WorkedSolutionProps {
  /**
   * A solution the server already wrote out (`EvaluationResult.solution`).
   *
   * When it is here it is what gets printed, and the answer-key shapes below are not
   * consulted at all: the sentences are the server's, and there is nothing to take apart.
   * This is the Didact families' way in — they have no `ExerciseType` and no
   * `correct_answer`, so without it the panel had no branch that could ever match.
   */
  solution?: EvaluationSolution | null
  /** v1 item type, which decides how `correctAnswer` is read. */
  itemType?: ExerciseType
  /** `NodeAttemptResult.correct_answer` — only ever populated by the server. */
  correctAnswer?: Record<string, unknown> | null
  /** The item's options / steps, so an index can be printed as the text it means. */
  options?: string[]
}

function optionAt(options: string[] | undefined, index: unknown): string | null {
  if (typeof index !== 'number' || !options) return null
  return options[index] ?? null
}

/**
 * The two halves of a revealed answer key, before either is put into words.
 *
 * `answer` stays a value instead of a finished string because `true_false` reveals a
 * translated word, and this reader has no `intl`: it is a plain function precisely so a
 * call site can ask **whether there is anything to show** before promising the learner a
 * solution. `WorkedSolution` renders nothing when there is not, and a caller that gated
 * its own copy on a different rule would be a second answer to the same question.
 */
export interface RevealedSolution {
  answer: { kind: 'text'; text: string } | { kind: 'boolean'; value: boolean } | null
  explanation: string | null
}

/**
 * Read `NodeAttemptResult.correct_answer` into what the panel prints, or `null` when
 * there is nothing printable in it.
 *
 * Nothing printable is a real outcome and not an error: `_correct_answer`
 * (`routes/nodes.py`) projects only `correct` / `correct_order` / `blanks` /
 * `explanation`, so an open item whose key is a rubric arrives with an `explanation` or
 * with nothing at all — rubrics are deliberately never exposed. An `order_steps` item
 * arrives as a list of INDICES, so it also comes to nothing when the texts they index
 * into are missing (see `QuizItemBlockProps.steps`).
 */
export function readRevealedSolution(
  itemType: ExerciseType | undefined,
  correctAnswer: Record<string, unknown> | null | undefined,
  options?: string[],
): RevealedSolution | null {
  if (!correctAnswer) return null

  const explanation =
    typeof correctAnswer.explanation === 'string' && correctAnswer.explanation
      ? correctAnswer.explanation
      : null

  let answer: RevealedSolution['answer'] = null
  if (itemType === 'true_false' && typeof correctAnswer.correct === 'boolean') {
    answer = { kind: 'boolean', value: correctAnswer.correct }
  } else if (itemType === 'test') {
    const text = optionAt(options, correctAnswer.correct)
    answer = text ? { kind: 'text', text } : null
  } else if (itemType === 'fill_blank' && Array.isArray(correctAnswer.blanks)) {
    const blanks = correctAnswer.blanks.map((blank) => String(blank)).filter(Boolean)
    answer = blanks.length > 0 ? { kind: 'text', text: blanks.join(', ') } : null
  } else if (itemType === 'order_steps' && Array.isArray(correctAnswer.correct_order)) {
    const steps = correctAnswer.correct_order
      .map((index) => optionAt(options, index))
      .filter((step): step is string => Boolean(step))
    answer = steps.length > 0 ? { kind: 'text', text: steps.join(' -> ') } : null
  }

  if (!answer && !explanation) return null
  return { answer, explanation }
}

/** The panel itself, shared by both ways of arriving at a solution. */
function SolutionPanel({
  solution,
  explanation,
}: {
  solution: string | null
  explanation: string | null
}) {
  const intl = useIntl()
  return (
    <div className="mt-4 rounded-lg border border-border bg-bg-subtle p-4" role="note">
      <p className="text-sm font-medium text-text">{intl.formatMessage({ id: 'hints.solutionTitle' })}</p>
      {solution ? (
        <p className="mt-2 text-sm text-text">
          <span className="text-text-secondary">{intl.formatMessage({ id: 'hints.correctAnswer' })}</span>
          {solution}
        </p>
      ) : null}
      {explanation ? <p className="mt-2 text-sm text-text">{explanation}</p> : null}
      <p className="mt-3 text-xs text-text-muted">
        {intl.formatMessage({ id: 'hints.closedNote' })}
      </p>
    </div>
  )
}

/**
 * What the end of the ladder earns: the solution, spelled out.
 *
 * Rendered **only** when the server has already handed the answer over — either by
 * setting `show_worked_solution` or by sending `correct_answer` back once the hint quota
 * is spent. The component never decides that, and never invents the solution either:
 * every line comes out of `correct_answer`, which the server populates from the answer
 * key it kept, and a missing field is simply not printed. When nothing at all is
 * printable it renders nothing, so the call site has to ask `readRevealedSolution`
 * before it announces a solution — see `QuizItemBlock`.
 */
export function WorkedSolution({
  solution: written,
  itemType,
  correctAnswer,
  options,
}: WorkedSolutionProps) {
  const intl = useIntl()

  // A solution somebody already wrote wins, and short-circuits everything below: nothing
  // about the item's type is needed to print a finished sentence.
  if (written) {
    return <SolutionPanel solution={written.solution} explanation={written.explanation ?? null} />
  }

  const revealed = readRevealedSolution(itemType, correctAnswer, options)
  if (!revealed) return null

  const solution =
    revealed.answer === null
      ? null
      : revealed.answer.kind === 'boolean'
        ? intl.formatMessage({ id: revealed.answer.value ? 'hints.true' : 'hints.false' })
        : revealed.answer.text

  return <SolutionPanel solution={solution} explanation={revealed.explanation} />
}
