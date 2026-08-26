import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CoursePreview } from './CoursePreview'

/**
 * The second door to the schema screen: the course the creator already has open.
 *
 * The schema button is always available for every course.
 */

const COURSE_ID = '11111111-1111-4111-8111-111111111111'

const mockFetch = vi.fn()

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
  })
}

const COURSE = {
  id: COURSE_ID,
  title: 'Devoluciones en tienda',
  description: null,
  outcome: null,
  status: 'draft',
  source_document_id: null,
  created_at: '2026-07-01T00:00:00Z',
  module_count: 1,
  delivery_mode: 'static',
  modules: [
    {
      id: 'mod-1',
      title: 'Modulo de devoluciones',
      summary: null,
      position: 1,
      lessons: [
        {
          id: 'lesson-1',
          title: 'Plazo legal',
          content: 'Se aceptan devoluciones durante 30 dias naturales.',
          position: 1,
          exercises: [],
        },
      ],
    },
  ],
}

function installFetch(onDelete?: () => ReturnType<typeof jsonResponse>) {
  mockFetch.mockImplementation((input: string, options?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/health')) {
      return jsonResponse(200, {
        status: 'ok',
        version: '1',
        database: 'ok',
      })
    }
    if (url.endsWith(`/courses/${COURSE_ID}`) && options?.method === 'DELETE') {
      return onDelete ? onDelete() : jsonResponse(204, null)
    }
    if (url.endsWith(`/courses/${COURSE_ID}`)) {
      return jsonResponse(200, COURSE)
    }
    return jsonResponse(404, { detail: 'Not Found', code: 'NOT_FOUND' })
  })
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/admin/curso/${COURSE_ID}`]}>
        <Routes>
          <Route path="/admin/curso/:id" element={<CoursePreview />} />
          <Route path="/admin/curso/:id/ajustes" element={<div>AJUSTES</div>} />
          <Route path="/admin/contenido" element={<div>CONTENIDO</div>} />
        </Routes>
      </MemoryRouter>
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

describe('CoursePreview — the settings entry point', () => {
  it('opens the settings of the course on screen', async () => {
    installFetch()
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Ajustes' }))
    expect(await screen.findByText('AJUSTES')).toBeInTheDocument()
  })

  it('shows the settings button alongside the v1 action row', async () => {
    installFetch()
    renderPage()

    expect(await screen.findByRole('button', { name: 'Editar' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ajustes' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Publicar' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Contenido' })).toBeInTheDocument()
  })
})

describe('CoursePreview — deleting the draft on screen', () => {
  it('asks first, deletes, and returns to the library', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    installFetch()
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Eliminar' }))

    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('Devoluciones en tienda'))
    expect(mockFetch.mock.calls.some(([input, options]) =>
      String(input).endsWith(`/courses/${COURSE_ID}`) &&
      (options as RequestInit | undefined)?.method === 'DELETE',
    )).toBe(true)
    expect(await screen.findByText('CONTENIDO')).toBeInTheDocument()
  })

  it('stays put and shows what the server said when the delete is refused', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    installFetch(() => jsonResponse(409, { detail: 'Cannot delete a course that has enrollments', code: 'CONFLICT' }))
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Eliminar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot delete a course that has enrollments')
    expect(screen.queryByText('CONTENIDO')).toBeNull()
  })
})
