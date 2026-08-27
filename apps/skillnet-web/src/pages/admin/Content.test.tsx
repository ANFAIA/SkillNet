import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Content } from './Content'

/**
 * The per-course door to the schema screen, and the v1 course list it must not disturb.
 *
 * The schema button is always visible for every course: a course only reads
 * `'dynamic'` once its schema is validated, and a `draft` or `proposed` schema is
 * precisely what the schema link exists to reach.
 */

const COURSE_ID = '11111111-1111-4111-8111-111111111111'
const EMPTY_COURSE_ID = '22222222-2222-4222-8222-222222222222'

const mockFetch = vi.fn()

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
  })
}

function course(overrides: Record<string, unknown> = {}) {
  return {
    id: COURSE_ID,
    title: 'Devoluciones en tienda',
    description: null,
    outcome: null,
    status: 'published',
    source_document_id: null,
    created_at: '2026-07-01T00:00:00Z',
    module_count: 2,
    delivery_mode: 'static',
    ...overrides,
  }
}

/**
 * @param items       the courses the list returns; a second array, if given, is what the
 *                    list returns once a DELETE has gone through (the refetch).
 * @param onDelete    what `DELETE /courses/{id}` answers. Defaults to a 204.
 * @param onUnarchive what `POST /courses/{id}/unarchive` answers. Defaults to the course
 *                    back as `published`, which is what the endpoint returns: only a
 *                    published course can be archived, so that is the status it had.
 * @param afterUnarchive what the list returns once the unarchive has gone through (the
 *                    refetch), for asserting which buttons the restored row offers.
 */
function installFetch(
  items: unknown[] = [course()],
  { onDelete, afterDelete, onUnarchive, afterUnarchive }: {
    onDelete?: () => ReturnType<typeof jsonResponse>
    afterDelete?: unknown[]
    onUnarchive?: () => ReturnType<typeof jsonResponse>
    afterUnarchive?: unknown[]
  } = {},
) {
  let deleted = false
  let unarchived = false
  mockFetch.mockImplementation((input: string, options?: RequestInit) => {
    const url = String(input)
    if (url.includes('/unarchive') && options?.method === 'POST') {
      unarchived = true
      return onUnarchive
        ? onUnarchive()
        : jsonResponse(200, { ...(items[0] as Record<string, unknown>), status: 'published' })
    }
    if (url.endsWith('/health')) {
      return jsonResponse(200, {
        status: 'ok',
        version: '1',
        database: 'ok',
      })
    }
    // A folder born from a course row: `POST /course-folders`, then the move.
    if (url.includes('/course-folders') && options?.method === 'POST') {
      return jsonResponse(201, { id: 'folder-2', name: 'Atención al cliente' })
    }
    if (url.includes('/course-folders')) {
      return jsonResponse(200, [{ id: 'folder-1', name: 'Operaciones', course_count: 1 }])
    }
    if (url.includes('/courses/') && options?.method === 'DELETE') {
      const response = onDelete ? onDelete() : jsonResponse(204, null)
      deleted = true
      return response
    }
    if (url.includes('/courses/') && options?.method === 'PUT') {
      return jsonResponse(200, { ...(items[0] as Record<string, unknown>), folder_id: 'folder-1', folder_name: 'Operaciones' })
    }
    if (url.includes('/courses')) {
      let current = items
      if (deleted && afterDelete) current = afterDelete
      else if (unarchived && afterUnarchive) current = afterUnarchive
      return jsonResponse(200, { items: current, total: current.length, page: 1, size: 20 })
    }
    return jsonResponse(404, { detail: 'Not Found', code: 'NOT_FOUND' })
  })
}

