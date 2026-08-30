import { useCallback, useMemo, useState } from 'react'
import { useIntl } from 'react-intl'
import { Card, EmptyState, Modal } from '../ui'
import { useCourseArtifacts, type MediaArtifactRead } from '../../api/media'
import { mediaErrorMessageId } from '../../lib/mediaErrors'
import { useCourseNodes } from '../../api/nodes'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { CourseArtifactView } from './CourseArtifactView'
import { CourseMediaIcon } from './CourseMediaIcon'
import { MediaStatusLabel } from './MediaStatusLabel'

interface CourseMediaLibraryProps {
  courseId: string
  operational?: boolean
}

export function CourseMediaLibrary({ courseId, operational = false }: CourseMediaLibraryProps) {
  const intl = useIntl()
  const animated = !useReducedMotion()
  // The studio (operational) view lists every artefact including per-node ones, so the
  // podcasts/infographics attached to a lesson are visible and manageable — not just the
  // course-level overviews. The learner-facing library stays course-level only.
  const { data: artifacts } = useCourseArtifacts(courseId, { includeNodes: operational })
  const { data: nodeList } = useCourseNodes(courseId, { enabled: operational })
  const nodeLabelById = useMemo(() => {
    const sorted = [...(nodeList?.nodes ?? [])].sort((a, b) => a.position - b.position)
    return new Map(sorted.map((node, index) => [node.id, `${index + 1}. ${node.title}`]))
  }, [nodeList])
  const [openArtifact, setOpenArtifact] = useState<MediaArtifactRead | null>(null)
  const [origin, setOrigin] = useState<DOMRect | null>(null)
  const kindLabel = useCallback(
    (kind: string) => intl.formatMessage({ id: `overviews.kind.${kind}`, defaultMessage: kind }),
    [intl],
  )
  const list = operational ? (artifacts ?? []) : (artifacts ?? []).filter((artifact) => artifact.status === 'done')

  if (list.length === 0) {
    return (
      <Card className="overflow-hidden p-0">
        <EmptyState
          icon={<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" /></svg>}
          title={intl.formatMessage({ id: operational ? 'overviews.empty' : 'overviews.libraryEmpty' })}
        />
      </Card>
    )
  }

  return (
    <>
      <Card className="overflow-hidden p-0">
        <ul>
          {list.map((artifact) => {
            const canOpen = artifact.status === 'done'
            const focusValue = artifact.spec_json.steering ?? artifact.spec_json.prompt
            const focus = typeof focusValue === 'string' && focusValue.trim() ? focusValue.trim() : null
            const actionLabel = artifact.kind === 'podcast' || artifact.kind === 'video'
              ? intl.formatMessage({ id: 'overviews.play' })
              : intl.formatMessage({ id: 'overviews.view' })
            const createdAt = new Date(artifact.created_at)
            return (
              <li key={artifact.id} className="flex items-center justify-between gap-4 border-b border-border px-4 py-3.5 last:border-b-0">
                <div className="flex min-w-0 items-center gap-3.5">
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-border bg-bg-subtle text-text-secondary">
                    <CourseMediaIcon kind={artifact.kind} size={19} />
                  </span>
                  <div className="min-w-0">
                    <span className="flex flex-wrap items-center gap-2 text-sm font-medium text-text">
                      {kindLabel(artifact.kind)}
                      {operational && artifact.node_id && (
                        <span className="inline-flex items-center rounded-full border border-border bg-bg-subtle px-2 py-0.5 text-[11px] font-normal text-text-secondary">
                          {nodeLabelById.get(artifact.node_id) ?? intl.formatMessage({ id: 'overviews.node.badge' })}
                        </span>
                      )}
                      {operational && !artifact.node_id && (
                        <span className="inline-flex items-center rounded-full border border-border bg-bg-subtle px-2 py-0.5 text-[11px] font-normal text-text-muted">
                          {intl.formatMessage({ id: 'overviews.node.courseBadge' })}
                        </span>
                      )}
                    </span>
                    {operational && artifact.status === 'error' && <p className="mt-0.5 truncate text-xs text-danger">{intl.formatMessage({ id: mediaErrorMessageId(artifact.error_code) })}</p>}
                    {!operational && (
                      <>
                        <p className="mt-0.5 text-xs text-text-muted">
                          {intl.formatDate(createdAt, { day: 'numeric', month: 'short', year: 'numeric' })} · {intl.formatTime(createdAt, { hour: '2-digit', minute: '2-digit' })}
                        </p>
                        {focus && (
                          <p className="mt-0.5 line-clamp-1 text-xs text-text-secondary">
                            {intl.formatMessage({ id: 'overviews.customized' }, { focus })}
                          </p>
                        )}
                      </>
                    )}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  {operational && <MediaStatusLabel status={artifact.status} label={intl.formatMessage({ id: `overviews.status.${artifact.status}`, defaultMessage: artifact.status })} animated={animated} />}
                  {canOpen && (
                    <button
                      type="button"
                      onClick={(event) => { setOrigin(event.currentTarget.getBoundingClientRect()); setOpenArtifact(artifact) }}
                      className="inline-flex cursor-pointer items-center rounded-lg px-2.5 py-1 text-xs font-medium text-text-secondary hover:bg-bg-muted hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
                    >
                      {operational ? intl.formatMessage({ id: 'overviews.open' }) : actionLabel}
                    </button>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      </Card>

      <Modal open={openArtifact !== null} onClose={() => setOpenArtifact(null)} size="lg" origin={origin}>
        {openArtifact && (
          <div>
            <div className="mb-4 flex items-center gap-2 text-text">
              <CourseMediaIcon kind={openArtifact.kind} className="text-primary" size={18} />
              <h3 className="text-base font-medium">{kindLabel(openArtifact.kind)}</h3>
            </div>
            <CourseArtifactView artifact={openArtifact} />
          </div>
        )}
      </Modal>
    </>
  )
}
