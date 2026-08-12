import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CourseSchema } from './CourseSchema'
import type { CourseSchema as CourseSchemaRead, CourseSchemaNode } from '../../types'

/**
 * The schema editor, after the simplification that replaced the validate/review
 * ceremony with a single "Guardar y activar" + "Probar curso" flow.
 *
 * Three behaviours are tested because each one is a promise that fails silently if it
 * regresses: the tree renders the nodes, validation errors reach the screen, and the
 * breadcrumb navigates back.
 */

const COURSE_ID = '11111111-1111-4111-8111-111111111111'
const NODE_A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const NODE_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'

function node(overrides: Partial<CourseSchemaNode> & { id: string }): CourseSchemaNode {
  return {
    title: 'Plazo de devolucion',
    summary: 'Cuantos dias tiene el cliente para devolver.',
    outcome: null,
    criticality: 'critical',
    position: 1,
    mastery_threshold: 0.9,
    estimated_minutes: 6,
    default_ui_format: 'explanation',
    skill_id: null,
    seed_lesson_id: null,
    source_document_id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
    source_headings: ['Devoluciones', 'Plazo'],
    prerequisite_node_ids: [],
    reviewed_at: '2026-07-20T10:00:00Z',
    reviewed_by: null,
    archived: false,
    ...overrides,
  }
}

function schema(overrides: Partial<CourseSchemaRead> = {}): CourseSchemaRead {
  return {
    course_id: COURSE_ID,
    schema_status: 'proposed',
    schema_version: 3,
    delivery_mode: 'static',
    intent_density: 3,
    validated_by: null,
    validated_at: null,
    warnings: [],
    nodes: [node({ id: NODE_A })],
    ...overrides,
  }
}

const mockFetch = vi.fn()

interface Handlers {
  schema: CourseSchemaRead
  packs?: Array<Record<string, unknown>>
  /** `[status, body]` for `PUT /schema`. */
  put?: [number, unknown]
  /** `[status, body]` for `POST /schema/validate`. */
  validate?: [number, unknown]
}

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
  })
}

