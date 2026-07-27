import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { post } from '../../../api/client'
import { Button } from '../../ui'
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
  return (
    <div
      role="status"
      className={`mt-4 rounded-lg border p-4 ${
        result.passed ? 'border-accent bg-accent-subtle' : 'border-danger bg-danger/5'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span
          className={`text-sm font-medium ${result.passed ? 'text-accent' : 'text-danger'}`}
        >
          {result.passed ? 'Correcto' : 'Incorrecto'}
        </span>
        <span className="text-xs text-text-secondary tabular-nums">
          Dominio: {Math.round((result.mastery ?? 0) * 100)}%
        </span>
      </div>
      {result.feedback ? <p className="text-sm text-text mt-2">{result.feedback}</p> : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 text-sm font-medium text-primary hover:text-primary/80 transition-colors"
        >
          Reintentar
        </button>
      ) : null}
    </div>
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
          } ${selected === idx && !disabled ? 'border-primary' : 'border-border'}`}
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
  return (
    <textarea
      value={value}
      disabled={disabled}
      rows={rows}
      onChange={(e) => onChange(e.target.value)}
      placeholder="Escribe tu respuesta..."
      aria-label="Tu respuesta"
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
  const [selected, setSelected] = useState<number | null>(null)
  const [text, setText] = useState('')
  const queryClient = useQueryClient()

  // Latency is measured from mount, which is when the item became visible.
  const openedAt = useRef(Date.now())

  const submit = useMutation({
    mutationFn: (body: NodeAnswerRequest) =>
      post<NodeAttemptResult>(`/nodes/${nodeId}/answer`, body),
    onSuccess: () => {
      // Mastery moved server-side; the node list and the enrollment progress
      // that depend on it are now stale.
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
    },
  })

  const result = submit.data ?? null
  const isSingleChoice = SINGLE_CHOICE_TYPES.includes(item_type)
  const choices =
    item_type === 'true_false' && (!options || options.length === 0)
      ? TRUE_FALSE_OPTIONS
      : (options ?? [])

  // A passed item is final. A failed one can be retried, which is what
  // `next === 'retry'` asks for.
  const locked = result?.passed === true
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
      // Hints come from `POST /nodes/{id}/hint`, owned by the node view (B9).
      // This block never grants one, so it always reports zero.
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
      className="rounded-lg border border-border bg-bg-subtle p-4 min-w-0"
    >
      <p className="text-sm font-medium text-text mb-4">{question}</p>

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
          Vista previa: esta respuesta no se corrige.
        </p>
      ) : (
        !locked && (
          <Button
            size="sm"
            className="mt-4"
            disabled={!answer || submit.isPending}
            onClick={send}
          >
            {submit.isPending ? 'Comprobando...' : 'Comprobar'}
          </Button>
        )
      )}

      {submit.isError ? (
        <p className="mt-3 text-sm text-danger">No se pudo enviar la respuesta.</p>
      ) : null}

      {result ? <ResultPanel result={result} onRetry={result.passed ? undefined : retry} /> : null}
    </div>
  )
}
