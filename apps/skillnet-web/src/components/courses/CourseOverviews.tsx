import { useCallback, useRef, useState } from 'react'
import { useIntl } from 'react-intl'
import { Card, Modal, EmptyState } from '../ui'
import { useReducedMotion } from '../../hooks/useReducedMotion'
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
 * Four compact icon cards enqueue one of the rich-media artifacts (podcast / video /
 * infographic / slides). Each job streams live progress over SSE while the list of the
 * course's existing artifacts refetches itself to a settled status. Opening a done artifact
 * renders it inline in a modal with the exact viewer components the lesson surface uses,
 * fed straight from the persisted `spec_json`.
 */

const KINDS: MediaKind[] = ['podcast', 'video', 'infographic', 'slides']

// ─── Icons ──────────────────────────────────────────────────────────────────
// Inline SVG in the repo's stroke style (viewBox 0 0 24 24, round caps/joins),
// matching `Content.tsx` and `AdminSidebar.tsx`.

interface IconProps {
  className?: string
  size?: number
}

function iconBaseProps(size: number, className: string) {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    className,
    'aria-hidden': true,
  }
}

/** Podcast — a microphone. */
function MicIcon({ className = '', size = 20 }: IconProps) {
  return (
    <svg {...iconBaseProps(size, className)}>
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  )
}

/** Video — a play triangle inside a frame. */
function VideoIcon({ className = '', size = 20 }: IconProps) {
  return (
    <svg {...iconBaseProps(size, className)}>
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <polygon points="10 9 15 12 10 15 10 9" />
    </svg>
  )
}

/** Infographic — a bar chart. */
function BarChartIcon({ className = '', size = 20 }: IconProps) {
  return (
    <svg {...iconBaseProps(size, className)}>
      <line x1="6" y1="20" x2="6" y2="14" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="18" y1="20" x2="18" y2="10" />
    </svg>
  )
}

/** Slides — a presentation screen. */
function SlidesIcon({ className = '', size = 20 }: IconProps) {
  return (
    <svg {...iconBaseProps(size, className)}>
      <rect x="3" y="4" width="18" height="12" rx="1" />
      <line x1="12" y1="16" x2="12" y2="20" />
      <line x1="9" y1="20" x2="15" y2="20" />
    </svg>
  )
}

const KIND_ICON: Record<MediaKind, (p: IconProps) => React.ReactElement> = {
  podcast: MicIcon,
  video: VideoIcon,
  infographic: BarChartIcon,
  slides: SlidesIcon,
}

function KindIcon({ kind, className = '', size = 20 }: { kind: string; className?: string; size?: number }) {
  const Icon = KIND_ICON[kind as MediaKind]
  return Icon ? <Icon className={className} size={size} /> : null
}

/** done — check-circle. */
function CheckCircleIcon({ className = '', size = 14 }: IconProps) {
  return (
    <svg {...iconBaseProps(size, className)}>
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  )
}

/** running — a spinner arc (spun via `animate-spin` unless motion is reduced). */
function SpinnerIcon({ className = '', size = 14 }: IconProps) {
  return (
    <svg {...iconBaseProps(size, className)}>
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  )
}

/** pending — a clock. */
function ClockIcon({ className = '', size = 14 }: IconProps) {
  return (
    <svg {...iconBaseProps(size, className)}>
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  )
}

/** error — an alert triangle. */
function AlertTriangleIcon({ className = '', size = 14 }: IconProps) {
  return (
    <svg {...iconBaseProps(size, className)}>
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )
}

/** An empty-panel glyph (a stack of media sheets). */
function GalleryIcon({ className = '', size = 32 }: IconProps) {
  return (
    <svg {...iconBaseProps(size, className)}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <polyline points="21 15 16 10 5 21" />
    </svg>
  )
}

const STATUS_COLOR: Record<string, string> = {
  pending: 'text-text-muted',
  running: 'text-primary',
  done: 'text-accent',
  error: 'text-danger',
}

