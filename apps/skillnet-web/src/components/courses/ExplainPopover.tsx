/**
 * The explanation popover (§8.4).
 *
 * Positioned **by hand**. Floating UI is not in the repo and adding it for one
 * popover is not a justified dependency, so this measures the anchor, prefers below,
 * flips above when the viewport is tight, and clamps horizontally — the same job in
 * about thirty lines, re-measured on scroll and resize so it tracks the word.
 *
 * Two rules from §8.4 that are easy to get wrong:
 *
 * * The content is **not** recursively clickable. It is painted as plain text, so a
 *   click inside it cannot start another generation. Explaining the explanation adds
 *   nothing and loops cost.
 * * It does carry one action — a next step for someone who did not understand the single
 *   sentence. It used to be **"No lo entiendo"**, which navigated to the v1 chat seeded
 *   with the term and the block text; `2a750f5` made it **"Ver mas"**, which opens
 *   `ExplainModal` over the lesson instead. Same purpose, without leaving the page and
 *   without re-explaining the context to a chat that knows nothing about this node. It
 *   only appears once there *is* an explanation to expand on, so it can never open an
 *   empty panel and spend a generation on it.
 *
 * The open/close animation lives in `index.css` behind
 * `@media (prefers-reduced-motion: reduce)` — the original had no such guard.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useExplain } from '../../api/explain'
import type { ExplainSelection } from './ClickableSurface'

/** Clearance from the viewport edges. */
const PADDING = 12
/** Gap between the anchor and the popover. */
const OFFSET = 6
const WIDTH = 320

export interface ExplainPopoverProps {
  selection: ExplainSelection
  nodeId?: string | null
  language?: string
  /**
   * Overrides the `.explain-popover` z-index. `null` keeps the stylesheet's base-layer
   * value; `ExplainModal` lifts it above its own card so a word clicked inside the
   * "Ver mas" panel actually shows a bubble instead of one hidden behind the card.
   */
  zIndex?: number | null
  onClose: () => void
  /** Called when the learner clicks "Ver mas" to open the full ExplainModal. */
  onVerMas?: (selection: ExplainSelection) => void
}

interface Position {
  top: number
  left: number
  placement: 'top' | 'bottom'
}

function anchorRect(selection: ExplainSelection): DOMRect | null {
  if (selection.el) return selection.el.getBoundingClientRect()
  if (selection.range) return selection.range.getBoundingClientRect()
  return null
}

export function ExplainPopover({
  selection,
  nodeId = null,
  language,
  zIndex = null,
  onClose,
  onVerMas,
}: ExplainPopoverProps) {
  const ref = useRef<HTMLDivElement>(null)
  const returnFocusTo = useRef<HTMLElement | null>(null)
  const [position, setPosition] = useState<Position | null>(null)
  const { status, text, error, run } = useExplain()

  // One request per (term, context) pair. The server cache makes a repeat free, so
  // there is no client-side memo to keep in sync with it.
  useEffect(() => {
    run({
      term: selection.term,
      context: selection.context,
      node_id: nodeId,
      language,
    })
  }, [run, selection.term, selection.context, nodeId, language])

  const measure = useCallback(() => {
    const anchor = anchorRect(selection)
    const popover = ref.current
    if (!anchor || !popover) return

    const { width, height } = popover.getBoundingClientRect()
    const viewportHeight = window.innerHeight
    const viewportWidth = window.innerWidth

    const below = anchor.bottom + OFFSET
    const fitsBelow = below + height <= viewportHeight - PADDING
    const placement: 'top' | 'bottom' = fitsBelow ? 'bottom' : 'top'
    const top = fitsBelow
      ? below
      : Math.max(PADDING, anchor.top - height - OFFSET)

    const centered = anchor.left + anchor.width / 2 - width / 2
    const left = Math.min(
      Math.max(PADDING, centered),
      Math.max(PADDING, viewportWidth - width - PADDING),
    )

    setPosition({ top, left, placement })
  }, [selection])

  // Measure after paint so the popover's real height is known: placement depends on
  // it, and guessing produces a visible jump on the first frame.
  useLayoutEffect(() => {
    measure()
  }, [measure, text, status, error])

  useEffect(() => {
    let frame = 0
    const onChange = () => {
      if (!frame) {
        frame = requestAnimationFrame(() => {
          frame = 0
          measure()
        })
      }
    }
    window.addEventListener('scroll', onChange, true)
    window.addEventListener('resize', onChange)
    return () => {
      window.removeEventListener('scroll', onChange, true)
      window.removeEventListener('resize', onChange)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [measure])

  // Dismiss on a press outside. `mousedown`, not `click`, so clicking a different
  // word closes this popover before the surface opens the next one.
  useEffect(() => {
    const onPointerDown = (event: globalThis.MouseEvent) => {
      const target = event.target as Node | null
      if (target && ref.current?.contains(target)) return
      onClose()
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [onClose])

  // Move focus in only when the popover was opened from the keyboard, and give it
  // back on close. A mouse user keeps their focus where it was.
  useEffect(() => {
    if (!selection.viaKeyboard) return
    returnFocusTo.current = document.activeElement as HTMLElement | null
    ref.current?.focus()
    return () => returnFocusTo.current?.focus?.()
  }, [selection.viaKeyboard])

  const body =
    status === 'error' ? (
      <p className="text-sm text-danger">{error}</p>
    ) : text ? (
      // Plain text on purpose: the popover is not recursively clickable.
      <p className="text-sm text-text leading-relaxed">{text}</p>
    ) : (
      <p className="text-sm text-text-muted">Buscando una explicacion...</p>
    )

  return createPortal(
    <div
      ref={ref}
      role="dialog"
      aria-modal="false"
      aria-label={`Explicacion de ${selection.term}`}
      tabIndex={-1}
      data-no-explain
      data-placement={position?.placement ?? 'bottom'}
      className="explain-popover"
      style={{
        top: position ? `${position.top}px` : 0,
        left: position ? `${position.left}px` : 0,
        width: `${WIDTH}px`,
        visibility: position ? 'visible' : 'hidden',
        ...(zIndex == null ? {} : { zIndex }),
      }}
    >
      <p className="text-xs font-medium text-text-secondary mb-1 break-words">
        {selection.term}
      </p>
      <div aria-live="polite">{body}</div>
      {onVerMas && text && (
        <button
          type="button"
          onClick={() => { onClose(); onVerMas(selection) }}
          className="mt-2 text-xs font-medium text-primary hover:underline"
        >
          Ver mas
        </button>
      )}
    </div>,
    document.body,
  )
}
