import { createContext, useContext } from 'react'
import type { NodeEventInput } from '../../../types'

/**
 * Where a `QuizItem` posts its answers.
 *
 * OpenUI's runtime instantiates a component renderer with exactly three things:
 * `props`, `renderNode` and `statementId`. There is no way to pass ambient data
 * down through the tree — so the node and render ids, which are *not* props of
 * the dialect (they are not in the §5.3 table and the model must never write
 * them), travel by React context instead.
 */
export interface NodeRenderTarget {
  /** Target of `POST /nodes/{nodeId}/answer`. */
  nodeId: string
  /**
   * `node_renders.id` of the program being rendered. Absent in a preview
   * (Storybook, admin preview): quiz items then render read-only rather than
   * posting an ungradeable attempt.
   */
  renderId?: string
  /**
   * Batched event recorder (§3.3). Absent in previews where no node is open.
   * Used by `QuizItemBlock` to emit `quiz_correct` / `quiz_wrong` events that
   * feed the `format_vector`.
   */
  recordEvent?: (event: NodeEventInput) => void
}

/**
 * Lower-cased deliberately: it is a context object, not a component, and the
 * `react/only-export-components` rule (7 warnings' worth of house style already)
 * treats a PascalCase export in a file that also exports a hook as a mistake.
 * Consumers write `<nodeRenderContext.Provider value={…}>`.
 */
export const nodeRenderContext = createContext<NodeRenderTarget>({ nodeId: '' })

export function useNodeRenderTarget(): NodeRenderTarget {
  return useContext(nodeRenderContext)
}
