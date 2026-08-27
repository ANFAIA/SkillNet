import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { IntlProvider } from '../../i18n/IntlProvider'
import { Employees } from './Employees'

/**
 * The people screen with more people than fit on a screen.
 *
 * It used to call `GET /users` with a search term and a role and *nothing else*, which
 * takes the server's default page of 50 and reports a `total` the screen never read. In
 * a company of 240 the table showed 50 and said "240 personas" in the header — the two
 * numbers on screen contradicted each other and neither said the list was a window.
 *
 * These tests pin the three things that make it scale, and one that makes it honest:
 * every read is a bounded page, every filter is a query parameter (never a `.filter()`
 * on what came back), paging works, and changing a filter goes back to page one.
 */

const PAGE = 25
const TOTAL = 240

const mockFetch = vi.fn()

type Call = { method: string; url: string }

function jsonResponse(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) })
}

function person(index: number) {
  return {
    id: `u${index}`,
    email: `p${index}@test.dev`,
    full_name: `Persona ${index}`,
    role: index === 0 ? 'admin' : 'employee',
    is_active: index % 7 !== 0,
    learning_profile: 'standard',
    accessibility: {},
  }
}

const EVERYONE = Array.from({ length: TOTAL }, (_, index) => person(index))

/** A fake `/users` that honours every filter, so a client-side one would show up as a bug. */
function installFetch(groups: { id: string; name: string; member_count: number }[] = []): Call[] {
  const calls: Call[] = []
  mockFetch.mockImplementation((input: string, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    calls.push({ method, url })

    // `/user-groups` is a paginated, searchable read like `/users`, and this fake
    // honours both — a rail that filtered the page in the browser would pass a mock
    // that just handed back the array.
    if (url.startsWith('/api/v1/user-groups')) {
      const query = new URLSearchParams(url.split('?')[1] ?? '')
      const offset = Number(query.get('offset') ?? 0)
      const limit = Number(query.get('limit') ?? 50)
      const search = (query.get('search') ?? '').toLowerCase()
      let rows = groups
      if (search) rows = rows.filter((row) => row.name.toLowerCase().includes(search))
      return jsonResponse({
        items: rows.slice(offset, offset + limit),
        total: rows.length,
        offset,
        limit,
      })
    }
    if (url.startsWith('/api/v1/course-folders')) return jsonResponse([])
    if (/^\/api\/v1\/users(\?|$)/.test(url) && method === 'GET') {
      const query = new URLSearchParams(url.split('?')[1] ?? '')
      const offset = Number(query.get('offset') ?? 0)
      const limit = Number(query.get('limit') ?? 50)
      const search = (query.get('search') ?? '').toLowerCase()
      const role = query.get('role')
      const isActive = query.get('is_active')
      const groupId = query.get('group_id')
      const ungrouped = query.get('ungrouped')
      let rows = EVERYONE
      if (search) rows = rows.filter((row) => row.full_name.toLowerCase().includes(search))
      if (role) rows = rows.filter((row) => row.role === role)
      if (isActive !== null) rows = rows.filter((row) => row.is_active === (isActive === 'true'))
      // The group filter is the server's job too: two people, and nobody else.
      if (groupId) rows = rows.filter((row) => row.id === 'u1' || row.id === 'u2')
      // …and its "in no group at all" counterpart: everyone except those same two.
      if (ungrouped) rows = rows.filter((row) => row.id !== 'u1' && row.id !== 'u2')
      return jsonResponse({
        items: rows.slice(offset, offset + limit),
        total: rows.length,
        offset,
        limit,
      })
    }
    return jsonResponse({ items: [], total: 0, offset: 0, limit: 50 })
  })
  return calls
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

/** The `/users` reads that actually fetch a page, not the rail's one-row count probe.
 *
 * `limit` is the last parameter the client builds, so the probe's URL *ends* with
 * `limit=1` — matching `limit=1&` would exclude nothing and quietly turn this helper
 * into `calls.filter(everything)`.
 */
function pageReads(calls: Call[]): Call[] {
  return calls.filter((call) => call.url.includes('/users?') && !call.url.endsWith('limit=1'))
}

/** Guards the helper above: if it stops excluding the probe, these tests get weaker. */
function countProbes(calls: Call[]): Call[] {
  return calls.filter((call) => call.url.endsWith('limit=1'))
}

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Employees at scale', () => {
  it('asks for a bounded page and never for "everyone"', async () => {
    const calls = installFetch()
    renderPage()
    await screen.findAllByText('Persona 1')

    const reads = calls.filter((call) => call.url.includes('/users?'))
    expect(reads.length).toBeGreaterThan(0)
    reads.forEach((call) => {
      expect(call.url).toMatch(/limit=\d+/)
      expect(call.url).toMatch(/offset=\d+/)
    })
  })

  it('separates the page read from the rail count probe', async () => {
    const calls = installFetch()
    renderPage()
    await screen.findAllByText('Persona 1')

    // The rail's "everyone" count is its own one-row read; without this the helper the
    // other tests rely on would be matching every request and asserting nothing.
    expect(countProbes(calls).length).toBeGreaterThan(0)
    expect(pageReads(calls).every((call) => !call.url.endsWith('limit=1'))).toBe(true)
  })

  it('says which slice of the organization is on screen', async () => {
    installFetch()
    renderPage()
    await screen.findAllByText('Persona 1')

    // The number the old screen never showed. Without it, 25 rows and a header saying
    // 240 people are two facts the admin has to reconcile alone.
    expect(await screen.findByText(`1-${PAGE} de ${TOTAL}`)).toBeInTheDocument()
  })

  it('pages forward and back through the whole organization', async () => {
    installFetch()
    renderPage()
    await screen.findAllByText('Persona 1')

    await userEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
    expect(await screen.findByText(`26-50 de ${TOTAL}`)).toBeInTheDocument()
    // Somebody the first page could not reach — the exact person the old screen lost.
    expect((await screen.findAllByText('Persona 30')).length).toBeGreaterThan(0)

    await userEvent.click(screen.getByRole('button', { name: 'Anterior' }))
    expect(await screen.findByText(`1-${PAGE} de ${TOTAL}`)).toBeInTheDocument()
  })

  it('cannot go back from the first page', async () => {
    installFetch()
    renderPage()
    await screen.findAllByText('Persona 1')
    expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled()
  })

  it('filters by status on the server, not on the fetched page', async () => {
    const calls = installFetch()
    renderPage()
    await screen.findAllByText('Persona 1')

    await userEvent.selectOptions(screen.getByLabelText('Estado'), 'inactive')

    await waitFor(() =>
      expect(pageReads(calls).some((call) => call.url.includes('is_active=false'))).toBe(true),
    )
  })

  it('filters by group on the server, and the rail is where it lives', async () => {
    const calls = installFetch([{ id: 'g1', name: 'Turno de tarde', member_count: 2 }])
    renderPage()
    await screen.findAllByText('Persona 1')

    // Exact name: the rail's row actions (assign, members, rename, delete) all carry the
    // group's name in their labels too, so a loose matcher finds five buttons.
    await userEvent.click(await screen.findByRole('button', { name: /^Turno de tarde\s*2$/ }))

    await waitFor(() =>
      expect(pageReads(calls).some((call) => call.url.includes('group_id=g1'))).toBe(true),
    )
    // Two members, so the count line follows the filter rather than the organization.
    expect(await screen.findByText('1-2 de 2')).toBeInTheDocument()
  })

  it('can list the people who are in no group at all', async () => {
    const calls = installFetch([{ id: 'g1', name: 'Turno de tarde', member_count: 2 }])
    renderPage()
    await screen.findAllByText('Persona 1')

    // The question an admin actually asks — "who have I not covered?" — and the one the
    // rail could not answer until it had this row, because a paginated list cannot be
    // scanned by eye for an absence.
    await userEvent.click(await screen.findByRole('button', { name: /^Sin grupo/ }))

    await waitFor(() =>
      expect(pageReads(calls).some((call) => call.url.includes('ungrouped=true'))).toBe(true),
    )
    expect(await screen.findByText(`1-${PAGE} de ${TOTAL - 2}`)).toBeInTheDocument()
  })

  it('goes back to the first page when a filter changes', async () => {
    const calls = installFetch()
    renderPage()
    await screen.findAllByText('Persona 1')

    await userEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
    await screen.findByText(`26-50 de ${TOTAL}`)

    await userEvent.selectOptions(screen.getByLabelText('Filtrar por rol'), 'admin')

    // Page 2 of the old result set is meaningless for the new one, and staying there is
    // how a filter with one match comes back empty.
    await waitFor(() =>
      expect(
        pageReads(calls).some((call) => call.url.includes('role=admin') && call.url.includes('offset=0')),
      ).toBe(true),
    )
    expect(await screen.findByText('1-1 de 1')).toBeInTheDocument()
  })

  it('searching narrows the query, not the page already in hand', async () => {
    const calls = installFetch()
    renderPage()
    await screen.findAllByText('Persona 1')

    await userEvent.type(screen.getByPlaceholderText(/buscar/i), 'Persona 137')

    await waitFor(() =>
      expect(pageReads(calls).some((call) => call.url.includes('search=Persona+137'))).toBe(true),
    )
    // Person 137 is far past the first page; a client-side filter could never find them.
    expect((await screen.findAllByText('Persona 137')).length).toBeGreaterThan(0)
  })
})

