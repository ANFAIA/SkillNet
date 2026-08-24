import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { IntlProvider } from '../../i18n/IntlProvider'
import { Employees } from './Employees'

/**
 * Deactivate/reactivate: a reversible alternative to deleting an employee
 * (`user_service.update_user` already supported `is_active`; this pins the
 * button that was missing on top of it). Confirmed only on deactivate — going
 * the other way should not need a confirmation dialog.
 */

const mockFetch = vi.fn()

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
  })
}

function employee(overrides: Record<string, unknown> = {}) {
  return {
    id: 'e1',
    email: 'bruno@test.dev',
    full_name: 'Bruno',
    role: 'employee',
    is_active: true,
    learning_profile: 'standard',
    accessibility: {},
    ...overrides,
  }
}

function installFetch(emp: ReturnType<typeof employee>) {
  mockFetch.mockImplementation((input: string, options?: RequestInit) => {
    const url = String(input)
    const method = options?.method ?? 'GET'
    if (url.startsWith('/api/v1/users?')) {
      return jsonResponse(200, { items: [emp], total: 1, offset: 0, limit: 50 })
    }
    if (url.startsWith('/api/v1/courses?')) {
      return jsonResponse(200, { items: [], total: 0, offset: 0, limit: 100 })
    }
    if (url.startsWith('/api/v1/enrollments?')) {
      return jsonResponse(200, { items: [], total: 0, offset: 0, limit: 50 })
    }
    if (url === `/api/v1/users/${emp.id}` && method === 'PUT') {
      const body = JSON.parse(String(options?.body))
      return jsonResponse(200, { ...emp, ...body })
    }
    return jsonResponse(404, { detail: 'Not Found', code: 'NOT_FOUND' })
  })
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <IntlProvider>
        <Employees />
      </IntlProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Employees — deactivate / reactivate', () => {
  it('deactivates an active employee after confirming, and shows the PUT payload', async () => {
    installFetch(employee({ is_active: true }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPage()

    // Desktop table and mobile cards both render in jsdom (no real media query),
    // so "Bruno" matches twice — either opens the same detail modal.
    await userEvent.click((await screen.findAllByText('Bruno'))[0])
    const dialog = await screen.findByRole('button', { name: 'Desactivar' })
    await userEvent.click(dialog)

    expect(window.confirm).toHaveBeenCalled()
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/users/e1',
      expect.objectContaining({ method: 'PUT', body: JSON.stringify({ is_active: false }) }),
    )
  })

  it('does not deactivate when the confirmation is dismissed', async () => {
    installFetch(employee({ is_active: true }))
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderPage()

    // Desktop table and mobile cards both render in jsdom (no real media query),
    // so "Bruno" matches twice — either opens the same detail modal.
    await userEvent.click((await screen.findAllByText('Bruno'))[0])
    await userEvent.click(await screen.findByRole('button', { name: 'Desactivar' }))

    expect(window.confirm).toHaveBeenCalled()
    expect(mockFetch).not.toHaveBeenCalledWith(
      '/api/v1/users/e1',
      expect.objectContaining({ method: 'PUT' }),
    )
  })

  it('reactivates an inactive employee without asking for confirmation', async () => {
    installFetch(employee({ is_active: false }))
    const confirmSpy = vi.spyOn(window, 'confirm')
    renderPage()

    // Desktop table and mobile cards both render in jsdom (no real media query),
    // so "Bruno" matches twice — either opens the same detail modal.
    await userEvent.click((await screen.findAllByText('Bruno'))[0])
    await userEvent.click(await screen.findByRole('button', { name: 'Reactivar' }))

    expect(confirmSpy).not.toHaveBeenCalled()
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/users/e1',
      expect.objectContaining({ method: 'PUT', body: JSON.stringify({ is_active: true }) }),
    )
  })

  it('shows an "Inactive" badge on an inactive employee in the list', async () => {
    installFetch(employee({ is_active: false }))
    renderPage()

    await screen.findAllByText('Bruno')
    // Desktop table + mobile card both show the badge in jsdom.
    expect(screen.getAllByText('Inactivo').length).toBeGreaterThan(0)
  })
})
