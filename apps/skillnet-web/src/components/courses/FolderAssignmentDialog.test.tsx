import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FolderAssignmentDialog } from './FolderAssignmentDialog'

/**
 * The dialog manages who holds a folder: ticking assigns it, unticking takes it back.
 *
 * Both halves used to be wrong in the same place — the tick. It came from a `selected`
 * list that starts empty, so a person already enrolled in every course of the folder
 * rendered UNTICKED, identical to someone who had never been assigned anything. Fixing
 * that by ticking *and disabling* the row swapped one lie for another: the box was then
 * honest about the state and dead as a control. It is now live, with the one boundary the
 * server actually draws — `DELETE /enrollments/{id}` answers 409 for anything that is not
 * still `assigned` — spelled out in words on the row it locks.
 */

const FOLDER_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const COURSE_A = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
const COURSE_B = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
/** Holds both courses, neither started: fully revocable. */
const ANA = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'
/** Holds both courses and has started both: nothing left to revoke. */
const BRUNO = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'
/** Holds nothing. */
const CARLA = 'ffffffff-ffff-4fff-8fff-ffffffffffff'
/** Holds both, started one of them: revocable in part. */
const DIEGO = '11111111-1111-4111-8111-111111111111'

type Enrollment = {
  id: string
  user_id: string
  course_id: string
  status: 'assigned' | 'in_progress' | 'completed'
}

const mockFetch = vi.fn()

function jsonResponse(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) })
}

function noContent() {
  return Promise.resolve({ ok: true, status: 204, json: () => Promise.reject(new Error('no body')) })
}

function conflict(detail: string) {
  return Promise.resolve({ ok: false, status: 409, json: () => Promise.resolve({ detail }) })
}

function user(id: string, name: string) {
  return { id, email: `${name}@example.com`, full_name: name, role: 'employee', is_active: true }
}

function enrollment(userId: string, courseId: string, status: Enrollment['status'] = 'assigned'): Enrollment {
  return { id: `${userId}:${courseId}`, user_id: userId, course_id: courseId, status }
}

/** Every enrollment the fake API knows about, across both published courses. */
const ENROLLMENTS: Enrollment[] = [
  enrollment(ANA, COURSE_A),
  enrollment(ANA, COURSE_B),
  enrollment(BRUNO, COURSE_A, 'in_progress'),
  enrollment(BRUNO, COURSE_B, 'completed'),
  enrollment(DIEGO, COURSE_A, 'in_progress'),
  enrollment(DIEGO, COURSE_B),
]

type Call = { method: string; url: string; body: unknown }

/**
 * Two published courses in the folder and four employees covering the four states the
 * tick has to distinguish: whole folder revocable, whole folder stuck, nothing yet, and
 * half-and-half.
 *
 * `conflictOn` makes the fake API answer 409 for the given enrollment ids, which is the
 * race the dialog has to survive: the person started that course between the list being
 * read and the click.
 */
