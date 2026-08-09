import { useState, useCallback, useId, useRef, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { duration, ease } from '../../../lib/motion'
import { INLINE_SURFACE } from './rhythm'

export interface TabsBlockProps {
  /** One rendered child per TabItem. */
  children?: ReactNode
}

export interface TabItemBlockProps {
  /** Label shown on the tab button. */
  trigger: string
  children?: ReactNode
}

/**
 * Individual tab pane. Rendered inside `TabsBlock` — never standalone.
 *
 * The component itself is a passthrough: all layout and selection logic lives in
 * `TabsBlock`, which reads the `trigger` through the React element tree. This
 * keeps each `TabItemBlock` a plain presentational wrapper that the OpenUI
 * runtime can resolve the same way it resolves any children-bearing component.
 */
export function TabItemBlock({ children }: TabItemBlockProps) {
  return <div className="flex flex-col gap-3 min-w-0">{children}</div>
}

/**
 * Tabbed container. Each direct child is expected to be a `TabItemBlock` whose
 * `trigger` prop supplies the tab label.
 *
 * Design rules followed:
 * - NO blur — opacity-only crossfade on tab switch.
 * - `text-sm`, `border-border`, `rounded-md` for interactive elements.
 * - Primary colour for the active tab indicator.
 * - Keyboard accessible: arrow keys cycle tabs, Enter/Space activate.
 */
export function TabsBlock({ children }: TabsBlockProps) {
  const instanceId = useId()
  const [activeIndex, setActiveIndex] = useState(0)
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([])

  // Flatten children into an array so we can index them.
  const items = flattenChildren(children)
  const count = items.length

  // Extract trigger labels from TabItemBlock elements.
  const labels = items.map((child, i) => {
    if (isTabItemElement(child)) {
      return typeof child.props.trigger === 'string' ? child.props.trigger : `Tab ${i + 1}`
    }
    return `Tab ${i + 1}`
  })

  const safeIndex = activeIndex < count ? activeIndex : 0

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (count === 0) return
      let next = safeIndex
      switch (e.key) {
        case 'ArrowRight':
          next = (safeIndex + 1) % count
          break
        case 'ArrowLeft':
          next = (safeIndex - 1 + count) % count
          break
        case 'Home':
          next = 0
          break
        case 'End':
          next = count - 1
          break
        default:
          return
      }
      e.preventDefault()
      setActiveIndex(next)
      tabRefs.current[next]?.focus()
    },
    [safeIndex, count],
  )

  if (count === 0) return null

  return (
    <div data-no-explain="" className={`${INLINE_SURFACE} bg-bg-subtle`}>
      {/* Tab bar */}
      <div
        role="tablist"
        aria-orientation="horizontal"
        onKeyDown={handleKeyDown}
        className="flex gap-1 border-b border-border mb-4 -mx-4 px-4"
      >
        {labels.map((label, i) => {
          const isActive = i === safeIndex
          return (
            <button
              key={i}
              ref={(el) => { tabRefs.current[i] = el }}
              role="tab"
              id={`tab-${i}`}
              aria-selected={isActive}
              aria-controls={`tabpanel-${i}`}
              tabIndex={isActive ? 0 : -1}
              type="button"
              onClick={() => setActiveIndex(i)}
              className={`relative px-3 py-2 text-sm font-medium transition-colors duration-150 rounded-t-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                isActive
                  ? 'text-primary'
                  : 'text-text-muted hover:text-text'
              }`}
            >
              {label}
              {/* Active indicator bar */}
              {isActive && (
                <motion.span
                  layoutId={`${instanceId}-tab-indicator`}
                  className="absolute inset-x-0 -bottom-px h-0.5 bg-primary rounded-full"
                  transition={{ duration: duration.fast, ease: ease.base }}
                />
              )}
            </button>
          )
        })}
      </div>

      {/* Tab panels */}
      <AnimatePresence mode="wait">
        <motion.div
          key={safeIndex}
          role="tabpanel"
          id={`tabpanel-${safeIndex}`}
          aria-labelledby={`tab-${safeIndex}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: duration.fast, ease: ease.base }}
          className="min-w-0"
        >
          {items[safeIndex]}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}

// ── Helpers ─────────────────────────────────────────────────

/** Flatten React children into an indexable array, dropping nulls. */
function flattenChildren(children: ReactNode): React.ReactElement[] {
  const result: React.ReactElement[] = []
  const arr = Array.isArray(children) ? children : [children]
  for (const child of arr) {
    if (child == null || typeof child === 'boolean') continue
    if (Array.isArray(child)) {
      result.push(...flattenChildren(child))
    } else if (typeof child === 'object' && 'props' in child) {
      result.push(child as React.ReactElement)
    }
  }
  return result
}

/** Type guard for elements rendered by TabItemBlock. */
function isTabItemElement(
  element: React.ReactElement,
): element is React.ReactElement<TabItemBlockProps> {
  const p = element.props as Record<string, unknown> | null | undefined
  return p != null && typeof p === 'object' && 'trigger' in p
}
