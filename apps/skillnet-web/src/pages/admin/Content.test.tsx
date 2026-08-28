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

/** Archive and delete are icons now, so the row's actions are found by their names. */
const SETTINGS_LABEL = 'Ajustes de Devoluciones en tienda'
const ARCHIVE_LABEL = 'Archivar Devoluciones en tienda'
const UNARCHIVE_LABEL = 'Desarchivar Devoluciones en tienda'
const DELETE_LABEL = 'Eliminar Devoluciones en tienda'

const COURSE_ID = '11111111-1111-4111-8111-111111111111'
const ARCHIVED_ID = '33333333-3333-4333-8333-333333333333'
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
  { onDelete, afterDelete, onUnarchive, afterUnarchive, enrollments }: {
    onDelete?: () => ReturnType<typeof jsonResponse>
    afterDelete?: unknown[]
    onUnarchive?: () => ReturnType<typeof jsonResponse>
    afterUnarchive?: unknown[]
    enrollments?: { total: number; completed: number }
  } = {},
) {
  let deleted = false
  let unarchived = false
  const impact = enrollments ?? { total: 0, completed: 0 }
  mockFetch.mockImplementation((input: string, options?: RequestInit) => {
    const url = String(input)
    // The two one-row reads the library makes before a delete, to size the warning.
    if (url.includes('/enrollments?') && options?.method !== 'POST') {
      const asked = new URL(url, 'http://test.local')
      const total = asked.searchParams.get('status') === 'completed' ? impact.completed : impact.total
      return jsonResponse(200, { items: [], total, offset: 0, limit: 1 })
    }
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
      // The server-side half of the archive: an explicit `status` wins, and otherwise
      // `include_archived=false` — which the library always sends — drops the archived
      // rows. Without this the mock would answer every query with the whole list and no
      // test here could tell the normal view from the archive.
      const asked = new URL(url, 'http://test.local')
      const wanted = asked.searchParams.get('status')
      const rows = (current as Record<string, unknown>[]).filter((row) =>
        wanted ? row.status === wanted : asked.searchParams.get('include_archived') !== 'false' || row.status !== 'archived',
      )
      return jsonResponse(200, { items: rows, total: rows.length, page: 1, size: 20 })
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
    // A draft, because the URL under test asks for drafts and the mock honours it.
    installFetch([course({ status: 'draft' })])
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

    await userEvent.click(await screen.findByRole('button', { name: SETTINGS_LABEL }))
    expect(await screen.findByText('AJUSTES', {}, { timeout: 5000 })).toBeInTheDocument()
  })

  it('offers it for a course with no modules, whose only other action is to delete it', async () => {
    installFetch([course({ id: EMPTY_COURSE_ID, module_count: 0, status: 'draft' })])
    renderPage()

    expect(await screen.findByRole('button', { name: SETTINGS_LABEL })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: DELETE_LABEL })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ver curso' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Publicar' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Overviews' })).toBeNull()
  })

  it('shows the settings button alongside the v1 row', async () => {
    installFetch()
    renderPage()

    expect(await screen.findByText('Devoluciones en tienda')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: SETTINGS_LABEL })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ver curso' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: ARCHIVE_LABEL })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Crear nuevo/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Overviews' })).toBeNull()
  })
})

/**
 * Deleting a course, and a warning sized to what it destroys.
 *
 * The reported incident was the opposite problem: a generation run left a course in
 * DRAFT, the retry published a second one, and there was no way to remove the first. The
 * fix went too narrow — only an empty draft could be deleted — so an admin who wanted a
 * published course gone had nowhere to go. Any course can be deleted now, and the
 * safeguard is the warning: a confirm when nobody finished it, and a typed-title dialog
 * when somebody did.
 */
