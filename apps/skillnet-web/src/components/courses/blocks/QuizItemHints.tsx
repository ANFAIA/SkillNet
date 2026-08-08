import { useState } from 'react'
import { useIntl } from 'react-intl'
import { useMutation } from '@tanstack/react-query'
import { ApiError, post } from '../../../api/client'
import type { ExerciseType, NodeHintResult } from '../../../types'

/**
 * The scaffolding ladder of §7.4, and the piece that made a whole system state reachable.
 *
 * ## Why this exists
 *
 * `POST /nodes/{id}/hint` is the **only** writer of `node_attempts.hints_used`. Rule 8 of
 * §7.3 — fourth failure of an item after three hints -> worked solution + `needs_review` —
 * reads that column, so with nothing calling the endpoint the rule could never fire: the
 * `needs_review` state was unreachable, `NodeSummaryRead.needs_practice` was permanently
 * `false`, and the "Para practicar" queue `NodeList` already renders could never fill.
 * The server half was built and dead. This is the client half.
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
  nodeId: string
  /** `node_renders.id`. The hint endpoint resolves the item inside this render. */
  renderId: string
  itemId: string
  /** True once the item is closed (passed, or the worked solution is out). */
  disabled?: boolean
}

export function HintLadder({ nodeId, renderId, itemId, disabled = false }: HintLadderProps) {
  const intl = useIntl()
  const [hints, setHints] = useState<NodeHintResult[]>([])
  const [refusal, setRefusal] = useState<string | null>(null)

  const ask = useMutation({
    mutationFn: () =>
      post<NodeHintResult>(`/nodes/${nodeId}/hint`, { render_id: renderId, item_id: itemId }),
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
  itemType: ExerciseType
  /** `NodeAttemptResult.correct_answer` — only ever populated by the server. */
  correctAnswer: Record<string, unknown> | null
  /** The item's options / steps, so an index can be printed as the text it means. */
  options?: string[]
}

function optionAt(options: string[] | undefined, index: unknown): string | null {
  if (typeof index !== 'number' || !options) return null
  return options[index] ?? null
}

/**
 * What the fourth failure earns: the solution, spelled out.
 *
 * Rendered **only** when the server sets `show_worked_solution`. The component never
 * decides that — see the module docstring. It also never invents the solution: every
 * line comes out of `correct_answer`, which the server populates from the answer key it
 * kept, and if a field is missing the line is simply not printed.
 */
export function WorkedSolution({ itemType, correctAnswer, options }: WorkedSolutionProps) {
  const intl = useIntl()
  if (!correctAnswer) return null

  const explanation =
    typeof correctAnswer.explanation === 'string' ? correctAnswer.explanation : null

  let solution: string | null = null
  if (itemType === 'true_false' && typeof correctAnswer.correct === 'boolean') {
    solution = correctAnswer.correct ? intl.formatMessage({ id: 'hints.true' }) : intl.formatMessage({ id: 'hints.false' })
  } else if (itemType === 'test') {
    solution = optionAt(options, correctAnswer.correct)
  } else if (itemType === 'fill_blank' && Array.isArray(correctAnswer.blanks)) {
    solution = correctAnswer.blanks.map((blank) => String(blank)).join(', ')
  } else if (itemType === 'order_steps' && Array.isArray(correctAnswer.correct_order)) {
    const steps = correctAnswer.correct_order
      .map((index) => optionAt(options, index))
      .filter((step): step is string => step !== null)
    solution = steps.length > 0 ? steps.join(' -> ') : null
  }

  if (!solution && !explanation) return null

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
