import { useNavigate } from 'react-router-dom'
import { useIntl } from 'react-intl'
import { motion } from 'framer-motion'
import {
  Badge,
  Button,
  Card,
  CardTitle,
  CourseItem,
  EmptyState,
  MetricCard,
  PageHeader,
  ProgressBar,
  SkillBars,
  SkeletonRow,
} from '../../components/ui'
import { useMe } from '../../api/auth'
import { useEnrollments } from '../../api/enrollments'
import { useMySkills } from '../../api/users'
import { staggerContainer, staggerItem } from '../../lib/motion'
import type { EnrollmentRead } from '../../types'

function BookIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

function ClockIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  )
}

function PlayIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <polygon points="6 4 20 12 6 20 6 4" />
    </svg>
  )
}

export function Dashboard() {
  const intl = useIntl()
  const navigate = useNavigate()
  const { data: me } = useMe()
  const { data: enrollmentData, isLoading, error } = useEnrollments()

  const enrollments = enrollmentData?.items ?? []
  const isDone = (e: EnrollmentRead) => e.status === 'completed' || (e.progress ?? 0) >= 1
  const active = enrollments.filter((e) => !isDone(e) && e.status === 'in_progress')
  const completed = enrollments.filter((e) => isDone(e))
  const pending = enrollments.filter((e) => !isDone(e) && e.status === 'assigned')
  // Everything the learner still has to work on, newest attention first: courses in
  // progress (highest progress first) then the not-yet-started ones. This is what makes
  // the home useful for a freshly-onboarded learner — every enrollment starts as
  // `assigned` with progress 0, so a "only show in_progress" list is empty on day one.
  const ongoing = [...active, ...pending].sort((a, b) => {
    const aStarted = a.status === 'in_progress'
    const bStarted = b.status === 'in_progress'
    if (aStarted !== bStarted) return aStarted ? -1 : 1
    return (b.progress ?? 0) - (a.progress ?? 0)
  })
  const resume = ongoing[0]

  const { data: userSkills, isLoading: skillsLoading } = useMySkills()
  const dashboardSkills = (userSkills ?? []).slice(0, 4)
  const firstName = me?.full_name?.split(' ')[0] ?? ''

  const statusLabel: Record<string, string> = {
    not_started: intl.formatMessage({ id: 'mycourses.statusPending' }),
    assigned: intl.formatMessage({ id: 'mycourses.statusPending' }),
    in_progress: intl.formatMessage({ id: 'mycourses.statusInProgress' }),
    completed: intl.formatMessage({ id: 'mycourses.statusCompleted' }),
    overdue: intl.formatMessage({ id: 'mycourses.statusOverdue' }),
  }

  function dynamicBadge(e: EnrollmentRead) {
    if (e.delivery_mode !== 'dynamic') return undefined
    return (
      <Badge variant="primary" badgeStyle="plain">
        {intl.formatMessage({ id: 'mycourses.byNodes' })}
      </Badge>
    )
  }

  function subtitleFor(e: EnrollmentRead): string {
    const label = statusLabel[e.status] ?? e.status
    if (e.deadline) {
      return intl.formatMessage({ id: 'mycourses.deadline' }, { label, date: new Date(e.deadline).toLocaleDateString() })
    }
    return label
  }

  const started = resume ? resume.status === 'in_progress' : false

  return (
    <div>
      <div className="mb-6">
        <PageHeader
          title={
            firstName
              ? intl.formatMessage({ id: 'home.greetingName' }, { name: firstName })
              : intl.formatMessage({ id: 'home.greeting' })
          }
          description={intl.formatMessage({ id: 'home.subtitle' })}
        />
      </div>

      {/* Continue / start hero — the primary call to action. Only shown once we know the
          learner has an open course; hidden while loading or when everything is done. */}
      {!isLoading && !error && resume && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-6" data-tour="home-hero">
          <Card className="border-primary/30 bg-primary/[0.04]">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium uppercase tracking-wide text-primary">
                  {intl.formatMessage({ id: started ? 'home.resumeEyebrow' : 'home.startEyebrow' })}
                </p>
                <div className="mt-1 flex items-center gap-2">
                  <h2 className="truncate text-lg font-semibold text-text">{resume.course_title}</h2>
                  {dynamicBadge(resume)}
                </div>
                <div className="mt-3 flex items-center gap-3">
                  {/*
                    `variant="auto"`, not a fixed `color`. A fixed colour wins over the
                    variant inside `ProgressBar` (it becomes an inline `backgroundColor`),
                    so this bar was primary blue at 3% and primary blue at 100% — a
                    finished course could not look finished however right the number was.
                    `auto` is the same reading the rest of the learner surface uses
                    (`CourseOverview`, `NodeList`, `CourseView`): green from 80%.
                  */}
                  <ProgressBar
                    value={Math.round((resume.progress ?? 0) * 100)}
                    variant="auto"
                    size="md"
                    className="max-w-xs flex-1"
                  />
                  <span className="shrink-0 text-xs font-medium text-text-secondary">
                    {intl.formatMessage({ id: 'home.percentComplete' }, { progress: Math.round((resume.progress ?? 0) * 100) })}
                  </span>
                </div>
              </div>
              <Button
                size="lg"
                className="shrink-0 gap-2"
                data-tour="home-start"
                /*
                  "Continuar" has to land on the node the learner left, not on the course
                  page — the label promised something the click did not do. The node is
                  chosen by `selectResumeNode`, but from the course page: picking it here
                  would mean one `GET /courses/{id}/nodes` per enrollment on the home
                  screen, for a list where at most one row is ever clicked. So the intent
                  travels in the route state and `CourseOverview` forwards it with the
                  node list it already has.
                */
                onClick={() =>
                  navigate(`/empleado/curso/${resume.course_id}`, { state: { resume: true } })
                }
              >
                <PlayIcon />
                {intl.formatMessage({ id: started ? 'home.resumeCta' : 'home.startCta' })}
              </Button>
            </div>
          </Card>
        </motion.div>
      )}

      <motion.div
        className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6"
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
      >
        <motion.div variants={staggerItem}>
          <MetricCard value={String(active.length)} label={intl.formatMessage({ id: 'home.metricActive' })} icon={<BookIcon />} />
        </motion.div>
        <motion.div variants={staggerItem}>
          <MetricCard value={String(completed.length)} label={intl.formatMessage({ id: 'home.metricCompleted' })} icon={<CheckIcon />} />
        </motion.div>
        <motion.div variants={staggerItem}>
          <MetricCard value={String(pending.length)} label={intl.formatMessage({ id: 'home.metricPending' })} icon={<ClockIcon />} />
        </motion.div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card data-tour="home-courses">
          <div className="mb-2 flex items-center justify-between gap-2">
            <CardTitle>{intl.formatMessage({ id: 'home.coursesTitle' })}</CardTitle>
            {ongoing.length > 0 && (
              <button
                type="button"
                onClick={() => navigate('/empleado/cursos')}
                className="shrink-0 text-xs font-medium text-primary hover:underline cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-1 rounded"
              >
                {intl.formatMessage({ id: 'home.viewAllCourses' })}
              </button>
            )}
          </div>
          {isLoading ? (
            <div className="space-y-1">
              <SkeletonRow />
              <SkeletonRow />
            </div>
          ) : error ? (
            <EmptyState title={intl.formatMessage({ id: 'home.loadError' })} />
          ) : ongoing.length === 0 ? (
            enrollments.length === 0 ? (
              <EmptyState
                title={intl.formatMessage({ id: 'home.coursesEmptyTitle' })}
                description={intl.formatMessage({ id: 'home.coursesEmptyDesc' })}
                action={{ label: intl.formatMessage({ id: 'home.viewAllCourses' }), onClick: () => navigate('/empleado/cursos') }}
              />
            ) : (
              <EmptyState
                title={intl.formatMessage({ id: 'home.coursesAllDoneTitle' })}
                description={intl.formatMessage({ id: 'home.coursesAllDoneDesc' })}
                action={{ label: intl.formatMessage({ id: 'home.viewAllCourses' }), onClick: () => navigate('/empleado/cursos') }}
              />
            )
          ) : (
            <motion.div initial="hidden" animate="visible" variants={staggerContainer}>
              {ongoing.map((e) => (
                <motion.div key={e.id} variants={staggerItem}>
                  <CourseItem
                    title={e.course_title}
                    badge={dynamicBadge(e)}
                    subtitle={subtitleFor(e)}
                    progress={Math.round((e.progress ?? 0) * 100)}
                    color="var(--color-primary)"
                    onClick={() => navigate(`/empleado/curso/${e.course_id}`)}
                  />
                </motion.div>
              ))}
            </motion.div>
          )}
        </Card>

        <Card data-tour="home-skillmap">
          <CardTitle className="mb-4">{intl.formatMessage({ id: 'home.skillMapTitle' })}</CardTitle>
          {skillsLoading ? (
            <div className="space-y-1">
              <SkeletonRow />
              <SkeletonRow />
            </div>
          ) : dashboardSkills.length === 0 ? (
            <EmptyState
              title={intl.formatMessage({ id: 'home.skillsEmptyTitle' })}
              description={intl.formatMessage({ id: 'home.skillsEmptyDesc' })}
              action={{ label: intl.formatMessage({ id: 'home.skillsEmptyAction' }), onClick: () => navigate('/empleado/skillmap') }}
            />
          ) : (
            <div className="space-y-3">
              {dashboardSkills.map((skill) => (
                <div key={skill.id} className="flex items-center justify-between gap-2 min-w-0">
                  <span className="text-sm text-text truncate min-w-0">{skill.skill_name}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    <SkillBars level={skill.level} />
                    <span className="text-xs text-text-secondary capitalize w-14">{skill.level}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