function installFetch(
  options: {
    conflictOn?: string[]
    groups?: { id: string; name: string; member_count: number }[]
    /** Override the folder's published-course count, which sets the people page size. */
    publishedCourses?: number
    /** Extra nameless employees, to push the roster past one page. */
    extraPeople?: number
  } = {},
) {
  const calls: Call[] = []
  const conflicting = new Set(options.conflictOn ?? [])
  mockFetch.mockImplementation((input: string, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    calls.push({ method, url, body })

    if (method === 'DELETE' && url.includes('/enrollments/')) {
      const id = decodeURIComponent(url.split('/enrollments/')[1])
      return conflicting.has(id)
        ? conflict('Only assigned (not started) enrollments can be removed')
        : noContent()
    }
    if (method === 'POST' && url.includes('/assign')) {
      return jsonResponse({
        course_count: 2,
        created_count: 2,
        skipped_existing_count: 0,
        person_count: 1,
        skipped_inactive_count: 0,
      })
    }
    if (url.includes('/user-groups')) {
      // Paginated and searchable like the real endpoint: filtering here in the fake is
      // what lets a test assert that the component is NOT filtering in the browser.
      const query = new URLSearchParams(url.split('?')[1] ?? '')
      const offset = Number(query.get('offset') ?? 0)
      const limit = Number(query.get('limit') ?? 25)
      const search = (query.get('search') ?? '').toLowerCase()
      const all = (options.groups ?? []).filter(
        (group) => !search || group.name.toLowerCase().includes(search),
      )
      return jsonResponse({
        items: all.slice(offset, offset + limit),
        total: all.length,
        offset,
        limit,
      })
    }
    if (url.includes('/users')) {
      // Paginated like the real endpoint, so a test can put a person on page two and
      // assert that the dialog still knows where they went.
      const query = new URLSearchParams(url.split('?')[1] ?? '')
      const offset = Number(query.get('offset') ?? 0)
      const limit = Number(query.get('limit') ?? 25)
      const search = (query.get('search') ?? '').toLowerCase()
      const extra = Array.from({ length: options.extraPeople ?? 0 }, (_, index) =>
        user(`extra-${index}`, `Extra ${index}`),
      )
      const all = [user(ANA, 'Ana'), user(BRUNO, 'Bruno'), user(CARLA, 'Carla'), user(DIEGO, 'Diego'), ...extra]
        .filter((person) => !search || person.full_name.toLowerCase().includes(search))
      return jsonResponse({
        items: all.slice(offset, offset + limit),
        total: all.length,
        offset,
        limit,
      })
    }
    if (url.includes('/courses')) {
      if (options.publishedCourses) {
        // Only the count matters for the page-size arithmetic; the titles are only used
        // to name a course in a removal message.
        return jsonResponse({ items: [], total: options.publishedCourses, offset: 0, limit: 100 })
      }
      return jsonResponse({
        items: [
          { id: COURSE_A, title: 'Curso A', status: 'published', folder_id: FOLDER_ID, module_count: 1, delivery_mode: 'static', created_at: '2026-07-01T00:00:00Z', description: null, outcome: null, source_document_id: null },
          { id: COURSE_B, title: 'Curso B', status: 'published', folder_id: FOLDER_ID, module_count: 1, delivery_mode: 'static', created_at: '2026-07-01T00:00:00Z', description: null, outcome: null, source_document_id: null },
        ],
        total: 2,
        offset: 0,
        limit: 100,
      })
    }
    if (url.includes('/enrollments')) {
      // One filtered read for the whole page: `?folder_id=` resolves to the folder's
      // published courses server-side and `?user_ids=` narrows it to the rows on screen.
      const query = new URLSearchParams(url.split('?')[1] ?? '')
      const wanted = new Set(query.getAll('user_ids'))
      const items = ENROLLMENTS.filter((row) => wanted.size === 0 || wanted.has(row.user_id)).map(
        (row) => ({
          ...row,
          course_title: row.course_id === COURSE_A ? 'Curso A' : 'Curso B',
          deadline: null,
          score: null,
          progress: 0,
          started_at: null,
          completed_at: null,
          delivery_mode: 'static',
        }),
      )
      return jsonResponse({ items, total: items.length, offset: 0, limit: 100 })
    }
    return jsonResponse({ items: [], total: 0, offset: 0, limit: 50 })
  })
  return calls
}

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <FolderAssignmentDialog
        folder={{ id: FOLDER_ID, name: 'Operaciones', course_count: 2, created_at: '2026-07-01T00:00:00Z', updated_at: '2026-07-01T00:00:00Z' }}
        onClose={() => {}}
      />
    </QueryClientProvider>,
  )
}

/** The checkbox in the same row as `name`. */
function boxFor(name: string): HTMLInputElement {
  const row = screen.getByText(name).closest('label')
  if (!row) throw new Error(`no encontré la fila de ${name}`)
  const box = row.querySelector('input[type="checkbox"]')
  if (!box) throw new Error(`la fila de ${name} no tiene checkbox`)
  return box as HTMLInputElement
}

function rowText(name: string): string {
  return screen.getByText(name).closest('label')?.textContent ?? ''
}

/** The DELETE calls the fake API received, by enrollment id. */
function deletedIds(calls: Call[]): string[] {
  return calls
    .filter((call) => call.method === 'DELETE')
    .map((call) => decodeURIComponent(call.url.split('/enrollments/')[1]))
}

function assignCalls(calls: Call[]): Call[] {
  return calls.filter((call) => call.method === 'POST' && call.url.includes('/assign'))
}

