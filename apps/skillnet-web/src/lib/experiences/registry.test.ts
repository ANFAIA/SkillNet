import { describe, expect, it, vi } from 'vitest'

import { ExperienceAdapterRegistry } from './registry'

const Renderer = () => null

describe('ExperienceAdapterRegistry', () => {
  it('loads an exact version lazily and memoizes the adapter', async () => {
    const registry = new ExperienceAdapterRegistry()
    const loader = vi.fn(async () => ({ Renderer }))
    registry.register('provider.activity@1', loader)

    expect(loader).not.toHaveBeenCalled()
    expect(registry.has('provider.activity@1')).toBe(true)
    expect(registry.load('provider.activity@2')).toBeUndefined()

    const first = registry.load('provider.activity@1')
    const second = registry.load('provider.activity@1')
    expect(first).toBe(second)
    await expect(first).resolves.toEqual({ Renderer })
    expect(loader).toHaveBeenCalledOnce()
  })

  it('allows a failed lazy import to be retried', async () => {
    const registry = new ExperienceAdapterRegistry()
    const loader = vi.fn()
      .mockRejectedValueOnce(new Error('chunk unavailable'))
      .mockResolvedValueOnce({ Renderer })
    registry.register('provider.activity@1', loader)

    await expect(registry.load('provider.activity@1')).rejects.toThrow('chunk unavailable')
    await expect(registry.load('provider.activity@1')).resolves.toEqual({ Renderer })
    expect(loader).toHaveBeenCalledTimes(2)
  })

  it('rejects duplicate registrations so ownership stays unambiguous', () => {
    const registry = new ExperienceAdapterRegistry()
    registry.register('provider.activity@1', async () => ({ Renderer }))

    expect(() => registry.register('provider.activity@1', async () => ({ Renderer })))
      .toThrow('already registered')
  })
})

