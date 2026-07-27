import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, LayoutGroup } from 'framer-motion'
import { Badge, Card, CardTitle, CourseItem, EmptyState, SkeletonRow } from '../../components/ui'
import { useEnrollments } from '../../api/enrollments'
import { ApiError } from '../../api/client'
import { staggerContainer, staggerItem, spring } from '../../lib/motion'
import type { EnrollmentRead } from '../../types'

type Tab = 'in_progress' | 'completed' | 'not_started'

const tabs: { key: Tab; label: string }[] = [
  { key: 'in_progress', label: 'En progreso' },
  { key: 'completed', label: 'Completados' },
  { key: 'not_started', label: 'Pendientes' },
]

const statusLabel: Record<string, string> = {
  not_started: 'Pendiente',
  assigned: 'Pendiente',
  in_progress: 'En progreso',
  completed: 'Completado',
  overdue: 'Atrasado',
}

/**
 * A node-based course opens as a map of nodes instead of a list of lessons, so the
 * learner is told which of the two they are about to open. `delivery_mode` comes on the
 * enrollment because an employee cannot read `GET /courses`, and it only says
 * `'dynamic'` when the schema is validated and the flag is `on` — so no extra gate is
 * needed here.
 */
function dynamicBadge(e: EnrollmentRead) {
  if (e.delivery_mode !== 'dynamic') return undefined
  return (
    <Badge variant="primary" badgeStyle="plain">
      Por nodos
    </Badge>
  )
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
        : e.status === 'not_started' || e.status === 'assigned',
  )

  return (
    <div>
      <h2 className="text-xl font-semibold text-text mb-6">Mis Cursos</h2>

      <LayoutGroup>
        <div className="flex gap-1 mb-6 border-b border-border">
          {tabs.map((tab) => {
            const active = activeTab === tab.key
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTab(tab.key)}
                className={`relative px-4 py-2 text-sm font-medium transition-colors whitespace-nowrap ${
                  active ? 'text-primary' : 'text-text-secondary hover:text-text'
                }`}
              >
                {tab.label}
                {active && (
                  <motion.span
                    layoutId="mycourses-tab-underline"
                    className="absolute left-3 right-3 -bottom-px h-0.5 rounded-full bg-primary"
                    transition={spring.stiff}
                  />
                )}
              </button>
            )
          })}
        </div>
      </LayoutGroup>

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
              error instanceof ApiError
                ? error.body?.detail ?? 'Error del servidor'
                : error instanceof Error
                  ? error.message
                  : 'Comprueba tu conexion e intentalo de nuevo'
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
                    badge={dynamicBadge(e)}
                    subtitle={subtitleFor(e)}
                    progress={Math.round((e.progress ?? 0) * 100)}
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
