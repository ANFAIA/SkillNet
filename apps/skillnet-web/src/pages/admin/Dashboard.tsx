import { motion } from 'framer-motion'
import { Link } from 'react-router-dom'
import { useIntl, type IntlShape } from 'react-intl'
import { useStats } from '../../api/stats'
import { useAuth, useWorkspaceMode } from '../../hooks/useAuth'
import { Card, CardTitle, MetricCard, PageHeader, Skeleton } from '../../components/ui'
import { staggerContainer, staggerItem } from '../../lib/motion'
import type { RecentActivityItem } from '../../types'

function UsersIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  )
}

function BookIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  )
}

function TargetIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="2" />
    </svg>
  )
}

function AlertClockIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="13" r="8" />
      <path d="M12 9v4l2.5 2.5" />
      <path d="M5 3 3 5" />
      <path d="m21 5-2-2" />
    </svg>
  )
}

function MetricCardSkeleton() {
  return <Skeleton className="h-[108px] rounded-lg" />
}

function ActivitySkeleton() {
  return (
    <div className="space-y-0">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-center justify-between py-3 border-b border-border last:border-b-0">
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3.5 w-3/5" />
            <Skeleton className="h-3 w-2/5" />
          </div>
          <Skeleton className="h-3 w-14 ml-4" />
        </div>
      ))}
    </div>
  )
}

function formatActivityLabel(item: RecentActivityItem, intl: IntlShape): { employee: string; action: string; detail: string } {
  switch (item.type) {
    case 'enrollment_completed':
      return {
        employee: item.user_name ?? intl.formatMessage({ id: 'admin.dashboard.activity.defaultUser' }),
        action: intl.formatMessage({ id: 'admin.dashboard.activity.completedCourse' }),
        detail: item.course_title ?? '',
      }
    case 'course_published':
      return {
        employee: intl.formatMessage({ id: 'admin.dashboard.activity.system' }),
        action: intl.formatMessage({ id: 'admin.dashboard.activity.publishedCourse' }),
        detail: item.course_title ?? '',
      }
    case 'user_created':
      return {
        employee: item.user_name ?? intl.formatMessage({ id: 'admin.dashboard.activity.newEmployee' }),
        action: intl.formatMessage({ id: 'admin.dashboard.activity.signedUp' }),
        detail: '',
      }
    default:
      return {
        employee: item.user_name ?? '',
        action: item.type,
        detail: item.course_title ?? '',
      }
  }
}

function formatRelativeTime(isoDate: string, intl: IntlShape): string {
  const diff = Date.now() - new Date(isoDate).getTime()
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 1) return intl.formatMessage({ id: 'admin.dashboard.time.now' })
  if (minutes < 60) return intl.formatMessage({ id: 'admin.dashboard.time.minutes' }, { count: minutes })
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return intl.formatMessage({ id: 'admin.dashboard.time.hours' }, { count: hours })
  const days = Math.floor(hours / 24)
  return intl.formatMessage({ id: 'admin.dashboard.time.days' }, { count: days })
}

/**
 * The individual owner's home. In an `individual` deployment there is no team,
 * so the company panel (employees, collective enrollments, others' activity) has
 * nothing to show and its `/stats` endpoint 404s. This replaces it with a
 * personal starting point: create a course, or open the ones you have. See
 * docs/design/audience-modes.md.
 */
function IndividualHome() {
  const intl = useIntl()
  const { user } = useAuth()
  const name = user?.full_name?.split(' ')[0] ?? ''
  const greeting = name
    ? intl.formatMessage({ id: 'admin.home.greetingName' }, { name })
    : intl.formatMessage({ id: 'admin.home.greeting' })

  return (
    <div>
      <PageHeader
        title={greeting}
        description={intl.formatMessage({ id: 'admin.home.individualSubtitle' })}
      />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-6">
        <Link to="/admin/crear-curso" className="block">
          <Card className="h-full transition-colors hover:border-primary">
            <CardTitle>{intl.formatMessage({ id: 'admin.nav.createCourse' })}</CardTitle>
            <p className="mt-2 text-sm text-text-secondary">
              {intl.formatMessage({ id: 'admin.home.createHint' })}
            </p>
          </Card>
        </Link>
        <Link to="/admin/contenido" className="block">
          <Card className="h-full transition-colors hover:border-primary">
            <CardTitle>{intl.formatMessage({ id: 'admin.nav.myCourses' })}</CardTitle>
            <p className="mt-2 text-sm text-text-secondary">
              {intl.formatMessage({ id: 'admin.home.myCoursesHint' })}
            </p>
          </Card>
        </Link>
      </div>
    </div>
  )
}

