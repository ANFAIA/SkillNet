import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { TooltipRenderProps } from 'react-joyride'
import { TourTooltip } from './TourTooltip'
import { TourTrigger } from './TourTrigger'
import { adminTourSteps, employeeTourSteps, resolveSteps, tourSteps } from './steps'
import {
  ONBOARDING_STORAGE_KEY,
  readOnboardingState,
  shouldAutoRun,
  writeOnboardingState,
} from './storage'
import { useTourStore } from './useTourStore'

function renderInRouter(ui: React.ReactElement) {
  return render(<MemoryRouter initialEntries={['/empleado']}>{ui}</MemoryRouter>)
}

/** Minimal joyride render-props for one step, enough to drive TourTooltip. */
function tooltipProps(index: number, isLastStep: boolean): TooltipRenderProps {
  const step = employeeTourSteps[index]
  const action = (label: string) => ({
    'aria-label': label,
    'data-action': label,
    role: 'button',
    title: label,
    onClick: vi.fn(),
  })
  return {
    continuous: true,
    index,
    size: employeeTourSteps.length,
    isLastStep,
    step: { target: step.target, title: step.title, content: step.body },
    backProps: action('back'),
    primaryProps: action('primary'),
    skipProps: action('skip'),
    closeProps: action('close'),
    tooltipProps: { 'aria-modal': true, role: 'dialog' },
  } as unknown as TooltipRenderProps
}

beforeEach(() => {
  window.localStorage.clear()
  useTourStore.setState({ run: false, runId: 0 })
})

describe('onboarding tour — steps data', () => {
  it('is declarative, employee-only and ordered', () => {
    const steps = resolveSteps(employeeTourSteps, 'employee')
    expect(steps.length).toBeGreaterThan(0)
    expect(steps.every((s) => s.role === 'employee')).toBe(true)
    expect(steps.map((s) => s.order)).toEqual([...steps.map((s) => s.order)].sort((a, b) => a - b))
    // The tour ends by pointing at the start CTA — "abre tu primera lección".
    expect(steps[steps.length - 1].target).toBe('[data-tour="home-start"]')
  })

  it('resolves the admin tour by role from the shared list, ending on the create CTA', () => {
    // The create step needs `generation`; pass it so the full admin tour resolves.
    const steps = resolveSteps(tourSteps, 'admin', { generation: true })
    expect(steps).toEqual(adminTourSteps)
    expect(steps.every((s) => s.role === 'admin')).toBe(true)
    // No employee step leaks into the admin slice (per-role, not shared state).
    expect(steps.some((s) => s.target.startsWith('[data-tour="home-'))).toBe(false)
    // Every admin step declares the real screen it lives on (guided multi-screen flow).
    expect(steps.every((s) => Boolean(s.route))).toBe(true)
    // The admin "aha" / first win is creating a course — the tour ends on that CTA.
    expect(steps[steps.length - 1].target).toBe('[data-tour="demo-create-cta"]')
  })

  it('drops the create-course step when generation is unavailable (§2.3)', () => {
    const withGen = resolveSteps(tourSteps, 'admin', { generation: true })
    const withoutGen = resolveSteps(tourSteps, 'admin', { generation: false })
    // The gated step is present with the capability and absent without it — the tour
    // never ends on a dead "create a course" action when there is no AI key.
    expect(withGen.some((s) => s.id === 'admin-create')).toBe(true)
    expect(withoutGen.some((s) => s.id === 'admin-create')).toBe(false)
    // Every other (ungated) admin step survives regardless.
    expect(withoutGen.map((s) => s.id)).toEqual(['admin-welcome', 'admin-content', 'admin-preview'])
  })
})

describe('TourTooltip', () => {
  it('renders the step title, body and 1-of-N progress', () => {
    renderInRouter(<TourTooltip {...tooltipProps(0, false)} />)
    expect(screen.getByText('Te damos la bienvenida')).toBeInTheDocument()
    expect(screen.getByText('Paso 1 de 4')).toBeInTheDocument()
    // Skip + close are present on every step (persistent escape hatch).
    expect(screen.getByText('Saltar')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cerrar' })).toBeInTheDocument()
  })

  it('shows the finish label on the last step', () => {
    const last = employeeTourSteps.length - 1
    renderInRouter(<TourTooltip {...tooltipProps(last, true)} />)
    expect(screen.getByText('Abre tu primera lección')).toBeInTheDocument()
    expect(screen.getByText('Empezar')).toBeInTheDocument()
  })
})

describe('onboarding state (localStorage)', () => {
  it('auto-runs for a first-time employee, not after dismissal', () => {
    expect(shouldAutoRun()).toBe(true)
    writeOnboardingState({ dismissedAt: new Date().toISOString() })
    expect(shouldAutoRun()).toBe(false)
    // dismissal is persisted under the documented key + shape
    const raw = window.localStorage.getItem(ONBOARDING_STORAGE_KEY)
    expect(raw).toBeTruthy()
    expect(readOnboardingState().dismissedAt).toBeTruthy()
  })

  it('does not auto-run once completed, and records lastStepId', () => {
    writeOnboardingState({ completed: true, lastStepId: 'start' })
    expect(shouldAutoRun()).toBe(false)
    expect(readOnboardingState()).toMatchObject({ completed: true, lastStepId: 'start' })
  })
})

describe('TourTrigger — reopen', () => {
  it('starts the tour when clicked from the home route', async () => {
    const user = userEvent.setup()
    renderInRouter(<TourTrigger />)
    expect(useTourStore.getState().run).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Ver la guía de bienvenida' }))
    expect(useTourStore.getState().run).toBe(true)
  })
})
