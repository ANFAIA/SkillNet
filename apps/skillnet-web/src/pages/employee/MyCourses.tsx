import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Card, CardTitle, CourseItem, EmptyState, SkeletonRow } from '../../components/ui'
import { useEnrollments } from '../../api/enrollments'
import { ApiError } from '../../api/client'
import { staggerContainer, staggerItem } from '../../lib/motion'
import type { EnrollmentRead } from '../../types'

type Tab = 'in_progress' | 'completed' | 'not_started'

const tabs: { key: Tab; label: string }[] = [
  { key: 'in_progress', label: 'En progreso' },
  { key: 'completed', label: 'Completados' },
  { key: 'not_started', label: 'Pendientes' },
]

const statusLabel: Record<string, string> = {
  not_started: 'Pendiente',
  in_progress: 'En progreso',
  completed: 'Completado',
  overdue: 'Atrasado',
}

function subtitleFor(e: EnrollmentRead): string {
  const label = statusLabel[e.status] ?? e.status
  if (e.deadline) {
    return `${label} · Fecha limite ${new Date(e.deadline).toLocaleDateString()}`
  }
  return label
}

export function MyCourses() {
  const [activeTab, setActiveTab] = useState<Tab>('in_progress')
  const navigate = useNavigate()
  const { data, isLoading, error } = useEnrollments()

  const items = data?.items ?? []
  const filtered = items.filter((e) =>
    activeTab === 'completed'
      ? e.status === 'completed'
      : activeTab === 'in_progress'
        ? e.status === 'in_progress' || e.status === 'overdue'
        : e.status === 'not_started',
  )

  return (
    <div>
      <h2 className="text-xl font-semibold text-text mb-6">Mis Cursos</h2>

      <div className="flex gap-1 mb-6 border-b border-border overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px whitespace-nowrap shrink-0 ${
              activeTab === tab.key
                ? 'border-primary text-primary'
                : 'border-transparent text-text-secondary hover:text-text'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <Card>
        {isLoading ? (
          <div className="space-y-1">
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </div>
        ) : error ? (
          <EmptyState
            title="No se pudieron cargar los cursos"
            description={
              error instanceof ApiError ? error.body.detail : 'Comprueba tu conexion e intentalo de nuevo'
            }
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No hay cursos en esta categoria"
            description="Los cursos apareceran aqui cuando esten disponibles"
          />
        ) : (
          <>
            <CardTitle className="mb-2">{tabs.find((t) => t.key === activeTab)?.label}</CardTitle>
            <motion.div key={activeTab} initial="hidden" animate="visible" variants={staggerContainer}>
              {filtered.map((e) => (
                <motion.div key={e.id} variants={staggerItem}>
                  <CourseItem
                    title={e.course_title}
                    subtitle={subtitleFor(e)}
                    progress={e.progress ?? 0}
                    color="var(--color-primary)"
                    onClick={() => navigate(`/empleado/curso/${e.course_id}`)}
                  />
                </motion.div>
              ))}
            </motion.div>
          </>
        )}
      </Card>
    </div>
  )
}