/** Small status chip: an icon that matches the lifecycle state plus its label. */
function StatusChip({ status, label, animated }: { status: string; label: string; animated: boolean }) {
  const color = STATUS_COLOR[status] ?? 'text-text-muted'
  let icon: React.ReactNode
  switch (status) {
    case 'done':
      icon = <CheckCircleIcon />
      break
    case 'running':
      icon = <SpinnerIcon className={animated ? 'animate-spin' : ''} />
      break
    case 'error':
      icon = <AlertTriangleIcon />
      break
    default:
      icon = <ClockIcon />
  }
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${color}`}>
      {icon}
      {label}
    </span>
  )
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
          artifactId={artifact.id}
          title={(spec.title as string) ?? ''}
          subtitle={spec.subtitle as string | null | undefined}
          sections={(spec.sections as InfographicSectionSpec[]) ?? []}
          citations={(spec.citations as InfographicCitation[]) ?? []}
          orientation={spec.orientation as 'portrait' | 'landscape' | undefined}
          hasImage={(spec.has_image as boolean | undefined) ?? false}
        />
      )
    case 'slides':
      return (
        <SlideDeck
          artifactId={artifact.id}
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
  const animated = !useReducedMotion()
  const { data: artifacts } = useCourseArtifacts(courseId)
  const createArtifact = useCreateArtifact()
  const stream = useMediaStream()

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
      <div className="mb-4">
        <h3 className="text-base font-medium text-text">
          {intl.formatMessage({ id: 'overviews.title' })}
        </h3>
        <p className="text-sm text-text-secondary">
          {intl.formatMessage({ id: 'overviews.subtitle' })}
        </p>
      </div>

      {/* Generar — four compact icon cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
        {KINDS.map((kind) => (
          <button
            key={kind}
            type="button"
            onClick={() => generate(kind)}
            disabled={createArtifact.isPending}
            className="group flex flex-col items-center justify-center gap-2 rounded-lg border border-border bg-surface px-3 py-4 transition-colors cursor-pointer hover:border-primary hover:bg-bg-subtle disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-1"
          >
            <KindIcon kind={kind} className="text-text-secondary transition-colors group-hover:text-primary" />
            <span className="text-xs font-medium text-text">{kindLabel(kind)}</span>
          </button>
        ))}
      </div>

      {/* Live progress of the job just triggered */}
      {(streaming || createArtifact.isPending) && activeKind && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-border bg-bg-subtle px-3 py-2">
          <SpinnerIcon className={`text-primary ${animated ? 'animate-spin' : ''}`} />
          <span className="text-sm text-text-secondary">
            {intl.formatMessage(
              { id: 'overviews.generating' },
              { kind: kindLabel(activeKind), step: stepLabel },
            )}
          </span>
        </div>
      )}
      {stream.status === 'error' && stream.error && (
        <p className="mb-3 flex items-center gap-1.5 text-sm text-danger" role="alert">
          <AlertTriangleIcon />
          {intl.formatMessage({ id: 'overviews.error' })}: {stream.error}
        </p>
      )}

      {/* Artifact list */}
      {list.length === 0 ? (
        <Card className="p-0 overflow-hidden">
          <EmptyState
            icon={<GalleryIcon />}
            title={intl.formatMessage({ id: 'overviews.empty' })}
          />
        </Card>
      ) : (
        <Card className="p-0 overflow-hidden">
          <ul>
            {list.map((artifact) => {
              const canOpen = artifact.status === 'done'
              return (
                <li
                  key={artifact.id}
                  className="flex items-center justify-between gap-3 px-4 py-3 border-b border-border last:border-b-0"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <KindIcon kind={artifact.kind} className="text-text-muted shrink-0" size={18} />
                    <div className="min-w-0">
                      <span className="block text-sm font-medium text-text">
                        {kindLabel(artifact.kind)}
                      </span>
                      {artifact.status === 'error' && artifact.error && (
                        <p className="mt-0.5 text-xs text-danger truncate">{artifact.error}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <StatusChip
                      status={artifact.status}
                      label={intl.formatMessage({
                        id: `overviews.status.${artifact.status}`,
                        defaultMessage: artifact.status,
                      })}
                      animated={animated}
                    />
                    {canOpen && (
                      <button
                        type="button"
                        onClick={(e) => {
                          setOrigin(e.currentTarget.getBoundingClientRect())
                          setOpenArtifact(artifact)
                        }}
                        className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-medium text-text-secondary transition-colors cursor-pointer hover:bg-bg-muted hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
                      >
                        {intl.formatMessage({ id: 'overviews.open' })}
                      </button>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        </Card>
      )}

      <Modal
        open={openArtifact !== null}
        onClose={() => setOpenArtifact(null)}
        size="lg"
        origin={origin}
      >
        {openArtifact && (
          <div>
            <div className="flex items-center gap-2 mb-4 text-text">
              <KindIcon kind={openArtifact.kind} className="text-primary" size={18} />
              <h3 className="text-base font-medium">{kindLabel(openArtifact.kind)}</h3>
            </div>
            <ArtifactView artifact={openArtifact} />
          </div>
        )}
      </Modal>
    </div>
  )
}
