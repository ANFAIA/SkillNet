import { motion } from 'framer-motion'
import { Link } from 'react-router-dom'
import { useIntl } from 'react-intl'
import { useStats } from '../../api/stats'
import { useAuth, useWorkspaceMode } from '../../hooks/useAuth'
import { AdminOnboardingScene, useAdminScene } from '../../features/onboarding/adminScene'
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

function ChartIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
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

function formatActivityLabel(item: RecentActivityItem): { employee: string; action: string; detail: string } {
  switch (item.type) {
    case 'enrollment_completed':
      return {
        employee: item.user_name ?? 'Usuario',
        action: 'completo curso',
        detail: item.course_title ?? '',
      }
    case 'course_published':
      return {
        employee: 'Sistema',
        action: 'publico curso',
        detail: item.course_title ?? '',
      }
    case 'user_created':
      return {
        employee: item.user_name ?? 'Nuevo empleado',
        action: 'se registro',
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

function formatRelativeTime(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime()
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 1) return 'ahora'
  if (minutes < 60) return `hace ${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `hace ${hours}h`
  const days = Math.floor(hours / 24)
  return `hace ${days}d`
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
  const mode = useWorkspaceMode()
  const { data: stats, isLoading, isError } = useStats({ enabled: mode !== 'individual' })
  const { dismissed: sceneDismissed, dismiss: dismissScene } = useAdminScene()

  if (mode === 'individual') return <IndividualHome />

  // First run: an org admin with no content yet gets the interactive onboarding
  // scene in place of an empty panel (docs/design/onboarding.md §3.2). It is
  // dismissible and, once there is any real course, the gate falls through to the
  // real panel on its own — nothing to clean up.
  if (!isLoading && !isError && stats && stats.total_courses === 0 && !sceneDismissed) {
    return <AdminOnboardingScene onDismiss={dismissScene} />
  }

  if (isError) {
    return (
      <div>
        <PageHeader title="Panel de empresa" description="Vista general del equipo y la formación." />
        <Card className="mt-6">
          <p className="text-sm text-danger">
            Error al cargar las estadisticas. Intenta recargar la pagina.
          </p>
        </Card>
      </div>
    )
  }

  return (
    <div>
      <PageHeader title="Panel de empresa" description="Vista general del equipo y la formación." />

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
                label="Empleados activos"
                icon={<UsersIcon />}
              />
            </motion.div>
            <motion.div variants={staggerItem}>
              <MetricCard
                value={String(stats!.published_courses)}
                label="Cursos publicados"
                icon={<BookIcon />}
              />
            </motion.div>
            <motion.div variants={staggerItem}>
              <MetricCard
                value={String(stats!.total_enrollments)}
                label="Inscripciones"
                icon={<TargetIcon />}
              />
            </motion.div>
            <motion.div variants={staggerItem}>
              <MetricCard
                value={stats!.avg_score != null ? `${Math.round(stats!.avg_score * 100)}%` : '--'}
                label="Puntuacion media"
                icon={<ChartIcon />}
              />
            </motion.div>
          </>
        )}
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
        {/* Enrollment summary */}
        <Card>
          <CardTitle>Inscripciones</CardTitle>
          {isLoading ? (
            <div className="mt-3 space-y-3">
              <Skeleton className="h-3.5 w-full" />
              <Skeleton className="h-3.5 w-4/5" />
              <Skeleton className="h-3.5 w-3/5" />
            </div>
          ) : (
            <div className="mt-3 space-y-0">
              <div className="flex items-center justify-between py-3 border-b border-border">
                <span className="text-sm text-text-secondary">Completadas</span>
                <span className="text-sm font-medium text-text">{stats!.completed_enrollments}</span>
              </div>
              <div className="flex items-center justify-between py-3 border-b border-border">
                <span className="text-sm text-text-secondary">En progreso</span>
                <span className="text-sm font-medium text-text">{stats!.in_progress_enrollments}</span>
              </div>
              <div className="flex items-center justify-between py-3 border-b border-border">
                <span className="text-sm text-text-secondary">Total cursos</span>
                <span className="text-sm font-medium text-text">{stats!.total_courses}</span>
              </div>
              <div className="flex items-center justify-between py-3">
                <span className="text-sm text-text-secondary">Borradores</span>
                <span className="text-sm font-medium text-text">{stats!.draft_courses}</span>
              </div>
            </div>
          )}
        </Card>

        {/* Recent activity */}
        <Card>
          <CardTitle>Actividad reciente</CardTitle>
          {isLoading ? (
            <div className="mt-3">
              <ActivitySkeleton />
            </div>
          ) : stats!.recent_activity.length === 0 ? (
            <p className="mt-3 text-sm text-text-muted">Sin actividad reciente.</p>
          ) : (
            <motion.div
              className="mt-3 space-y-0"
              variants={staggerContainer}
              initial="hidden"
              animate="visible"
            >
              {stats!.recent_activity.map((activity, i) => {
                const { employee, action, detail } = formatActivityLabel(activity)
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
                      {formatRelativeTime(activity.at)}
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
