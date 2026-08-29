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
