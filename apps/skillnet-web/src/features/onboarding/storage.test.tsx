import { beforeEach, describe, expect, it } from 'vitest'
import {
  ONBOARDING_STORAGE_KEY,
  readOnboardingState,
  shouldAutoRun,
  writeOnboardingState,
} from './storage'

beforeEach(() => {
  window.localStorage.clear()
})

describe('onboarding storage — per-role keys', () => {
  it('stores the employee state under the bare base key (back-compat)', () => {
    writeOnboardingState({ completed: true }, 'employee')
    // The employee key must stay unsuffixed so pre-role-aware state still counts.
    expect(window.localStorage.getItem(ONBOARDING_STORAGE_KEY)).toBeTruthy()
    expect(window.localStorage.getItem(`${ONBOARDING_STORAGE_KEY}-admin`)).toBeNull()
  })

  it('stores the admin state under a "-admin" suffixed key', () => {
    writeOnboardingState({ completed: true }, 'admin')
    expect(window.localStorage.getItem(`${ONBOARDING_STORAGE_KEY}-admin`)).toBeTruthy()
    // The bare (employee) key is untouched.
    expect(window.localStorage.getItem(ONBOARDING_STORAGE_KEY)).toBeNull()
  })

  it('keeps the two roles independent: completing one never suppresses the other', () => {
    writeOnboardingState({ completed: true }, 'employee')
    // Employee is done, admin has never seen its tour.
    expect(readOnboardingState('employee').completed).toBe(true)
    expect(readOnboardingState('admin').completed).toBe(false)
    expect(shouldAutoRun('employee')).toBe(false)
    expect(shouldAutoRun('admin')).toBe(true)

    // Now finish the admin tour; the employee state is unaffected.
    writeOnboardingState({ completed: true }, 'admin')
    expect(shouldAutoRun('admin')).toBe(false)
    expect(readOnboardingState('employee').completed).toBe(true)
  })

  it('defaults to the employee role when none is passed', () => {
    writeOnboardingState({ completed: true })
    expect(readOnboardingState().completed).toBe(true)
    expect(window.localStorage.getItem(ONBOARDING_STORAGE_KEY)).toBeTruthy()
  })
})

describe('onboarding storage — shouldAutoRun', () => {
  it('auto-runs only when neither completed nor dismissed', () => {
    expect(shouldAutoRun('admin')).toBe(true)
  })

  it('does not auto-run once dismissed', () => {
    writeOnboardingState({ dismissedAt: new Date().toISOString() }, 'admin')
    expect(shouldAutoRun('admin')).toBe(false)
  })

  it('does not auto-run once completed', () => {
    writeOnboardingState({ completed: true }, 'admin')
    expect(shouldAutoRun('admin')).toBe(false)
  })
})

describe('onboarding storage — resilience', () => {
  it('reads corrupt JSON as the empty "not seen" state, never throwing', () => {
    window.localStorage.setItem(ONBOARDING_STORAGE_KEY, '{not valid json')
    expect(() => readOnboardingState('employee')).not.toThrow()
    expect(readOnboardingState('employee')).toEqual({ completed: false })
    // And so the tour would auto-run rather than get wedged shut.
    expect(shouldAutoRun('employee')).toBe(true)
  })

  it('merges patches into existing state rather than replacing it', () => {
    writeOnboardingState({ completed: true, lastStepId: 'start' }, 'employee')
    writeOnboardingState({ dismissedAt: '2026-08-20T00:00:00Z' }, 'employee')
    expect(readOnboardingState('employee')).toMatchObject({
      completed: true,
      lastStepId: 'start',
      dismissedAt: '2026-08-20T00:00:00Z',
    })
  })
})
