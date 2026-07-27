import { useState } from 'react'
import { Button } from '../ui'
import { useNodeFeedback } from '../../api/nodes'

/**
 * End-of-node feedback (§3.3, §11.3).
 *
 * Three fixed answers and one optional free-text box, and both halves have consequences
 * the learner can feel:
 *
 * - `difficulty` is what fires the tutor signals: `hard` → `bajar_dificultad`,
 *   `easy` + three correct in a row → `subir_dificultad`. The signals are applied in the
 *   same transaction as the row, so the next node is already affected.
 * - `unclear` is one of only **two** places in the product where text the learner wrote
 *   is persisted (the other is the term they clicked). It is optional, it is bounded at
 *   1000 characters server-side, and the label says what it is for instead of pretending
 *   to be a support channel.
 *
 * `POST /feedback` upserts on `(user_id, node_id)`, so answering twice corrects the
 * answer rather than duplicating it — which is why the row stays editable after sending.
 */

export interface NodeFeedbackProps {
  nodeId: string
}

const OPTIONS: { value: 'easy' | 'ok' | 'hard'; label: string }[] = [
  { value: 'easy', label: 'Facil' },
  { value: 'ok', label: 'Bien' },
  { value: 'hard', label: 'Dificil' },
]

export function NodeFeedback({ nodeId }: NodeFeedbackProps) {
  const feedback = useNodeFeedback(nodeId)
  const [difficulty, setDifficulty] = useState<'easy' | 'ok' | 'hard' | null>(null)
  const [unclear, setUnclear] = useState('')
  const [showUnclear, setShowUnclear] = useState(false)

  function send(next: 'easy' | 'ok' | 'hard', text: string) {
    setDifficulty(next)
    feedback.mutate({ difficulty: next, unclear: text.trim() ? text.trim() : null })
  }

  return (
    <div className="mt-6 space-y-3" data-no-explain="" data-testid="node-feedback">
      <p className="text-sm text-text-secondary">Como te ha resultado este nodo?</p>

      <div className="flex flex-wrap items-center gap-2">
        {OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            aria-pressed={difficulty === option.value}
            onClick={() => send(option.value, unclear)}
            className={`px-3 py-1.5 text-xs font-medium rounded-md border transition-colors ${
              difficulty === option.value
                ? 'border-primary text-primary bg-primary-subtle'
                : 'border-border text-text-secondary hover:border-primary'
            }`}
          >
            {option.label}
          </button>
        ))}
        {difficulty !== null && !feedback.isPending && !feedback.isError && (
          <span className="text-xs text-text-muted" role="status">
            Gracias, lo tendremos en cuenta en el siguiente nodo.
          </span>
        )}
      </div>

      {!showUnclear ? (
        <button
          type="button"
          onClick={() => setShowUnclear(true)}
          className="text-xs font-medium text-primary hover:text-primary/80 transition-colors"
        >
          Algo no ha quedado claro
        </button>
      ) : (
        <div className="space-y-2">
          <label htmlFor={`unclear-${nodeId}`} className="block text-xs text-text-secondary">
            Que parte no ha quedado clara? (opcional)
          </label>
          <textarea
            id={`unclear-${nodeId}`}
            value={unclear}
            rows={3}
            maxLength={1000}
            onChange={(event) => setUnclear(event.target.value)}
            className="w-full px-3 py-2 text-sm text-text border border-border rounded-lg bg-bg placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors resize-y"
          />
          <Button
            size="sm"
            variant="secondary"
            disabled={!unclear.trim() || feedback.isPending}
            onClick={() => send(difficulty ?? 'ok', unclear)}
          >
            Enviar
          </Button>
        </div>
      )}

      {feedback.isError && (
        <p className="text-sm text-danger">No se pudo enviar tu valoracion.</p>
      )}
    </div>
  )
}
