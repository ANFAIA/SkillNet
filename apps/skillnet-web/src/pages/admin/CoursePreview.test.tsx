import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CoursePreview } from './CoursePreview'
import type { DynamicCoursesMode } from '../../api/health'

/**
 * The second door to the schema screen: the course the creator already has open.
 *
 * Same gate as the list — the global flag, never `delivery_mode` — and the same
 * non-regression: with the flag `off` the action row is the v1 one, nothing more.
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

function installFetch(mode: DynamicCoursesMode) {
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
          <Route path="/admin/curso/:id/esquema" element={<div>ESQUEMA</div>} />
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

describe('CoursePreview — the schema entry point', () => {
  it('opens the schema of the course on screen in shadow mode', async () => {
    installFetch('shadow')
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Esquema' }))
    expect(await screen.findByText('ESQUEMA')).toBeInTheDocument()
  })

  it('offers the link with the flag on too', async () => {
    installFetch('on')
    renderPage()

    expect(await screen.findByRole('button', { name: 'Esquema' })).toBeInTheDocument()
  })
})

describe('CoursePreview — flag off', () => {
  it('shows no v2 affordance and leaves the v1 action row intact', async () => {
    installFetch('off')
    renderPage()

    expect(await screen.findByRole('button', { name: 'Editar' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Esquema' })).toBeNull()
    // The v1 row, unchanged: edit, publish a draft, and the way back.
    expect(screen.getByRole('button', { name: 'Publicar' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '← Contenido' })).toBeInTheDocument()
  })
})
