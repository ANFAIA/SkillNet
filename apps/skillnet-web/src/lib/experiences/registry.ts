import type { ComponentType } from 'react'

import type { LearningExperienceReference } from '../../types/learning-experience'

export type ExperienceAdapterProps = {
  reference: LearningExperienceReference
}

export type ExperienceAdapter = {
  Renderer: ComponentType<ExperienceAdapterProps>
}

export type ExperienceAdapterLoader = () => Promise<ExperienceAdapter>

/** Lazy registry keyed by the stable `implementation_id@version` contract. */
export class ExperienceAdapterRegistry {
  private readonly loaders = new Map<string, ExperienceAdapterLoader>()
  private readonly loaded = new Map<string, Promise<ExperienceAdapter>>()

  register(implementationRef: string, loader: ExperienceAdapterLoader): void {
    if (!implementationRef || this.loaders.has(implementationRef)) {
      throw new Error(`Experience adapter already registered or invalid: ${implementationRef}`)
    }
    this.loaders.set(implementationRef, loader)
  }

  has(implementationRef: string): boolean {
    return this.loaders.has(implementationRef)
  }

  load(implementationRef: string): Promise<ExperienceAdapter> | undefined {
    const loader = this.loaders.get(implementationRef)
    if (!loader) return undefined

    const existing = this.loaded.get(implementationRef)
    if (existing) return existing

    const pending = loader().catch((error: unknown) => {
      this.loaded.delete(implementationRef)
      throw error
    })
    this.loaded.set(implementationRef, pending)
    return pending
  }
}

