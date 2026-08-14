import { DIDACT_COMPONENT_REGISTRY } from '../didact/generated-registry'
import { ExperienceAdapterRegistry } from './registry'

export const experienceAdapterRegistry = new ExperienceAdapterRegistry()

const loadDidactAdapter = async () => {
  const module = await import('./adapters/DidactExperienceAdapter')
  return { Renderer: module.DidactExperienceAdapter }
}

for (const entry of DIDACT_COMPONENT_REGISTRY) {
  experienceAdapterRegistry.register(`${entry.componentId}@1`, loadDidactAdapter)
}

experienceAdapterRegistry.register('media.checkpoint-video@1', async () => {
  const module = await import('./adapters/CheckpointVideoAdapter')
  return { Renderer: module.CheckpointVideoAdapter }
})

experienceAdapterRegistry.register('skillnet.text-content@1', async () => {
  const module = await import('./adapters/TextContentAdapter')
  return { Renderer: module.TextContentAdapter }
})
