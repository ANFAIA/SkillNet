import { motion } from 'framer-motion'
import { useIntl } from 'react-intl'
import { Card, SkeletonText } from '../ui'
import { useCourseNodes } from '../../api/nodes'
import { staggerContainer, staggerItem } from '../../lib/motion'
import type { LearningNode, NodeState } from '../../types'

const STATE_CLASS: Record<NodeState, string> = {
  not_started: 'text-text-muted',
  learning: 'text-primary',
  mastered: 'text-accent',
  needs_review: 'text-warning',
}

function StateIcon({ node }: { node: LearningNode }) {
  const common = {
    width: 16,
    height: 16,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  }

  if (node.locked) {
    return (
      <svg {...common} className="shrink-0 text-text-muted">
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
        <path d="M7 11V7a5 5 0 0 1 10 0v4" />
      </svg>
    )
  }

  if (node.state === 'mastered') {
    return (
      <svg {...common} className="shrink-0 text-accent">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
        <polyline points="22 4 12 14.01 9 11.01" />
      </svg>
    )
  }

  return (
    <svg {...common} className={`shrink-0 ${STATE_CLASS[node.state]}`}>
      <circle cx="12" cy="12" r="9" />
      {(node.state === 'learning' || node.state === 'needs_review') && (
        <circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" />
      )}
    </svg>
  )
}

export function CourseIndex({ courseId }: { courseId: string }) {
  const intl = useIntl()
  const nodesQuery = useCourseNodes(courseId)
  const nodes = nodesQuery.data?.nodes
  const stateLabel: Record<NodeState, string> = {
    not_started: intl.formatMessage({ id: 'nodelist.stateNotStarted' }),
    learning: intl.formatMessage({ id: 'nodelist.stateLearning' }),
    mastered: intl.formatMessage({ id: 'nodelist.stateMastered' }),
    needs_review: intl.formatMessage({ id: 'nodelist.stateNeedsReview' }),
  }

  return (
    <div>
      <h3 className="mb-3 text-base font-medium text-text">
        {intl.formatMessage({ id: 'preview.index' })}
      </h3>
      <Card className="overflow-hidden p-0">
        {nodesQuery.isLoading ? (
          <div className="p-4"><SkeletonText lines={4} /></div>
        ) : !nodes || nodes.length === 0 ? (
          <p className="p-4 text-sm text-text-muted">
            {intl.formatMessage({ id: 'preview.indexEmpty' })}
          </p>
        ) : (
          <motion.ul initial="hidden" animate="visible" variants={staggerContainer}>
            {[...nodes]
              .sort((a, b) => a.position - b.position)
              .map((node, index) => (
                <motion.li
                  key={node.id}
                  variants={staggerItem}
                  className="flex items-start gap-3 border-b border-border px-4 py-3 last:border-b-0"
                >
                  <StateIcon node={node} />
                  <span className="w-4 shrink-0 text-xs tabular-nums text-text-muted">{index + 1}</span>
                  <span className="min-w-0 flex-1 text-sm leading-5 text-text">{node.title}</span>
                  <span className={`mt-0.5 shrink-0 text-xs ${STATE_CLASS[node.state]}`}>
                    {stateLabel[node.state]}
                  </span>
                </motion.li>
              ))}
          </motion.ul>
        )}
      </Card>
    </div>
  )
}
