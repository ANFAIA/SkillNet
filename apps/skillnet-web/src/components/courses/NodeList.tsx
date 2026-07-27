import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Card, ProgressBar } from '../ui'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { staggerContainer, staggerItem } from '../../lib/motion'
import type { LearningNode, NodeList as NodeListRead, NodeState } from '../../types'

/**
 * The node map of a dynamic course — the employee's entry point to §11.3.
 *
 * What it has to make visible, because each one is a promise made elsewhere:
 *
 * - **Why a node is locked**, not just that it is. `locked_by` names the unmet
 *   prerequisites, so the list can say "necesitas antes: X" instead of showing a padlock
 *   with no way out.
 * - **The practice queue** (§7.4). A node in `needs_review` gets its own section instead
 *   of disappearing: that is one of the three things the state was introduced to give
 *   (visibility, re-entry, the human waiver).
 * - **Why the course cannot be completed yet.** `can_complete` plus `blocked_by` are
 *   rendered as a sentence, because "the course does not close in silence and does not
 *   block in silence" is the §7.4 rule.
 * - **A node mastered by the probe reads as mastered.** It never went through a lesson —
 *   and it deliberately did not count towards `nodes_completed` (§3.3) — but for the
 *   learner it is done, and the list says so.
 */

export interface NodeListProps {
  courseId: string
  data: NodeListRead
}

const STATE_LABEL: Record<NodeState, string> = {
  not_started: 'Sin empezar',
  probing: 'En diagnostico',
  learning: 'En curso',
  mastered: 'Dominado',
  needs_review: 'Para practicar',
}

const STATE_CLASS: Record<NodeState, string> = {
  not_started: 'text-text-muted',
  probing: 'text-primary',
  learning: 'text-primary',
  mastered: 'text-accent',
  needs_review: 'text-warning',
}

const CRITICALITY_LABEL = {
  critical: 'Imprescindible',
  recommended: 'Recomendado',
  contextual: 'Contexto',
} as const

function LockIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-text-muted shrink-0"
      aria-hidden="true"
    >
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  )
}

function NodeRow({
  courseId,
  node,
  titleById,
  animated,
}: {
  courseId: string
  node: LearningNode
  titleById: Map<string, string>
  /** Off under reduced motion, and off for the parent that is not staggering. */
  animated: boolean
}) {
  const blockers = node.locked_by
    .map((id) => titleById.get(id))
    .filter((title): title is string => !!title)

  const body = (
    <>
      <div className="flex items-center gap-2 min-w-0">
        {node.locked && <LockIcon />}
        <span className="text-sm font-medium text-text truncate min-w-0">{node.title}</span>
        <span className={`text-xs shrink-0 ${STATE_CLASS[node.state]}`}>
          {STATE_LABEL[node.state]}
        </span>
      </div>
      {node.summary && (
        <p className="mt-1 text-sm text-text-secondary line-clamp-2">{node.summary}</p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-muted">
        <span>{CRITICALITY_LABEL[node.criticality]}</span>
        <span className="tabular-nums">{node.estimated_minutes} min</span>
        <span className="tabular-nums">Dominio {Math.round(node.mastery * 100)}%</span>
      </div>
      {node.locked && (
        <p className="mt-2 text-xs text-text-muted">
          {blockers.length > 0
            ? `Necesitas antes: ${blockers.join(', ')}`
            : 'Necesitas completar antes otro nodo de este curso.'}
        </p>
      )}
    </>
  )

  const variants = animated ? staggerItem : undefined

  if (node.locked) {
    return (
      <motion.li variants={variants}>
        <div className="px-4 py-3 border-b border-border last:border-b-0 opacity-60">{body}</div>
      </motion.li>
    )
  }

  return (
    <motion.li variants={variants}>
      <Link
        to={`/empleado/curso/${courseId}/nodo/${node.id}`}
        className="block px-4 py-3 border-b border-border last:border-b-0 hover:bg-bg-subtle transition-colors"
      >
        {body}
      </Link>
    </motion.li>
  )
}

export function NodeList({ courseId, data }: NodeListProps) {
  const reduceMotion = useReducedMotion()
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
  const practice = ordered.filter((node) => node.needs_practice)
  const main = ordered.filter((node) => !node.needs_practice)

  const blockedTitles = data.blocked_by
    .map((id) => titleById.get(id))
    .filter((title): title is string => !!title)

  if (ordered.length === 0) {
    return (
      <Card>
        <p className="text-sm text-text-muted">
          Este curso todavia no tiene nodos publicados.
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
            ? 'Has dominado todo lo imprescindible de este curso.'
            : blockedTitles.length > 0
              ? `Para completar el curso te falta: ${blockedTitles.join(', ')}.`
              : 'Completa los nodos imprescindibles para cerrar el curso.'}
        </p>
      </div>

      <Card className="p-0 overflow-hidden">
        <motion.ul {...listMotion}>
          {main.map((node) => (
            <NodeRow
              key={node.id}
              courseId={courseId}
              node={node}
              titleById={titleById}
              animated={!reduceMotion}
            />
          ))}
        </motion.ul>
      </Card>

      {practice.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-text mb-2">Para practicar</h3>
          <p className="text-sm text-text-secondary mb-2">
            Estos nodos siguen abiertos: puedes volver cuando quieras y, pasados 7 dias,
            repetir el diagnostico.
          </p>
          <Card className="p-0 overflow-hidden">
            <motion.ul {...listMotion}>
              {practice.map((node) => (
                <NodeRow
                  key={node.id}
                  courseId={courseId}
                  node={node}
                  titleById={titleById}
                  animated={!reduceMotion}
                />
              ))}
            </motion.ul>
          </Card>
        </div>
      )}
    </div>
  )
}
