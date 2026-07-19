import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { motion, useAnimationControls } from 'framer-motion'
import { duration, ease } from '../../lib/motion'

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
  /** Rect of the control that opened the modal — the panel grows from / shrinks to it (FLIP). */
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

/** Delta transform that maps the panel's current box onto the origin control's box. */
function flipToOrigin(panel: DOMRect, origin: DOMRect | null | undefined) {
  const o = origin && origin.width ? origin : new DOMRect(panel.left + panel.width / 2 - 24, panel.top + panel.height / 2 - 24, 48, 48)
  const scale = Math.min(Math.max(o.width / panel.width, 0.08), 1)
  return {
    x: o.left + o.width / 2 - (panel.left + panel.width / 2),
    y: o.top + o.height / 2 - (panel.top + panel.height / 2),
    scale,
  }
}

/**
 * Clean, native-feeling modal — modeled on stepbro.site's `<window>`:
 * a borderless surface with a large radius and deep soft shadow that **grows
 * from the trigger control** (FLIP zoom-from-origin) over the signature ease,
 * while the content **blurs in** once the box has settled. Portaled to
 * `document.body` so it escapes the page-transition transform.
 */
export function Modal({ open, onClose, children, size = 'md', origin, hideClose = false }: ModalProps) {
  const [mounted, setMounted] = useState(open)
  const panelRef = useRef<HTMLDivElement>(null)
  const panel = useAnimationControls()
  const scrim = useAnimationControls()
  const closingRef = useRef(false)

  // Mount as soon as it opens; unmount only after the close animation finishes.
  useEffect(() => {
    if (open) {
      closingRef.current = false
      setMounted(true)
    }
  }, [open])

  // Enter — grow from the origin control.
  useLayoutEffect(() => {
    if (!open || !mounted) return
    const el = panelRef.current
    if (!el) return
    const from = flipToOrigin(el.getBoundingClientRect(), origin)
    panel.set({ x: from.x, y: from.y, scale: from.scale, opacity: 0 })
    panel.start({ x: 0, y: 0, scale: 1, opacity: 1, transition: { duration: duration.slow, ease: ease.base } })
    scrim.set({ opacity: 0 })
    scrim.start({ opacity: 1, transition: { duration: duration.fast } })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, mounted])

  // Exit — shrink back toward the origin control, then unmount.
  useEffect(() => {
    if (open || !mounted || closingRef.current) return
    closingRef.current = true
    const el = panelRef.current
    if (!el) {
      setMounted(false)
      return
    }
    const to = flipToOrigin(el.getBoundingClientRect(), origin)
    scrim.start({ opacity: 0, transition: { duration: duration.normal } })
    panel
      .start({ x: to.x, y: to.y, scale: to.scale, opacity: 0, transition: { duration: duration.normal, ease: ease.base } })
      .then(() => setMounted(false))
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
        className="absolute inset-0 bg-slate-900/25 backdrop-blur-md"
        initial={false}
        animate={scrim}
        onClick={onClose}
      />
      <motion.div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        initial={false}
        animate={panel}
        style={{ borderRadius: 28, transformOrigin: 'center', willChange: 'transform' }}
        className={`relative z-10 w-full ${sizeClasses[size]} max-h-[calc(100vh-2rem)] overflow-y-auto bg-bg shadow-[0_32px_80px_-24px_rgba(15,23,42,0.45)] p-6 sm:p-7`}
      >
        {!hideClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="absolute top-4 right-4 z-10 w-8 h-8 flex items-center justify-center rounded-full text-text-muted hover:text-text hover:bg-bg-muted transition-colors cursor-pointer"
          >
            <CloseIcon />
          </button>
        )}
        {/* Content blurs in once the box has grown. */}
        <motion.div
          initial={{ opacity: 0, filter: 'blur(6px)' }}
          animate={{ opacity: 1, filter: 'blur(0px)' }}
          transition={{ delay: 0.18, duration: duration.normal, ease: ease.base }}
        >
          {children}
        </motion.div>
      </motion.div>
    </div>,
    document.body,
  )
}
