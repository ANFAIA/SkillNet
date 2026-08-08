import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useIntl } from 'react-intl'
import { motion, LayoutGroup } from 'framer-motion'
import { Badge, Card, CardTitle, CourseItem, EmptyState, SkeletonRow } from '../../components/ui'
import { useEnrollments } from '../../api/enrollments'
import { ApiError } from '../../api/client'
import { staggerContainer, staggerItem, spring } from '../../lib/motion'
import type { EnrollmentRead } from '../../types'

type Tab = 'in_progress' | 'completed' | 'not_started'

export function MyCourses() {
  const intl = useIntl()
  const [activeTab, setActiveTab] = useState<Tab>('not_started')
  const navigate = useNavigate()
  const { data, isLoading, error } = useEnrollments()

  const tabs: { key: Tab; label: string }[] = [
    { key: 'not_started', label: intl.formatMessage({ id: 'mycourses.notStarted' }) },
    { key: 'in_progress', label: intl.formatMessage({ id: 'mycourses.inProgress' }) },
    { key: 'completed', label: intl.formatMessage({ id: 'mycourses.completed' }) },
  ]

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

  const items = data?.items ?? []
  const filtered = items.filter((e) => {
    const done = e.status === 'completed' || (e.progress ?? 0) >= 1.0
    if (activeTab === 'completed') return done
    if (activeTab === 'in_progress')
      return !done && (e.status === 'in_progress' || e.status === 'overdue')
    return !done && (e.status === 'not_started' || e.status === 'assigned')
  })

  return (
    <div>
      <h2 className="text-xl font-semibold text-text mb-6">{intl.formatMessage({ id: 'mycourses.title' })}</h2>

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
            title={intl.formatMessage({ id: 'mycourses.loadError' })}
            description={
              error instanceof ApiError
                ? error.body?.detail ?? intl.formatMessage({ id: 'mycourses.serverError' })
                : error instanceof Error
                  ? error.message
                  : intl.formatMessage({ id: 'mycourses.connectionError' })
            }
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            title={intl.formatMessage({ id: 'mycourses.emptyTitle' })}
            description={intl.formatMessage({ id: 'mycourses.emptyDesc' })}
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
