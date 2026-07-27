/**
 * The typographic rhythm the ten kit blocks share.
 *
 * ## Why this file exists
 *
 * The blocks are generated in **varying orders and combinations**: a lesson may be a
 * Callout above a Table, or a Card wrapping a StepSequence next to a Chart, and the
 * model chooses. Each one looked composed on its own story page, and together they
 * did not — the same object (a small heading over a block of content) was written six
 * different ways: `mb-1`, `mb-1.5`, `mb-3` and `mb-4` for the gap under it, `p-3`,
 * `p-4` and `px-4 py-3` for the surface around it, and two sizes (`text-[11px]`) that
 * are not on the scale at all. Nothing was wrong; nothing lined up either.
 *
 * So the family is declared once, here, and every block imports it. Three roles, and
 * a block picks the one that matches what the text *is* — not the one that happens to
 * look right in isolation:
 *
 * - `BLOCK_TITLE` — the block names itself. A StepSequence's procedure title, a
 *   Chart's caption, a QuizItem's question stem.
 * - `BLOCK_EYEBROW` — chrome above the content that classifies it rather than titling
 *   it: a Callout's tone, a CodeBlock's language. Smaller, and it keeps its own
 *   colour, because "Atencion" and "python" are not the same kind of label.
 * - `INLINE_SURFACE` — a block that sits *inside* the lesson flow on its own panel.
 *   One radius and one padding for all of them, so a Callout next to a QuizItem next
 *   to a code slab reads as three of the same thing.
 *
 * `Card` is deliberately NOT in this list: it is the v1 primitive (`rounded-xl p-5`)
 * and it is the *outer* grouping, so it must stay a size larger than what it contains.
 * Flattening the two would delete the only hierarchy a Stack of blocks has.
 */

/** A block titling itself. `text-text`, medium — it competes with prose, not with h2. */
export const BLOCK_TITLE = 'text-sm font-medium text-text mb-3'

/**
 * A classifying label above the content. Colour is left to the caller: the tone label
 * of a Callout is secondary text, a code language is muted and monospaced, and
 * Tailwind class order in a template string does not decide which colour wins.
 */
export const BLOCK_EYEBROW = 'text-xs font-medium mb-1.5'

/** A panel inside the lesson flow. Callout, QuizItem, the code slab, the probe item. */
export const INLINE_SURFACE = 'rounded-lg border border-border p-4 min-w-0'
