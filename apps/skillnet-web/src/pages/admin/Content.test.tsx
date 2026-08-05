import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
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

function installFetch(items: unknown[] = [course()]) {
  mockFetch.mockImplementation((input: string) => {
    const url = String(input)
    if (url.endsWith('/health')) {
      return jsonResponse(200, {
        status: 'ok',
        version: '1',
        database: 'ok',
      })
    }
    if (url.includes('/courses')) {
      return jsonResponse(200, { items, total: items.length, page: 1, size: 20 })
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
      <MemoryRouter initialEntries={['/admin/contenido']}>
        <Routes>
          <Route path="/admin/contenido" element={<Content />} />
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

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Content — the schema entry point', () => {
  it('opens the schema screen of an existing course', async () => {
    installFetch()
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Esquema' }))
    // A longer timeout than the 1000 ms default, and it is not papering over anything:
    // this is the only assertion in the file that waits on a *route change* rather than
    // on a render, and with 33 test files across parallel workers it intermittently
    // exceeded the default on a loaded machine. It passes alone every time. The
    // assertion is unchanged — the sentinel still has to be in the document.
    expect(await screen.findByText('ESQUEMA', {}, { timeout: 5000 })).toBeInTheDocument()
  })

  it('offers it for a course with no modules, which has no other action at all', async () => {
    installFetch([course({ id: EMPTY_COURSE_ID, module_count: 0, status: 'draft' })])
    renderPage()

    expect(await screen.findByRole('button', { name: 'Esquema' })).toBeInTheDocument()
    // A schema-first course is created empty: without this link the row is a dead end.
    expect(screen.queryByRole('button', { name: 'Ver curso' })).toBeNull()
  })

  it('shows the schema button alongside the v1 row', async () => {
    installFetch()
    renderPage()

    expect(await screen.findByText('Devoluciones en tienda')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Esquema' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ver curso' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Crear nuevo/ })).toBeInTheDocument()
  })
})
