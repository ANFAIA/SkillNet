import { useMemo, useState } from 'react'
import { Button } from '../ui'
import type { NodeRenderVersion } from '../../types'

/**
 * The node footer, and the counterpart of adapting anything (§5.5).
 *
 * Two affordances, neither optional:
 *
 * 1. **"Actualizar esta leccion"** → `POST /nodes/{id}/render {"force": true}`. It is the
 *    *only* way the content of an open node changes. Everything else — answering an item,
 *    refetching on focus, coming back tomorrow — serves the pinned `active_render_id`
 *    byte for byte, which is what the "Estable" row of the stability table promises.
 * 2. **"Ver la version anterior"** → after a regeneration, the line "esta leccion se ha
 *    adaptado a tus ultimas respuestas" with a way back to the render that was replaced.
 *
 * **What the second one can and cannot do, precisely.** `GET /nodes/{id}/renders` lists
 * the versions this learner was served (`node_render_views`, so it is their history and
 * not everybody's), but there is **no endpoint that serves the program of a render by
 * id** — `GET /nodes/{id}/render` only ever returns the pinned one. So a version is
 * viewable when this session still holds its program (the one "Actualizar" just
 * replaced) and is listed with its date otherwise. That is honest and it covers the case
 * §5.5 actually describes ("al regenerar... enlace al render previo"); a version from
 * last week needs an endpoint that does not exist yet.
 */

export interface RenderControlsProps {
  /** `true` while `POST /render {force:true}` and its stream are in flight. */
  refreshing: boolean
  onRefresh: () => void
  /** Versions this learner was served, newest first. */
  versions: NodeRenderVersion[]
  /** The render currently on screen. */
  activeRenderId: string | null
  /**
   * Render ids whose program this session still holds, so they can be shown again.
   * Anything else in `versions` is listed as history only.
   */
  viewableRenderIds: string[]
  /** Show the previous version. */
  onViewVersion: (renderId: string) => void
  /** Back to the pinned render. */
  onViewCurrent: () => void
  /** True when the screen is showing something other than the pinned render. */
  viewingPrevious: boolean
  /** Set once a regeneration has landed in this session (§5.5's adaptation notice). */
  adapted: boolean
}

function formatDate(value: string | null): string {
  if (!value) return 'sin fecha'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'sin fecha'
  return date.toLocaleString('es-ES', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function RenderControls({
  refreshing,
  onRefresh,
  versions,
  activeRenderId,
  viewableRenderIds,
  onViewVersion,
  onViewCurrent,
  viewingPrevious,
  adapted,
}: RenderControlsProps) {
  const [open, setOpen] = useState(false)
  const viewable = useMemo(() => new Set(viewableRenderIds), [viewableRenderIds])

  const previous = versions.filter((version) => version.render_id !== activeRenderId)
  const hasHistory = previous.length > 0

  return (
    <div
      className="mt-8 border-t border-border pt-4 space-y-3"
      // Controls, not prose: a click here must never be read as a term to explain (§8.5).
      data-no-explain=""
      data-testid="render-controls"
    >
      {adapted && !viewingPrevious && (
        <p className="text-sm text-text-secondary" role="status">
          Esta leccion se ha adaptado a tus ultimas respuestas.
        </p>
      )}

      {viewingPrevious && (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-sm text-text">Estas viendo una version anterior.</p>
          <button
            type="button"
            onClick={onViewCurrent}
            className="text-sm font-medium text-primary hover:text-primary/80 transition-colors"
          >
            Volver a la actual
          </button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" variant="secondary" disabled={refreshing} onClick={onRefresh}>
          {refreshing ? 'Actualizando...' : 'Actualizar esta leccion'}
        </Button>

        {hasHistory && (
          <button
            type="button"
            onClick={() => setOpen((prev) => !prev)}
            aria-expanded={open}
            className="text-sm font-medium text-primary hover:text-primary/80 transition-colors"
          >
            Ver la version anterior
          </button>
        )}
      </div>

      <p className="text-xs text-text-muted">
        Solo este boton cambia el contenido de este nodo. Responder o volver mas tarde te
        devuelve exactamente la misma leccion.
      </p>

      {open && hasHistory && (
        <ul className="space-y-1.5">
          {previous.map((version) => {
            const canView = viewable.has(version.render_id)
            return (
              <li key={version.render_id} className="text-sm flex flex-wrap items-baseline gap-2">
                {canView ? (
                  <button
                    type="button"
                    onClick={() => onViewVersion(version.render_id)}
                    className="font-medium text-primary hover:text-primary/80 transition-colors"
                  >
                    Version del {formatDate(version.created_at)}
                  </button>
                ) : (
                  <span className="text-text-secondary">
                    Version del {formatDate(version.created_at)}
                  </span>
                )}
                <span className="text-xs text-text-muted">{version.ui_format}</span>
                {!canView && (
                  <span className="text-xs text-text-muted">
                    no disponible en esta sesion
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
