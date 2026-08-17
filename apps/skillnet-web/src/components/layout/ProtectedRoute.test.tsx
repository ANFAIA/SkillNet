import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { ProtectedRoute } from './ProtectedRoute'

/**
 * The three rules of §6.1, one test each — plus the loop that rule 2 exists to
 * prevent. This component wraps the admin pages as well as the employee ones, so a
 * gate that fires one step too eagerly breaks a role that has no onboarding at all.
 */

const mockFetch = vi.fn()

type Handler = { status: number; body: unknown } | 'pending'

/** Answers by path (without the `/api/v1` prefix). Unlisted paths 404. */
function serve(handlers: Record<string, Handler>) {
  mockFetch.mockImplementation((url: string) => {
    const path = String(url).replace('/api/v1', '')
    const handler = handlers[path]
    if (handler === undefined) {
      return Promise.resolve({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: 'Not Found' }),
      })
    }
    if (handler === 'pending') return new Promise(() => {})
    return Promise.resolve({
      ok: handler.status >= 200 && handler.status < 300,
      status: handler.status,
      json: () => Promise.resolve(handler.body),
    })
  })
}

const EMPLOYEE = {
  id: 'u1',
  email: 'empleado@skillnet.dev',
  full_name: 'Empleada',
  role: 'employee',
}

const ADMIN = { id: 'u2', email: 'admin@skillnet.dev', full_name: 'Admin', role: 'admin' }

// The owner of an individual deployment: an admin who also learns, so the
// onboarding gate must treat them like a learner. See audience-modes.md.
const INDIVIDUAL_OWNER = { ...ADMIN, workspace_mode: 'individual' }

function health(): Handler {
  return {
    status: 200,
    body: { status: 'ok', version: '0.1.0', database: 'connected' },
  }
}

function profile(overrides: Record<string, unknown> = {}): Handler {
  return {
    status: 200,
    body: {
      role_title: null,
      sector: null,
      goal: null,
      experience_level: 'unknown',
      preset: 'standard',
      nodes_completed: 0,
      onboarding_completed_at: null,
      onboarding_skipped: false,
      calibrating: true,
      ...overrides,
    },
  }
}

