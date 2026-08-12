import { useMemo, useState } from 'react'
import { useSkills } from '../../api/skills'
import { useTalentCourses, useTalentPeople } from '../../api/talent'
import { CourseProgressChart } from '../../components/talent/CourseProgressChart'
import { EnrollmentDistributionChart } from '../../components/talent/EnrollmentDistributionChart'
import { TalentFilters, type TalentStatusFilter } from '../../components/talent/TalentFilters'
import { TalentMetricIcon } from '../../components/talent/TalentMetricIcon'
import { TalentPersonDetail } from '../../components/talent/TalentPersonDetail'
import { Card, EmptyState, MetricCard, PageHeader, Skeleton, SkeletonRow } from '../../components/ui'

function formatDate(value: string | null): string {
  if (!value) return 'Sin actividad'
  return new Intl.DateTimeFormat('es', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value))
}

function MetricsSkeleton() {
  return <>{Array.from({ length: 5 }).map((_, index) => <Skeleton key={index} className="h-[108px] rounded-xl" />)}</>
}

export function Talent() {
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
      <PageHeader title="Talento" description="Consulta la formación y las habilidades registradas de cada persona." />

      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {people.isLoading ? <MetricsSkeleton /> : (
          <>
            <MetricCard value={String(people.data?.total ?? 0)} label="Personas visibles" icon={<TalentMetricIcon kind="people" />} color="blue" />
            <MetricCard value={String(metrics.assigned)} label="Matrículas" icon={<TalentMetricIcon kind="enrollments" />} color="purple" />
            <MetricCard value={String(metrics.inProgress)} label="En curso" icon={<TalentMetricIcon kind="progress" />} color="orange" />
            <MetricCard value={String(metrics.completed)} label="Completadas" icon={<TalentMetricIcon kind="completed" />} color="green" />
            <MetricCard value={String(metrics.skills)} label="Habilidades registradas" icon={<TalentMetricIcon kind="skills" />} color="blue" />
          </>
        )}
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        {people.isLoading ? <Skeleton className="h-[286px] rounded-xl" /> : <EnrollmentDistributionChart assigned={metrics.assigned} inProgress={metrics.inProgress} completed={metrics.completed} />}
        {courses.isLoading ? <Skeleton className="h-[286px] rounded-xl" /> : <CourseProgressChart courses={chartCourses} />}
      </div>

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

      <div className={`mt-5 grid gap-5 ${selectedUserId ? 'lg:grid-cols-[minmax(0,1fr)_minmax(360px,0.85fr)]' : ''}`}>
        <Card className="min-w-0 overflow-hidden">
          {people.isLoading ? (
            <div className="divide-y divide-border"><SkeletonRow /><SkeletonRow /><SkeletonRow /></div>
          ) : people.error ? (
            <EmptyState title="No se pudo cargar Talento" description="No se han perdido datos. Intenta consultar de nuevo." action={{ label: 'Reintentar', onClick: () => void people.refetch() }} />
          ) : !people.data?.items.length ? (
            <EmptyState
              title={hasFilters ? 'No hay coincidencias' : 'Todavía no hay personas'}
              description={hasFilters ? 'Prueba con otros filtros.' : 'Cuando asignes cursos, su progreso aparecerá aquí.'}
              action={hasFilters ? { label: 'Limpiar filtros', onClick: clearFilters } : undefined}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead><tr className="border-b border-border text-xs text-text-muted"><th className="pb-3 pr-4 font-medium">Persona</th><th className="px-3 pb-3 text-center font-medium">Matrículas</th><th className="px-3 pb-3 text-center font-medium">En curso</th><th className="px-3 pb-3 text-center font-medium">Completadas</th><th className="px-3 pb-3 text-center font-medium">Habilidades</th><th className="pb-3 pl-4 font-medium">Actividad</th></tr></thead>
                <tbody className="divide-y divide-border">
                  {people.data.items.map((person) => (
                    <tr key={person.user_id} className={selectedUserId === person.user_id ? 'bg-primary-subtle' : ''}>
                      <td className="min-w-48 py-3 pr-4"><button type="button" onClick={() => setSelectedUserId(person.user_id)} className="block w-full rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40" aria-label={`Ver registro de ${person.full_name}`}><span className="block text-sm font-medium text-text hover:text-primary">{person.full_name}</span><span className="block text-xs text-text-muted">{person.email}</span></button></td>
                      <td className="px-3 py-3 text-center text-sm text-text-secondary tabular-nums">{person.assigned_count}</td>
                      <td className="px-3 py-3 text-center text-sm text-text-secondary tabular-nums">{person.in_progress_count}</td>
                      <td className="px-3 py-3 text-center text-sm text-text-secondary tabular-nums">{person.completed_count}</td>
                      <td className="px-3 py-3 text-center text-sm text-text-secondary tabular-nums">{person.skill_count}</td>
                      <td className="whitespace-nowrap py-3 pl-4 text-xs text-text-muted">{formatDate(person.last_activity_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        {selectedUserId && <TalentPersonDetail userId={selectedUserId} onClose={() => setSelectedUserId(null)} />}
      </div>
    </div>
  )
}
