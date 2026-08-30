import { useCallback, useMemo, useRef, useState } from 'react'
import { useIntl } from 'react-intl'
import { AnimatePresence, motion } from 'framer-motion'
import {
  MEDIA_KINDS,
  useCreateArtifact,
  useMediaArtifact,
  useMediaStream,
  type MediaKind,
  type MediaScope,
} from '../../api/media'
import { useCourseNodes } from '../../api/nodes'
import {
  isAvailable,
  isReady,
  useCapabilities,
  useMediaRequirements,
  type CapabilityName,
} from '../../api/setup'
import { ApiError } from '../../api/client'
import { Gated } from '../Gated'
import { capabilityReduced } from '../../lib/capabilityCopy'
import { mediaErrorMessageId } from '../../lib/mediaErrors'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { CourseArtifactView } from './CourseArtifactView'
import { CourseMediaIcon } from './CourseMediaIcon'

const SCOPES: MediaScope[] = ['course', 'node', 'standalone']

export function CourseMediaGenerator({ courseId }: { courseId: string }) {
  const intl = useIntl()
  const animated = !useReducedMotion()
  const createArtifact = useCreateArtifact()
  const capabilities = useCapabilities()
  const requirements = useMediaRequirements()
  const stream = useMediaStream()
  const [activeKind, setActiveKind] = useState<MediaKind | null>(null)
  const [selectedKind, setSelectedKind] = useState<MediaKind | null>(null)
  const [scope, setScope] = useState<MediaScope>('course')
  const [nodeId, setNodeId] = useState<string>('')
  const [note, setNote] = useState('')
  // The artefact just generated here. Kept so its result can be previewed inline — the
  // course-home library only lists course-level artefacts, so a node-scoped or standalone
  // result would otherwise be invisible right after generating it.
  const [lastArtifactId, setLastArtifactId] = useState<string | null>(null)
  // Set only when the API refuses a kind the UI believed was fine (`capability_blocked`).
  const [blockedError, setBlockedError] = useState<string | null>(null)
  const streamRef = useRef(stream)
  streamRef.current = stream

  const { data: lastArtifact } = useMediaArtifact(lastArtifactId ?? undefined)

  // The node picker is only needed for the per-node scope. Fetch lazily so the course/
  // standalone paths never pay for it.
  const { data: nodeList } = useCourseNodes(courseId, { enabled: scope === 'node' })
  // Numbered like the course index (CourseIndex): by list order, not the raw `position`.
  const nodes = [...(nodeList?.nodes ?? [])].sort((a, b) => a.position - b.position)

  const kindLabel = useCallback(
    (kind: string) => intl.formatMessage({ id: `overviews.kind.${kind}`, defaultMessage: kind }),
    [intl],
  )

  /**
   * The capability standing in the way of a kind, or `null` when it can run.
   *
   * Read off the backend's `media_requirements` table rather than a hardcoded map:
   * which capabilities a podcast or an infographic needs is the backend's business,
   * and the copy of that table this component used to imply is exactly what let a
   * keyless deployment accept an "infografía" job and kill it thirty seconds later.
   *
   * A requirement naming a capability we do not know is treated as satisfied — the
   * same "unknown ⇒ available" policy as `DEFAULT_CAPABILITIES`, so a newer backend
   * never strips a control from an older SPA.
   */
  const blockerFor = useCallback(
    (kind: MediaKind): CapabilityName | null => {
      const required = requirements[kind] ?? []
      return (
        required.find((name) => name in capabilities && !isAvailable(capabilities[name])) ?? null
      )
    },
    [requirements, capabilities],
  )

  /**
   * A requirement that is present but reduced — the kind still runs, it just returns
   * less. Deliberately NOT a blocker, and the API agrees: only `blocked` is refused
   * there, because the podcast always has the offline eSpeak voice underneath it.
   * Turning a tile off for a capability the server would happily serve would take
   * away a feature that works today.
   */
  const degradedFor = useCallback(
    (kind: MediaKind): CapabilityName | null => {
      const required = requirements[kind] ?? []
      return required.find((name) => name in capabilities && !isReady(capabilities[name])) ?? null
    },
    [requirements, capabilities],
  )

  const kinds = useMemo(
    () => MEDIA_KINDS.map((kind) => ({ kind, blocker: blockerFor(kind) })),
    [blockerFor],
  )

  const selectKind = useCallback((kind: MediaKind) => {
    setSelectedKind((previous) => {
      const next = previous === kind ? null : kind
      setNote('')
      return next
    })
  }, [])

  const selectScope = useCallback((next: MediaScope) => {
    setScope(next)
    // Leaving the node scope drops the node selection so a stale id can never be sent.
    if (next !== 'node') setNodeId('')
  }, [])

  // A per-node generation needs a chosen node; the other two scopes are node-less.
  const nodeMissing = scope === 'node' && !nodeId

  const generate = useCallback((kind: MediaKind) => {
    if (scope === 'node' && !nodeId) return
    // Belt to the braces of the inert tile: nothing reaches the API for a kind whose
    // capabilities are not there, whatever route got us here.
    if (blockerFor(kind)) return
    setBlockedError(null)
    setActiveKind(kind)
    const trimmedNote = note.trim()
    createArtifact.mutate(
      {
        course_id: courseId,
        kind,
        scope,
        node_id: scope === 'node' ? nodeId : undefined,
        note: trimmedNote || undefined,
        spec: { language: 'es' },
      },
      {
        onSuccess: (accepted) => {
          setLastArtifactId(accepted.artifact_id)
          void streamRef.current.start(accepted.artifact_id)
        },
        onError: (error) => {
          setActiveKind(null)
          // Last line of defence. The tiles should make this unreachable, but a
          // capability can go blocked between the page load and the click, and a raw
          // exception string is what this whole feature exists to stop showing.
          if (error instanceof ApiError && error.body.code === 'capability_blocked') {
            setBlockedError(intl.formatMessage({ id: 'capability.unavailable' }))
          }
        },
      },
    )
    setSelectedKind(null)
    setNote('')
  }, [courseId, createArtifact, scope, nodeId, note, blockerFor, intl])

  const stepLabel = stream.step
    ? intl.formatMessage({ id: `overviews.step.${stream.step}`, defaultMessage: stream.step })
    : intl.formatMessage({ id: 'overviews.step.running' })

  return (
    <>
      {/* Scope: whole course, a single lesson, or a free-standing artefact */}
      <fieldset className="mb-3">
        <legend className="mb-1.5 text-xs font-medium text-text-secondary">
          {intl.formatMessage({ id: 'overviews.scope.label' })}
        </legend>
        <div className="inline-flex rounded-lg border border-border bg-surface p-0.5">
          {SCOPES.map((value) => {
            const on = scope === value
            return (
              <button
                key={value}
                type="button"
                onClick={() => selectScope(value)}
                disabled={createArtifact.isPending}
                aria-pressed={on}
                className={`cursor-pointer rounded-md px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${on ? 'bg-primary text-white' : 'text-text-secondary hover:text-text'}`}
              >
                {intl.formatMessage({ id: `overviews.scope.${value}` })}
              </button>
            )
          })}
        </div>
      </fieldset>

      <AnimatePresence initial={false}>
        {scope === 'node' && (
          <motion.div
            initial={animated ? { height: 0, opacity: 0 } : false}
            animate={{ height: 'auto', opacity: 1 }}
            exit={animated ? { height: 0, opacity: 0 } : { opacity: 0 }}
            transition={{ duration: animated ? 0.2 : 0 }}
            className="overflow-hidden"
          >
            <div className="mb-3">
              <label htmlFor="overviews-node" className="sr-only">
                {intl.formatMessage({ id: 'overviews.nodeLabel' })}
              </label>
              <select
                id="overviews-node"
                value={nodeId}
                onChange={(event) => setNodeId(event.target.value)}
                disabled={createArtifact.isPending}
                className="w-full cursor-pointer rounded-md border border-border bg-surface px-3 py-2 text-sm text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <option value="">{intl.formatMessage({ id: 'overviews.nodePlaceholder' })}</option>
                {nodes.map((node, index) => (
                  <option key={node.id} value={node.id}>
                    {index + 1}. {node.title}
                  </option>
                ))}
              </select>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {kinds.map(({ kind, blocker }) => {
          const selected = selectedKind === kind
          const tile = (
            <button
              key={kind}
              type="button"
              // A blocked kind gets no handler and no `disabled` attribute: <Gated
              // mode="explain"> makes it inert with `aria-disabled` instead, which
              // keeps it focusable so its explanation is reachable by keyboard.
              onClick={blocker ? undefined : () => selectKind(kind)}
              disabled={blocker ? undefined : createArtifact.isPending}
              aria-expanded={selected}
              className={`group flex h-full w-full cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border bg-surface px-3 py-4 transition-colors hover:border-primary hover:bg-bg-subtle disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-1 ${selected ? 'border-primary bg-bg-subtle' : 'border-border'}`}
            >
              <CourseMediaIcon kind={kind} className={selected ? 'text-primary' : 'text-text-secondary transition-colors group-hover:text-primary'} />
              <span className="text-xs font-medium text-text">{kindLabel(kind)}</span>
            </button>
          )
          // A ready tile stays a direct grid child, exactly as before. Only a blocked
          // one gains the wrapper that holds its explanation.
          return blocker ? (
            <Gated key={kind} requires={blocker} mode="explain">
              {tile}
            </Gated>
          ) : (
            tile
          )
        })}
      </div>

      <AnimatePresence initial={false}>
        {/* A kind that went blocked while its panel was open closes the panel with it:
            the generate button must not survive the capability it depends on. */}
        {selectedKind && !blockerFor(selectedKind) && (
          <motion.div
            initial={animated ? { height: 0, opacity: 0 } : false}
            animate={{ height: 'auto', opacity: 1 }}
            exit={animated ? { height: 0, opacity: 0 } : { opacity: 0 }}
            transition={{ duration: animated ? 0.2 : 0 }}
            className="overflow-hidden"
          >
            <div className="mb-4 rounded-lg border border-border bg-bg-subtle p-3">
              <label htmlFor="overviews-note" className="sr-only">{intl.formatMessage({ id: 'overviews.steeringLabel' })}</label>
              <textarea
                id="overviews-note"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                rows={2}
                placeholder={intl.formatMessage({ id: 'overviews.notePlaceholder' })}
                className="w-full resize-y rounded-md border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
              />
              {/* A reduced requirement is a promise about the RESULT, not a refusal:
                  said here, next to the button, rather than on the tile, so it is read
                  at the moment it changes what you get. */}
              {degradedFor(selectedKind) && (
                <CapabilityNote name={degradedFor(selectedKind) as CapabilityName} />
              )}
              <div className="mt-2 flex items-center justify-end gap-3">
                {nodeMissing && (
                  <span className="text-xs text-text-muted">{intl.formatMessage({ id: 'overviews.nodeRequired' })}</span>
                )}
                <button type="button" onClick={() => generate(selectedKind)} disabled={createArtifact.isPending || nodeMissing} className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50">
                  <CourseMediaIcon kind={selectedKind} size={16} className="text-white" />
                  {intl.formatMessage({ id: 'overviews.generate' })}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {(stream.status === 'streaming' || createArtifact.isPending) && activeKind && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-border bg-bg-subtle px-3 py-2">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={`text-primary ${animated ? 'animate-spin' : ''}`} aria-hidden="true"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
          <span className="text-sm text-text-secondary">{intl.formatMessage({ id: 'overviews.generating' }, { kind: kindLabel(activeKind), step: stepLabel })}</span>
        </div>
      )}
      {blockedError && (
        <p className="mb-3 text-sm text-danger" role="alert">{blockedError}</p>
      )}
      {stream.status === 'error' && (
        <p className="mb-3 text-sm text-danger" role="alert">{intl.formatMessage({ id: 'overviews.error' })}: {intl.formatMessage({ id: mediaErrorMessageId(stream.errorCode) })}</p>
      )}

      {/* Inline preview of the just-generated artefact — plays/shows it here regardless of
          scope, since node-scoped and standalone results are not listed in the library. */}
      {lastArtifact && lastArtifact.status === 'done' && (
        <div className="mt-2">
          <CourseArtifactView artifact={lastArtifact} />
        </div>
      )}
    </>
  )
}

/**
 * One line saying a kind will run reduced. Local to this file on purpose: the
 * deployment banner and `<Gated mode="explain">` already own the other two places a
 * capability speaks, and a third shared component for one sentence would be a
 * component invented rather than reused.
 */
function CapabilityNote({ name }: { name: CapabilityName }) {
  const intl = useIntl()
  return (
    <p className="mt-2 text-xs text-text-muted">{capabilityReduced(intl, name)}</p>
  )
}
