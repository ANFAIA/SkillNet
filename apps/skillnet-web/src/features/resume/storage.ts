/**
 * Where inside a node the learner was, remembered across reloads.
 *
 * The server knows *which* node somebody reached (`LearningNode.first_seen_at`, stamped
 * when a render is served) but nothing finer: the screen index of a multi-screen episode
 * and the "Empezar" gate live entirely in `NodeView`'s `useState`, so leaving the course
 * always dropped the learner back on the intro screen of whatever node reopened.
 *
 * **This is deliberately per device.** A `localStorage` blob is not the learner's
 * progress, it is a bookmark; the same person on their phone starts the node at its
 * intro, which is acceptable and honest. The server-side version — a column on
 * `learner_node_states` — needs an Alembic migration, and this batch does not add one.
 * Keeping every read and write behind these four helpers is what makes that a one-file
 * swap later, the same bet `features/onboarding/storage.ts` makes for the tour.
 *
 * Layout: one key holding `{ "<courseId>:<nodeId>": { s, e, t } }`. One key rather than
 * one per node because it is the only way to bound what accumulates — see `MAX_ENTRIES`.
 * Every access is wrapped: storage can be absent (SSR, tests), disabled (private mode),
 * full (quota) or corrupt, and none of those may break a lesson.
 */

/** The single `localStorage` key. Exposed for tests. */
export const NODE_POSITION_STORAGE_KEY = 'skillnet-node-position'

/**
 * Retention policy: the 40 most recently written positions survive, older ones are
 * dropped on the next write. A bookmark for a node nobody has opened in 40 nodes is
 * worthless, and an unbounded map here would grow for the lifetime of the browser
 * profile — one entry per node of every course the person ever touched.
 */
const MAX_ENTRIES = 40

/** Where the learner was inside one node. */
export interface NodePosition {
  /** Screen index of the episode pager. */
  screen: number
  /** `true` once "Empezar" was pressed, so the intro gate is not shown again. */
  entered: boolean
}

/** Stored shape — short names because this string is rewritten on every screen turn. */
interface StoredEntry {
  s: number
  e: boolean
  /** `Date.now()` of the last write; the only input to the eviction above. */
  t: number
}

type Store = Record<string, StoredEntry>

function entryKey(courseId: string, nodeId: string): string {
  return `${courseId}:${nodeId}`
}

function readStore(): Store {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(NODE_POSITION_STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return parsed as Store
  } catch {
    // Corrupt or unavailable storage reads as "no bookmark", never as an error.
    return {}
  }
}

function writeStore(store: Store): void {
  if (typeof window === 'undefined') return
  try {
    const keys = Object.keys(store)
    if (keys.length > MAX_ENTRIES) {
      const keep = keys
        .sort((a, b) => (store[b]?.t ?? 0) - (store[a]?.t ?? 0))
        .slice(0, MAX_ENTRIES)
      const trimmed: Store = {}
      for (const key of keep) trimmed[key] = store[key]
      store = trimmed
    }
    window.localStorage.setItem(NODE_POSITION_STORAGE_KEY, JSON.stringify(store))
  } catch {
    /* quota exceeded / storage disabled — losing a bookmark is not a failure */
  }
}

/** The saved position for one node, or `null` when there is none. */
export function readNodePosition(
  courseId: string | undefined,
  nodeId: string | undefined,
): NodePosition | null {
  if (!courseId || !nodeId) return null
  const entry = readStore()[entryKey(courseId, nodeId)]
  if (!entry || typeof entry !== 'object') return null
  const screen = Number(entry.s)
  return {
    // A hand-edited or half-written entry must not produce `NaN` as a screen index.
    screen: Number.isFinite(screen) && screen > 0 ? Math.floor(screen) : 0,
    entered: Boolean(entry.e),
  }
}

/** Remember (part of) a position. Merges over whatever is already stored. */
export function writeNodePosition(
  courseId: string | undefined,
  nodeId: string | undefined,
  patch: Partial<NodePosition>,
): void {
  if (!courseId || !nodeId) return
  const store = readStore()
  const current = readNodePosition(courseId, nodeId) ?? { screen: 0, entered: false }
  const next: NodePosition = { ...current, ...patch }
  store[entryKey(courseId, nodeId)] = { s: next.screen, e: next.entered, t: Date.now() }
  writeStore(store)
}

/** Forget one node — called when the learner leaves it finished. */
export function clearNodePosition(
  courseId: string | undefined,
  nodeId: string | undefined,
): void {
  if (!courseId || !nodeId) return
  const store = readStore()
  const key = entryKey(courseId, nodeId)
  if (!(key in store)) return
  delete store[key]
  writeStore(store)
}

/** Forget a whole course — called when the learner finishes it. */
export function clearCoursePositions(courseId: string | undefined): void {
  if (!courseId) return
  const store = readStore()
  const prefix = `${courseId}:`
  let removed = false
  for (const key of Object.keys(store)) {
    if (key.startsWith(prefix)) {
      delete store[key]
      removed = true
    }
  }
  if (removed) writeStore(store)
}
