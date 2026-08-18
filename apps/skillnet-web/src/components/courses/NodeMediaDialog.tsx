import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useIntl } from 'react-intl'
import { Modal } from '../ui'
import {
  useCreateArtifact,
  useMediaArtifact,
  useMediaStream,
  type MediaKind,
} from '../../api/media'
import { useCourseNodes } from '../../api/nodes'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { CourseArtifactView } from './CourseArtifactView'
import { CourseMediaIcon } from './CourseMediaIcon'

const KINDS: MediaKind[] = ['podcast', 'infographic', 'video', 'slides']

interface NodeMediaDialogProps {
  courseId: string
  open: boolean
  onClose: () => void
  origin?: DOMRect | null
  /** Preselect a lesson (e.g. opened from a node row). Empty = the picker starts unset. */
  initialNodeId?: string
}

/**
 * The "link to a lesson" flow: pick a lesson, pick a format, generate an artefact grounded on
 * and attached to THAT node, then watch its status and preview/play it inline — all without
 * leaving the dialog. It is the first-class node-scoped counterpart to the course-wide
 * generator: the header always names the lesson the artefact belongs to, so the association
 * is explicit, and the just-generated result is shown here even though the course-home
 * library groups by node separately.
 */
export function NodeMediaDialog({
  courseId,
  open,
  onClose,
  origin,
  initialNodeId = '',
}: NodeMediaDialogProps) {
  const intl = useIntl()
  const animated = !useReducedMotion()
  const createArtifact = useCreateArtifact()
  const stream = useMediaStream()
  const streamRef = useRef(stream)
  streamRef.current = stream

  const [nodeId, setNodeId] = useState(initialNodeId)
  const [kind, setKind] = useState<MediaKind>('podcast')
  const [note, setNote] = useState('')
  const [lastArtifactId, setLastArtifactId] = useState<string | null>(null)

  const { data: nodeList } = useCourseNodes(courseId, { enabled: open })
  const nodes = useMemo(
    () => [...(nodeList?.nodes ?? [])].sort((a, b) => a.position - b.position),
    [nodeList],
  )
  const { data: lastArtifact } = useMediaArtifact(lastArtifactId ?? undefined)

  // Reopen resets the transient generation state so a previous run never bleeds into a new one.
  useEffect(() => {
    if (open) {
      setNodeId(initialNodeId)
      setNote('')
      setLastArtifactId(null)
      streamRef.current.reset()
    }
  }, [open, initialNodeId])

  const kindLabel = useCallback(
    (value: string) =>
      intl.formatMessage({ id: `overviews.kind.${value}`, defaultMessage: value }),
    [intl],
  )

  const nodeTitle = useMemo(() => {
    const index = nodes.findIndex((node) => node.id === nodeId)
    return index >= 0 ? `${index + 1}. ${nodes[index].title}` : ''
  }, [nodes, nodeId])

  const generate = useCallback(() => {
    if (!nodeId) return
    const trimmed = note.trim()
    createArtifact.mutate(
      {
        course_id: courseId,
        kind,
        scope: 'node',
        node_id: nodeId,
        note: trimmed || undefined,
        spec: { language: 'es' },
      },
      {
        onSuccess: (accepted) => {
          setLastArtifactId(accepted.artifact_id)
          void streamRef.current.start(accepted.artifact_id)
        },
      },
    )
  }, [courseId, createArtifact, kind, nodeId, note])

  const busy = createArtifact.isPending || stream.status === 'streaming'
  const stepLabel = stream.step
    ? intl.formatMessage({ id: `overviews.step.${stream.step}`, defaultMessage: stream.step })
    : intl.formatMessage({ id: 'overviews.step.running' })

  return (
    <Modal open={open} onClose={onClose} size="lg" origin={origin}>
      <div className="mb-4 flex items-center gap-2 text-text">
        <CourseMediaIcon kind={kind} className="text-primary" size={18} />
        <h3 className="text-base font-medium">
          {intl.formatMessage({ id: 'overviews.node.dialogTitle' })}
        </h3>
      </div>

      {/* Lesson picker — the artefact is linked to this node */}
      <label htmlFor="node-media-node" className="mb-1.5 block text-xs font-medium text-text-secondary">
        {intl.formatMessage({ id: 'overviews.node.pickLabel' })}
      </label>
      <select
        id="node-media-node"
        value={nodeId}
        onChange={(event) => setNodeId(event.target.value)}
        disabled={busy}
        className="mb-4 w-full cursor-pointer rounded-md border border-border bg-surface px-3 py-2 text-sm text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <option value="">{intl.formatMessage({ id: 'overviews.nodePlaceholder' })}</option>
        {nodes.map((node, index) => (
          <option key={node.id} value={node.id}>
            {index + 1}. {node.title}
          </option>
        ))}
      </select>

      {/* Format */}
      <span className="mb-1.5 block text-xs font-medium text-text-secondary">
        {intl.formatMessage({ id: 'overviews.node.formatLabel' })}
      </span>
      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {KINDS.map((value) => {
          const on = kind === value
          return (
            <button
              key={value}
              type="button"
              onClick={() => setKind(value)}
              disabled={busy}
              aria-pressed={on}
              className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border bg-surface px-3 py-3 transition-colors hover:border-primary disabled:cursor-not-allowed disabled:opacity-50 ${on ? 'border-primary bg-bg-subtle' : 'border-border'}`}
            >
              <CourseMediaIcon kind={value} className={on ? 'text-primary' : 'text-text-secondary'} />
              <span className="text-xs font-medium text-text">{kindLabel(value)}</span>
            </button>
          )
        })}
      </div>

      {/* Steering note */}
      <label htmlFor="node-media-note" className="sr-only">
        {intl.formatMessage({ id: 'overviews.steeringLabel' })}
      </label>
      <textarea
        id="node-media-note"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        rows={2}
        disabled={busy}
        placeholder={intl.formatMessage({ id: 'overviews.notePlaceholder' })}
        className="mb-4 w-full resize-y rounded-md border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-50"
      />

      <div className="flex items-center justify-end gap-3">
        {!nodeId && (
          <span className="text-xs text-text-muted">
            {intl.formatMessage({ id: 'overviews.nodeRequired' })}
          </span>
        )}
        <button
          type="button"
          onClick={generate}
          disabled={busy || !nodeId}
          className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <CourseMediaIcon kind={kind} size={16} className="text-white" />
          {intl.formatMessage({ id: 'overviews.generate' })}
        </button>
      </div>

      {/* Live status */}
      {busy && (
        <div className="mt-4 flex items-center gap-2 rounded-lg border border-border bg-bg-subtle px-3 py-2">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={`text-primary ${animated ? 'animate-spin' : ''}`} aria-hidden="true">
            <path d="M21 12a9 9 0 1 1-6.219-8.56" />
          </svg>
          <span className="text-sm text-text-secondary">
            {intl.formatMessage({ id: 'overviews.generating' }, { kind: kindLabel(kind), step: stepLabel })}
          </span>
        </div>
      )}
      {stream.status === 'error' && stream.error && (
        <p className="mt-3 text-sm text-danger" role="alert">
          {intl.formatMessage({ id: 'overviews.error' })}: {stream.error}
        </p>
      )}

      {/* Result — clearly associated with the linked lesson */}
      {lastArtifact && lastArtifact.status === 'done' && (
        <div className="mt-4 rounded-lg border border-border bg-bg-subtle p-3">
          {nodeTitle && (
            <p className="mb-2 text-xs text-text-secondary">
              {intl.formatMessage({ id: 'overviews.node.attachedTo' }, { node: nodeTitle })}
            </p>
          )}
          <CourseArtifactView artifact={lastArtifact} />
        </div>
      )}
    </Modal>
  )
}