function renderPage(initialEntry = '/admin/contenido') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/admin/contenido" element={<Content />} />
          <Route path="/admin/curso/:id/ajustes" element={<div>AJUSTES</div>} />
          <Route path="/admin/curso/:id/esquema" element={<div>ESQUEMA</div>} />
          <Route path="/admin/curso/:id" element={<div>PREVIEW</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

describe('Content — library navigation', () => {
  it('sends URL-backed search, status, and folder filters to the API', async () => {
    installFetch()
    renderPage('/admin/contenido?q=devoluciones&status=draft&folder=folder-1')

    await screen.findByText('Devoluciones en tienda')
    expect(mockFetch.mock.calls.some(([input]) => {
      const url = String(input)
      return url.includes('/courses?') && url.includes('search=devoluciones') && url.includes('status=draft') && url.includes('folder_id=folder-1')
    })).toBe(true)
  })

  it('moves a course into a folder from its row', async () => {
    installFetch()
    renderPage()

    await userEvent.click(await screen.findByLabelText(/Mover Devoluciones en tienda/))
    await userEvent.click(screen.getByRole('button', { name: 'Operaciones' }))

    expect(mockFetch.mock.calls.some(([input, options]) =>
      String(input).includes(`/courses/${COURSE_ID}`) &&
      options?.method === 'PUT' &&
      options.body === JSON.stringify({ folder_id: 'folder-1' }),
    )).toBe(true)
  })

  it('creates a folder from the row and files the course in it without leaving the menu', async () => {
    installFetch()
    renderPage()

    // Scoped to the row's own menu: the folder sidebar offers a "new folder" button too,
    // and the point of this one is that the admin never has to walk over there.
    const summary = await screen.findByLabelText(/Mover Devoluciones en tienda/)
    const menu = summary.closest('details')
    if (!menu) throw new Error('el selector de carpeta del curso no es un <details>')
    await userEvent.click(summary)
    await userEvent.click(within(menu).getByRole('button', { name: /Nueva carpeta/ }))
    await userEvent.type(within(menu).getByLabelText('Nombre de la carpeta'), 'Atención al cliente')
    await userEvent.click(within(menu).getByRole('button', { name: /Crear/i }))

    await waitFor(() => expect(mockFetch.mock.calls.some(([input, options]) =>
      String(input).includes('/course-folders') &&
      (options as RequestInit | undefined)?.method === 'POST' &&
      (options as RequestInit).body === JSON.stringify({ name: 'Atención al cliente' }),
    )).toBe(true))
    await waitFor(() => expect(mockFetch.mock.calls.some(([input, options]) =>
      String(input).includes(`/courses/${COURSE_ID}`) &&
      (options as RequestInit | undefined)?.method === 'PUT' &&
      (options as RequestInit).body === JSON.stringify({ folder_id: 'folder-2' }),
    )).toBe(true))
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Content — the settings entry point', () => {
  it('opens the settings screen of an existing course', async () => {
    installFetch()
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Ajustes' }))
    expect(await screen.findByText('AJUSTES', {}, { timeout: 5000 })).toBeInTheDocument()
  })

  it('offers it for a course with no modules, whose only other action is to delete it', async () => {
    installFetch([course({ id: EMPTY_COURSE_ID, module_count: 0, status: 'draft' })])
    renderPage()

    expect(await screen.findByRole('button', { name: 'Ajustes' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Eliminar' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ver curso' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Publicar' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Overviews' })).toBeNull()
  })

  it('shows the settings button alongside the v1 row', async () => {
    installFetch()
    renderPage()

    expect(await screen.findByText('Devoluciones en tienda')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ajustes' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ver curso' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Archivar' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Crear nuevo/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Overviews' })).toBeNull()
  })
})

/**
 * The reported incident: a generation run left a course in DRAFT, the retry published a
 * second one, and there was no way to remove the first. The route existed; nothing called
 * it. These cover the row that now does.
 */
describe('Content — deleting a draft', () => {
  const draft = () => course({ status: 'draft', module_count: 0 })

  it('offers the action only for a draft', async () => {
    installFetch([course({ status: 'published' })])
    renderPage()

    await screen.findByText('Devoluciones en tienda')
    expect(screen.queryByRole('button', { name: 'Eliminar' })).toBeNull()
  })

  it('does not offer it for the seeded demo course', async () => {
    installFetch([course({ status: 'draft', module_count: 0, is_demo: true })])
    renderPage()

    await screen.findByText('Devoluciones en tienda')
    expect(screen.queryByRole('button', { name: 'Eliminar' })).toBeNull()
  })

  it('asks first, and does nothing when the confirmation is dismissed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    installFetch([draft()])
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Eliminar' }))

    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('Devoluciones en tienda'))
    expect(mockFetch.mock.calls.some(([, options]) => (options as RequestInit | undefined)?.method === 'DELETE')).toBe(false)
  })

  it('deletes the course and refreshes the list once confirmed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    installFetch([draft()], { afterDelete: [] })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Eliminar' }))

    expect(mockFetch.mock.calls.some(([input, options]) =>
      String(input).includes(`/courses/${COURSE_ID}`) &&
      (options as RequestInit | undefined)?.method === 'DELETE',
    )).toBe(true)
    expect(await screen.findByText('Aún no hay cursos')).toBeInTheDocument()
  })

  it('shows what the server said when the delete is refused', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    installFetch([draft()], {
      onDelete: () => jsonResponse(409, { detail: 'Cannot delete a course that has enrollments', code: 'CONFLICT' }),
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Eliminar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot delete a course that has enrollments')
    expect(screen.getByText('Devoluciones en tienda')).toBeInTheDocument()
  })
})