export function Dashboard() {
  const intl = useIntl()
  const mode = useWorkspaceMode()
  const { data: stats, isLoading, isError } = useStats({ enabled: mode !== 'individual' })

  if (mode === 'individual') return <IndividualHome />

  if (isError) {
    return (
      <div>
        <PageHeader
          title={intl.formatMessage({ id: 'admin.dashboard.title' })}
          description={intl.formatMessage({ id: 'admin.dashboard.description' })}
        />
        <Card className="mt-6">
          <p className="text-sm text-danger">
            {intl.formatMessage({ id: 'admin.dashboard.loadError' })}
          </p>
        </Card>
      </div>
    )
  }

  return (
    <div>
      <PageHeader
        title={intl.formatMessage({ id: 'admin.dashboard.title' })}
        description={intl.formatMessage({ id: 'admin.dashboard.description' })}
      />

      {/* Metric cards */}
      <motion.div
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-6"
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
      >
        {isLoading ? (
          <>
            <MetricCardSkeleton />
            <MetricCardSkeleton />
            <MetricCardSkeleton />
            <MetricCardSkeleton />
          </>
        ) : (
          <>
            <motion.div variants={staggerItem}>
              <MetricCard
                value={`${stats!.active_employees}/${stats!.total_employees}`}
                label={intl.formatMessage({ id: 'admin.dashboard.activeEmployees' })}
                icon={<UsersIcon />}
              />
            </motion.div>
            <motion.div variants={staggerItem}>
              <MetricCard
                value={String(stats!.published_courses)}
                label={intl.formatMessage({ id: 'admin.dashboard.publishedCourses' })}
                icon={<BookIcon />}
              />
            </motion.div>
            <motion.div variants={staggerItem}>
              <MetricCard
                value={
                  stats!.total_enrollments > 0
                    ? `${Math.round((stats!.completed_enrollments / stats!.total_enrollments) * 100)}%`
                    : '--'
                }
                label={intl.formatMessage({ id: 'admin.dashboard.completionRate' })}
                icon={<TargetIcon />}
              />
            </motion.div>
            <motion.div variants={staggerItem}>
              <MetricCard
                value={String(stats!.overdue_assignments)}
                label={intl.formatMessage({ id: 'admin.dashboard.overdueAssignments' })}
                icon={<AlertClockIcon />}
              />
            </motion.div>
          </>
        )}
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
        {/* Enrollment summary */}
        <Card>
          <CardTitle>{intl.formatMessage({ id: 'admin.dashboard.enrollmentsTitle' })}</CardTitle>
          {isLoading ? (
            <div className="mt-3 space-y-3">
              <Skeleton className="h-3.5 w-full" />
              <Skeleton className="h-3.5 w-4/5" />
              <Skeleton className="h-3.5 w-3/5" />
            </div>
          ) : (
            <div className="mt-3 space-y-0">
              <div className="flex items-center justify-between py-3 border-b border-border">
                <span className="text-sm text-text-secondary">{intl.formatMessage({ id: 'admin.dashboard.completed' })}</span>
                <span className="text-sm font-medium text-text">{stats!.completed_enrollments}</span>
              </div>
              <div className="flex items-center justify-between py-3 border-b border-border">
                <span className="text-sm text-text-secondary">{intl.formatMessage({ id: 'admin.dashboard.inProgress' })}</span>
                <span className="text-sm font-medium text-text">{stats!.in_progress_enrollments}</span>
              </div>
              <div className="flex items-center justify-between py-3 border-b border-border">
                <span className="text-sm text-text-secondary">{intl.formatMessage({ id: 'admin.dashboard.totalCourses' })}</span>
                <span className="text-sm font-medium text-text">{stats!.total_courses}</span>
              </div>
              <div className="flex items-center justify-between py-3">
                <span className="text-sm text-text-secondary">{intl.formatMessage({ id: 'admin.dashboard.drafts' })}</span>
                <span className="text-sm font-medium text-text">{stats!.draft_courses}</span>
              </div>
            </div>
          )}
        </Card>

        {/* Recent activity */}
        <Card>
          <CardTitle>{intl.formatMessage({ id: 'admin.dashboard.recentActivity' })}</CardTitle>
          {isLoading ? (
            <div className="mt-3">
              <ActivitySkeleton />
            </div>
          ) : stats!.recent_activity.length === 0 ? (
            <p className="mt-3 text-sm text-text-muted">{intl.formatMessage({ id: 'admin.dashboard.noRecentActivity' })}</p>
          ) : (
            <motion.div
              className="mt-3 space-y-0"
              variants={staggerContainer}
              initial="hidden"
              animate="visible"
            >
              {stats!.recent_activity.map((activity, i) => {
                const { employee, action, detail } = formatActivityLabel(activity, intl)
                return (
                  <motion.div
                    key={i}
                    variants={staggerItem}
                    className="flex items-center justify-between py-3 border-b border-border last:border-b-0"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-text truncate">
                        <span className="font-medium">{employee}</span>
                        {' '}{action}
                      </p>
                      {detail && (
                        <p className="text-xs text-text-muted mt-0.5 truncate">{detail}</p>
                      )}
                    </div>
                    <span className="text-xs text-text-muted shrink-0 ml-4">
                      {formatRelativeTime(activity.at, intl)}
                    </span>
                  </motion.div>
                )
              })}
            </motion.div>
          )}
        </Card>
      </div>
    </div>
  )
}
