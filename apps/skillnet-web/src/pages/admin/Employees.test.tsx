import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { IntlProvider } from '../../i18n/IntlProvider'
import { Employees } from './Employees'

/**
 * Deactivate/reactivate: a reversible alternative to deleting an employee
 * (`user_service.update_user` already supported `is_active`; this pins the
 * button that was missing on top of it). Confirmed only on deactivate — going
 * the other way should not need a confirmation dialog.
 *
 * Plus, further down, what the record can assign and un-assign: one course as always,
 * and now a whole library folder — including the folder that holds nothing publishable,
 * which answers 200 and enrols nobody, and used to say nothing about it.
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

function enrollment(overrides: Record<string, unknown> = {}) {
  return {
    id: 'en1',
    course_id: 'c1',
    user_id: 'e1',
    status: 'assigned',
    deadline: null,
    score: null,
    progress: 0,
    course_title: 'Bienvenida',
    started_at: null,
    completed_at: null,
    delivery_mode: 'static',
    ...overrides,
  }
}

interface World {
  /** What `GET /course-folders` answers with. */
  folders?: Array<{ id: string; name: string; course_count: number }>
  /** Published courses per folder id — what `GET /courses?status=published&folder_id=` counts. */
  publishedByFolder?: Record<string, number>
  /** The person's existing enrollments. */
  enrollments?: Array<Record<string, unknown>>
  /** What `POST /enrollments` answers. */
  assignResult?: unknown
  /** Status for `DELETE /enrollments/{id}`. */
  deleteStatus?: number
}

function installFetch(emp: ReturnType<typeof employee>, world: World = {}) {
  mockFetch.mockImplementation((input: string, options?: RequestInit) => {
    const url = String(input)
    const method = options?.method ?? 'GET'
    if (/^\/api\/v1\/users(\?|$)/.test(url) && method === 'GET') {
      return jsonResponse(200, { items: [emp], total: 1, offset: 0, limit: 50 })
    }
    if (url.startsWith('/api/v1/course-folders')) {
      return jsonResponse(200, world.folders ?? [])
    }
    if (url.startsWith('/api/v1/courses')) {
      const params = new URLSearchParams(url.split('?')[1] ?? '')
      const folderId = params.get('folder_id')
      const total = folderId ? world.publishedByFolder?.[folderId] ?? 0 : 0
      return jsonResponse(200, { items: [], total, offset: 0, limit: 100 })
    }
    if (url.startsWith('/api/v1/enrollments?')) {
      const items = world.enrollments ?? []
      return jsonResponse(200, { items, total: items.length, offset: 0, limit: 50 })
    }
    if (url === '/api/v1/enrollments' && method === 'POST') {
      return jsonResponse(201, world.assignResult ?? [])
    }
    if (/^\/api\/v1\/enrollments\/[^/]+$/.test(url) && method === 'DELETE') {
      const status = world.deleteStatus ?? 204
      return jsonResponse(status, status === 204 ? null : { detail: 'Conflict', code: 'CONFLICT' })
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

/** The detail modal, reached the way an admin reaches it. */
async function openDetail() {
  // Desktop table and mobile cards both render in jsdom (no real media query),
  // so "Bruno" matches twice — either opens the same detail modal.
  await userEvent.click((await screen.findAllByText('Bruno'))[0])
}

async function chooseFolderMode() {
  await userEvent.selectOptions(await screen.findByLabelText('¿Qué quieres asignar?'), 'folder')
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

    await openDetail()
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

    await openDetail()
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

    await openDetail()
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

describe('Employees — assigning a whole folder from the record', () => {
  const ONBOARDING = { id: 'f1', name: 'Onboarding', course_count: 3 }

  it('sends folder_id to POST /enrollments and reports created vs already-had-it', async () => {
    installFetch(employee(), {
      folders: [ONBOARDING],
      // Three courses in the folder, two of them published: only those get assigned.
      publishedByFolder: { f1: 2 },
      assignResult: {
        course_count: 2,
        created_count: 1,
        skipped_existing_count: 1,
        enrollments: [enrollment()],
      },
    })
    renderPage()
    await openDetail()
    await chooseFolderMode()

    await userEvent.selectOptions(await screen.findByLabelText('Carpeta'), 'f1')
    // The number shown before the click is the PUBLISHED count, not `course_count`.
    expect(await screen.findByText('Se asignarán 2 cursos publicados.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Asignar la carpeta' }))

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/enrollments',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ user_ids: ['e1'], folder_id: 'f1' }),
        }),
      ),
    )
    // Both halves of the outcome: "assigned" alone would hide the skips.
    expect(await screen.findByText('1 matrículas creadas en 2 cursos.')).toBeInTheDocument()
    expect(screen.getByText('1 matrículas ya existían y se conservaron.')).toBeInTheDocument()
  })

  it('warns instead of assigning when the folder has no published course', async () => {
    installFetch(employee(), { folders: [ONBOARDING], publishedByFolder: { f1: 0 } })
    renderPage()
    await openDetail()
    await chooseFolderMode()

    await userEvent.selectOptions(await screen.findByLabelText('Carpeta'), 'f1')

    expect(await screen.findByText(/no tiene ningún curso publicado/i)).toBeInTheDocument()
    // And the button cannot fire the request that would enrol nobody.
    expect(screen.getByRole('button', { name: 'Asignar la carpeta' })).toBeDisabled()
    expect(mockFetch).not.toHaveBeenCalledWith(
      '/api/v1/enrollments',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('keeps the single course as the default mode', async () => {
    installFetch(employee())
    renderPage()
    await openDetail()

    expect(await screen.findByLabelText('Curso')).toBeInTheDocument()
    // Nothing selected yet, so there is nothing to assign.
    expect(screen.getByRole('button', { name: 'Asignar curso' })).toBeDisabled()
  })
})

describe('Employees — removing an assigned course', () => {
  it('removes a course that has not started, after confirming', async () => {
    installFetch(employee(), { enrollments: [enrollment()] })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPage()
    await openDetail()

    await userEvent.click(await screen.findByRole('button', { name: 'Quitar' }))

    expect(window.confirm).toHaveBeenCalled()
    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/enrollments/en1',
        expect.objectContaining({ method: 'DELETE' }),
      ),
    )
  })

  it('does not offer to remove a course already in progress', async () => {
    installFetch(employee(), {
      enrollments: [enrollment({ status: 'in_progress', progress: 0.5 })],
    })
    renderPage()
    await openDetail()

    // The server would answer 409, so the action is not offered at all.
    expect(await screen.findByText('Bienvenida')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Quitar' })).not.toBeInTheDocument()
    // And the progress reads as a percentage, not as the raw 0..1 fraction.
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('translates the 409 when the course started between the fetch and the click', async () => {
    installFetch(employee(), { enrollments: [enrollment()], deleteStatus: 409 })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderPage()
    await openDetail()

    await userEvent.click(await screen.findByRole('button', { name: 'Quitar' }))

    expect(
      await screen.findByText(/Solo se pueden quitar cursos sin empezar/i),
    ).toBeInTheDocument()
  })
})
