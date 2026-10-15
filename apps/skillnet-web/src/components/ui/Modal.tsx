import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useIntl } from 'react-intl'
import { animate, motion, useAnimationControls, useMotionValue, useTransform } from 'framer-motion'
import { duration, ease } from '../../lib/motion'
import { useReducedMotion } from '../../hooks/useReducedMotion'

type ModalSize = 'sm' | 'md' | 'lg'

const sizeClasses: Record<ModalSize, string> = {
  sm: 'max-w-md',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
}

export interface ModalProps {
  open: boolean
  onClose: () => void
  children: React.ReactNode
  size?: ModalSize
  /** Rect of the control that opened the modal. The box grows from it and folds back into it. */
  origin?: DOMRect | null
  /** Hide the top-right close button (e.g. when the content provides its own). */
  hideClose?: boolean
}

function CloseIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

interface Box {
  left: number
  top: number
  width: number
  height: number
}

const boxOf = (r: DOMRect): Box => ({ left: r.left, top: r.top, width: r.width, height: r.height })

/** Content comes in once the box is mostly there, and leaves before it folds back (seconds). */
const CONTENT_IN_DELAY = 0.3
const CONTENT_IN = 0.22
const CONTENT_OUT = 0.16
/** How far out of focus the content starts. */
const BLUR_PX = 6

/** Corner radius of a control, and of the panel it grows into. */
const ORIGIN_RADIUS = 8
const PANEL_RADIUS = 16

/** Where the box starts: the control that opened it, or a small box in the middle of the panel. */
function startBox(origin: DOMRect | null | undefined, final: Box): Box {
  if (origin && origin.width) return boxOf(origin)
  return {
    left: final.left + final.width / 2 - 24,
    top: final.top + final.height / 2 - 24,
    width: 48,
    height: 48,
  }
}

const lerp = (from: number, to: number, t: number) => from + (to - from) * t

/**
 * Calm modal: a box that grows out of the control that opened it.
 *
 * Modeled on elastic-ui's rules (DECISIONS.md, "Motion rules"):
 *
 * - **The text never scales.** The panel is laid out at its final size from the first frame and
 *   a clip uncovers it, so nothing is stretched. The box behind it changes its real size.
 * - **It starts exactly on the control** that was pressed, and folds back into it.
 * - **Closing is faster than opening**, and the content leaves first, before the box folds.
 * - **The content fades in** once the box has nearly arrived, coming into focus rather than
 *   switching on, and leaves in a blink before the box folds.
 * - **Depth from tones, not shadows.** The box is a raised surface with a hairline round it and
 *   only a soft shadow under it. The page behind is dimmed, never blurred.
 * - With reduced motion (system or declared) it just appears and disappears.
 *
 * Portaled to `document.body` so it escapes the page-transition transform.
 */
