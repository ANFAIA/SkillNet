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
 * clause then always matched the first node. Worse, the row exists either way:
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
 * 1. the most recently seen node that is not yet **done** (ties broken by the earlier
 *    position, so a course seeded in one batch is still deterministic);
 * 2. failing that, `nextNodeId` — a learner whose every visited node is finished should
 *    move forward, not reopen the last one;
 * 3. failing that, the last node: everything is done, so this is a review;
 * 4. `undefined` only for an empty course.
 *
 * "Done" is `node.done` and never `state !== 'mastered'`. `mastered` needs 0.90 mastery
 * plus three consecutive correct answers, which an expository node can never produce, so
 * asking `state` kept offering to resume a node the learner had finished.
 *
 * Rung 2 is the server's answer, not a local one: `nextNodeId` is
 * `NodeListRead.next_node_id`, "the first node not yet done, in order". Computing it here
 * as `unfinished[0]` was the same arithmetic over the same list, and the point of the
 * server publishing it is that the day "what is left" stops meaning "the next one in
 * position order" — a non-linear progression — nothing on this side has to be found and
 * rewritten. Note this whole function is still **not** `next_node_id`: rung 1 wins
 * whenever it can, because "where did I leave off" and "what is missing" are different
 * questions and they disagree the moment somebody skips ahead.
 */
export function selectResumeNode(
  nodes: LearningNode[],
  nextNodeId: string | null,
): LearningNode | undefined {
  const open = [...nodes].sort((a, b) => a.position - b.position)
  if (open.length === 0) return undefined

  const unfinished = open.filter((node) => !node.done)

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

  // A `nextNodeId` naming a node this list does not carry is treated as no answer at all,
  // the same as the `null` the server sends for a finished course: the fallback is a
  // review of the last node, never a dead link.
  const next = nextNodeId ? open.find((node) => node.id === nextNodeId) : undefined
  return next ?? open[open.length - 1]
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
