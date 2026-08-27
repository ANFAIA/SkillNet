import type { LearningNode } from '../../types'

/**
 * Which node "Continuar" opens — from a recorded fact, not from a guess.
 *
 * The guess it replaces was:
 *
 * ```ts
 * nodes.find((n) => n.state === 'learning' && !n.locked) ??
 * nodes.find((n) => n.state === 'not_started' && !n.locked) ??
 * nodes.find((n) => !n.locked)
 * ```
 *
 * and it failed in the ordinary case. `state === 'learning'` is only reachable by
 * answering a **graded** item (rule 0 of §7.3), so an expository node, or a node whose
 * screens were read without answering anything, stays `not_started` — and the second
 * clause then always matched the first unlocked node. Worse, the row exists either way:
 * opening *or* prefetching a node creates `learner_node_states` with `state
 * 'not_started'`, so the state column cannot tell "never seen" from "read to the end".
 *
 * `first_seen_at` can: the server stamps it when a render is actually served to this
 * learner (`GET /nodes/{id}/render`), and never for a prefetch. Because it is a *first*
 * seen — it is audit evidence and is never moved — the newest stamp means "the deepest
 * node this learner reached", which is what "continue where you left off" wants.
 *
 * Order of preference:
 *
 * 1. the most recently seen unlocked node that is not yet mastered (ties broken by the
 *    earlier position, so a course seeded in one batch is still deterministic);
 * 2. failing that, the first unlocked node with nothing mastered in it — a learner whose
 *    every visited node is done should move forward, not reopen the last one;
 * 3. failing that, the last unlocked node: everything is mastered, so this is a review;
 * 4. `undefined` when nothing is unlocked at all, which is what disables the button.
 */
export function selectResumeNode(nodes: LearningNode[]): LearningNode | undefined {
  const open = [...nodes].filter((node) => !node.locked).sort((a, b) => a.position - b.position)
  if (open.length === 0) return undefined

  const unfinished = open.filter((node) => node.state !== 'mastered')

  let deepestSeen: LearningNode | undefined
  let deepestSeenAt = -Infinity
  for (const node of unfinished) {
    const seenAt = seenTimestamp(node)
    if (seenAt === null) continue
    if (seenAt > deepestSeenAt) {
      deepestSeenAt = seenAt
      deepestSeen = node
    }
  }
  if (deepestSeen) return deepestSeen

  return unfinished[0] ?? open[open.length - 1]
}

/**
 * `first_seen_at` as a number, or `null` when the node was never served. An unparsable
 * date counts as never seen rather than as `NaN`, which would poison the comparison.
 */
function seenTimestamp(node: LearningNode): number | null {
  if (!node.first_seen_at) return null
  const parsed = Date.parse(node.first_seen_at)
  return Number.isFinite(parsed) ? parsed : null
}

/** Whether this learner has already been served any node of the course. */
export function hasStartedCourse(nodes: LearningNode[]): boolean {
  return nodes.some((node) => seenTimestamp(node) !== null || node.mastery > 0)
}