export function Modal({ open, onClose, children, size = 'md', origin, hideClose = false }: ModalProps) {
  const intl = useIntl()
  const reduceMotion = useReducedMotion()
  const [mounted, setMounted] = useState(open)
  // Once the box has landed it follows the panel's own size (the content may grow).
  const [settled, setSettled] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)
  const closingRef = useRef(false)
  const geo = useRef<{ final: Box; start: Box } | null>(null)
  const scrim = useAnimationControls()

  // 0 = the box is the control, 1 = the box is the panel.
  const t = useMotionValue(0)
  const content = useMotionValue(0)
  // `none` once it is in focus: any filter, even blur(0px), would become the containing block of
  // what is positioned inside it.
  const contentBlur = useTransform(content, (v) => (v >= 1 ? 'none' : `blur(${(1 - v) * BLUR_PX}px)`))

  // Positions are relative to the wrapper, which is where the panel and its box live.
  const rel = (v: number) => {
    const g = geo.current
    if (!g) return null
    const left = lerp(g.start.left - g.final.left, 0, v)
    const top = lerp(g.start.top - g.final.top, 0, v)
    const width = lerp(g.start.width, g.final.width, v)
    const height = lerp(g.start.height, g.final.height, v)
    return { left, top, width, height, right: g.final.width - left - width, bottom: g.final.height - top - height }
  }
  const radius = (v: number) => lerp(ORIGIN_RADIUS, PANEL_RADIUS, v)

  const boxLeft = useTransform(t, (v) => rel(v)?.left ?? 0)
  const boxTop = useTransform(t, (v) => rel(v)?.top ?? 0)
  const boxWidth = useTransform(t, (v) => rel(v)?.width ?? 0)
  const boxHeight = useTransform(t, (v) => rel(v)?.height ?? 0)
  const boxRadius = useTransform(t, radius)
  const clipPath = useTransform(t, (v) => {
    const r = rel(v)
    // Until the box has been measured nothing shows, so there is no flash at the wrong size.
    if (!r) return 'inset(50% 50% 50% 50%)'
    if (v >= 1) return 'none'
    return `inset(${r.top}px ${r.right}px ${r.bottom}px ${r.left}px round ${radius(v)}px)`
  })

  // Mount as soon as it opens; unmount only after the close animation finishes.
  useEffect(() => {
    if (open) {
      closingRef.current = false
      setMounted(true)
    }
  }, [open])

  // Enter: measure the panel at its final size, then grow the box from the control.
  useLayoutEffect(() => {
    if (!open || !mounted) return
    const wrap = wrapRef.current
    if (!wrap) return
    const final = boxOf(wrap.getBoundingClientRect())
    geo.current = { final, start: startBox(origin, final) }

    if (reduceMotion) {
      t.set(1)
      content.set(1)
      scrim.set({ opacity: 1 })
      setSettled(true)
      return
    }

    setSettled(false)
    t.set(0.0001) // wakes the transforms now that the box is measured
    content.set(0)
    scrim.set({ opacity: 0 })
    scrim.start({ opacity: 1, transition: { duration: duration.normal, ease: 'linear' } })
    const grow = animate(t, 1, {
      duration: duration.medium,
      ease: [...ease.base],
      onComplete: () => setSettled(true),
    })
    const fade = animate(content, 1, {
      delay: CONTENT_IN_DELAY,
      duration: CONTENT_IN,
      ease: 'linear',
    })
    return () => {
      grow.stop()
      fade.stop()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, mounted])

  // Exit: the content leaves at once, then the box folds back into the control, faster than it
  // opened.
  useEffect(() => {
    if (open || !mounted || closingRef.current) return
    closingRef.current = true
    const wrap = wrapRef.current
    if (reduceMotion || !wrap) {
      setMounted(false)
      return
    }
    const final = boxOf(wrap.getBoundingClientRect())
    geo.current = { final, start: startBox(origin, final) }
    setSettled(false)
    scrim.start({ opacity: 0, transition: { duration: duration.normal, ease: 'linear' } })
    animate(content, 0, { duration: CONTENT_OUT, ease: 'linear' })
    animate(t, 0, {
      delay: CONTENT_OUT,
      duration: duration.normal,
      ease: [...ease.base],
      onComplete: () => setMounted(false),
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, mounted])

  // Escape to close + scroll lock while mounted.
  useEffect(() => {
    if (!mounted) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [mounted, onClose])

  if (!mounted) return null

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-start sm:items-center justify-center p-4 sm:p-6">
      <motion.div
        className="absolute inset-0 bg-black/40"
        initial={false}
        animate={scrim}
        onClick={onClose}
      />
      <div ref={wrapRef} className={`relative z-10 w-full ${sizeClasses[size]}`}>
        {/* The box: it changes its real size, from the control to the panel. */}
        <motion.div
          aria-hidden="true"
          className={`absolute bg-surface border border-border shadow-[0_6px_20px_-8px_rgba(0,0,0,0.12)] ${
            settled ? 'inset-0 rounded-2xl' : ''
          }`}
          style={
            settled
              ? undefined
              : { left: boxLeft, top: boxTop, width: boxWidth, height: boxHeight, borderRadius: boxRadius }
          }
        />
        {/* The panel: laid out at its final size, uncovered by the clip. */}
        <motion.div
          role="dialog"
          aria-modal="true"
          style={{ clipPath }}
          className="relative max-h-[calc(100vh-2rem)] overflow-y-auto rounded-2xl p-6"
        >
          {/* Outside the filtered wrapper, so it stays pinned to the panel's corner. */}
          {!hideClose && (
            <motion.button
              type="button"
              onClick={onClose}
              aria-label={intl.formatMessage({ id: 'modal.close' })}
              style={{ opacity: content }}
              className="absolute top-4 right-4 z-10 w-8 h-8 flex items-center justify-center rounded-full text-text-muted hover:text-text hover:bg-bg-muted transition-colors cursor-pointer"
            >
              <CloseIcon />
            </motion.button>
          )}
          <motion.div style={{ opacity: content, filter: contentBlur }}>{children}</motion.div>
        </motion.div>
      </div>
    </div>,
    document.body,
  )
}
