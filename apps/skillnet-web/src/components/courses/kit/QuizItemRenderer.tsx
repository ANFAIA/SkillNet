import type { ComponentRenderProps } from '@openuidev/react-lang'

import { QuizItemBlock } from '../blocks'
import { readEnum, readString, readStringArray } from './coerce'
import { useNodeRenderTarget } from './NodeRenderContext'
import { BLOOM_LEVELS, ITEM_TYPES } from './schemas'

/**
 * The one kit component that needs ambient data, which is why it lives in its own
 * file instead of inline in `library.tsx`: it calls a hook.
 *
 * `nodeId`/`renderId` are NOT props of the dialect — a generated program must not
 * be able to redirect an answer POST — so they arrive through
 * `NodeRenderContext`.
 *
 * §5.3: this block is autonomous React talking to `POST /nodes/{id}/answer`. It
 * deliberately does NOT go through OpenUI's `Mutation`/`ActionPlan`. Nothing in
 * the library calls `useTriggerAction()`, and that is what makes an action or a
 * mutation physically unfirable in this app.
 */
export function QuizItemRenderer({
  props,
  statementId,
}: ComponentRenderProps<{
  item_id: string
  item_type: string
  bloom_level: string
  question: string
  options: string[]
}>) {
  const { nodeId, renderId } = useNodeRenderTarget()
  return (
    <QuizItemBlock
      // The statement name is the id in the IR, so it is the sane fallback when a
      // generated program forgets `item_id`.
      item_id={readString(props.item_id, statementId ?? '')}
      item_type={readEnum(props.item_type, ITEM_TYPES, 'test')}
      bloom_level={readEnum(props.bloom_level, BLOOM_LEVELS, 'apply')}
      question={readString(props.question)}
      options={readStringArray(props.options)}
      nodeId={nodeId}
      renderId={renderId}
    />
  )
}
