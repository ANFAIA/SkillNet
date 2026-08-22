import { lazy, Suspense, useMemo, useState } from 'react'
import { useIntl, type IntlShape } from 'react-intl'
import { useSkills } from '../../api/skills'
import { useTalentCourses, useTalentPeople } from '../../api/talent'
import { TalentFilters, type TalentStatusFilter } from '../../components/talent/TalentFilters'
import { TalentPersonDetail } from '../../components/talent/TalentPersonDetail'
import { TalentSummary } from '../../components/talent/TalentSummary'
import { Card, EmptyState, PageHeader, Skeleton, SkeletonRow } from '../../components/ui'

const EnrollmentDistributionChart = lazy(() => import('../../components/talent/EnrollmentDistributionChart').then((module) => ({ default: module.EnrollmentDistributionChart })))
const CourseProgressChart = lazy(() => import('../../components/talent/CourseProgressChart').then((module) => ({ default: module.CourseProgressChart })))

function formatDate(value: string | null, intl: IntlShape): string {
  if (!value) return intl.formatMessage({ id: 'talent.noActivity' })
  return new Intl.DateTimeFormat(intl.locale, { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value))
}

export function Talent() {
  const intl = useIntl()
  const [search, setSearch] = useState('')
  const [courseId, setCourseId] = useState('')
  const [skillId, setSkillId] = useState('')
  const [status, setStatus] = useState<TalentStatusFilter>('')
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const filters = useMemo(() => ({
    search,
    course_id: courseId || undefined,
    skill_id: skillId || undefined,
    status: status || undefined,
  }), [courseId, search, skillId, status])
  const people = useTalentPeople(filters)
  const skills = useSkills()
  const courses = useTalentCourses()

  const metrics = useMemo(() => (people.data?.items ?? []).reduce((total, person) => ({
    assigned: total.assigned + person.assigned_count,
    inProgress: total.inProgress + person.in_progress_count,
    completed: total.completed + person.completed_count,
    skills: total.skills + person.skill_count,
  }), { assigned: 0, inProgress: 0, completed: 0, skills: 0 }), [people.data?.items])

  const chartCourses = courseId
    ? (courses.data ?? []).filter((course) => course.course_id === courseId)
    : (courses.data ?? [])
  const hasFilters = Boolean(search.trim() || courseId || skillId || status)

  function clearFilters() {
    setSearch('')
    setCourseId('')
    setSkillId('')
    setStatus('')
  }

  return (
    <div>
      <PageHeader title={intl.formatMessage({ id: 'talent.title' })} description={intl.formatMessage({ id: 'talent.description' })} />

      <TalentFilters
        search={search}
        courseId={courseId}
        skillId={skillId}
        status={status}
        courses={courses.data ?? []}
        skills={skills.data?.items ?? []}
        onSearchChange={setSearch}
        onCourseChange={setCourseId}
        onSkillChange={setSkillId}
        onStatusChange={setStatus}
        onClear={clearFilters}
      />

      {people.isLoading ? (
        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, index) => <Skeleton key={index} className="h-[108px] rounded-lg" />)}
        </div>
      ) : (
        <TalentSummary
          people={people.data?.total ?? 0}
          assigned={metrics.assigned}
          inProgress={metrics.inProgress}
          completed={metrics.completed}
          skills={metrics.skills}
        />
      )}

      <div className={`mt-5 grid gap-5 ${selectedUserId ? 'lg:grid-cols-[minmax(0,1fr)_minmax(360px,0.85fr)]' : ''}`}>
        <Card className="min-w-0 overflow-hidden rounded-lg">
          {people.isLoading ? (
            <div className="divide-y divide-border"><SkeletonRow /><SkeletonRow /><SkeletonRow /></div>
          ) : people.error ? (
            <EmptyState title={intl.formatMessage({ id: 'talent.loadErrorTitle' })} description={intl.formatMessage({ id: 'talent.loadErrorDescription' })} action={{ label: intl.formatMessage({ id: 'talent.retry' }), onClick: () => void people.refetch() }} />
          ) : !people.data?.items.length ? (
            <EmptyState
              title={intl.formatMessage({ id: hasFilters ? 'talent.noMatchesTitle' : 'talent.noPeopleTitle' })}
              description={intl.formatMessage({ id: hasFilters ? 'talent.noMatchesDescription' : 'talent.noPeopleDescription' })}
              action={hasFilters ? { label: intl.formatMessage({ id: 'talent.clearFilters' }), onClick: clearFilters } : undefined}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead><tr className="border-b border-border text-xs text-text-muted"><th className="pb-3 pr-4 font-medium">{intl.formatMessage({ id: 'talent.table.person' })}</th><th className="px-3 pb-3 text-center font-medium">{intl.formatMessage({ id: 'talent.table.enrollments' })}</th><th className="px-3 pb-3 text-center font-medium">{intl.formatMessage({ id: 'talent.table.inProgress' })}</th><th className="px-3 pb-3 text-center font-medium">{intl.formatMessage({ id: 'talent.table.completed' })}</th><th className="px-3 pb-3 text-center font-medium">{intl.formatMessage({ id: 'talent.table.skills' })}</th><th className="pb-3 pl-4 font-medium">{intl.formatMessage({ id: 'talent.table.activity' })}</th></tr></thead>
                <tbody className="divide-y divide-border">
                  {people.data.items.map((person) => (
                    <tr key={person.user_id} className={selectedUserId === person.user_id ? 'bg-primary-subtle' : ''}>
                      <td className="min-w-48 py-3 pr-4"><button type="button" onClick={() => setSelectedUserId(person.user_id)} className="block w-full rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40" aria-label={intl.formatMessage({ id: 'talent.viewRecord' }, { name: person.full_name })}><span className="block text-sm font-medium text-text hover:text-primary">{person.full_name}</span><span className="block text-xs text-text-muted">{person.email}</span></button></td>
                      <td className="px-3 py-3 text-center text-sm text-text-secondary tabular-nums">{person.assigned_count}</td>
                      <td className="px-3 py-3 text-center text-sm text-text-secondary tabular-nums">{person.in_progress_count}</td>
                      <td className="px-3 py-3 text-center text-sm text-text-secondary tabular-nums">{person.completed_count}</td>
                      <td className="px-3 py-3 text-center text-sm text-text-secondary tabular-nums">{person.skill_count}</td>
                      <td className="whitespace-nowrap py-3 pl-4 text-xs text-text-muted">{formatDate(person.last_activity_at, intl)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        {selectedUserId && <TalentPersonDetail userId={selectedUserId} onClose={() => setSelectedUserId(null)} />}
      </div>

      <section className="mt-8 border-t border-border pt-6" aria-labelledby="talent-overview-title">
        <h2 id="talent-overview-title" className="text-lg font-semibold text-text">{intl.formatMessage({ id: 'talent.overviewTitle' })}</h2>
        <p className="mt-1 text-sm text-text-muted">{intl.formatMessage({ id: 'talent.overviewDescription' })}</p>
        <Suspense fallback={<div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2"><Skeleton className="h-[286px] rounded-lg" /><Skeleton className="h-[286px] rounded-lg" /></div>}>
          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
            {people.isLoading ? <Skeleton className="h-[286px] rounded-lg" /> : <EnrollmentDistributionChart assigned={metrics.assigned} inProgress={metrics.inProgress} completed={metrics.completed} />}
            {courses.isLoading ? <Skeleton className="h-[286px] rounded-lg" /> : <CourseProgressChart courses={chartCourses} />}
          </div>
        </Suspense>
      </section>
    </div>
  )
}
