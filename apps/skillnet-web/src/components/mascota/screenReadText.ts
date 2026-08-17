/**
 * Per-screen narration text for the mascot.
 *
 * A dynamic episode is one program whose root `Stack` has one child PER SCREEN
 * (see `blocks/StackBlock.tsx` → `EpisodeStack`: `items[screen]`). The mascot lives
 * outside that render tree, in `NodeView`, so to speak the CURRENT screen it has to
 * pull the screen's own text out of the same program the renderer paints — indexing
 * the root's children exactly as `EpisodeStack` does.
 *
 * We parse with the very library the runtime uses (`skillnetLibrarySchema`), so the
 * child order here is the child order on screen. Parsing is pure and the result is
 * memoised per program string, so paging between screens never re-parses.
 *
 * The text picked is what the screen would want read aloud, in this order:
 *   1. an `AudioExplanation` — its `text` prop is *defined* as "el texto que se leera
 *      en voz alta", so when the author put one on the screen it wins outright;
 *   2. otherwise the first prose block (`TextContent` / `Callout` / `Markdown`);
 *   3. otherwise the first titled/interactive block (a `Card`, `QuizItem`, …).
 *
 * `null` when there is no program, no root yet (still streaming), or the screen holds
 * nothing readable — the caller then falls back to the node summary/title.
 */

import { createParser, type ElementNode } from '@openuidev/react-lang'
import { skillnetLibrarySchema } from '../courses/kit/library'

// One pure parser instance serves every program (same pattern as the gate's).
const parser = createParser(skillnetLibrarySchema, 'Stack')

/** Prose blocks: their text is the thing to read. First one on the screen wins. */
const PROSE_TEXT: Record<string, string> = {
  TextContent: 'text',
  Callout: 'text',
  Markdown: 'content',
}

/** Titled / interactive blocks: a fallback when the screen has no prose. */
const TITLE_TEXT: Record<string, string> = {
  Card: 'title',
  StepSequence: 'title',
  BeforeAfter: 'title',
  Chart: 'title',
  QuizItem: 'question',
  DragOrder: 'instruction',
  Flashcard: 'front',
}

function isElementNode(value: unknown): value is ElementNode {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { type?: unknown }).type === 'element' &&
    typeof (value as { typeName?: unknown }).typeName === 'string'
  )
}

function propString(node: ElementNode, prop: string): string | null {
  const raw = node.props?.[prop]
  if (typeof raw !== 'string') return null
  const trimmed = raw.trim()
  return trimmed.length > 0 ? trimmed : null
}

/**
 * Walk a screen subtree in document order, gathering the best read text. An
 * `AudioExplanation` short-circuits; otherwise we remember the first prose block and,
 * failing that, the first titled block, and let prose beat a title.
 */
function readableFromScreen(screen: ElementNode): string | null {
  let prose: string | null = null
  let title: string | null = null
  const seen = new WeakSet<object>()

  const visit = (value: unknown): string | null => {
    if (Array.isArray(value)) {
      for (const entry of value) {
        const hit = visit(entry)
        if (hit) return hit // an AudioExplanation bubbled up: done
      }
      return null
    }
    if (typeof value !== 'object' || value === null) return null
    if (seen.has(value)) return null
    seen.add(value)

    if (isElementNode(value)) {
      if (value.typeName === 'AudioExplanation') {
        const spoken = propString(value, 'text')
        if (spoken) return spoken
      }
      if (prose === null && value.typeName in PROSE_TEXT) {
        prose = propString(value, PROSE_TEXT[value.typeName])
      }
      if (title === null && value.typeName in TITLE_TEXT) {
        title = propString(value, TITLE_TEXT[value.typeName])
      }
      return visit(value.props)
    }
    for (const entry of Object.values(value as Record<string, unknown>)) {
      const hit = visit(entry)
      if (hit) return hit
    }
    return null
  }

  return visit(screen) ?? prose ?? title
}

const cache = new Map<string, (ElementNode | null)[]>()

/** Root `Stack` children — the screens — parsed once per program string. */
function screensOf(program: string): (ElementNode | null)[] {
  const cached = cache.get(program)
  if (cached) return cached

  let screens: (ElementNode | null)[] = []
  try {
    const root = parser.parse(program).root
    const children = root?.props?.children
    if (Array.isArray(children)) {
      screens = children.filter((c): c is ElementNode | null => c === null || isElementNode(c))
    }
  } catch {
    screens = []
  }
  cache.set(program, screens)
  return screens
}

/**
 * The read/speak text for `screen` of a paginated episode `program`, or `null` when
 * the program has no such screen or nothing readable on it.
 */
export function screenReadText(program: string | null | undefined, screen: number): string | null {
  if (!program || program.trim() === '') return null
  const screens = screensOf(program)
  if (screens.length === 0) return null
  const idx = Math.min(Math.max(screen, 0), screens.length - 1)
  const node = screens[idx]
  return node ? readableFromScreen(node) : null
}
