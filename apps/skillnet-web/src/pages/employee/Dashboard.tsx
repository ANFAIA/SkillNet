import { useNavigate } from 'react-router-dom'
import { Card, CardTitle, MetricCard, CourseItem, SkillBars } from '../../components/ui'
import { user, courses, skills, activity } from '../../data/mockData'

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

function FlameIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z" />
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
  const inProgress = courses.filter((c) => c.status === 'in-progress')
  const dashboardSkills = skills.slice(0, 4)

  return (
    <div>
      {/* Greeting */}
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-text">Hola, {user.name}</h2>
        <p className="text-sm text-text-secondary mt-0.5">Lo que toca hoy</p>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <MetricCard
          value={String(user.activeCourses)}
          label="Cursos activos"
          icon={<BookIcon />}
          color="blue"
        />
        <MetricCard
          value={String(user.completedCourses)}
          label="Completados"
          icon={<CheckIcon />}
          color="green"
        />
        <MetricCard
          value={`${user.streak} dias`}
          label="Racha"
          icon={<FlameIcon />}
          color="orange"
        />
        <MetricCard
          value={String(user.level)}
          label="Nivel"
          icon={<TrendUpIcon />}
          color="purple"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Cursos en progreso */}
        <Card>
          <CardTitle className="mb-2">Cursos en progreso</CardTitle>
          <div>
            {inProgress.map((course) => (
              <CourseItem
                key={course.id}
                title={course.title}
                subtitle={course.subtitle}
                progress={course.progress}
                color={course.color}
                onClick={() => navigate(`/empleado/curso/${course.id}`)}
              />
            ))}
          </div>
        </Card>

        {/* Skill Map preview */}
        <Card>
          <CardTitle className="mb-4">Mi Skill Map</CardTitle>
          <div className="space-y-3">
            {dashboardSkills.map((skill) => (
              <div key={skill.name} className="flex items-center justify-between">
                <span className="text-sm text-text">{skill.name}</span>
                <div className="flex items-center gap-2">
                  <SkillBars level={skill.level} />
                  <span className="text-xs text-text-secondary capitalize w-14">{skill.level}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Actividad reciente */}
        <Card className="lg:col-span-2">
          <CardTitle className="mb-3">Actividad reciente</CardTitle>
          <div className="space-y-0">
            {activity.map((item) => (
              <div key={item.id} className="flex items-center justify-between py-2.5 border-b border-border last:border-b-0">
                <span className="text-sm text-text">{item.text}</span>
                <span className="text-xs text-text-muted shrink-0 ml-4">{item.time}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}
