export type DidactMaturity = 'experimental' | 'beta' | 'stable' | 'deprecated'

/** Metadata for a future dynamic import from the pinned vendored snapshot. */
export type DidactLazyModule = {
  strategy: 'vendor-export'
  exportName: string
  registryItem: string
  sourceModule: string
}

/** Host adapter state only. OpenUI exposure intentionally does not live here. */
export type DidactRegistryAdapterState = {
  rendererAvailable: boolean
  rendererSymbol: string | null
}

/** One installed educational type from Didact's authoritative availableTypes. */
export type DidactRegistryEntry = {
  componentId: `didact.${string}`
  manifestId: `didact.${string}`
  exportName: string
  registryItem: string
  maturity: DidactMaturity
  didactVersion: string
  lazyModule: DidactLazyModule
  adapter: DidactRegistryAdapterState
}
