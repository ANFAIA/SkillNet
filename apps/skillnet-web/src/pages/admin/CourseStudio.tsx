import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useIntl } from 'react-intl'
import { motion } from 'framer-motion'
import { Button, Badge, Card, EmptyState, Input, Skeleton, SkeletonText } from '../../components/ui'
import { CourseOverviews } from '../../components/courses/CourseOverviews'
import { useCourse, useUpdateCourse, usePublishCourse, useArchiveCourse } from '../../api/courses'
import { useDocument } from '../../api/documents'
import { useCourseNodes } from '../../api/nodes'
import { duration, ease, staggerContainer, staggerItem } from '../../lib/motion'
import type { LearningNode, NodeState } from '../../types'

function useStatusConfig() {
  const intl = useIntl()
  return {
    published: { label: intl.formatMessage({ id: 'status.published' }), variant: 'accent' as const },
    draft: { label: intl.formatMessage({ id: 'status.draft' }), variant: 'warning' as const },
    archived: { label: intl.formatMessage({ id: 'status.archived' }), variant: 'primary' as const },
  }
}

const NODE_STATE_CLASS: Record<NodeState, string> = {
  not_started: 'text-text-muted',
  learning: 'text-primary',
  mastered: 'text-accent',
  needs_review: 'text-warning',
}

// ─── Inline icons (repo stroke style: viewBox 0 0 24 24, round caps/joins) ────

interface GlyphProps {
  className?: string
  size?: number
}