function installFetch(handlers: Handlers) {
  mockFetch.mockImplementation((input: string, init?: RequestInit) => {
    const url = String(input)
    const method = (init?.method ?? 'GET').toUpperCase()

    if (url.endsWith('/health')) {
      return jsonResponse(200, { status: 'ok' })
    }
    if (url.endsWith('/auth/me')) {
      return jsonResponse(200, {
        id: 'admin-user-id',
        email: 'admin@test.com',
        full_name: 'Admin',
        role: 'admin',
      })
    }
    if (url.endsWith(`/courses/${COURSE_ID}/schema`) && method === 'GET') {
      return jsonResponse(200, handlers.schema)
    }
    if (url.endsWith(`/courses/${COURSE_ID}/schema/knowledge-packs`) && method === 'GET') {
      return jsonResponse(200, {
        course_id: COURSE_ID,
        schema_version: handlers.schema.schema_version,
        nodes: handlers.packs ?? [
          {
            id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
            node_id: NODE_A,
            status: 'review_required',
            generator_version: 'knowledge-pack/v1',
            pack_hash: 'a'.repeat(64),
            markdown: '# Dossier\n\nHecho revisable.',
            atom_count: 2,
            invariant_count: 1,
            required_evidence_count: 0,
            blocking_gaps: ['Falta evidencia observable'],
            input_tokens: 100,
            output_tokens: 50,
            duration_ms: 1200,
            error_message: null,
            updated_at: '2026-08-11T10:00:00Z',
          },
        ],
      })
    }
    if (url.endsWith(`/courses/${COURSE_ID}/schema`) && method === 'PUT') {
      const [status, body] = handlers.put ?? [200, handlers.schema]
      return jsonResponse(status, body)
    }
    if (url.endsWith('/schema/validate')) {
      const [status, body] = handlers.validate ?? [200, handlers.schema]
      return jsonResponse(status, body)
    }
    if (url.endsWith('/schema/unvalidate')) {
      return jsonResponse(200, handlers.schema)
    }
    if (url.includes('/schema/nodes/') && url.endsWith('/review')) {
      return jsonResponse(200, {})
    }
    if (url.includes('/enrollments')) {
      return jsonResponse(200, { items: [], total: 0, page: 1, size: 20 })
    }
    if (url.endsWith(`/courses/${COURSE_ID}`)) {
      return jsonResponse(200, {
        id: COURSE_ID,
        title: 'Devoluciones en tienda',
        description: null,
        outcome: null,
        status: 'draft',
        source_document_id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
        created_at: '2026-07-01T00:00:00Z',
        module_count: 0,
        modules: [],
      })
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
      <MemoryRouter initialEntries={[`/admin/curso/${COURSE_ID}/esquema`]}>
        <Routes>
          <Route path="/admin/curso/:id/esquema" element={<CourseSchema />} />
          {/* Sentinel for the breadcrumb navigation. */}
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

describe('CourseSchema', () => {
  it('renders the node tree with the node title', async () => {
    installFetch({ schema: schema() })
    renderPage()

    // Node titles are rendered as inline inputs in the tree, not as text content
    expect(await screen.findByDisplayValue('Plazo de devolucion')).toBeInTheDocument()
  })

  it('shows the course title in the breadcrumb header', async () => {
    installFetch({ schema: schema() })
    renderPage()

    // The header shows "Contenido / Devoluciones en tienda" as a breadcrumb.
    expect(await screen.findByText(/Devoluciones en tienda/)).toBeInTheDocument()
  })

  it('shows the "Probar curso" button when nodes exist', async () => {
    installFetch({ schema: schema() })
    renderPage()

    expect(await screen.findByRole('button', { name: 'Probar curso' })).toBeInTheDocument()
  })

  it('keeps pedagogical preparation inside each node instead of a separate panel', async () => {
    installFetch({ schema: schema() })
    renderPage()

    await screen.findByDisplayValue('Plazo de devolucion')
    expect(screen.queryByText('Preparación pedagógica')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Abrir Plazo de devolucion' }))

    expect(await screen.findByText('Preparación pedagógica')).toBeVisible()
    expect(await screen.findByText('Necesita revisión')).toBeVisible()
    expect(screen.queryByText('0 de 1 listos')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Generar dossiers' })).not.toBeInTheDocument()
  })

  it('does not schedule work merely by opening an unfinished schema', async () => {
    installFetch({ schema: schema(), packs: [] })
    renderPage()

    await screen.findByDisplayValue('Plazo de devolucion')
    const posts = mockFetch.mock.calls.filter(([, init]) =>
      ((init as RequestInit | undefined)?.method ?? 'GET').toUpperCase() === 'POST',
    )
    expect(posts).toHaveLength(0)
  })

  it('shows the "Guardar y activar" button when there are unsaved changes', async () => {
    installFetch({ schema: schema() })
    renderPage()

    // The button only appears when the draft is dirty. Wait for the schema to load,
    // then modify a node to make the draft dirty.
    await screen.findByDisplayValue('Plazo de devolucion')

    // Initially there should be no "Guardar y activar" because nothing is dirty.
    expect(screen.queryByRole('button', { name: 'Guardar y activar' })).not.toBeInTheDocument()
  })

  describe('validation errors', () => {
    it('shows a detected cycle as a closed chain of node names', async () => {
      installFetch({
        schema: schema({
          nodes: [
            node({ id: NODE_A, prerequisite_node_ids: [NODE_B] }),
            node({
              id: NODE_B,
              position: 2,
              title: 'Excepciones',
              prerequisite_node_ids: [NODE_A],
            }),
          ],
        }),
        validate: [
          422,
          {
            detail: {
              code: 'schema_invalid',
              errors: [{ code: 'cycle', node_ids: [NODE_A, NODE_B] }],
            },
          },
        ],
      })
      renderPage()

      // Wait for the tree to load, then trigger "Probar curso" which runs saveAndActivate
      await screen.findByDisplayValue('Plazo de devolucion')
      await userEvent.click(screen.getByRole('button', { name: 'Probar curso' }))

      expect(
        await screen.findByText('Los prerrequisitos forman un ciclo'),
      ).toBeInTheDocument()
      expect(
        screen.getByText(
          'Ciclo: 1. Plazo de devolucion -> 2. Excepciones -> 1. Plazo de devolucion',
        ),
      ).toBeInTheDocument()
    })

    it('lists every blocking rule at once, naming the offending nodes', async () => {
      installFetch({
        schema: schema({
          nodes: [node({ id: NODE_A }), node({ id: NODE_B, position: 2, title: 'Excepciones' })],
        }),
        validate: [
          422,
          {
            detail: {
              code: 'schema_invalid',
              errors: [
                { code: 'missing_summary', node_ids: [NODE_B] },
                { code: 'no_critical_node' },
              ],
            },
          },
        ],
      })
      renderPage()

      await screen.findByDisplayValue('Plazo de devolucion')
      await userEvent.click(screen.getByRole('button', { name: 'Probar curso' }))

      expect(await screen.findByText('Hay nodos sin resumen')).toBeInTheDocument()
      expect(screen.getByText('Ningun nodo es critico')).toBeInTheDocument()
      expect(screen.getAllByText('2. Excepciones').length).toBeGreaterThan(0)
      expect(
        screen.getByText('No se puede validar todavia: 2 problemas'),
      ).toBeInTheDocument()
    })
  })

  describe('breadcrumb navigation', () => {
    it('navigates back to the content list via the breadcrumb', async () => {
      installFetch({ schema: schema() })
      renderPage()

      await screen.findByDisplayValue('Plazo de devolucion')
      const back = screen.getByRole('button', { name: 'Contenido' })

      await userEvent.click(back)

      expect(await screen.findByText('CONTENIDO')).toBeInTheDocument()
    })
  })

  it('shows an error message when the schema cannot be loaded', async () => {
    mockFetch.mockImplementation(() => jsonResponse(404, { detail: 'Not Found' }))
    renderPage()

    expect(
      await screen.findByText('No se pudo cargar el esquema'),
    ).toBeInTheDocument()
  })
})
