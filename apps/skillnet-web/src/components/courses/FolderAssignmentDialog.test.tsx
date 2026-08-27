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
function installFetch(options: { conflictOn?: string[] } = {}) {
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
      return jsonResponse({ course_count: 2, created_count: 2, skipped_existing_count: 0 })
    }
    if (url.includes('/users')) {
      return jsonResponse({
        items: [user(ANA, 'Ana'), user(BRUNO, 'Bruno'), user(CARLA, 'Carla'), user(DIEGO, 'Diego')],
        total: 4,
        offset: 0,
        limit: 50,
      })
    }
    if (url.includes('/courses')) {
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
      const courseId = url.includes(COURSE_A) ? COURSE_A : COURSE_B
      const items = ENROLLMENTS.filter((row) => row.course_id === courseId).map((row) => ({
        ...row,
        course_title: courseId === COURSE_A ? 'Curso A' : 'Curso B',
        deadline: null,
        score: null,
        progress: 0,
        started_at: null,
        completed_at: null,
        delivery_mode: 'static',
      }))
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
})
