import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, CardTitle, CourseItem, EmptyState } from '../../components/ui'
import { courses } from '../../data/mockData'

type Tab = 'in-progress' | 'completed' | 'pending'

const tabs: { key: Tab; label: string }[] = [
  { key: 'in-progress', label: 'En progreso' },
  { key: 'completed', label: 'Completados' },
  { key: 'pending', label: 'Pendientes' },
]

export function MyCourses() {
  const [activeTab, setActiveTab] = useState<Tab>('in-progress')
  const navigate = useNavigate()

  const filtered = courses.filter((c) => c.status === activeTab)

  return (
    <div>
      <h2 className="text-xl font-semibold text-text mb-6">Mis Cursos</h2>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 border-b border-border">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === tab.key
                ? 'border-primary text-primary'
                : 'border-transparent text-text-secondary hover:text-text'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Course list */}
      <Card>
        {filtered.length === 0 ? (
          <EmptyState
            title="No hay cursos en esta categoria"
            description="Los cursos apareceran aqui cuando esten disponibles"
          />
        ) : (
          <>
            <CardTitle className="mb-2">
              {tabs.find((t) => t.key === activeTab)?.label}
            </CardTitle>
            <div>
              {filtered.map((course) => (
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
          </>
        )}
      </Card>
    </div>
  )
}