function renderGuard(guarded: ReactNode, initial = '/empleado') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route path="/empleado" element={guarded} />
          <Route path="/admin" element={guarded} />
          <Route path="/onboarding" element={<div>WIZARD</div>} />
          <Route path="/login" element={<div>LOGIN</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function employeeGuard() {
  return (
    <ProtectedRoute role="employee">
      <div>APP</div>
    </ProtectedRoute>
  )
}

function profileCalls() {
  return mockFetch.mock.calls.filter((call) => String(call[0]).includes('learner-profile'))
}

beforeEach(() => {
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
  mockFetch.mockReset()
})

describe('ProtectedRoute — auth', () => {
  it('sends an anonymous visitor to /login', async () => {
    serve({ '/health': health(), '/auth/me': { status: 401, body: { detail: 'Unauthorized' } } })
    renderGuard(employeeGuard())
    expect(await screen.findByText('LOGIN')).toBeInTheDocument()
  })

  it('sends a user to their own home when the role does not match', async () => {
    serve({ '/health': health(), '/auth/me': { status: 200, body: ADMIN } })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/empleado']}>
          <Routes>
            <Route
              path="/empleado"
              element={
                <ProtectedRoute role="employee">
                  <div>APP</div>
                </ProtectedRoute>
              }
            />
            <Route path="/admin" element={<div>ADMIN HOME</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByText('ADMIN HOME')).toBeInTheDocument()
    expect(screen.queryByText('APP')).toBeNull()
  })
})

describe('ProtectedRoute — onboarding gate (§6.1)', () => {
  it('redirects an employee whose profile has no onboarding_completed_at', async () => {
    serve({
      '/health': health(),
      '/auth/me': { status: 200, body: EMPLOYEE },
      '/users/me/learner-profile': profile(),
    })
    renderGuard(employeeGuard())
    expect(await screen.findByText('WIZARD')).toBeInTheDocument()
  })

  it('lets through an employee who already answered', async () => {
    serve({
      '/health': health(),
      '/auth/me': { status: 200, body: EMPLOYEE },
      '/users/me/learner-profile': profile({ onboarding_completed_at: '2026-07-25T09:12:00Z' }),
    })
    renderGuard(employeeGuard())
    expect(await screen.findByText('APP')).toBeInTheDocument()
  })

  // Rule 1 — the query is conditioned on role.
  it('never queries the profile for an admin', async () => {
    serve({
      '/health': health(),
      '/auth/me': { status: 200, body: ADMIN },
      '/users/me/learner-profile': profile(),
    })
    renderGuard(
      <ProtectedRoute role="admin">
        <div>ADMIN</div>
      </ProtectedRoute>,
      '/admin',
    )
    expect(await screen.findByText('ADMIN')).toBeInTheDocument()
    expect(profileCalls()).toHaveLength(0)
  })

  // Rule 2 — a 404 means "do not redirect", not "not onboarded".
  it('treats a 404 profile as "do not redirect"', async () => {
    serve({
      '/health': health(),
      '/auth/me': { status: 200, body: EMPLOYEE },
      '/users/me/learner-profile': { status: 404, body: { detail: 'Not Found' } },
    })
    renderGuard(employeeGuard())
    expect(await screen.findByText('APP')).toBeInTheDocument()
    expect(screen.queryByText('WIZARD')).toBeNull()
  })

  it('does not loop when the profile route 404s', async () => {
    // The exact scenario rule 2 exists for: the profile route 404s. Reading that as
    // "not onboarded" would bounce the learner to a route that no longer exists.
    serve({
      '/health': health(),
      '/auth/me': { status: 200, body: EMPLOYEE },
      // /users/me/learner-profile is deliberately unlisted → 404, like a router
      // whose feature dependency now rejects the path.
    })
    renderGuard(employeeGuard())
    expect(await screen.findByText('APP')).toBeInTheDocument()
    await waitFor(() => expect(profileCalls().length).toBeGreaterThan(0))
    // One attempt, no retry storm, and still no redirect.
    expect(screen.queryByText('WIZARD')).toBeNull()
  })

  // Rule 3 — skeleton while in flight, never a redirect.
  it('paints the skeleton while the profile query is in flight', async () => {
    serve({
      '/health': health(),
      '/auth/me': { status: 200, body: EMPLOYEE },
      '/users/me/learner-profile': 'pending',
    })
    renderGuard(employeeGuard())
    expect(await screen.findByAltText('SkillNet')).toBeInTheDocument()
    expect(screen.queryByText('WIZARD')).toBeNull()
    expect(screen.queryByText('APP')).toBeNull()
  })

  it('does not redirect when the profile request fails with a server error', async () => {
    serve({
      '/health': health(),
      '/auth/me': { status: 200, body: EMPLOYEE },
      '/users/me/learner-profile': { status: 500, body: { detail: 'boom' } },
    })
    renderGuard(employeeGuard())
    expect(await screen.findByText('APP')).toBeInTheDocument()
    expect(screen.queryByText('WIZARD')).toBeNull()
  })

  it('gates the individual-mode owner (admin) to onboarding when unanswered', async () => {
    serve({
      '/health': health(),
      '/auth/me': { status: 200, body: INDIVIDUAL_OWNER },
      '/users/me/learner-profile': profile(),
    })
    renderGuard(
      <ProtectedRoute role="admin">
        <div>APP</div>
      </ProtectedRoute>,
      '/admin',
    )
    expect(await screen.findByText('WIZARD')).toBeInTheDocument()
  })

  it('lets the individual-mode owner through once onboarding is answered', async () => {
    serve({
      '/health': health(),
      '/auth/me': { status: 200, body: INDIVIDUAL_OWNER },
      '/users/me/learner-profile': profile({ onboarding_completed_at: '2026-07-25T09:12:00Z' }),
    })
    renderGuard(
      <ProtectedRoute role="admin">
        <div>APP</div>
      </ProtectedRoute>,
      '/admin',
    )
    expect(await screen.findByText('APP')).toBeInTheDocument()
  })

  it('skipOnboardingGate keeps /onboarding from redirecting to itself', async () => {
    serve({
      '/health': health(),
      '/auth/me': { status: 200, body: EMPLOYEE },
      '/users/me/learner-profile': profile(),
    })
    renderGuard(
      <ProtectedRoute role="employee" skipOnboardingGate>
        <div>WIZARD PAGE</div>
      </ProtectedRoute>,
    )
    expect(await screen.findByText('WIZARD PAGE')).toBeInTheDocument()
    expect(profileCalls()).toHaveLength(0)
  })
})