describe('Content — deleting a course', () => {
  const draft = () => course({ status: 'draft', module_count: 0 })

  it('offers the action for a published course too, not only for a draft', async () => {
    installFetch([course({ status: 'published' })])
    renderPage()

    await screen.findByText('Devoluciones en tienda')
    expect(screen.getByRole('button', { name: DELETE_LABEL })).toBeInTheDocument()
  })

  it('does not offer it for the seeded demo course', async () => {
    installFetch([course({ status: 'draft', module_count: 0, is_demo: true })])
    renderPage()

    await screen.findByText('Devoluciones en tienda')
    expect(screen.queryByRole('button', { name: DELETE_LABEL })).toBeNull()
  })

  it('names every icon after the course, so a row of icons is still readable aloud', async () => {
    installFetch([course({ status: 'published' })])
    renderPage()

    const settings = await screen.findByRole('button', { name: SETTINGS_LABEL })
    const archive = screen.getByRole('button', { name: ARCHIVE_LABEL })
    const remove = screen.getByRole('button', { name: DELETE_LABEL })
    // Icons, not words: no text of their own, and an accessible name that is theirs.
    for (const control of [settings, archive, remove]) expect(control.textContent).toBe('')
  })

  it('names the shared slot after the action it will actually perform', async () => {
    // Archive and unarchive are one place in two states, so a generic label would tell a
    // screen reader the shape of the code instead of what the press does.
    installFetch([course({ status: 'archived' })])
    renderPage('/admin/contenido?status=archived')

    const restore = await screen.findByRole('button', { name: UNARCHIVE_LABEL })
    expect(restore.textContent).toBe('')
    expect(screen.queryByRole('button', { name: ARCHIVE_LABEL })).toBeNull()
  })

  it('keeps the three icon slots in the same order whatever the status', async () => {
    installFetch([course({ status: 'archived' })])
    renderPage('/admin/contenido?status=archived')

    await screen.findByText('Devoluciones en tienda')
    const names = screen.getAllByRole('button')
      .map((control) => control.getAttribute('aria-label'))
      .filter((label): label is string => [SETTINGS_LABEL, ARCHIVE_LABEL, UNARCHIVE_LABEL, DELETE_LABEL].includes(label ?? ''))
    expect(names).toEqual([SETTINGS_LABEL, UNARCHIVE_LABEL, DELETE_LABEL])
  })

  it('asks first, and does nothing when the confirmation is dismissed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    installFetch([draft()])
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: DELETE_LABEL }))

    await waitFor(() => expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('Devoluciones en tienda')))
    expect(mockFetch.mock.calls.some(([, options]) => (options as RequestInit | undefined)?.method === 'DELETE')).toBe(false)
  })

  it('deletes the course and refreshes the list once confirmed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    installFetch([draft()], { afterDelete: [] })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: DELETE_LABEL }))

    await waitFor(() => expect(mockFetch.mock.calls.some(([input, options]) =>
      String(input).includes(`/courses/${COURSE_ID}`) &&
      (options as RequestInit | undefined)?.method === 'DELETE',
    )).toBe(true))
    expect(await screen.findByText('Aún no hay cursos')).toBeInTheDocument()
  })

  it('counts the enrollments before asking, and says how many in the confirm', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    installFetch([course({ status: 'published' })], { enrollments: { total: 7, completed: 0 }, afterDelete: [] })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: DELETE_LABEL }))

    await waitFor(() => expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('7 matrículas')))
  })

  it('explains a refused delete in the admin\'s language, on the row that failed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    installFetch([draft()], {
      onDelete: () => jsonResponse(409, { detail: 'This course is still referenced by other records and cannot be deleted. Archive it instead.', code: 'CONFLICT' }),
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: DELETE_LABEL }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/algo m\u00e1s sigue apuntando a este curso/)
    expect(screen.getByText('Devoluciones en tienda')).toBeInTheDocument()
  })

  it('deletes nothing when the enrollment counts cannot be read', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    installFetch([course({ status: 'published' })])
    renderPage()

    const remove = await screen.findByRole('button', { name: DELETE_LABEL })
    // Guessing "nobody is enrolled" would silently downgrade the dialog into a confirm,
    // which is the one wrong answer available here.
    mockFetch.mockImplementation(() => Promise.reject(new TypeError('offline')))
    await userEvent.click(remove)

    expect(await screen.findByRole('alert')).toHaveTextContent(/No se pudo comprobar/)
    expect(confirmSpy).not.toHaveBeenCalled()
    expect(mockFetch.mock.calls.some(([, options]) => (options as RequestInit | undefined)?.method === 'DELETE')).toBe(false)
  })
})

