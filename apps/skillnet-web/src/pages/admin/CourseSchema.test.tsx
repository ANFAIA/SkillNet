import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CourseSchema } from './CourseSchema'
import type { CourseSchema as CourseSchemaRead, CourseSchemaNode } from '../../types'

/**
 * The gate, from the creator's side.
 *
 * Three behaviours are tested because each one is a promise that fails silently if it
 * regresses: validation cannot be reached while a node is unreviewed (§11.1 rule 2),
 * `422 schema_locked` reaches the screen with the server's own sentence instead of
 * being flattened into "error al guardar" (rule 1), and a detected prerequisite cycle
 * is shown to the person who can fix it rather than swallowed.
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
      return jsonResponse(200, { status: 'ok', features: { dynamic_courses: 'shadow' } })
    }
    if (url.endsWith(`/courses/${COURSE_ID}/schema`) && method === 'GET') {
      return jsonResponse(200, handlers.schema)
    }
    if (url.endsWith(`/courses/${COURSE_ID}/schema`) && method === 'PUT') {
      const [status, body] = handlers.put ?? [200, handlers.schema]
      return jsonResponse(status, body)
    }
    if (url.endsWith('/schema/validate')) {
      const [status, body] = handlers.validate ?? [200, handlers.schema]
      return jsonResponse(status, body)
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
          {/* Sentinels for the two back-links. */}
          <Route path="/admin/curso/:id" element={<div>PREVIEW</div>} />
          <Route path="/admin/contenido" element={<div>CONTENIDO</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function validateButton() {
  return screen.getByRole('button', { name: 'Validar esquema' })
}

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('CourseSchema', () => {
  it('says nothing is generated until the schema is validated', async () => {
    installFetch({ schema: schema() })
    renderPage()

    expect(await screen.findByText('Todavia no se genera nada')).toBeInTheDocument()
  })

  describe('the validate button', () => {
    it('is disabled while a node has no reviewed_at, and says how many', async () => {
      installFetch({
        schema: schema({
          nodes: [
            node({ id: NODE_A }),
            node({ id: NODE_B, position: 2, title: 'Excepciones', reviewed_at: null }),
          ],
        }),
      })
      renderPage()

      await screen.findByLabelText('Titulo')
      expect(validateButton()).toBeDisabled()
      expect(screen.getByText('Queda 1 nodo sin revisar.')).toBeInTheDocument()
      // The reason is on the checklist too — that is where the fix happens.
      expect(screen.getByText('Queda 1 nodo por revisar antes de poder validar.')).toBeInTheDocument()
    })

    it('is enabled once every live node is reviewed and nothing is dirty', async () => {
      installFetch({ schema: schema({ nodes: [node({ id: NODE_A })] }) })
      renderPage()

      await screen.findByLabelText('Titulo')
      await waitFor(() => expect(validateButton()).toBeEnabled())
      expect(
        screen.getByText('Todos los nodos estan revisados. Ya puedes validar el esquema.'),
      ).toBeInTheDocument()
    })

    it('is disabled while there are unsaved edits, because the server validates its own copy', async () => {
      installFetch({ schema: schema() })
      renderPage()

      await screen.findByLabelText('Titulo')
      await waitFor(() => expect(validateButton()).toBeEnabled())

      await userEvent.type(screen.getByLabelText('Titulo'), ' urgente')

      expect(validateButton()).toBeDisabled()
      expect(
        screen.getByText(
          'Guarda los cambios antes de validar: se valida lo que hay en el servidor.',
        ),
      ).toBeInTheDocument()
    })
  })

  describe('schema_locked', () => {
    it('prints the server message and offers unvalidate when a save is refused', async () => {
      const message =
        'Este esquema esta validado. Usa /schema/unvalidate antes de editarlo.'
      installFetch({
        schema: schema(),
        put: [422, { detail: { code: 'schema_locked', message } }],
      })
      renderPage()

      await screen.findByLabelText('Titulo')
      await userEvent.type(screen.getByLabelText('Titulo'), '!')
      await userEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))

      expect(await screen.findByText(message)).toBeInTheDocument()
      expect(screen.getByText('No se guardo nada')).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'Sacar de validacion' }),
      ).toBeInTheDocument()
    })

    it('shows the lock and the way out when the schema is already validated', async () => {
      installFetch({ schema: schema({ schema_status: 'validated', delivery_mode: 'dynamic' }) })
      renderPage()

      expect(await screen.findByText('Esquema validado y en servicio')).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'Sacar de validacion' }),
      ).toBeInTheDocument()
      // Locked means locked: the fields are not editable and saving is impossible.
      expect(screen.getByLabelText('Titulo')).toBeDisabled()
      expect(screen.getByRole('button', { name: 'Guardar cambios' })).toBeDisabled()
    })
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

      await screen.findByLabelText('Titulo')
      await waitFor(() => expect(validateButton()).toBeEnabled())
      await userEvent.click(validateButton())

      expect(
        await screen.findByText('Los prerrequisitos forman un ciclo'),
      ).toBeInTheDocument()
      expect(
        screen.getByText(
          'Ciclo: 1. Plazo de devolucion -> 2. Excepciones -> 1. Plazo de devolucion',
        ),
      ).toBeInTheDocument()
      // Not swallowed into a generic failure.
      expect(screen.queryByText('No se pudo completar la operacion.')).not.toBeInTheDocument()
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

      await screen.findByLabelText('Titulo')
      await waitFor(() => expect(validateButton()).toBeEnabled())
      await userEvent.click(validateButton())

      expect(await screen.findByText('Hay nodos sin resumen')).toBeInTheDocument()
      expect(screen.getByText('Ningun nodo es critico')).toBeInTheDocument()
      expect(screen.getByText('2. Excepciones')).toBeInTheDocument()
      expect(
        screen.getByText('No se puede validar todavia: 2 problemas'),
      ).toBeInTheDocument()
    })
  })

  describe('back-links', () => {
    it('returns to the course it belongs to', async () => {
      installFetch({ schema: schema() })
      renderPage()

      await screen.findByLabelText('Titulo')
      await userEvent.click(screen.getByRole('button', { name: '← Volver al curso' }))

      expect(await screen.findByText('PREVIEW')).toBeInTheDocument()
    })

    it('still returns to the course list', async () => {
      installFetch({ schema: schema() })
      renderPage()

      await screen.findByLabelText('Titulo')
      await userEvent.click(screen.getByRole('button', { name: '← Contenido' }))

      expect(await screen.findByText('CONTENIDO')).toBeInTheDocument()
    })
  })

  it('explains that the surface is off instead of showing a broken screen', async () => {
    mockFetch.mockImplementation(() => jsonResponse(404, { detail: 'Not Found' }))
    renderPage()

    expect(
      await screen.findByText('Los cursos dinamicos estan desactivados'),
    ).toBeInTheDocument()
  })
})