function glyphProps(size: number, className: string) {
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

/** Completed node — check-circle. */
function CheckCircleGlyph({ className = '', size = 16 }: GlyphProps) {
  return (
    <svg {...glyphProps(size, className)}>
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  )
}

/** In-progress / needs-review node — a filled dot inside a ring. */
function CurrentDotGlyph({ className = '', size = 16 }: GlyphProps) {
  return (
    <svg {...glyphProps(size, className)}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" />
    </svg>
  )
}

/** Not-started node — an outline circle. */
function CircleGlyph({ className = '', size = 16 }: GlyphProps) {
  return (
    <svg {...glyphProps(size, className)}>
      <circle cx="12" cy="12" r="9" />
    </svg>
  )
}

/** Locked node — a padlock. */
function LockGlyph({ className = '', size = 16 }: GlyphProps) {
  return (
    <svg {...glyphProps(size, className)}>
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  )
}

/** State glyph for one index node — a padlock wins over the mastery state. */
function NodeStateIcon({ node }: { node: LearningNode }) {
  if (node.locked) return <LockGlyph className="text-text-muted shrink-0" />
  switch (node.state) {
    case 'mastered':
      return <CheckCircleGlyph className="text-accent shrink-0" />
    case 'learning':
      return <CurrentDotGlyph className="text-primary shrink-0" />
    case 'needs_review':
      return <CurrentDotGlyph className="text-warning shrink-0" />
    default:
      return <CircleGlyph className="text-text-muted shrink-0" />
  }
}

/** Node count — a stack of layers. */
function LayersGlyph({ className = '', size = 14 }: GlyphProps) {
  return (
    <svg {...glyphProps(size, className)}>
      <polygon points="12 2 2 7 12 12 22 7 12 2" />
      <polyline points="2 17 12 22 22 17" />
      <polyline points="2 12 12 17 22 12" />
    </svg>
  )
}

/** Dynamic delivery — a lightning bolt. */
function ZapGlyph({ className = '', size = 14 }: GlyphProps) {
  return (
    <svg {...glyphProps(size, className)}>
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  )
}

/** Static delivery — a document. */
function FileGlyph({ className = '', size = 14 }: GlyphProps) {
  return (
    <svg {...glyphProps(size, className)}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  )
}

/** Validated schema — a badge check. */
function BadgeCheckGlyph({ className = '', size = 14 }: GlyphProps) {
  return (
    <svg {...glyphProps(size, className)}>
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  )
}

/** A bordered inline stat pill with a tiny leading icon. */
function StatPill({ icon, children, className = 'text-text-secondary' }: { icon: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border border-border px-2 py-0.5 text-xs font-medium ${className}`}>
      {icon}
      {children}
    </span>
  )
}

/** The course index — the ordered node outline, the same list the course views render. */
function CourseIndex({ courseId }: { courseId: string }) {
  const intl = useIntl()
  const nodesQuery = useCourseNodes(courseId)
  const nodes = nodesQuery.data?.nodes

  const stateLabel: Record<NodeState, string> = {
    not_started: intl.formatMessage({ id: 'nodelist.stateNotStarted' }),
    learning: intl.formatMessage({ id: 'nodelist.stateLearning' }),
    mastered: intl.formatMessage({ id: 'nodelist.stateMastered' }),
    needs_review: intl.formatMessage({ id: 'nodelist.stateNeedsReview' }),
  }

  return (
    <div>
      <h3 className="text-base font-medium text-text mb-3">
        {intl.formatMessage({ id: 'preview.index' })}
      </h3>
      <Card className="p-0 overflow-hidden">
        {nodesQuery.isLoading ? (
          <div className="p-4"><SkeletonText lines={4} /></div>
        ) : !nodes || nodes.length === 0 ? (
          <p className="p-4 text-sm text-text-muted">
            {intl.formatMessage({ id: 'preview.indexEmpty' })}
          </p>
        ) : (
          <motion.ul initial="hidden" animate="visible" variants={staggerContainer}>
            {[...nodes]
              .sort((a: LearningNode, b: LearningNode) => a.position - b.position)
              .map((node, i) => (
                <motion.li
                  key={node.id}
                  variants={staggerItem}
                  className="flex items-center gap-3 px-4 py-3 border-b border-border last:border-b-0"
                >
                  <NodeStateIcon node={node} />
                  <span className="text-xs tabular-nums text-text-muted w-4 shrink-0">{i + 1}</span>
                  <span className="text-sm text-text truncate min-w-0 flex-1">{node.title}</span>
                  <span className={`text-xs shrink-0 ${NODE_STATE_CLASS[node.state]}`}>
                    {stateLabel[node.state]}
                  </span>
                </motion.li>
              ))}
          </motion.ul>
        )}
      </Card>
    </div>
  )
}

/**
 * Course Studio for `/admin/curso/:id/estudio` — the media hub of one course.
 *
 * A separate screen from CoursePreview, reached from the Contenido page. It shows the
 * header (title + meta), an action row (Probar / Esquema / edit / publish), the course
 * index (the node outline the runtime serves), and the Overviews panel that generates and
 * plays the rich-media artifacts (podcast, video, infographic, slides). Admin only.
 */
export function CourseStudio() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const intl = useIntl()
  const statusConfig = useStatusConfig()
  const { data: course, isLoading, error } = useCourse(id)
  // Where the content came from. A course built on a source the model wrote is not the
  // same claim as one built on the company's own material, and the creator has to be
  // able to see which one they are looking at without going digging.
  const { data: sourceDoc } = useDocument(course?.source_document_id)

  const updateCourse = useUpdateCourse()
  const publishCourse = usePublishCourse()
  const archiveCourse = useArchiveCourse()

  const [editing, setEditing] = useState(false)
  const [editTitle, setEditTitle] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editOutcome, setEditOutcome] = useState('')

  if (isLoading) {
    return (
      <div>
        <Skeleton className="h-6 w-1/3 mb-6" />
        <div className="flex flex-col lg:flex-row gap-6">
          <div className="flex-1 min-w-0"><Card><SkeletonText lines={5} /></Card></div>
          <div className="flex-1 min-w-0"><Card><SkeletonText lines={5} /></Card></div>
        </div>
      </div>
    )
  }

  if (error || !course) {
    return (
      <EmptyState
        title={intl.formatMessage({ id: 'preview.notFound' })}
        description={intl.formatMessage({ id: 'preview.notFoundDesc' })}
        action={{ label: intl.formatMessage({ id: 'preview.backToContent' }), onClick: () => navigate('/admin/contenido') }}
      />
    )
  }

  const status = statusConfig[course.status as keyof typeof statusConfig] ?? { label: course.status, variant: 'primary' as const }

  function startEditing() {
    if (!course) return
    setEditTitle(course.title)
    setEditDescription(course.description ?? '')
    setEditOutcome(course.outcome ?? '')
    setEditing(true)
  }

  function saveEditing() {
    if (!id) return
    updateCourse.mutate(
      { id, payload: { title: editTitle, description: editDescription, outcome: editOutcome } },
      { onSuccess: () => setEditing(false) },
    )
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        {editing ? (
          <div className="space-y-3">
            <Input
              label={intl.formatMessage({ id: 'preview.titleLabel' })}
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
            />
            <div className="space-y-1">
              <label className="block text-sm font-medium text-text">{intl.formatMessage({ id: 'preview.descLabel' })}</label>
              <textarea
                className="w-full px-3 py-2 text-sm text-text border border-border rounded-lg bg-bg placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors duration-150 min-h-[80px] resize-y"
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
              />
            </div>
            <Input
              label={intl.formatMessage({ id: 'preview.outcomeLabel' })}
              value={editOutcome}
              onChange={(e) => setEditOutcome(e.target.value)}
            />
            <div className="flex items-center gap-2">
              <Button size="sm" onClick={saveEditing} disabled={updateCourse.isPending || !editTitle.trim()}>
                {updateCourse.isPending ? intl.formatMessage({ id: 'preview.saving' }) : intl.formatMessage({ id: 'preview.save' })}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setEditing(false)} disabled={updateCourse.isPending}>
                {intl.formatMessage({ id: 'preview.cancel' })}
              </Button>
              {updateCourse.isError && (
                <span className="text-xs text-danger">{intl.formatMessage({ id: 'preview.saveError' })}</span>
              )}
            </div>
          </div>
        ) : (
          <>
            <div className="shrink-0 flex items-baseline gap-1.5 mb-2 flex-wrap">
              <h2
                className="text-xl font-semibold transition-colors duration-200 text-text-muted cursor-pointer hover:text-text"
                onClick={() => navigate('/admin/contenido')}
                role="button"
              >
                {intl.formatMessage({ id: 'content.title' })}
              </h2>
              <span className="text-xl font-semibold text-text-muted">/</span>
              <span
                className="text-xl font-semibold transition-colors duration-200 text-text-muted cursor-pointer hover:text-text"
                onClick={() => navigate(`/admin/curso/${id}`)}
                role="button"
              >
                {course.title}
              </span>
              <motion.span
                key="breadcrumb-studio"
                className="text-xl font-semibold text-text"
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0, transition: { duration: duration.normal, ease: ease.base } }}
              >
                / {intl.formatMessage({ id: 'overviews.studio' })}
              </motion.span>
              <Badge variant={status.variant} badgeStyle="plain" className="shrink-0 ml-1.5">
                {status.label}
              </Badge>
            </div>
            {course.description && (
              <p className="text-sm text-text-secondary mb-1">{course.description}</p>
            )}
            {course.outcome && (
              <p className="text-sm text-text-muted mb-1">{intl.formatMessage({ id: 'preview.objective' }, { outcome: course.outcome })}</p>
            )}
            {/* Meta: node count + delivery mode / validated */}
            <div className="flex items-center gap-2 flex-wrap mt-2">
              {course.node_count != null && (
                <StatPill icon={<LayersGlyph />}>
                  {intl.formatMessage({ id: 'preview.metaNodes' }, { count: course.node_count })}
                </StatPill>
              )}
              {course.delivery_mode === 'dynamic' ? (
                <StatPill icon={<ZapGlyph />} className="text-primary">
                  {intl.formatMessage({ id: 'preview.metaDynamic' })}
                </StatPill>
              ) : (
                <StatPill icon={<FileGlyph />}>
                  {intl.formatMessage({ id: 'preview.metaStatic' })}
                </StatPill>
              )}
              {course.schema_status === 'validated' && (
                <StatPill icon={<BadgeCheckGlyph />} className="text-accent">
                  {intl.formatMessage({ id: 'preview.metaValidated' })}
                </StatPill>
              )}
            </div>
            {sourceDoc && (
              <p className="text-sm text-text-secondary mt-1 flex items-center gap-2 flex-wrap">
                <span className="text-text-muted">{intl.formatMessage({ id: 'preview.source' })}</span>
                <span className="truncate">{sourceDoc.title}</span>
                {sourceDoc.origin === 'generated' && (
                  <Badge variant="warning" badgeStyle="plain" className="shrink-0">
                    {intl.formatMessage({ id: 'preview.aiGenerated' })}
                  </Badge>
                )}
              </p>
            )}

            {/* Action row */}
            <div className="flex items-center gap-2 mt-3 flex-wrap">
              <Button variant="secondary" size="sm" onClick={() => navigate(`/admin/probar-curso/${id}`)}>
                {intl.formatMessage({ id: 'preview.test' })}
              </Button>
              <Button variant="secondary" size="sm" onClick={() => navigate(`/admin/curso/${id}/esquema`)}>
                {intl.formatMessage({ id: 'preview.schema' })}
              </Button>
              <Button variant="ghost" size="sm" onClick={startEditing}>
                {intl.formatMessage({ id: 'preview.edit' })}
              </Button>
              {course.status === 'draft' && (
                <Button
                  variant="accent"
                  size="sm"
                  onClick={() => id && publishCourse.mutate(id)}
                  disabled={publishCourse.isPending}
                >
                  {publishCourse.isPending ? intl.formatMessage({ id: 'preview.publishing' }) : intl.formatMessage({ id: 'preview.publish' })}
                </Button>
              )}
              {course.status === 'published' && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => id && archiveCourse.mutate(id)}
                  disabled={archiveCourse.isPending}
                >
                  {archiveCourse.isPending ? intl.formatMessage({ id: 'preview.archiving' }) : intl.formatMessage({ id: 'preview.archive' })}
                </Button>
              )}
              {(publishCourse.isError || archiveCourse.isError) && (
                <span className="text-xs text-danger">{intl.formatMessage({ id: 'preview.statusError' })}</span>
              )}
            </div>
          </>
        )}
      </div>

      {/* Body: index + overviews */}
      <div className="flex flex-col lg:flex-row gap-6 items-start">
        <div className="w-full lg:w-80 lg:shrink-0">
          {id && <CourseIndex courseId={id} />}
        </div>
        <div className="flex-1 min-w-0">
          {id && <CourseOverviews courseId={id} />}
        </div>
      </div>
    </div>
  )
}