/**
 * The delete that reaches somebody else's record.
 *
 * A confirm is dismissed with the same gesture whether it was read or not, and what is
 * destroyed here is other people's completed training. So the numbers are exact and the
 * course title has to be typed back before the button does anything.
 */
describe('Content — deleting a course somebody completed', () => {
  it('asks for the title instead of a confirm, and says the exact numbers', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    installFetch([course({ status: 'published' })], { enrollments: { total: 34, completed: 12 } })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: DELETE_LABEL }))

    const dialog = await screen.findByRole('dialog')
    expect(confirmSpy).not.toHaveBeenCalled()
    expect(within(dialog).getByText(/34/)).toBeInTheDocument()
    expect(within(dialog).getByText(/12/)).toBeInTheDocument()
  })

  it('keeps the delete button disabled until the title is typed back', async () => {
    installFetch([course({ status: 'published' })], { enrollments: { total: 34, completed: 12 }, afterDelete: [] })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: DELETE_LABEL }))
    const dialog = await screen.findByRole('dialog')
    const confirm = within(dialog).getByRole('button', { name: 'Eliminar el curso' })
    expect(confirm).toBeDisabled()

    const field = within(dialog).getByLabelText(/Escribe/)
    await userEvent.type(field, 'Devoluciones')
    expect(confirm).toBeDisabled()
    expect(mockFetch.mock.calls.some(([, options]) => (options as RequestInit | undefined)?.method === 'DELETE')).toBe(false)

    await userEvent.type(field, ' en tienda')
    expect(confirm).toBeEnabled()

    await userEvent.click(confirm)
    await waitFor(() => expect(mockFetch.mock.calls.some(([input, options]) =>
      String(input).includes(`/courses/${COURSE_ID}`) &&
      (options as RequestInit | undefined)?.method === 'DELETE',
    )).toBe(true))
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

/**
 * The archive is a place, not a filter — the WhatsApp shape.
 *
 * Archiving used to hide a course from the learners and leave it in the admin's list, so
 * tidying the library left the library exactly as full as before. Archived courses are
 * out of the normal view entirely now, behind one entry that carries their count.
 */
describe('Content — the archive', () => {
  const live = () => course({ status: 'published' })
  const shelved = () => course({ id: ARCHIVED_ID, title: 'Manual antiguo', status: 'archived' })

  it('keeps archived courses out of the normal view and offers them behind their count', async () => {
    installFetch([live(), shelved()])
    renderPage()

    expect(await screen.findByText('Devoluciones en tienda')).toBeInTheDocument()
    expect(screen.queryByText('Manual antiguo')).toBeNull()
    // The list is asked for it server-side, not filtered after the fact.
    expect(mockFetch.mock.calls.some(([input]) =>
      String(input).includes('/courses?') && String(input).includes('include_archived=false'),
    )).toBe(true)

    const entry = screen.getByRole('button', { name: /Archivados/ })
    expect(within(entry).getByText('1')).toBeInTheDocument()
  })

  it('shows them once you go in, and lets you come back out', async () => {
    installFetch([live(), shelved()])
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: /Archivados/ }))

    expect(await screen.findByText('Manual antiguo')).toBeInTheDocument()
    expect(screen.queryByText('Devoluciones en tienda')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'Biblioteca' }))

    expect(await screen.findByText('Devoluciones en tienda')).toBeInTheDocument()
    expect(screen.queryByText('Manual antiguo')).toBeNull()
  })

  it('does not offer the entry when nothing is archived', async () => {
    installFetch([live()])
    renderPage()

    await screen.findByText('Devoluciones en tienda')
    expect(screen.queryByRole('button', { name: /Archivados/ })).toBeNull()
  })

  it('says so when the archive is empty, instead of offering to create a course', async () => {
    installFetch([live()])
    renderPage('/admin/contenido?status=archived')

    expect(await screen.findByText('No hay nada archivado')).toBeInTheDocument()
  })

  it('drops the archived option from the status dropdown', async () => {
    installFetch([live(), shelved()])
    renderPage()

    await screen.findByText('Devoluciones en tienda')
    // The entry is the one door in; a second one in the dropdown would contradict it.
    expect(screen.queryByRole('option', { name: 'Archivados' })).toBeNull()
    expect(screen.getByRole('option', { name: 'Borradores' })).toBeInTheDocument()
  })
})

