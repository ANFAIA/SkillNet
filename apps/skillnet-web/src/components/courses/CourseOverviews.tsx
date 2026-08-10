import { useCallback, useRef, useState } from 'react'
import { useIntl } from 'react-intl'
import { AnimatePresence, motion } from 'framer-motion'
import { Button, Card, Modal } from '../ui'
import {
  useCourseArtifacts,
  useCreateArtifact,
  useMediaStream,
  type MediaArtifactRead,
  type MediaKind,
} from '../../api/media'
import { PodcastPlayer, type PodcastTurn, type PodcastCitation } from './PodcastPlayer'
import { VideoOverview, type VideoSlideSpec } from './VideoOverview'
import { Infographic, type InfographicSectionSpec, type InfographicCitation } from './Infographic'
import { SlideDeck, type SlideSpec, type SlideCitation } from './SlideDeck'

/**
 * Course-home "Overviews" panel (admin) — the Studio surface of a course.
 *
 * A `Generar ▾` menu enqueues one of the four rich-media artifacts (podcast / video /
 * infographic / slides). Each job streams live progress over SSE while the list of the
 * course's existing artifacts refetches itself to a settled status. Opening a done artifact
 * renders it inline in a modal with the exact viewer components the lesson surface uses,
 * fed straight from the persisted `spec_json`.
 */

const KINDS: MediaKind[] = ['podcast', 'video', 'infographic', 'slides']

