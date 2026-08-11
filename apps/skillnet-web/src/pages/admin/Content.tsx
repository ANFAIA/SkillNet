import { useNavigate } from 'react-router-dom'
import { useIntl } from 'react-intl'
import { motion } from 'framer-motion'
import { Card, Badge, Button, EmptyState, SkeletonCard } from '../../components/ui'
import { useCourses } from '../../api/courses'
import { ApiError, post } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import { staggerContainer, staggerItem } from '../../lib/motion'
import type { CourseStatus } from '../../types'

function useStatusConfig() {
  const intl = useIntl()
  const config: Record<string, { label: string; variant: 'accent' | 'warning' | 'primary' }> = {
    published: { label: intl.formatMessage({ id: 'status.published' }), variant: 'accent' },
    draft: { label: intl.formatMessage({ id: 'status.draft' }), variant: 'warning' },
    archived: { label: intl.formatMessage({ id: 'status.archived' }), variant: 'primary' },
  }
  return (status: CourseStatus) => config[status] ?? { label: status, variant: 'primary' as const }
}

function BookIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  )
}

function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

/** The rich-media Studio (overviews) — a gallery of media sheets. */
function StudioIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <polyline points="21 15 16 10 5 21" />
    </svg>
  )
}

export function Content() {
  const navigate = useNavigate()
  const intl = useIntl()
  const { data, isLoading, error } = useCourses()
  const { user: currentUser } = useAuth()
  const statusOf = useStatusConfig()

  const courses = data?.items ?? []
  const published = courses.filter((c) => c.status === 'published')
  const drafts = courses.filter((c) => c.status === 'draft')
  const archived = courses.filter((c) => c.status === 'archived')

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-text">{intl.formatMessage({ id: 'content.title' })}</h2>
          <p className="text-sm text-text-secondary mt-1">{intl.formatMessage({ id: 'content.totalCourses' }, { count: courses.length })}</p>
        </div>
        <Button variant="primary" size="md" onClick={() => navigate('/admin/crear-curso')}>
          <span className="flex items-center gap-1.5">
            <PlusIcon />
            {intl.formatMessage({ id: 'content.createNew' })}
          </span>
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-2 sm:gap-4 mt-4">
        <div className="border border-border rounded-lg px-3 sm:px-4 py-3">
          <p className="text-xs text-text-muted">{intl.formatMessage({ id: 'content.published' })}</p>
          <p className="text-lg font-semibold text-text">{published.length}</p>
        </div>
        <div className="border border-border rounded-lg px-3 sm:px-4 py-3">
          <p className="text-xs text-text-muted">{intl.formatMessage({ id: 'content.drafts' })}</p>
          <p className="text-lg font-semibold text-text">{drafts.length}</p>
        </div>
        <div className="border border-border rounded-lg px-3 sm:px-4 py-3">
          <p className="text-xs text-text-muted">{intl.formatMessage({ id: 'content.archived' })}</p>
          <p className="text-lg font-semibold text-text">{archived.length}</p>
        </div>
      </div>

      <div className="mt-4 space-y-2">
        {isLoading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : error ? (
          <Card>
            <EmptyState
              title={intl.formatMessage({ id: 'content.loadError' })}
              description={error instanceof ApiError ? error.body.detail : intl.formatMessage({ id: 'content.loadErrorRetry' })}
            />
          </Card>
        ) : courses.length === 0 ? (
          <Card>
            <EmptyState
              title={intl.formatMessage({ id: 'content.emptyTitle' })}
              description={intl.formatMessage({ id: 'content.emptyDesc' })}
              action={{ label: intl.formatMessage({ id: 'content.emptyAction' }), onClick: () => navigate('/admin/crear-curso') }}
            />
          </Card>
        ) : (
          <motion.div className="space-y-2" initial="hidden" animate="visible" variants={staggerContainer}>
          {courses.map((course) => {
            const status = statusOf(course.status)
            return (
              <Card key={course.id} variants={staggerItem}>
                <div className="flex items-center gap-4 min-w-0">
                  <div className="text-text-muted shrink-0">
                    <BookIcon />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-sm font-medium text-text truncate min-w-0">{course.title}</span>
                      <Badge variant={status.variant} badgeStyle="plain" className="shrink-0">
                        {status.label}
                      </Badge>
                    </div>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-0.5 mt-1 text-xs text-text-muted">
                      {course.delivery_mode === 'dynamic' ? (
                        <>
                          <span className="text-primary font-medium">{intl.formatMessage({ id: 'content.dynamic' })}</span>
                          {(course.node_count ?? 0) > 0 && (
                            <span>{intl.formatMessage({ id: 'content.nodesCount' }, { count: course.node_count })}</span>
                          )}
                        </>
                      ) : (
                        <span>{intl.formatMessage({ id: 'content.modulesCount' }, { count: course.module_count })}</span>
                      )}
                      {course.outcome && <span className="truncate max-w-xs">{course.outcome}</span>}
                      <span>{intl.formatMessage({ id: 'content.createdAt' }, { date: new Date(course.created_at).toLocaleDateString() })}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {course.delivery_mode === 'dynamic' && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={async () => {
                          if (!currentUser) return
                          await post('/enrollments', { user_ids: [currentUser.id], course_id: course.id }).catch(() => {})
                          navigate(`/admin/probar-curso/${course.id}`)
                        }}
                      >
                        {intl.formatMessage({ id: 'content.test' })}
                      </Button>
                    )}
                    {course.module_count > 0 && course.delivery_mode !== 'dynamic' && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => navigate(`/admin/curso/${course.id}`)}
                      >
                        {intl.formatMessage({ id: 'content.viewCourse' })}
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => navigate(`/admin/curso/${course.id}/estudio`)}
                    >
                      <span className="flex items-center gap-1.5">
                        <StudioIcon />
                        {intl.formatMessage({ id: 'content.overviews' })}
                      </span>
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => navigate(`/admin/curso/${course.id}/esquema`)}
                    >
                      {intl.formatMessage({ id: 'content.schema' })}
                    </Button>
                  </div>
                </div>
              </Card>
            )
          })}
          </motion.div>
        )}
      </div>
    </div>
  )
}
