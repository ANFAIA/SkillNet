import { Link, useLocation } from 'react-router-dom'
import { useIntl } from 'react-intl'
import { motion } from 'framer-motion'
import type { MouseEvent } from 'react'
import { Card, ProgressBar } from '../ui'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { staggerContainer, staggerItem } from '../../lib/motion'
import { useNodeMorph } from '../../stores/nodeMorph'
import { NODE_STATUS_CLASS, NODE_STATUS_LABEL_ID, nodeStatus } from './nodeStatus'
import type { LearningNode, NodeList as NodeListRead } from '../../types'

/**
 * The node map of a dynamic course — the employee's entry point to §11.3.
 *
 * What it has to make visible, because each one is a promise made elsewhere:
 *
 * - **Why the course cannot be completed yet.** `can_complete` plus `blocked_by` are
 *   rendered as a sentence, because "the course does not close in silence and does not
 *   block in silence" is the §7.4 rule.
 * - **A node mastered by the probe reads as mastered.** It never went through a lesson —
 *   and it deliberately did not count towards `nodes_completed` (§3.3) — but for the
 *   learner it is done, and the list says so.
 * - **A finished node reads as finished, however it was finished.** The badge comes from
 *   `done`, and `state` only chooses the word — "mastered" or "completed". See
 *   `nodeStatus`: the same progress the bar above is drawing has to be the progress the
 *   rows show, or the screen contradicts itself.
 */

export interface NodeListProps {
  data: NodeListRead
}


function NodeRow({
  node,
  animated,
  courseBasePath,
}: {
  node: LearningNode
  /** Off under reduced motion, and off for the parent that is not staggering. */
  animated: boolean
  /** Base path to the course view, derived from current location. */
  courseBasePath: string
}) {
  const intl = useIntl()
  const status = nodeStatus(node)

  const body = (
    <>
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-sm font-medium text-text truncate min-w-0">
          {node.title}
        </span>
        <span className={`text-xs shrink-0 ${NODE_STATUS_CLASS[status]}`}>
          {intl.formatMessage({ id: NODE_STATUS_LABEL_ID[status] })}
        </span>
      </div>
      {node.summary && (
        <p className="mt-1 text-sm text-text-secondary line-clamp-2">{node.summary}</p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-muted">
        <span className="tabular-nums">{intl.formatMessage({ id: 'nodelist.mastery' }, { pct: Math.round(node.mastery * 100) })}</span>
      </div>
    </>
  )

  const variants = animated ? staggerItem : undefined

  const setMorphOrigin = useNodeMorph((s) => s.setOrigin)

  function captureOrigin(e: MouseEvent<HTMLAnchorElement>) {
    const rect = e.currentTarget.getBoundingClientRect()
    setMorphOrigin({ top: rect.top, left: rect.left, width: rect.width, height: rect.height })
  }

  return (
    <motion.li variants={variants}>
      <Link
        to={`${courseBasePath}/nodo/${node.id}`}
        onClick={captureOrigin}
        className="block px-4 py-3 border-b border-border last:border-b-0 hover:bg-bg-subtle transition-colors"
      >
        {body}
      </Link>
    </motion.li>
  )
}

export function NodeList({ data }: NodeListProps) {
  const intl = useIntl()
  const reduceMotion = useReducedMotion()
  const { pathname } = useLocation()
  // Works for /empleado/curso/:id and /admin/probar-curso/:id
  const courseBasePath = pathname.replace(/\/$/, '')
  /**
   * The map is the last thing the learner sees before a node opens, so it is half of
   * the course → node transition. Rows resolving 60 ms apart give the list a reading
   * order; arriving all at once gives it none. Under reduced motion the props are
   * simply absent and the rows are static markup.
   */
  const listMotion = reduceMotion
    ? {}
    : { initial: 'hidden' as const, animate: 'visible' as const, variants: staggerContainer }

  const titleById = new Map(data.nodes.map((node) => [node.id, node.title]))
  const ordered = [...data.nodes].sort((a, b) => a.position - b.position)

  const blockedTitles = data.blocked_by
    .map((id) => titleById.get(id))
    .filter((title): title is string => !!title)

  if (ordered.length === 0) {
    return (
      <Card>
        <p className="text-sm text-text-muted">
          {intl.formatMessage({ id: 'nodelist.empty' })}
        </p>
      </Card>
    )
  }

  return (
    <div className="space-y-6" data-testid="node-list">
      <div>
        <ProgressBar value={data.progress_percent} variant="auto" size="lg" showLabel />
        <p className="mt-2 text-sm text-text-secondary">
          {data.can_complete
            ? intl.formatMessage({ id: 'nodelist.canComplete' })
            : blockedTitles.length > 0
              ? intl.formatMessage({ id: 'nodelist.blockedBy' }, { titles: blockedTitles.join(', ') })
              : intl.formatMessage({ id: 'nodelist.completeRequired' })}
        </p>
      </div>

      <Card className="p-0 overflow-hidden">
        <motion.ul {...listMotion}>
          {ordered.map((node) => (
            <NodeRow
              key={node.id}
              node={node}
              animated={!reduceMotion}
              courseBasePath={courseBasePath}
            />
          ))}
        </motion.ul>
      </Card>
    </div>
  )
}
