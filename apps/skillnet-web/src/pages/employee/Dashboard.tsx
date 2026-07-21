import { useNavigate } from 'react-router-dom'
import { Card, CardTitle, MetricCard, CourseItem, SkillBars, EmptyState, SkeletonRow } from '../../components/ui'
import { useMe } from '../../api/auth'
import { useEnrollments } from '../../api/enrollments'
import { useMySkills } from '../../api/users'

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

function TrendUpIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
      <polyline points="17 6 23 6 23 12" />
    </svg>
  )
}

export function Dashboard() {
  const navigate = useNavigate()
  const { data: me } = useMe()
  const { data: enrollmentData, isLoading, error } = useEnrollments()

  const enrollments = enrollmentData?.items ?? []
  const active = enrollments.filter((e) => e.status === 'in_progress' || e.status === 'overdue')
  const completed = enrollments.filter((e) => e.status === 'completed')
  const pending = enrollments.filter((e) => e.status === 'not_started' || e.status === 'assigned')
  const scored = completed.filter((e) => e.score !== null)
  const avgScore = scored.length
    ? Math.round(scored.reduce((acc, e) => acc + (e.score ?? 0), 0) / scored.length)
    : 0

  const { data: userSkills, isLoading: skillsLoading } = useMySkills()
  const dashboardSkills = (userSkills ?? []).slice(0, 4)
  const firstName = me?.full_name?.split(' ')[0] ?? ''

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-text">Hola{firstName ? `, ${firstName}` : ''}</h2>
        <p className="text-sm text-text-secondary mt-0.5">Lo que toca hoy</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <MetricCard value={String(active.length)} label="Cursos activos" icon={<BookIcon />} color="blue" />
        <MetricCard value={String(completed.length)} label="Completados" icon={<CheckIcon />} color="green" />
        <MetricCard value={String(pending.length)} label="Pendientes" icon={<ClockIcon />} color="orange" />
        <MetricCard value={`${avgScore}`} label="Nota media" icon={<TrendUpIcon />} color="purple" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardTitle className="mb-2">Cursos en progreso</CardTitle>
          {isLoading ? (
            <div className="space-y-1">
              <SkeletonRow />
              <SkeletonRow />
            </div>
          ) : error ? (
            <EmptyState title="No se pudieron cargar tus cursos" />
          ) : active.length === 0 ? (
            <EmptyState
              title="No tienes cursos en progreso"
              description="Empieza un curso desde Mis Cursos"
              action={{ label: 'Ver mis cursos', onClick: () => navigate('/empleado/cursos') }}
            />
          ) : (
            <div>
              {active.map((e) => (
                <CourseItem
                  key={e.id}
                  title={e.course_title}
                  subtitle={e.deadline ? `Fecha limite ${new Date(e.deadline).toLocaleDateString()}` : 'En progreso'}
                  progress={Math.round((e.progress ?? 0) * 100)}
                  color="var(--color-primary)"
                  onClick={() => navigate(`/empleado/curso/${e.course_id}`)}
                />
              ))}
            </div>
          )}
        </Card>

        <Card>
          <CardTitle className="mb-4">Mi Skill Map</CardTitle>
          {skillsLoading ? (
            <div className="space-y-1">
              <SkeletonRow />
              <SkeletonRow />
            </div>
          ) : dashboardSkills.length === 0 ? (
            <EmptyState
              title="Sin skills registradas"
              description="Completa cursos para desarrollar tus competencias"
              action={{ label: 'Ver Skill Map', onClick: () => navigate('/empleado/skills') }}
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
