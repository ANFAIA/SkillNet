/**
 * Which stacking layer the explain popover and the phrase band paint at.
 *
 * ## Why this exists
 *
 * Both the popover and the band are portaled to `document.body`, so their z-index is
 * absolute — and `index.css` fixes it at `50` (popover) and `0` (band), which is right
 * for a lesson or a chat log painted at the page's base layer.
 *
 * Inside `ExplainModal` it is wrong. The modal's scrim is `z-[100]` and its card
 * `z-[101]`, so a popover at `50` opens *behind* an opaque card: clicking a word in the
 * "Ver mas" panel appeared to do nothing at all, which is the reported "dentro del ver
 * mas no puedo clicar otras palabras". Curio hits the same wall and answers it the same
 * way — its `DescribeModal` pins its own popover and band to `zIndex: 60`, one step
 * above its `z-50` card.
 *
 * A context rather than a prop because the surfaces that need lifting are not always
 * the modal's direct children: `UiSpecRenderer` blocks and `ChatMarkdown` nest
 * arbitrarily deep, and every `ClickableSurface` under the modal must lift, not just
 * the outermost one.
 */

import { createContext, useContext } from 'react'
import type { ReactNode } from 'react'

/**
 * The popover layer inside `ExplainModal`. Above the card (`z-[101]`) so it is visible,
 * and the band sits one below it so the popover always wins.
 */
export const EXPLAIN_LAYER_MODAL = 120

/** `null` means "use the `index.css` default", i.e. the page's base layer. */
const ExplainLayerContext = createContext<number | null>(null)

export interface ExplainLayerProps {
  /** Popover z-index; the phrase band paints at `zIndex - 1`. */
  zIndex: number
  children: ReactNode
}

export function ExplainLayer({ zIndex, children }: ExplainLayerProps) {
  return <ExplainLayerContext.Provider value={zIndex}>{children}</ExplainLayerContext.Provider>
}

export function useExplainLayer(): number | null {
  return useContext(ExplainLayerContext)
}
