import {
  Children,
  cloneElement,
  useCallback,
  useId,
  useState,
  type HTMLAttributes,
  type KeyboardEvent,
  type MouseEvent,
  type ReactElement,
} from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type { CapabilityName } from '../api/setup'
import { useCapabilityExplanation } from '../hooks/useCapabilityExplanation'
import { useReducedMotion } from '../hooks/useReducedMotion'
import { transition } from '../lib/motion'

/**
 * Renders a control that cannot work, **visibly and inertly**, with the reason
 * attached to it.
 *
 * This is the explain half of `<Gated>` and exists because hiding was the wrong
 * answer for one specific case: a deployment with no image-model key used to accept
 * the "infografía" job and kill it thirty seconds later with a raw exception. Hiding
 * the tile instead would have replaced one confusion with another — the option is
 * real, it is simply not available here, and saying so is the whole feature.
 *
 * Two decisions worth not undoing:
 *
 * * **`aria-disabled`, never the `disabled` attribute.** `disabled` takes the control
 *   out of the tab order, and a control nobody can reach is a control whose
 *   explanation nobody can reach either — which defeats the point. `aria-disabled`
 *   keeps it focusable and announces it as unavailable. It also blocks nothing on its
 *   own, so activation is suppressed here by hand: the click, and the Enter/Space
 *   keydown that a button turns into one.
 * * **The description is always in the DOM.** `aria-describedby` may not point at an
 *   element that only exists while a tooltip is open; a screen-reader user never
 *   hovers. So the sentence lives permanently in an `sr-only` span, and the visible
 *   bubble that hover/focus/tap summons is a second copy marked `aria-hidden` — same
 *   words, no duplicate announcement.
 *
 * Shown on tap as well as hover, because a touch screen has no hover: the wrapper
 * toggles on `onClickCapture`, which runs before the child's suppressed click.
 *
 * The bubble reuses the visual language of `ui/InfoTooltip` (the codebase's existing
 * tooltip: dark `bg-text` surface, `text-bg` label, `text-xs`, `rounded-md`,
 * `shadow-md`) minus its `z-10`. It does not need one: the wrapper only becomes
 * `relative` while the bubble is open, and a positioned element paints above
 * non-positioned siblings by CSS paint order alone. DOM order, not a z-index war.
 */
/**
 * The child's own classes, made to read as unavailable.
 *
 * Dropped rather than overridden: two `cursor-*` utilities on one element are settled
 * by their order in the generated stylesheet, not by their order in the attribute, so
 * appending `cursor-not-allowed` next to a `cursor-pointer` is a coin flip. The
 * `hover:` variants go for the same reason they would on a real disabled control —
 * lighting up under the pointer is a promise this tile cannot keep.
 *
 * `opacity-50` is the same dimming `disabled:opacity-50` already applies across the
 * app, so an inert control looks exactly like a disabled one. Only the semantics
 * differ, which is the point.
 */
function inertClassName(original?: string): string {
  const kept = (original ?? '')
    .split(/\s+/)
    .filter((token) => token && token !== 'cursor-pointer' && !token.startsWith('hover:'))
  return [...kept, 'cursor-not-allowed', 'opacity-50'].join(' ')
}

export function CapabilityExplain({
  requires,
  children,
}: {
  requires: CapabilityName
  /** Exactly one element — the control that would have worked. */
  children: ReactElement
}) {
  const explanation = useCapabilityExplanation(requires)
  const animated = !useReducedMotion()
  const descriptionId = useId()
  const [open, setOpen] = useState(false)

  const suppress = useCallback((event: MouseEvent | KeyboardEvent) => {
    event.preventDefault()
    event.stopPropagation()
  }, [])

  const child = Children.only(children) as ReactElement<HTMLAttributes<HTMLElement>>
  const inert = cloneElement(child, {
    'aria-disabled': true,
    'aria-describedby': descriptionId,
    // Deliberately NOT `disabled`: see the note above. Also not `tabIndex={-1}`.
    onClick: suppress,
    onKeyDown: (event: KeyboardEvent<HTMLElement>) => {
      // A button activates on Enter (keydown) and on Space (keyup, armed by keydown).
      // Preventing the keydown default disarms both; the suppressed click is the net.
      if (event.key === 'Enter' || event.key === ' ') suppress(event)
    },
    className: inertClassName(child.props.className),
  } as Partial<HTMLAttributes<HTMLElement>>)

  return (
    <span
      // `relative` only while the bubble is up, so the one open tooltip is the only
      // positioned element in the row and nothing can paint over it.
      className={`inline-flex ${open ? 'relative' : ''}`}
      onPointerEnter={() => setOpen(true)}
      onPointerLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      // A touch screen has no hover, so the tap has to open it. Capture phase, because
      // the child suppresses the click before it could bubble up here. Open, never
      // toggle: a mouse click inside an already-hovered control would otherwise close
      // the bubble the pointer is asking for. It closes on leave or on blur — and a
      // tap moves focus to the control, so tapping elsewhere blurs and closes it.
      onClickCapture={() => setOpen(true)}
      onKeyDown={(event) => {
        if (event.key === 'Escape') setOpen(false)
      }}
    >
      {inert}
      {/* The accessible description. Permanent, so `aria-describedby` always resolves. */}
      <span id={descriptionId} className="sr-only">
        {explanation}
      </span>
      <AnimatePresence initial={false}>
        {open && (
          <motion.span
            aria-hidden="true"
            initial={animated ? { opacity: 0 } : false}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={animated ? transition.tooltip : { duration: 0 }}
            className="pointer-events-none absolute left-1/2 top-full mt-1 w-56 -translate-x-1/2 rounded-md bg-text px-3 py-2 text-xs leading-relaxed text-bg shadow-md"
          >
            {explanation}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  )
}
