import { useCallback, useRef, useState } from 'react'
import { useIntl } from 'react-intl'
import { AnimatePresence, motion } from 'framer-motion'
import { useCreateArtifact, useMediaStream, type MediaKind } from '../../api/media'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { CourseMediaIcon } from './CourseMediaIcon'

const KINDS: MediaKind[] = ['podcast', 'video', 'infographic', 'slides']

export function CourseMediaGenerator({ courseId }: { courseId: string }) {
  const intl = useIntl()
  const animated = !useReducedMotion()
  const createArtifact = useCreateArtifact()
  const stream = useMediaStream()
  const [activeKind, setActiveKind] = useState<MediaKind | null>(null)
  const [selectedKind, setSelectedKind] = useState<MediaKind | null>(null)
  const [steering, setSteering] = useState('')
  const streamRef = useRef(stream)
  streamRef.current = stream

  const kindLabel = useCallback(
    (kind: string) => intl.formatMessage({ id: `overviews.kind.${kind}`, defaultMessage: kind }),
    [intl],
  )

  const selectKind = useCallback((kind: MediaKind) => {
    setSelectedKind((previous) => {
      const next = previous === kind ? null : kind
      setSteering('')
      return next
    })
  }, [])

  const generate = useCallback((kind: MediaKind) => {
    setActiveKind(kind)
    const focus = steering.trim()
    const spec: Record<string, unknown> = { language: 'es' }
    if (focus) spec.steering = focus
    createArtifact.mutate(
      { course_id: courseId, kind, spec },
      { onSuccess: (accepted) => void streamRef.current.start(accepted.artifact_id), onError: () => setActiveKind(null) },
    )
    setSelectedKind(null)
    setSteering('')
  }, [courseId, createArtifact, steering])

  const stepLabel = stream.step
    ? intl.formatMessage({ id: `overviews.step.${stream.step}`, defaultMessage: stream.step })
    : intl.formatMessage({ id: 'overviews.step.running' })

  return (
    <>
      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {KINDS.map((kind) => {
          const selected = selectedKind === kind
          return (
            <button
              key={kind}
              type="button"
              onClick={() => selectKind(kind)}
              disabled={createArtifact.isPending}
              aria-expanded={selected}
              className={`group flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border bg-surface px-3 py-4 transition-colors hover:border-primary hover:bg-bg-subtle disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-1 ${selected ? 'border-primary bg-bg-subtle' : 'border-border'}`}
            >
              <CourseMediaIcon kind={kind} className={selected ? 'text-primary' : 'text-text-secondary transition-colors group-hover:text-primary'} />
              <span className="text-xs font-medium text-text">{kindLabel(kind)}</span>
            </button>
          )
        })}
      </div>

      <AnimatePresence initial={false}>
        {selectedKind && (
          <motion.div
            initial={animated ? { height: 0, opacity: 0 } : false}
            animate={{ height: 'auto', opacity: 1 }}
            exit={animated ? { height: 0, opacity: 0 } : { opacity: 0 }}
            transition={{ duration: animated ? 0.2 : 0 }}
            className="overflow-hidden"
          >
            <div className="mb-4 rounded-lg border border-border bg-bg-subtle p-3">
              <label htmlFor="overviews-steering" className="sr-only">{intl.formatMessage({ id: 'overviews.steeringLabel' })}</label>
              <textarea
                id="overviews-steering"
                value={steering}
                onChange={(event) => setSteering(event.target.value)}
                rows={2}
                placeholder={intl.formatMessage({ id: 'overviews.steeringPlaceholder' })}
                className="w-full resize-y rounded-md border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
              />
              <div className="mt-2 flex justify-end">
                <button type="button" onClick={() => generate(selectedKind)} disabled={createArtifact.isPending} className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50">
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
      {stream.status === 'error' && stream.error && (
        <p className="mb-3 text-sm text-danger" role="alert">{intl.formatMessage({ id: 'overviews.error' })}: {stream.error}</p>
      )}
    </>
  )
}
