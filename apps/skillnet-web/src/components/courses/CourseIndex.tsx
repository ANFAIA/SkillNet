import { motion } from 'framer-motion'
import { useIntl } from 'react-intl'
import { Card, SkeletonText } from '../ui'
import { useCourseNodes } from '../../api/nodes'
import { staggerContainer, staggerItem } from '../../lib/motion'
import { NODE_STATUS_CLASS, NODE_STATUS_LABEL_ID, nodeStatus } from './nodeStatus'
import type { LearningNode } from '../../types'

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

  // The tick is `done`, not `mastered` — see `nodeStatus`. Asking `state` here drew the
  // empty "not started" circle next to a finished expository node.
  if (node.done) {
    return (
      <svg {...common} className="shrink-0 text-accent">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
        <polyline points="22 4 12 14.01 9 11.01" />
      </svg>
    )
  }

  return (
    <svg {...common} className={`shrink-0 ${NODE_STATUS_CLASS[nodeStatus(node)]}`}>
      <circle cx="12" cy="12" r="9" />
      {node.state === 'learning' && (
        <circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" />
      )}
    </svg>
  )
}

export function CourseIndex({ courseId }: { courseId: string }) {
  const intl = useIntl()
  const nodesQuery = useCourseNodes(courseId)
  const nodes = nodesQuery.data?.nodes

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
              .map((node, index) => {
                const status = nodeStatus(node)
                return (
                  <motion.li
                    key={node.id}
                    variants={staggerItem}
                    className="flex items-start gap-3 border-b border-border px-4 py-3 last:border-b-0"
                  >
                    <StateIcon node={node} />
                    <span className="w-4 shrink-0 text-xs tabular-nums text-text-muted">{index + 1}</span>
                    <span className="min-w-0 flex-1 text-sm leading-5 text-text">{node.title}</span>
                    <span className={`mt-0.5 shrink-0 text-xs ${NODE_STATUS_CLASS[status]}`}>
                      {intl.formatMessage({ id: NODE_STATUS_LABEL_ID[status] })}
                    </span>
                  </motion.li>
                )
              })}
          </motion.ul>
        )}
      </Card>
    </div>
  )
}
