import { create } from 'zustand'

/**
 * Tiny store that passes the origin rect of a node row click to the NodeView
 * portal, so the portal can morph FROM that position instead of appearing from
 * nothing. The rect is set on click (NodeList), consumed on mount (NodeView),
 * and cleared after the enter animation completes.
 *
 * This is the "capture rect, animate from it" pattern (FLIP without layoutId),
 * needed because the source component (NodeList) unmounts before the target
 * (NodeView portal) mounts — framer-motion's layoutId cannot bridge that gap.
 */

export interface MorphOrigin {
  top: number
  left: number
  width: number
  height: number
}

interface NodeMorphState {
  origin: MorphOrigin | null
  /** Set by NodeRow on click, consumed by NodeView on mount. */
  setOrigin: (rect: MorphOrigin) => void
  clear: () => void
}

export const useNodeMorph = create<NodeMorphState>((set) => ({
  origin: null,
  setOrigin: (rect) => set({ origin: rect }),
  clear: () => set({ origin: null }),
}))
