import { Button, ProgressBar } from '../ui'
import { CriticalityBadge } from './CriticalityBadge'
import type { NodeCriticality } from '../../types'

/**
 * The human half of the gate (§11.1 rule 2).
 *
 * `POST /schema/validate` proves the graph is well formed. It cannot prove a person
 * read the pedagogy, which is why every node carries `reviewed_at` and why a node
 * without it is never served (`409 node_not_reviewed`). This list is where that stamp
 * is applied, one node at a time, and it is the reason the validate button upstream
 * stays disabled until the count reaches the total.
 *
 * Marking is a **separate request** from saving on purpose: `PUT /schema` clears
 * `reviewed_at` on any node whose title, summary, criticality or source headings
 * changed. Stamping a node that still has unsaved edits would therefore be undone by
 * the very next save, so a dirty node's button is disabled and says why.
 */

export interface ReviewChecklistItem {
  key: string
  /** `null` for a node that only exists in the draft — nothing to stamp yet. */
  id: string | null
  position: number
  title: string
  criticality: NodeCriticality
  reviewedAt: string | null
  archived: boolean
  /** Local edits not yet sent to the server. */
  dirty: boolean
}

export function ReviewChecklist({
  items,
  selectedKey,
  onSelect,
  onMarkReviewed,
  pendingNodeId,
  locked,
}: {
  items: ReviewChecklistItem[]
  selectedKey: string | null
  onSelect: (key: string) => void
  onMarkReviewed: (nodeId: string) => void
  /** Node whose review request is in flight. */
  pendingNodeId: string | null
  locked: boolean
}) {
  // Archived nodes are excluded from every gate rule server-side, so they are
  // excluded from the count here too — otherwise the tally could never complete.
  const live = items.filter((item) => !item.archived)
  const reviewed = live.filter((item) => item.reviewedAt && !item.dirty)
  const remaining = live.length - reviewed.length

  return (
    <div className="border border-border rounded-lg min-w-0">
      <div className="p-4 border-b border-border">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="text-base font-medium text-text">Revision</h3>
          <span className="text-xs text-text-muted shrink-0 tabular-nums">
            {reviewed.length} de {live.length}
          </span>
        </div>
        <ProgressBar
          value={live.length === 0 ? 0 : (reviewed.length / live.length) * 100}
          size="sm"
          className="mt-2"
        />
        <p className="text-xs text-text-secondary mt-2">
          {remaining === 0 && live.length > 0
            ? 'Todos los nodos estan revisados. Ya puedes validar el esquema.'
            : remaining === 1
              ? 'Queda 1 nodo por revisar antes de poder validar.'
              : `Quedan ${remaining} nodos por revisar antes de poder validar.`}
        </p>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-text-muted p-4">Este esquema no tiene nodos.</p>
      ) : (
        <ul>
          {items.map((item) => {
            const isSelected = item.key === selectedKey
            const isReviewed = !!item.reviewedAt && !item.dirty
            const canMark = !locked && !!item.id && !item.dirty
            return (
              <li
                key={item.key}
                className={`border-b border-border last:border-b-0 transition-colors ${
                  isSelected ? 'bg-primary-subtle' : ''
                }`}
              >
                <button
                  type="button"
                  onClick={() => onSelect(item.key)}
                  aria-current={isSelected}
                  className="w-full text-left px-4 py-3 hover:bg-bg-subtle transition-colors"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-xs text-text-muted shrink-0 tabular-nums">
                      {item.position}.
                    </span>
                    <span
                      className={`text-sm truncate min-w-0 ${
                        isSelected ? 'text-primary font-medium' : 'text-text-secondary'
                      }`}
                    >
                      {item.title || 'Nodo sin titulo'}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                    <CriticalityBadge criticality={item.criticality} />
                    {item.archived && (
                      <span className="text-xs text-text-muted">Archivado</span>
                    )}
                    {isReviewed ? (
                      <span className="text-xs text-accent">Revisado</span>
                    ) : (
                      <span className="text-xs text-warning">Sin revisar</span>
                    )}
                  </div>
                </button>

                {!isReviewed && !item.archived && (
                  <div className="px-4 pb-3">
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={!canMark || pendingNodeId === item.id}
                      onClick={() => item.id && onMarkReviewed(item.id)}
                    >
                      {pendingNodeId === item.id ? 'Marcando...' : 'Marcar revisado'}
                    </Button>
                    {!item.id && (
                      <p className="text-xs text-text-muted mt-1">
                        Guarda el esquema para poder revisar este nodo nuevo.
                      </p>
                    )}
                    {item.id && item.dirty && (
                      <p className="text-xs text-text-muted mt-1">
                        Guarda los cambios primero: al guardar se borra la revision de los
                        nodos que cambiaron.
                      </p>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
