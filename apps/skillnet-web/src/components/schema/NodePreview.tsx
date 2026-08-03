import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '../ui'
import { Modal } from '../ui/Modal'
import { NodeSkeleton } from '../courses/NodeSkeleton'
import { UiSpecRenderer } from '../courses/UiSpecRenderer'
import { useRequestRender, useNodeRenderStream, isServedRender } from '../../api/nodes'
import { get } from '../../api/client'
import type { NodeRender } from '../../types'

/**
 * Admin preview of a single node's generated content.
 *
 * Calls `POST /nodes/{id}/render { preview: true }` which generates without
 * caching or pinning (admin-only). The result is rendered with the same
 * `UiSpecRenderer` employees see, minus quiz grading (no `renderId`).
 *
 * <!-- Future: option B — full course simulation at /admin/curso/:id/simular
 *      where the admin walks through nodes sequentially with a selectable
 *      learner profile. This per-node preview is the building block for that. -->
 */

interface NodePreviewProps {
  nodeId: string
  nodeTitle: string
  open: boolean
  onClose: () => void
  origin?: DOMRect | null
}

export function NodePreview({ nodeId, nodeTitle, open, onClose, origin }: NodePreviewProps) {
  const requestRender = useRequestRender(nodeId)
  const [program, setProgram] = useState<string | null>(null)
  const [format, setFormat] = useState<import('../../types/node-render').UiFormat | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fetchedRenderRef = useRef<string | null>(null)

  const stream = useNodeRenderStream({
    onSettled: ({ reason, renderId }) => {
      if (reason === 'done' && renderId) {
        fetchRender(renderId)
      } else if (reason === 'error') {
        setError('No se pudo generar la previsualizacion.')
      }
    },
  })

  const fetchRender = useCallback(async (renderId: string) => {
    if (fetchedRenderRef.current === renderId) return
    fetchedRenderRef.current = renderId
    try {
      const render = await get<NodeRender>(`/nodes/${nodeId}/render`)
      if (isServedRender(render)) {
        setProgram(render.program)
        setFormat(render.ui_format)
      }
    } catch {
      setError('No se pudo cargar el contenido generado.')
    }
  }, [nodeId])

  // Start generation when modal opens
  useEffect(() => {
    if (!open) return
    setProgram(null)
    setError(null)
    setFormat(null)
    fetchedRenderRef.current = null
    requestRender.mutate(
      { preview: true },
      {
        onSuccess: (accepted) => {
          if (accepted.cached && accepted.render_id) {
            fetchRender(accepted.render_id)
          } else if (accepted.request_id) {
            stream.start(nodeId, accepted.request_id)
          }
        },
        onError: () => {
          setError('No se pudo iniciar la generacion. Asegurate de que el esquema esta guardado.')
        },
      },
    )
    return () => stream.stop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, nodeId])

  const isGenerating = !program && !error

  return (
    <Modal open={open} onClose={onClose} size="lg" origin={origin}>
      <div className="pr-6">
        <h3 className="text-lg font-semibold text-text">{nodeTitle}</h3>
        <p className="text-xs text-text-muted mt-1">
          Previsualizacion como empleado · no se guarda en cache
        </p>
      </div>

      <div className="mt-5">
        {error ? (
          <div className="text-center py-8 space-y-3">
            <p className="text-sm text-danger">{error}</p>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                setError(null)
                setProgram(null)
                fetchedRenderRef.current = null
                requestRender.mutate(
                  { preview: true },
                  {
                    onSuccess: (accepted) => {
                      if (accepted.cached && accepted.render_id) {
                        fetchRender(accepted.render_id)
                      } else if (accepted.request_id) {
                        stream.start(nodeId, accepted.request_id)
                      }
                    },
                    onError: () => setError('No se pudo reintentar.'),
                  },
                )
              }}
            >
              Reintentar
            </Button>
          </div>
        ) : isGenerating ? (
          <NodeSkeleton
            format={stream.format ?? format}
            message={stream.message}
            blocksReady={stream.blocks}
          />
        ) : (
          <UiSpecRenderer
            program={program}
            nodeId={nodeId}
            format={format ?? undefined}
            arriving
          />
        )}
      </div>
    </Modal>
  )
}