/** Wait until the enrollment reads have landed and the ticks reflect them. */
async function waitForTicks() {
  expect(await screen.findByText('Ana')).toBeInTheDocument()
  await waitFor(() => expect(boxFor('Ana').checked).toBe(true))
}

describe('FolderAssignmentDialog', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    mockFetch.mockReset()
  })

  describe('what the tick says', () => {
    it('ticks the person who already holds every published course of the folder', async () => {
      installFetch()
      renderDialog()
      await waitForTicks()
      expect(boxFor('Ana').checked).toBe(true)
      // And the tick is a live control now, not a read-only badge.
      expect(boxFor('Ana').disabled).toBe(false)
    })

    it('leaves someone with none of the folder unticked and selectable', async () => {
      installFetch()
      renderDialog()
      await waitForTicks()
      expect(boxFor('Carla').checked).toBe(false)
      expect(boxFor('Carla').disabled).toBe(false)
    })

    it('locks the tick of someone who started everything, and says why in words', async () => {
      installFetch()
      renderDialog()
      await waitForTicks()
      // Nothing of Bruno's is `assigned` any more, so unticking could delete nothing.
      await waitFor(() => expect(boxFor('Bruno').disabled).toBe(true))
      expect(boxFor('Bruno').checked).toBe(true)
      // The point of the fix: locked WITH the reason beside it, not a mute `disabled`.
      expect(rowText('Bruno')).toMatch(/no se puede quitar/i)
      expect(rowText('Bruno')).toMatch(/empez/i)
    })

    it('warns on the half-started row how much an untick will leave behind', async () => {
      installFetch()
      renderDialog()
      await waitForTicks()
      expect(boxFor('Diego').checked).toBe(true)
      // Diego has one started course and one not: revocable in part, so not locked.
      expect(boxFor('Diego').disabled).toBe(false)
      expect(rowText('Diego')).toMatch(/se conserva/i)
    })

    it('still says in words how much of the folder each one already has', async () => {
      installFetch()
      renderDialog()
      await waitForTicks()
      expect(rowText('Ana')).toMatch(/ya tiene/i)
      expect(rowText('Carla')).not.toMatch(/ya tiene/i)
    })
  })

  describe('unticking removes', () => {
    it('deletes the enrollments of an unticked person, after asking first', async () => {
      const calls = installFetch()
      const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
      renderDialog()
      await waitForTicks()

      await userEvent.click(boxFor('Ana'))
      expect(boxFor('Ana').checked).toBe(false)

      const button = screen.getByRole('button', { name: /quitar a 1 persona/i })
      await userEvent.click(button)

      // Destructive, so it asks — same `window.confirm` the rest of this area uses.
      expect(confirmSpy).toHaveBeenCalled()
      await waitFor(() =>
        expect(deletedIds(calls).sort()).toEqual([`${ANA}:${COURSE_A}`, `${ANA}:${COURSE_B}`]),
      )
      expect(assignCalls(calls)).toHaveLength(0)
      expect(await screen.findByText(/2 matrículas eliminadas/i)).toBeInTheDocument()
    })

    it('does nothing when the confirmation is dismissed', async () => {
      const calls = installFetch()
      vi.spyOn(window, 'confirm').mockReturnValue(false)
      renderDialog()
      await waitForTicks()

      await userEvent.click(boxFor('Ana'))
      await userEvent.click(screen.getByRole('button', { name: /quitar a 1 persona/i }))

      expect(deletedIds(calls)).toEqual([])
      // The form is still there, so a second attempt is possible.
      expect(screen.getByRole('button', { name: /quitar a 1 persona/i })).toBeInTheDocument()
    })

    it('removes only the not-started half of a half-started folder, and says so', async () => {
      const calls = installFetch()
      vi.spyOn(window, 'confirm').mockReturnValue(true)
      renderDialog()
      await waitForTicks()

      await userEvent.click(boxFor('Diego'))
      await userEvent.click(screen.getByRole('button', { name: /quitar a 1 persona/i }))

      // Course A is `in_progress`; the server would answer 409, so it is never attempted.
      await waitFor(() => expect(deletedIds(calls)).toEqual([`${DIEGO}:${COURSE_B}`]))
      expect(await screen.findByText(/1 matrícula eliminada/i)).toBeInTheDocument()
      expect(screen.getByText(/se conserv/i)).toBeInTheDocument()
    })

    it('keeps the button harmless when nothing has been changed', async () => {
      installFetch()
      renderDialog()
      await waitForTicks()
      // Neither assigning nor removing: the state on screen is the state on the server.
      expect(screen.getByRole('button', { name: /asignar 2 cursos/i })).toBeDisabled()
    })
  })

  describe('ticking assigns', () => {
    it('assigns the folder to a newly ticked person, without asking', async () => {
      const calls = installFetch()
      const confirmSpy = vi.spyOn(window, 'confirm')
      renderDialog()
      await waitForTicks()

      await userEvent.click(boxFor('Carla'))
      await userEvent.click(screen.getByRole('button', { name: /asignar a 1 persona/i }))

      await waitFor(() => expect(assignCalls(calls)).toHaveLength(1))
      expect(assignCalls(calls)[0].body).toMatchObject({ user_ids: [CARLA] })
      expect(deletedIds(calls)).toEqual([])
      // Granting takes nothing away, so there is nothing to warn about.
      expect(confirmSpy).not.toHaveBeenCalled()
    })

    it('assigns one person and removes another in the same pass', async () => {
      const calls = installFetch()
      vi.spyOn(window, 'confirm').mockReturnValue(true)
      renderDialog()
      await waitForTicks()

      await userEvent.click(boxFor('Carla'))
      await userEvent.click(boxFor('Ana'))

      // The button says both halves out loud before it does either.
      const button = screen.getByRole('button', { name: /asignar a 1 y quitar a 1/i })
      await userEvent.click(button)

      await waitFor(() => expect(assignCalls(calls)).toHaveLength(1))
      expect(assignCalls(calls)[0].body).toMatchObject({ user_ids: [CARLA] })
      expect(deletedIds(calls).sort()).toEqual([`${ANA}:${COURSE_A}`, `${ANA}:${COURSE_B}`])
      expect(await screen.findByText(/2 matrículas eliminadas/i)).toBeInTheDocument()
    })
  })

  describe('when a delete fails', () => {
    it('applies the rest and names what failed and why', async () => {
      // Ana's first course started between the read and the click.
      const calls = installFetch({ conflictOn: [`${ANA}:${COURSE_A}`] })
      vi.spyOn(window, 'confirm').mockReturnValue(true)
      renderDialog()
      await waitForTicks()

      await userEvent.click(boxFor('Ana'))
      await userEvent.click(screen.getByRole('button', { name: /quitar a 1 persona/i }))

      // The 409 does not abort the batch: the second enrollment is still deleted.
      await waitFor(() =>
        expect(deletedIds(calls).sort()).toEqual([`${ANA}:${COURSE_A}`, `${ANA}:${COURSE_B}`]),
      )
      expect(await screen.findByText(/1 matrícula eliminada/i)).toBeInTheDocument()
      // And the failure is reported with the server's own words, not swallowed.
      const failure = await screen.findByText(/no se pudo quitar/i)
      expect(failure).toHaveTextContent('Curso A')
      expect(failure).toHaveTextContent('Ana')
      expect(failure).toHaveTextContent('Only assigned (not started) enrollments can be removed')
    })

    it('lets the admin try again when every delete failed', async () => {
      const calls = installFetch({ conflictOn: [`${ANA}:${COURSE_A}`, `${ANA}:${COURSE_B}`] })
      vi.spyOn(window, 'confirm').mockReturnValue(true)
      renderDialog()
      await waitForTicks()

      await userEvent.click(boxFor('Ana'))
      await userEvent.click(screen.getByRole('button', { name: /quitar a 1 persona/i }))

      await waitFor(() => expect(deletedIds(calls)).toHaveLength(2))
      // Nothing landed, so no result panel: both reasons inline and the form still usable.
      await waitFor(() => expect(screen.getAllByText(/no se pudo quitar/i)).toHaveLength(2))
      expect(screen.queryByText(/matrícula eliminada/i)).not.toBeInTheDocument()
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /quitar a 1 persona/i })).toBeEnabled(),
      )
    })
  })

  describe('the list is a page, and says so', () => {
    it('asks for a bounded page and never for "everyone"', async () => {
      const calls = installFetch()
      renderDialog()
      await waitForTicks()

      const peopleReads = calls.filter((call) => call.url.includes('/users?'))
      expect(peopleReads.length).toBeGreaterThan(0)
      // The defect this replaced: a `/users` read with no `limit` takes the server's
      // default of 50 and says nothing about the 51st employee.
      peopleReads.forEach((call) => {
        expect(call.url).toMatch(/limit=\d+/)
        expect(call.url).toMatch(/offset=\d+/)
      })
    })

    it('shows how many people there are, not just how many fit', async () => {
      installFetch()
      renderDialog()
      await waitForTicks()
      expect(screen.getByText(/1-4 de 4/)).toBeInTheDocument()
    })

    it('reads the enrollments of the visible page in ONE filtered request', async () => {
      const calls = installFetch()
      renderDialog()
      await waitForTicks()

      const enrollmentReads = calls.filter(
        (call) => call.method === 'GET' && call.url.includes('/enrollments?'),
      )
      // It used to be one unfiltered read per course, each capped at 100 rows — which
      // reported people as unenrolled who were not, once a course passed a hundred.
      expect(enrollmentReads).toHaveLength(1)
      expect(enrollmentReads[0].url).toContain(`folder_id=${FOLDER_ID}`)
      expect(enrollmentReads[0].url).toContain('user_ids=')
    })

    it('searching goes to the server and resets to the first page', async () => {
      const calls = installFetch()
      renderDialog()
      await waitForTicks()

      await userEvent.type(screen.getByPlaceholderText(/buscar persona/i), 'Carla')

      await waitFor(() =>
        expect(
          calls.some((call) => call.url.includes('search=Carla') && call.url.includes('offset=0')),
        ).toBe(true),
      )
      // And the list narrowed rather than being filtered in the browser.
      await waitFor(() => expect(screen.queryByText('Ana')).not.toBeInTheDocument())
      expect(screen.getByText('Carla')).toBeInTheDocument()
    })
  })

  describe('groups', () => {
    const TARDE = '99999999-9999-4999-8999-999999999999'

    it('does not render a group block when there are no groups', async () => {
      installFetch()
      renderDialog()
      await waitForTicks()
      expect(screen.queryByRole('heading', { name: /grupos/i })).not.toBeInTheDocument()
      expect(screen.queryByText('Turno de tarde')).not.toBeInTheDocument()
    })

    it('puts groups before people, which is the order the work is done in', async () => {
      installFetch({ groups: [{ id: TARDE, name: 'Turno de tarde', member_count: 12 }] })
      renderDialog()
      await waitForTicks()

      // Assigning to a whole group is the common case and used to be the last thing on
      // screen, under a paginated people list.
      const sections = await screen.findAllByRole('heading', { level: 3 })
      expect(sections.map((heading) => heading.textContent)).toEqual([
        'Grupos · a quién asignársela',
        'Personas · quién la tiene',
      ])
    })

    it('sends the group id, never the members', async () => {
      const calls = installFetch({ groups: [{ id: TARDE, name: 'Turno de tarde', member_count: 12 }] })
      renderDialog()
      await waitForTicks()

      await userEvent.click(boxFor('Turno de tarde'))
      await userEvent.click(screen.getByRole('button', { name: /^asignar a 1 grupo$/i }))

      await waitFor(() => expect(assignCalls(calls)).toHaveLength(1))
      // The whole point: the browser holds one page of people and cannot know who is in
      // the group, so it says which group and lets the server resolve it.
      expect(assignCalls(calls)[0].body).toMatchObject({ user_ids: [], group_ids: [TARDE] })
    })

    it('sends people and groups in ONE request so nobody is counted twice', async () => {
      const calls = installFetch({ groups: [{ id: TARDE, name: 'Turno de tarde', member_count: 12 }] })
      renderDialog()
      await waitForTicks()

      await userEvent.click(boxFor('Carla'))
      await userEvent.click(boxFor('Turno de tarde'))
      await userEvent.click(screen.getByRole('button', { name: /asignar a 1 persona y 1 grupo/i }))

      await waitFor(() => expect(assignCalls(calls)).toHaveLength(1))
      expect(assignCalls(calls)[0].body).toMatchObject({
        user_ids: [CARLA],
        group_ids: [TARDE],
      })
    })

    it('never lets the group box pass for a state, even sharing the row shape', async () => {
      installFetch({ groups: [{ id: TARDE, name: 'Turno de tarde', member_count: 12 }] })
      renderDialog()
      await waitForTicks()

      // Same control as a person's now, so the meaning cannot ride on the shape — and it
      // is no longer explained by a paragraph either. It rides on the two things that
      // cost nothing: what each box is CALLED, and what its section heading is about.
      const box = boxFor('Turno de tarde')
      expect(box.type).toBe('checkbox')
      // Never pre-ticked from server state — there is none to read for a group.
      expect(box.checked).toBe(false)
      // The group box is named after the action it performs...
      expect(box).toHaveAccessibleName(/asignar la carpeta a todo el grupo turno de tarde/i)
      // ...and says nothing about what the group holds, which this dialog cannot know:
      // one page of people is not enough to answer it for every member.
      expect(box).not.toHaveAccessibleName(/tiene/i)
      // The person's box is named after the state, a claim the tick is the truth of.
      expect(boxFor('Ana')).toHaveAccessibleName(/ana tiene esta carpeta/i)
      expect(boxFor('Ana')).not.toHaveAccessibleName(/asignar/i)
      // Neither naming costs the row its own detail: that moved to the description.
      expect(box).toHaveAccessibleDescription(/12 personas/i)
      expect(boxFor('Ana')).toHaveAccessibleDescription(/ya tiene los 2 cursos/i)
      // And for anyone reading rather than listening, the headings carry the same split.
      expect(screen.getByRole('heading', { name: /grupos\s*· a quién asignársela/i })).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: /personas\s*· quién la tiene/i })).toBeInTheDocument()
      // No paragraph is doing this work any more.
      expect(screen.queryByText(/la casilla es una acción/i)).not.toBeInTheDocument()
      expect(screen.queryByText(/la casilla es un estado/i)).not.toBeInTheDocument()

      await userEvent.click(box)
      expect(box.checked).toBe(true)
      // Ticked says what will happen, not what is true: "up to 12 people", minus whoever
      // the server dedupes or finds deactivated.
      expect(screen.getByText(/hasta 12 personas/)).toBeInTheDocument()
    })
  })


  describe('a decision survives paging away from it', () => {
    /**
     * The defect this covers: with the list paginated, the tick states were derived from
     * the enrollment read of the *current* page, so a tick made on page 1 evaluated to
     * "no change" once page 2 was showing and the button silently dropped it. A dialog
     * that discards a decision the admin watched themselves make is worse than one that
     * cannot page at all.
     *
     * Twenty published courses forces a five-per-page window (100 rows / 20 courses), so
     * the four employees in the fixture span two pages.
     */
    it('keeps a tick made on the first page when submitting from the second', async () => {
      const calls = installFetch({ publishedCourses: 20, extraPeople: 4 })
      renderDialog()

      // Eight people, five per page: Carla is on page one and page two exists.
      expect(await screen.findByText('Carla')).toBeInTheDocument()
      await waitFor(() => expect(screen.getByText('1-5 de 8')).toBeInTheDocument())
      await userEvent.click(boxFor('Carla'))
      expect(boxFor('Carla').checked).toBe(true)

      // Nobody has all twenty courses in this world, so every row is a plain "assign".
      await userEvent.click(screen.getByRole('button', { name: /Siguiente/i }))
      await waitFor(() => expect(screen.queryByText('Carla')).not.toBeInTheDocument())

      // The button still knows about her, and says so.
      expect(screen.getByText(/1 cambio pendiente está en otra página/i)).toBeInTheDocument()
      await userEvent.click(screen.getByRole('button', { name: /asignar a 1 persona/i }))

      await waitFor(() => expect(assignCalls(calls)).toHaveLength(1))
      expect(assignCalls(calls)[0].body).toMatchObject({ user_ids: [CARLA] })
    })

    it('a tick taken back before submitting leaves no trace', async () => {
      const calls = installFetch({ publishedCourses: 20, extraPeople: 4 })
      renderDialog()

      expect(await screen.findByText('Carla')).toBeInTheDocument()
      await waitFor(() => expect(screen.getByText('1-5 de 8')).toBeInTheDocument())
      await userEvent.click(boxFor('Carla'))
      await userEvent.click(boxFor('Carla'))

      // Back to the server's own state, so there is nothing to apply and nothing to warn
      // about — an entry saying "no change" would inflate every count on the button.
      expect(screen.queryByText(/cambio pendiente/i)).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: /asignar 20 cursos/i })).toBeDisabled()
      expect(assignCalls(calls)).toHaveLength(0)
    })

    it('shrinks the page so the enrollment read can never truncate', async () => {
      const calls = installFetch({ publishedCourses: 20, extraPeople: 4 })
      renderDialog()
      await screen.findByText('Carla')
      // The first read fires before the folder's course count has landed, so it uses the
      // default window; the size settles once the count is known.
      await waitFor(() =>
        expect(calls.some((call) => call.url.includes('/users?') && call.url.includes('limit=5'))).toBe(true),
      )

      // 100 rows / 20 courses = 5 people. The page size is arithmetic, not taste: it is
      // what makes "the ticks are complete" true rather than merely likely.
      expect(screen.queryByText(/casillas pueden estar incompletas/i)).not.toBeInTheDocument()
    })
  })


  describe('when there are many groups', () => {
    /** Twelve groups, so the eight-per-page window leaves four on a second page. */
    const MANY = Array.from({ length: 12 }, (_, index) => ({
      id: `g${index}`,
      name: `Grupo ${index}`,
      member_count: index + 1,
    }))

    it('asks for a bounded page instead of every group', async () => {
      const calls = installFetch({ groups: MANY })
      renderDialog()
      await waitForTicks()

      const reads = calls.filter((call) => call.url.includes('/user-groups'))
      expect(reads.length).toBeGreaterThan(0)
      reads.forEach((call) => expect(call.url).toMatch(/limit=\d+/))
      // Eight rows on screen, not twelve.
      expect(screen.getByText('Grupo 0')).toBeInTheDocument()
      expect(screen.queryByText('Grupo 11')).not.toBeInTheDocument()
    })

    it('searches on the server, not in the page already fetched', async () => {
      const calls = installFetch({ groups: MANY })
      renderDialog()
      await waitForTicks()

      await userEvent.type(screen.getByPlaceholderText(/buscar grupo/i), 'Grupo 11')

      // "Grupo 11" is on the second page, so a client-side filter could never find it.
      await waitFor(() =>
        expect(calls.some((call) => call.url.includes('/user-groups') && call.url.includes('search=Grupo+11'))).toBe(true),
      )
      expect(await screen.findByText('Grupo 11')).toBeInTheDocument()
    })

    it('keeps the people count of a group picked on another page', async () => {
      /**
       * The regression this exists for: the summary used to sum `member_count` out of the
       * *current page*, so a group ticked on page 1 contributed zero once the admin moved
       * to page 2 and "hasta N personas" silently shrank. The decision is frozen at the
       * click, so the number has to survive the move.
       */
      installFetch({ groups: MANY })
      renderDialog()
      await waitForTicks()

      // `Grupo 3` has four members.
      await userEvent.click(boxFor('Grupo 3'))
      expect(await screen.findByText(/hasta 4 personas/i)).toBeInTheDocument()

      await userEvent.click(screen.getAllByRole('button', { name: /Siguiente/i })[0])
      await waitFor(() => expect(screen.queryByText('Grupo 3')).not.toBeInTheDocument())

      // Still four, and the dialog says where the tick went.
      expect(screen.getByText(/hasta 4 personas/i)).toBeInTheDocument()
      expect(screen.getByText(/está en otra página/i)).toBeInTheDocument()
    })

    it('still sends a group ticked on a page the admin has left', async () => {
      const calls = installFetch({ groups: MANY })
      renderDialog()
      await waitForTicks()

      await userEvent.click(boxFor('Grupo 3'))
      await userEvent.click(screen.getAllByRole('button', { name: /Siguiente/i })[0])
      await waitFor(() => expect(screen.queryByText('Grupo 3')).not.toBeInTheDocument())
      await userEvent.click(screen.getByRole('button', { name: /^asignar a 1 grupo$/i }))

      await waitFor(() => expect(assignCalls(calls)).toHaveLength(1))
      expect(assignCalls(calls)[0].body).toMatchObject({ group_ids: ['g3'] })
    })

    it('offers no search box when every group already fits', async () => {
      installFetch({ groups: MANY.slice(0, 3) })
      renderDialog()
      await waitForTicks()
      // A control with nothing to do, in a section that sits above the people list.
      expect(screen.queryByPlaceholderText(/buscar grupo/i)).not.toBeInTheDocument()
    })
  })

})