/** Archiving was a one-way door: an archived row had no action left that did anything. */
describe('Content — unarchiving', () => {
  it('offers the way back and calls the endpoint', async () => {
    installFetch([course({ status: 'archived' })])
    renderPage('/admin/contenido?status=archived')

    await userEvent.click(await screen.findByRole('button', { name: UNARCHIVE_LABEL }))

    expect(mockFetch.mock.calls.some(([input, options]) =>
      String(input).includes(`/courses/${COURSE_ID}/unarchive`) &&
      (options as RequestInit | undefined)?.method === 'POST',
    )).toBe(true)
  })

  it('brings the row back into the library as published, not as a draft', async () => {
    // `published` is the status the course had — archive only accepts a published
    // course — so the restored row offers Archive again, and never Publish.
    installFetch([course({ status: 'archived' })], {
      afterUnarchive: [course({ status: 'published' })],
    })
    renderPage('/admin/contenido?status=archived')

    await userEvent.click(await screen.findByRole('button', { name: UNARCHIVE_LABEL }))

    // It leaves the archive it was in...
    expect(await screen.findByText('No hay nada archivado')).toBeInTheDocument()
    // ...and is waiting in the library, with its Archive icon and no Publish button.
    await userEvent.click(screen.getByRole('button', { name: 'Biblioteca' }))
    expect(await screen.findByRole('button', { name: ARCHIVE_LABEL })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: UNARCHIVE_LABEL })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Publicar' })).toBeNull()
  })

  it('does not offer it for a published course', async () => {
    installFetch([course({ status: 'published' })])
    renderPage()

    await screen.findByText('Devoluciones en tienda')
    expect(screen.queryByRole('button', { name: UNARCHIVE_LABEL })).toBeNull()
  })

  it('says the course is no longer archived, in the admin\'s language', async () => {
    installFetch([course({ status: 'archived' })], {
      onUnarchive: () => jsonResponse(409, { detail: 'Only archived courses can be unarchived', code: 'CONFLICT' }),
    })
    renderPage('/admin/contenido?status=archived')

    await userEvent.click(await screen.findByRole('button', { name: UNARCHIVE_LABEL }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/ya no est\u00e1 archivado/)
  })

  /**
   * The reported bug: pressing Desarchivar showed "An outcome is required to publish" —
   * English, and about an action the admin never took. Unarchiving does republish, and
   * re-running the publish checks is right, but that is the code's business.
   */
  it('translates a refused republish into the action the admin actually pressed', async () => {
    installFetch([course({ status: 'archived' })], {
      onUnarchive: () => jsonResponse(422, { detail: 'An outcome is required to publish', code: 'VALIDATION_ERROR', field: 'outcome' }),
    })
    renderPage('/admin/contenido?status=archived')

    await userEvent.click(await screen.findByRole('button', { name: UNARCHIVE_LABEL }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/Para desarchivarlo hay que volver a publicarlo/)
    expect(alert).toHaveTextContent(/le falta el objetivo/)
    expect(alert.textContent).not.toContain('publish')
  })

  it('never leaves a failed action without a visible answer next to it', async () => {
    // The second half of the same incident: with no feedback anywhere the admin could
    // see, the only reading available was "the click did not register", so they pressed
    // again. The message now renders inside the row that failed.
    installFetch([course({ status: 'archived' })], {
      onUnarchive: () => jsonResponse(422, { detail: 'An outcome is required to publish', code: 'VALIDATION_ERROR', field: 'outcome' }),
    })
    renderPage('/admin/contenido?status=archived')

    const button = await screen.findByRole('button', { name: UNARCHIVE_LABEL })
    await userEvent.click(button)

    // The alert is a direct child of the row's Card, and that Card holds the button.
    const alert = await screen.findByRole('alert')
    expect(alert.parentElement?.contains(button)).toBe(true)
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
    expect(screen.queryByRole('button', { name: /^Archivar/ })).toBeNull()
  })
})
