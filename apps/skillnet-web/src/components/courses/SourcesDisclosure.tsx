import { useId, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useReducedMotion } from '../../hooks/useReducedMotion'

/**
 * Collapsed-by-default "Fuentes" disclosure for the media viewers (NotebookLM imitation).
 *
 * Provenance is available on demand, not up front: the viewer opens with the artifact
 * itself, and the citations/sources list lives behind a small, muted toggle labelled with
 * a chevron. Shared by the four viewers (`PodcastPlayer`, `VideoOverview`, `SlideDeck`,
 * `Infographic`) so the affordance — and its accessibility — stays identical across them.
 *
 * Accessible: the trigger is a real `<button>` with `aria-expanded`/`aria-controls`, the
 * region is labelled, and the whole thing is keyboard-focusable. Reduced-motion friendly:
 * the height/opacity reveal is skipped and the chevron's spin is dropped when motion is
 * silenced. Theme-aware via the existing surface tokens; no blur anywhere.
 */
export function SourcesDisclosure({
  label,
  count,
  children,
}: {
  /** The toggle label, e.g. the viewer's own "Fuentes"/"Sources" string. */
  label: string
  /** How many sources are behind the toggle, shown beside the label when > 0. */
  count: number
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(false)
  const animated = !useReducedMotion()
  const regionId = useId()

  return (
    <div className="mt-4 border-t border-border pt-3">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={regionId}
        className="group inline-flex items-center gap-1.5 rounded text-xs font-medium text-text-muted transition-colors cursor-pointer hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          className={`transition-transform motion-reduce:transition-none ${open ? 'rotate-90' : ''}`}
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>
        <span>
          {label}
          {count > 0 ? ` (${count})` : ''}
        </span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="region"
            id={regionId}
            role="region"
            aria-label={label}
            initial={animated ? { height: 0, opacity: 0 } : false}
            animate={{ height: 'auto', opacity: 1 }}
            exit={animated ? { height: 0, opacity: 0 } : { opacity: 0 }}
            transition={{ duration: animated ? 0.2 : 0 }}
            className="overflow-hidden"
          >
            <div className="pt-3">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
