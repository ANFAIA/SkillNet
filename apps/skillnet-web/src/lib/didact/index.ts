export type { DidactAdapterDescriptor } from './adapter'
export { DidactComponentMount } from './DidactComponentMount'
export { DidactErrorBoundary } from './DidactErrorBoundary'
export { DidactHostProvider, useDidactHost, useOptionalDidactHost } from './DidactHostContext'
export { isPublicActivityDefinition, validatePublicActivityDefinition } from './activity-definition'
export type { ActivityDefinitionValidation } from './activity-definition'
export { resolveDidactMount, withoutProtectedAnswerKeys } from './runtime'
export type { DidactMountResolution } from './runtime'
export { exposedComponentIds } from './exposure'
export type { DidactExposureDecision } from './exposure'
export {
  DIDACT_COMPONENT_BY_ID,
  DIDACT_COMPONENT_REGISTRY,
  DIDACT_REGISTRY_SOURCE,
} from './generated-registry'
export { DIDACT_COMPONENT_LOADERS, loadDidactExport } from './generated-loaders'
export { DidactRendererUnavailableError } from './loader-types'
export type {
  DidactComponentLoaderEntry,
  DidactModuleLoader,
  DidactModuleNamespace,
} from './loader-types'
export type {
  DidactLazyModule,
  DidactMaturity,
  DidactRegistryAdapterState,
  DidactRegistryEntry,
} from './registry-types'
export { deriveDidactAvailability } from './availability'
export type { DidactAdapterAvailability, DidactAvailabilityStatus } from './availability'
export { DIDACT_HOST_CAPABILITIES } from './host-ports'
export { DIDACT_COMPONENT_POLICY, didactPolicyFor } from './policy'
export type {
  DidactComponentPolicy,
  DidactFallbackMode,
  DidactProtectedData,
} from './policy'
export type {
  AssetPort,
  AssetReference,
  ClockPort,
  DidactEvent,
  DidactHostCapability,
  DidactHostPorts,
  DidactScope,
  DidactValue,
  EvaluationPort,
  EvaluationRequest,
  EvaluationResult,
  EventPort,
  ExecutionPort,
  ExecutionRequest,
  ExecutionResult,
  MediaPort,
  MediaRequest,
  PersistencePort,
  ProgressPort,
  ProgressRecord,
  ScheduledTask,
  SchedulerPort,
  SimulationPort,
  SimulationRequest,
  SimulationResult,
} from './host-ports'
