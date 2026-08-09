import { useState, useCallback, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { duration, ease } from '../../../lib/motion'
import { INLINE_SURFACE } from './rhythm'

export interface AccordionBlockProps {
  /** One rendered child per AccordionItem. */
  children?: ReactNode
}

export interface AccordionItemBlockProps {
  /** Section title shown on the clickable header. */
  trigger: string
  children?: ReactNode
}

/**
 * Individual accordion pane. Rendered inside `AccordionBlock` — never standalone.
 *
 * A presentational wrapper: the open/close logic
 * lives in `AccordionBlock`, which reads the `trigger` from the React element.
 */
export function AccordionItemBlock({ children }: AccordionItemBlockProps) {
  return <div className="flex flex-col gap-3 min-w-0">{children}</div>
}

/**
 * Collapsible sections for progressive disclosure. Single-open mode: opening
 * one section closes all others. The first section starts open.
 *
 * Design rules followed:
 * - NO blur — height + opacity animation only.
 * - Chevron icon rotates on open.
 * - Subtle borders, `rounded-lg` for the container.
 * - Keyboard accessible: Enter/Space toggle, arrow keys navigate headers.
 */
export function AccordionBlock({ children }: AccordionBlockProps) {
  const items = flattenChildren(children)
  const count = items.length

  // First item open by default.
  const [openIndex, setOpenIndex] = useState<number | null>(count > 0 ? 0 : null)

  const toggle = useCallback(
    (index: number) => {
      setOpenIndex((prev) => (prev === index ? null : index))
    },
    [],
  )

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
      let next = index
      switch (e.key) {
        case 'ArrowDown':
          next = (index + 1) % count
          break
        case 'ArrowUp':
          next = (index - 1 + count) % count
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
      // Focus the next header button.
      const container = e.currentTarget.closest('[data-accordion]')
      const buttons = container?.querySelectorAll<HTMLButtonElement>('[data-accordion-trigger]')
      buttons?.[next]?.focus()
    },
    [count],
  )

  if (count === 0) return null

  // Extract trigger labels from AccordionItemBlock elements.
  const labels = items.map((child, i) => {
    if (isAccordionItemElement(child)) {
      return typeof child.props.trigger === 'string' ? child.props.trigger : `Section ${i + 1}`
    }
    return `Section ${i + 1}`
  })

  return (
    <div data-no-explain="" data-accordion="" className={`${INLINE_SURFACE} bg-bg-subtle p-0 overflow-hidden`}>
      {items.map((item, i) => {
        const isOpen = openIndex === i
        const isLast = i === count - 1
        return (
          <div
            key={i}
            className={isLast ? '' : 'border-b border-border'}
          >
            {/* Header */}
            <button
              type="button"
              data-accordion-trigger=""
              aria-expanded={isOpen}
              aria-controls={`accordion-panel-${i}`}
              id={`accordion-header-${i}`}
              onClick={() => toggle(i)}
              onKeyDown={(e) => handleKeyDown(e, i)}
              className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm font-medium text-text hover:bg-bg-muted/50 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary"
            >
              <span className="min-w-0">{labels[i]}</span>
              <motion.span
                aria-hidden="true"
                animate={{ rotate: isOpen ? 180 : 0 }}
                transition={{ duration: duration.fast, ease: ease.base }}
                className="shrink-0 text-text-muted"
              >
                <ChevronIcon />
              </motion.span>
            </button>

            {/* Content */}
            <AnimatePresence initial={false}>
              {isOpen && (
                <motion.div
                  id={`accordion-panel-${i}`}
                  role="region"
                  aria-labelledby={`accordion-header-${i}`}
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: duration.normal, ease: ease.base }}
                  className="overflow-hidden"
                >
                  <div className="px-4 pb-4 pt-1 min-w-0">
                    {item}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )
      })}
    </div>
  )
}

// ── Chevron SVG ─────────────────────────────────────────────

function ChevronIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M4 6l4 4 4-4" />
    </svg>
  )
}

// ── Helpers ─────────────────────────────────────────────────

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

function isAccordionItemElement(
  element: React.ReactElement,
): element is React.ReactElement<AccordionItemBlockProps> {
  const p = element.props as Record<string, unknown> | null | undefined
  return p != null && typeof p === 'object' && 'trigger' in p
}