/**
 * A course sits in zero or one folder, and the row used to render nothing at all for the
 * "zero" case — which is what sent the admin into the picker to find out where a course
 * already was.
 */
describe('Content — the folder a course is in', () => {
  it('names the folder on the row', async () => {
    installFetch([course({ folder_id: 'folder-1', folder_name: 'Operaciones' })])
    renderPage()

    expect(await screen.findByText('Carpeta: Operaciones')).toBeInTheDocument()
  })

  it('says so explicitly when the course is in none', async () => {
    installFetch()
    renderPage()

    await screen.findByText('Devoluciones en tienda')
    expect(screen.getAllByText('Sin carpeta').length).toBeGreaterThan(0)
  })
})

/** Archiving was a one-way door: an archived row had no action left that did anything. */
describe('Content — unarchiving', () => {
  it('offers the way back and calls the endpoint', async () => {
    installFetch([course({ status: 'archived' })])
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Desarchivar' }))

    expect(mockFetch.mock.calls.some(([input, options]) =>
      String(input).includes(`/courses/${COURSE_ID}/unarchive`) &&
      (options as RequestInit | undefined)?.method === 'POST',
    )).toBe(true)
  })

  it('brings the row back as published, not as a draft', async () => {
    // `published` is the status the course had — archive only accepts a published
    // course — so the restored row offers Archive again, and never Publish.
    installFetch([course({ status: 'archived' })], {
      afterUnarchive: [course({ status: 'published' })],
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Desarchivar' }))

    expect(await screen.findByRole('button', { name: 'Archivar' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Desarchivar' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Publicar' })).toBeNull()
  })

  it('does not offer it for a published course', async () => {
    installFetch([course({ status: 'published' })])
    renderPage()

    await screen.findByText('Devoluciones en tienda')
    expect(screen.queryByRole('button', { name: 'Desarchivar' })).toBeNull()
  })

  it('shows what the server said when the course was not archived after all', async () => {
    installFetch([course({ status: 'archived' })], {
      onUnarchive: () => jsonResponse(409, { detail: 'Course is not archived', code: 'CONFLICT' }),
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Desarchivar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Course is not archived')
  })
})

describe('Content — publish and archive', () => {
  it('lets an admin publish a validated dynamic draft from the library', async () => {
    installFetch([course({
      status: 'draft',
      module_count: 0,
      node_count: 4,
      delivery_mode: 'dynamic',
      schema_status: 'validated',
    })])
    renderPage()

    expect(await screen.findByRole('button', { name: 'Publicar' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Archivar' })).toBeNull()
  })
})
