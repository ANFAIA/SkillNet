import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Header } from './Header'
import { SidebarProvider } from '../../contexts/SidebarContext'
import type { DynamicCoursesMode } from '../../api/health'

/**
 * The way back into the onboarding wizard (§6.1).
 *
 * `POST /onboarding/skip` marks the learner asked-and-answered forever, so the gate in
 * `ProtectedRoute` never fires again — without this menu item "lo hago luego" is a
 * one-way door and the learner profile can never be declared.
 *
 * Two gates, both tested from the closed side, because this header is also the admin
 * one: below `on` every onboarding route is a 404, and an admin has no wizard at all.
 */

const mockFetch = vi.fn()

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
  })
}

function installFetch(mode: DynamicCoursesMode, role: 'employee' | 'admin') {
  mockFetch.mockImplementation((input: string) => {
    const url = String(input)
    if (url.endsWith('/health')) {
      return jsonResponse(200, {
        status: 'ok',
        version: '1',
        database: 'ok',
        features: { dynamic_courses: mode },
      })
    }
    if (url.endsWith('/auth/me')) {
      return jsonResponse(200, {
        id: 'u1',
        email: role === 'admin' ? 'admin@skillnet.dev' : 'empleado@skillnet.dev',
        full_name: role === 'admin' ? 'Admin Ejemplo' : 'Empleada Ejemplo',
        role,
      })
    }
    return jsonResponse(404, { detail: 'Not Found', code: 'NOT_FOUND' })
  })
}

function renderHeader() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/empleado']}>
        <SidebarProvider>
          <Routes>
            <Route path="/empleado" element={<Header />} />
            <Route path="/onboarding" element={<div>WIZARD</div>} />
          </Routes>
        </SidebarProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Opens the account menu and waits for the identity block to prove it is populated. */
async function openMenu(name: string) {
  await userEvent.click(await screen.findByRole('button', { name: 'Cuenta' }))
  await screen.findByText(name)
}

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
  // jsdom has no matchMedia, and SidebarProvider reads it on mount.
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }))
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Header — re-entering onboarding', () => {
  it('offers the wizard to an employee with the flag on', async () => {
    installFetch('on', 'employee')
    renderHeader()

    await openMenu('Empleada Ejemplo')
    await userEvent.click(
      screen.getByRole('menuitem', { name: 'Preferencias de aprendizaje' }),
    )

    expect(await screen.findByText('WIZARD')).toBeInTheDocument()
  })
})

describe('Header — the closed side of both gates', () => {
  it('hides the wizard from an employee in shadow mode', async () => {
    installFetch('shadow', 'employee')
    renderHeader()

    await openMenu('Empleada Ejemplo')
    expect(screen.queryByRole('menuitem', { name: 'Preferencias de aprendizaje' })).toBeNull()
    expect(screen.getByRole('menuitem', { name: 'Cerrar sesion' })).toBeInTheDocument()
  })

  it('hides it with the flag off', async () => {
    installFetch('off', 'employee')
    renderHeader()

    await openMenu('Empleada Ejemplo')
    expect(screen.queryByRole('menuitem', { name: 'Preferencias de aprendizaje' })).toBeNull()
    expect(screen.getByRole('menuitem', { name: 'Cerrar sesion' })).toBeInTheDocument()
  })

  it('never offers it to an admin, flag on', async () => {
    installFetch('on', 'admin')
    renderHeader()

    await openMenu('Admin Ejemplo')
    expect(screen.queryByRole('menuitem', { name: 'Preferencias de aprendizaje' })).toBeNull()
    expect(screen.getByRole('menuitem', { name: 'Cerrar sesion' })).toBeInTheDocument()
  })
})
