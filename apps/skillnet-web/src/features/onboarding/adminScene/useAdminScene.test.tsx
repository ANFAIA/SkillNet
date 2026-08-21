import { beforeEach, describe, expect, it } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { isAdminSceneDismissed, useAdminScene } from './useAdminScene'

const KEY = 'skillnet-admin-scene'

beforeEach(() => {
  window.localStorage.clear()
})

describe('useAdminScene — dismissal persistence', () => {
  it('starts not dismissed on a fresh browser', () => {
    const { result } = renderHook(() => useAdminScene())
    expect(result.current.dismissed).toBe(false)
    expect(isAdminSceneDismissed()).toBe(false)
  })

  it('dismiss() flips state and persists to localStorage', () => {
    const { result } = renderHook(() => useAdminScene())
    act(() => result.current.dismiss())
    expect(result.current.dismissed).toBe(true)
    expect(window.localStorage.getItem(KEY)).toBe('dismissed')
    expect(isAdminSceneDismissed()).toBe(true)
  })

  it('reads a previously dismissed flag on mount, so the scene never returns', () => {
    window.localStorage.setItem(KEY, 'dismissed')
    const { result } = renderHook(() => useAdminScene())
    expect(result.current.dismissed).toBe(true)
  })

  it('treats any other stored value as not dismissed', () => {
    window.localStorage.setItem(KEY, 'anything-else')
    expect(isAdminSceneDismissed()).toBe(false)
  })
})
