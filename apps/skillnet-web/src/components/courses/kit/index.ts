// The SkillNet UI Kit as OpenUI sees it (§5.3): ten components declared with
// `defineComponent`, a library rooted at `Stack`, and the static-only gate.

export { skillnetLibrary, skillnetLibrarySchema } from './library'
export { assertStaticOnly, gateProgram, isBlocked } from './assertStaticOnly'
export type { GateResult, StaticViolation, ViolationSeverity } from './assertStaticOnly'
export { nodeRenderContext, useNodeRenderTarget } from './NodeRenderContext'
export type { NodeRenderTarget } from './NodeRenderContext'
export {
  BLOOM_LEVELS,
  CALLOUT_TONES,
  CHART_KINDS,
  CONTAINER_NAMES,
  ITEM_TYPES,
  KIT_COMPONENT_NAMES,
  MAX_COMPONENTS,
  STACK_GAPS,
  TEXT_VARIANTS,
} from './schemas'
export type {
  BloomLevel,
  CalloutTone,
  ChartKind,
  ItemType,
  KitComponentName,
  StackGap,
  TextVariant,
} from './schemas'