function ChevronDown() {
  return (
    <svg
      width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}

const STATUS_CLASS: Record<string, string> = {
  pending: 'text-text-muted',
  running: 'text-primary',
  done: 'text-accent',
  error: 'text-danger',
}

/** Render one done artifact with the matching viewer, fed from its `spec_json`. */
function ArtifactView({ artifact }: { artifact: MediaArtifactRead }) {
  const intl = useIntl()
  const spec = artifact.spec_json ?? {}

  switch (artifact.kind) {
    case 'podcast':
      return (
        <PodcastPlayer
          artifactId={artifact.id}
          turns={(spec.turns as PodcastTurn[]) ?? []}
          citations={(spec.citations as PodcastCitation[]) ?? []}
          format={spec.format as string | undefined}
        />
      )
    case 'video':
      return (
        <VideoOverview
          artifactId={artifact.id}
          slides={(spec.slides as VideoSlideSpec[]) ?? []}
          citations={(spec.citations as SlideCitation[]) ?? []}
          theme={spec.theme as string | undefined}
        />
      )
    case 'infographic':
      return (
        <Infographic
          title={(spec.title as string) ?? ''}
          subtitle={spec.subtitle as string | null | undefined}
          sections={(spec.sections as InfographicSectionSpec[]) ?? []}
          citations={(spec.citations as InfographicCitation[]) ?? []}
          orientation={spec.orientation as 'portrait' | 'landscape' | undefined}
        />
      )
    case 'slides':
      return (
        <SlideDeck
          slides={(spec.slides as SlideSpec[]) ?? []}
          citations={(spec.citations as SlideCitation[]) ?? []}
          theme={spec.theme as string | undefined}
        />
      )
    default:
      return (
        <p className="text-sm text-text-muted">
          {intl.formatMessage({ id: 'overviews.unsupported' })}
        </p>
      )
  }
}

export function CourseOverviews({ courseId }: { courseId: string }) {
  const intl = useIntl()
  const { data: artifacts } = useCourseArtifacts(courseId)
  const createArtifact = useCreateArtifact()
  const stream = useMediaStream()

  const [menuOpen, setMenuOpen] = useState(false)
  // The kind of the job currently streaming, for the progress line.
  const [activeKind, setActiveKind] = useState<MediaKind | null>(null)
  const [openArtifact, setOpenArtifact] = useState<MediaArtifactRead | null>(null)
  const [origin, setOrigin] = useState<DOMRect | null>(null)

  const kindLabel = useCallback(
    (kind: string) => intl.formatMessage({ id: `overviews.kind.${kind}`, defaultMessage: kind }),
    [intl],
  )

  const streamRef = useRef(stream)
  streamRef.current = stream

  const generate = useCallback(
    (kind: MediaKind) => {
      setMenuOpen(false)
      setActiveKind(kind)
      createArtifact.mutate(
        { course_id: courseId, kind, spec: { language: 'es' } },
        {
          onSuccess: (accepted) => {
            void streamRef.current.start(accepted.artifact_id)
          },
          onError: () => setActiveKind(null),
        },
      )
    },
    [courseId, createArtifact],
  )

  // When the streamed job settles, clear the progress line; the list poll shows the result.
  const streaming = stream.status === 'streaming'
  const stepLabel = stream.step
    ? intl.formatMessage({ id: `overviews.step.${stream.step}`, defaultMessage: stream.step })
    : intl.formatMessage({ id: 'overviews.step.running' })

  const list = artifacts ?? []

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="min-w-0">
          <h3 className="text-base font-medium text-text">
            {intl.formatMessage({ id: 'overviews.title' })}
          </h3>
          <p className="text-sm text-text-secondary">
            {intl.formatMessage({ id: 'overviews.subtitle' })}
          </p>
        </div>

        {/* Generar ▾ menu */}
        <div className="relative shrink-0">
          <Button
            size="sm"
            onClick={() => setMenuOpen((o) => !o)}
            disabled={createArtifact.isPending}
          >
            <span className="flex items-center gap-1.5">
              {intl.formatMessage({ id: 'overviews.generate' })}
              <ChevronDown />
            </span>
          </Button>
          <AnimatePresence>
            {menuOpen && (
              <>
                {/* Click-away scrim */}
                <button
                  type="button"
                  aria-hidden="true"
                  tabIndex={-1}
                  className="fixed inset-0 z-10 cursor-default"
                  onClick={() => setMenuOpen(false)}
                />
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.12 }}
                  className="absolute right-0 z-20 mt-1 w-44 rounded-lg border border-border bg-surface shadow-lg overflow-hidden"
                  role="menu"
                >
                  {KINDS.map((kind) => (
                    <button
                      key={kind}
                      type="button"
                      role="menuitem"
                      onClick={() => generate(kind)}
                      className="w-full text-left px-3 py-2 text-sm text-text hover:bg-bg-subtle transition-colors cursor-pointer"
                    >
                      {kindLabel(kind)}
                    </button>
                  ))}
                </motion.div>
              </>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Live progress of the job just triggered */}
      {(streaming || createArtifact.isPending) && activeKind && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-border bg-bg-subtle px-3 py-2">
          <span className="h-2 w-2 rounded-full bg-primary animate-pulse" aria-hidden="true" />
          <span className="text-sm text-text-secondary">
            {intl.formatMessage(
              { id: 'overviews.generating' },
              { kind: kindLabel(activeKind), step: stepLabel },
            )}
          </span>
        </div>
      )}
      {stream.status === 'error' && stream.error && (
        <p className="mb-3 text-sm text-danger" role="alert">
          {intl.formatMessage({ id: 'overviews.error' })}: {stream.error}
        </p>
      )}

      {/* Artifact list */}
      <Card className="p-0 overflow-hidden">
        {list.length === 0 ? (
          <p className="p-4 text-sm text-text-muted">
            {intl.formatMessage({ id: 'overviews.empty' })}
          </p>
        ) : (
          <ul>
            {list.map((artifact) => {
              const canOpen = artifact.status === 'done'
              return (
                <li
                  key={artifact.id}
                  className="flex items-center justify-between gap-3 px-4 py-3 border-b border-border last:border-b-0"
                >
                  <div className="min-w-0">
                    <span className="text-sm font-medium text-text">
                      {kindLabel(artifact.kind)}
                    </span>
                    <span
                      className={`ml-2 text-xs ${STATUS_CLASS[artifact.status] ?? 'text-text-muted'}`}
                    >
                      {intl.formatMessage({
                        id: `overviews.status.${artifact.status}`,
                        defaultMessage: artifact.status,
                      })}
                    </span>
                    {artifact.status === 'error' && artifact.error && (
                      <p className="mt-0.5 text-xs text-danger truncate">{artifact.error}</p>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={!canOpen}
                    onClick={(e) => {
                      setOrigin(e.currentTarget.getBoundingClientRect())
                      setOpenArtifact(artifact)
                    }}
                  >
                    {intl.formatMessage({ id: 'overviews.open' })}
                  </Button>
                </li>
              )
            })}
          </ul>
        )}
      </Card>

      <Modal
        open={openArtifact !== null}
        onClose={() => setOpenArtifact(null)}
        size="lg"
        origin={origin}
      >
        {openArtifact && <ArtifactView artifact={openArtifact} />}
      </Modal>
    </div>
  )
}
