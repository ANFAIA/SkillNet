import { ShimmerSkeleton, ShimmerSkeletonText } from '../ui/ShimmerSkeleton'
import type { UiFormat } from '../../types/node-render'

/**
 * The placeholder a node wears while its lesson is being written (§9.2).
 *
 * Three properties matter, and each one is a rule from the spec rather than taste:
 *
 * 1. **It occupies the space the content will occupy.** `MIN_CONTENT_HEIGHT` is set on
 *    the wrapper, so the footer (`RenderControls`, the feedback row) does not jump up
 *    the page and then get pushed back down when the program lands. Spatial stability is
 *    the "Congelada" row of the §5.5 table: the frame must not move.
 * 2. **It takes the shape the lesson will have.** The `ui_format` event arrives long
 *    before the program does (§9.2: "permite cambiar el skeleton por uno de la forma
 *    correcta"), so an exercise does not spend ten seconds pretending to be prose.
 * 3. **No `animate-pulse`.** `ShimmerSkeleton` sweeps a translated band and drops the
 *    sweep entirely under `prefers-reduced-motion`; `ui/Skeleton.tsx` is v1 and is left
 *    alone on purpose (changing it would be a visible v1 change with the flag off).
 *
 * `blocksReady` is the count of `ui_block` events. It is progress, **not content**: those
 * components come from `parse_partial`, before the validation gate, so they are never
 * painted. Showing "3 de ~5 bloques listos" is what the learner gets out of them.
 */

export interface NodeSkeletonProps {
  /** From the `ui_format` SSE event. `null` until `decide_formato` has spoken. */
  format?: UiFormat | null
  /** The server's own sentence for the current graph step. */
  message?: string | null
  /** Completed `ui_block` events so far. */
  blocksReady?: number
}

/** Tall enough that a typical lesson does not shift the footer when it replaces this. */
const MIN_CONTENT_HEIGHT = 'min-h-[22rem]'

/** Typical block count of a lesson — root fan-out is capped at 5 (§5.2 rule 4). */
const TYPICAL_BLOCKS = 5

function ExplanationShape() {
  return (
    <div className="space-y-5">
      <ShimmerSkeleton className="h-4 w-3/4" />
      <ShimmerSkeletonText lines={4} />
      <div className="rounded-lg border border-border p-4 space-y-2.5">
        <ShimmerSkeleton className="h-3 w-1/3" />
        <ShimmerSkeletonText lines={2} />
      </div>
      <ShimmerSkeletonText lines={3} />
    </div>
  )
}

function ExerciseShape() {
  return (
    <div className="space-y-5">
      <ShimmerSkeleton className="h-4 w-2/3" />
      <ShimmerSkeletonText lines={2} />
      <div className="rounded-lg border border-border bg-bg-subtle p-4 space-y-3">
        <ShimmerSkeleton className="h-3.5 w-4/5" />
        {[0, 1, 2, 3].map((i) => (
          <ShimmerSkeleton key={i} className="h-9 w-full rounded-lg" />
        ))}
      </div>
    </div>
  )
}

function ChartShape() {
  return (
    <div className="space-y-5">
      <ShimmerSkeleton className="h-4 w-1/2" />
      <ShimmerSkeletonText lines={2} />
      <ShimmerSkeleton className="h-48 w-full rounded-lg" />
      <ShimmerSkeletonText lines={2} />
    </div>
  )
}

function shapeFor(format: UiFormat | null | undefined) {
  switch (format) {
    case 'exercise':
      return <ExerciseShape />
    case 'chart':
      return <ChartShape />
    // `explanation`, `mixed`, the reserved `simulation` and the unknown-yet `null` all
    // read as prose: it is the shape a lesson has when nobody has said otherwise.
    default:
      return <ExplanationShape />
  }
}

export function NodeSkeleton({ format = null, message = null, blocksReady = 0 }: NodeSkeletonProps) {
  const ready = Math.min(blocksReady, TYPICAL_BLOCKS)

  return (
    <div
      className={`${MIN_CONTENT_HEIGHT} space-y-5`}
      data-testid="node-skeleton"
      data-ui-format={format ?? undefined}
      // One live region for the whole wait: a screen reader hears "Escribiendo la
      // leccion..." once per step instead of on every shimmer repaint.
      aria-busy="true"
      aria-live="polite"
    >
      <p className="text-sm text-text-secondary">{message ?? 'Preparando esta leccion...'}</p>
      {blocksReady > 0 && (
        <p className="text-xs text-text-muted tabular-nums">
          {ready} {ready === 1 ? 'bloque' : 'bloques'} listo{ready === 1 ? '' : 's'}
        </p>
      )}
      {shapeFor(format)}
    </div>
  )
}
