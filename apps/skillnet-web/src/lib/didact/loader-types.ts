export type DidactModuleNamespace = Readonly<Record<string, unknown>>

export type DidactModuleLoader = () => Promise<DidactModuleNamespace>

export type DidactComponentLoaderEntry = {
  componentId: `didact.${string}`
  exportName: string
  registryItem: string
  loadModule: DidactModuleLoader
}

export class DidactRendererUnavailableError extends Error {
  readonly componentId: string
  readonly registryItem: string

  constructor(componentId: string, registryItem: string) {
    super(`Didact renderer ${componentId} (${registryItem}) is installed but has no host adapter`)
    this.name = 'DidactRendererUnavailableError'
    this.componentId = componentId
    this.registryItem = registryItem
  }
}

export function unavailableDidactModule(
  componentId: string,
  registryItem: string,
): DidactModuleLoader {
  return () => Promise.reject(new DidactRendererUnavailableError(componentId, registryItem))
}
