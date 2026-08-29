import type { LearningNode, NodeState } from '../../types'

/**
 * How one node reads in a list: whether it is finished, and — only then — how it got
 * there.
 *
 * The two questions are separate on purpose and were being answered by the same column.
 * `state` cannot say "finished": `learning` and `mastered` are both reachable only by
 * answering a **graded** item (§7.3), so an expository node, or any node read to the end
 * without answering anything, stays `not_started` for ever. A list that branched on
 * `state` therefore drew the hollow "not started" circle next to a node the learner had
 * completed, while the course progress bar — which counts `done` — said 100%. That
 * disagreement is exactly what `done` was added to end.
 *
 * So: `done` answers "is it finished?", and `state` is kept for the *other* question,
 * "how?" — demonstrated (`mastered`) or simply worked through (`completed`).
 */
export type NodeStatus = NodeState | 'completed'

export function nodeStatus(node: LearningNode): NodeStatus {
  if (!node.done) return node.state
  return node.state === 'mastered' ? 'mastered' : 'completed'
}

export const NODE_STATUS_CLASS: Record<NodeStatus, string> = {
  not_started: 'text-text-muted',
  learning: 'text-primary',
  completed: 'text-accent',
  mastered: 'text-accent',
}

export const NODE_STATUS_LABEL_ID: Record<NodeStatus, string> = {
  not_started: 'nodelist.stateNotStarted',
  learning: 'nodelist.stateLearning',
  completed: 'nodelist.stateCompleted',
  mastered: 'nodelist.stateMastered',
}

/**
 * May this learner open the node — the other half of a row, and a different question
 * from `nodeStatus`.
 *
 * `available` is the server's answer, never a rule reproduced here: with
 * `navigation_mode: 'free'` every node comes back available, and with `'sequential'`
 * the server closes the ones whose predecessor is not `done`. A client that decided this
 * for itself would be the second source of truth that the padlocks removed on 2026-08-28
 * were — they asked `state !== 'mastered'`, which an expository node can never satisfy,
 * so they never opened again.
 *
 * A payload without the field reads as available. That is the legacy answer and the safe
 * one: an old response can hide a lesson by omission, never by mistake.
 */
export function nodeIsAvailable(node: LearningNode): boolean {
  return node.available !== false
}

/**
 * The one sentence every list prints for a node that cannot be opened yet.
 *
 * Shared so the node map and the course index say the same thing: two screens explaining
 * the same rule in two different words is how a learner concludes they are two rules.
 */
export const NODE_UNAVAILABLE_LABEL_ID = 'nodelist.unavailable'
