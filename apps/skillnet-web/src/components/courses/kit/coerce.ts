/**
 * Runtime coercion for kit props.
 *
 * Why this exists even though every prop has a zod schema: OpenUI's parser never
 * evaluates zod. It maps positional arguments onto named props by *arity* and
 * hands the values through untouched — measured, `Stack([a], "enorme")` and
 * `TextContent(42, "titulo")` both parse with `meta.errors == []`. So the values
 * reaching a component renderer are `unknown` in practice, whatever the schema
 * says.
 *
 * Every reader below degrades to a safe default instead of throwing. That is the
 * same contract the previous hand-written renderer offered (a mismatched deploy —
 * newer backend, older bundle — must lose a block, never the page), kept because
 * the runtime's per-element error boundary reverts to the *last good* subtree,
 * which during streaming means silently showing stale content.
 */

/** Reads a numeric prop, tolerating strings and nulls the parser lets through. */
export function readNumber(value: unknown, fallback: number): number {
  const num = Number(value)
  return Number.isFinite(num) ? num : fallback
}

/** Reads a string prop, tolerating the numbers and nulls the parser lets through. */
export function readString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

/** Reads a closed-enum prop, falling back when the value is not a member. */
export function readEnum<T extends string>(
  value: unknown,
  allowed: readonly T[],
  fallback: T,
): T {
  return typeof value === 'string' && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : fallback
}

export function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((entry) => (typeof entry === 'string' ? entry : String(entry ?? '')))
}

export function readStringMatrix(value: unknown): string[][] {
  if (!Array.isArray(value)) return []
  return value.map((row) => (Array.isArray(row) ? readStringArray(row) : []))
}

export function readNumberArray(value: unknown): number[] {
  if (!Array.isArray(value)) return []
  return value.map((entry) => {
    const num = Number(entry)
    return Number.isFinite(num) ? num : 0
  })
}

/**
 * Children as the runtime delivers them: an array of resolved `ElementNode`s.
 * A non-array (a string where a reference array belongs) becomes empty rather
 * than being rendered as raw text — `renderNode('foo')` would print `foo`.
 */
export function readChildren(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

import type { Hotspot } from '../blocks/HotspotImageBlock'

function clampPct(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, value))
}

/** Parses hotspot matrix: each row is [x, y, label, detail] with x,y as number strings. */
export function readHotspots(value: unknown): Hotspot[] {
  if (!Array.isArray(value)) return []
  return value
    .filter((entry) => Array.isArray(entry) && entry.length >= 4)
    .map((entry) => ({
      x: clampPct(Number(entry[0])),
      y: clampPct(Number(entry[1])),
      label: typeof entry[2] === 'string' ? entry[2] : String(entry[2] ?? ''),
      detail: typeof entry[3] === 'string' ? entry[3] : String(entry[3] ?? ''),
    }))
}

/** Parses step matrix: each row is [statement, explanation]. */
export function readStepPairs(value: unknown): Array<{ statement: string; explanation: string }> {
  if (!Array.isArray(value)) return []
  return value
    .filter((entry) => Array.isArray(entry) && entry.length >= 2)
    .map((entry) => ({
      statement: typeof entry[0] === 'string' ? entry[0] : String(entry[0] ?? ''),
      explanation: typeof entry[1] === 'string' ? entry[1] : String(entry[1] ?? ''),
    }))
}

/** Parses diagram step matrix: each row is [label, svgFragment, explanation]. */
export function readDiagramSteps(value: unknown): Array<{ label: string; svgFragment: string; explanation: string }> {
  if (!Array.isArray(value)) return []
  return value
    .filter((entry) => Array.isArray(entry) && entry.length >= 3)
    .map((entry) => ({
      label: typeof entry[0] === 'string' ? entry[0] : String(entry[0] ?? ''),
      svgFragment: typeof entry[1] === 'string' ? entry[1] : String(entry[1] ?? ''),
      explanation: typeof entry[2] === 'string' ? entry[2] : String(entry[2] ?? ''),
    }))
}