/**
 * The same argument, one rail to the left: a group is a row in a list nothing bounds.
 *
 * `GET /user-groups` used to answer with every group an organization had, and the rail
 * painted all of them with no search box — the exact shape of the defect the people list
 * beside it was rewritten to fix, sitting next to the fix.
 */
const RAIL_PAGE = 10
const MANY_GROUPS = Array.from({ length: 33 }, (_, index) => ({
  id: `g${index}`,
  name: index === 32 ? 'Delegacion Norte' : `Turno ${index}`,
  member_count: index,
}))

/** The rail's own reads, told apart from `/users` by their path. */
function groupReads(calls: Call[]): Call[] {
  return calls.filter((call) => call.url.includes('/user-groups?'))
}

describe('the group rail at scale', () => {
  it('asks for a bounded page of groups and never for all of them', async () => {
    const calls = installFetch(MANY_GROUPS)
    renderPage()
    await screen.findAllByText('Persona 1')

    const reads = groupReads(calls)
    expect(reads.length).toBeGreaterThan(0)
    reads.forEach((call) => {
      expect(call.url).toMatch(/limit=\d+/)
      expect(call.url).toMatch(/offset=\d+/)
    })
    // Ten rows on screen out of thirty-three, and the line that says so.
    expect(await screen.findByText(`1-${RAIL_PAGE} de 33`)).toBeInTheDocument()
  })

  it('searches groups on the server, not on the page already in hand', async () => {
    const calls = installFetch(MANY_GROUPS)
    renderPage()
    await screen.findAllByText('Persona 1')

    await userEvent.type(screen.getByPlaceholderText('Buscar grupo por nombre'), 'delegacion')

    await waitFor(() =>
      expect(groupReads(calls).some((call) => call.url.includes('search=delegacion'))).toBe(true),
    )
    // Thirty-third of thirty-three: a `.filter()` on the first page could never find it.
    expect(await screen.findByRole('button', { name: /^Delegacion Norte/ })).toBeInTheDocument()
  })

  it('pages through the groups while the two fixed views stay put', async () => {
    installFetch(MANY_GROUPS)
    renderPage()
    await screen.findAllByText('Persona 1')

    const rail = screen.getByRole('complementary', { name: 'Grupos' })
    await userEvent.click(within(rail).getByRole('button', { name: 'Siguiente' }))

    expect(await within(rail).findByText(`11-20 de 33`)).toBeInTheDocument()
    // "Todas las personas" and "Sin grupo" are views, not groups: they are not part of
    // the page and must survive every one of them.
    expect(within(rail).getByRole('button', { name: /^Todas las personas/ })).toBeInTheDocument()
    expect(within(rail).getByRole('button', { name: /^Sin grupo/ })).toBeInTheDocument()
  })

  it('keeps the selected group on screen after paging past it', async () => {
    installFetch(MANY_GROUPS)
    renderPage()
    await screen.findAllByText('Persona 1')

    const rail = screen.getByRole('complementary', { name: 'Grupos' })
    await userEvent.click(within(rail).getByRole('button', { name: /^Turno 1\s*1$/ }))
    await userEvent.click(within(rail).getByRole('button', { name: 'Siguiente' }))
    await within(rail).findByText(`11-20 de 33`)

    // The filter is still narrowing the list beside the rail, so its row cannot quietly
    // leave: an active filter with nothing on screen to show for it is unexplainable.
    expect(within(rail).getByRole('button', { name: /^Turno 1\s*1$/ })).toHaveAttribute(
      'aria-current',
      'true',
    )
  })

  it('has no search box while every group fits on one page', async () => {
    installFetch(MANY_GROUPS.slice(0, 3))
    renderPage()
    await screen.findAllByText('Persona 1')

    // Three groups are all on screen; a box to search them would be furniture.
    expect(screen.queryByPlaceholderText('Buscar grupo por nombre')).not.toBeInTheDocument()
  })
})
