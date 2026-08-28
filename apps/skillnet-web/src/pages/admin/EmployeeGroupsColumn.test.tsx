import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { IntlProvider } from '../../i18n/IntlProvider'
import { Employees } from './Employees'

/**
 * The group column on the people table.
 *
 * Three things make it worth its width, and each is a way it could quietly stop working:
 *
 * 1. **One read for the page.** The membership rides on the row (`?with_groups=true`),
 *    so a version that asked `GET /users/{id}/groups` per person would render exactly
 *    the same screen and cost twenty-five round-trips. Only counting requests catches
 *    that, which is why these tests count them.
 * 2. **The name filters.** The row already opens the person's record on click, so the
 *    cell has to stop the event or the filter never runs and a modal opens instead.
 * 3. **No groups, no column.** An organization that does not use groups gets a header
 *    and a column of dashes otherwise.
 */

const mockFetch = vi.fn()

type Call = { method: string; url: string }

function jsonResponse(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) })
}

const TARDE = { id: 'g1', name: 'Turno de tarde' }
const NORTE = { id: 'g2', name: 'Delegación Norte' }
const OBRADOR = { id: 'g3', name: 'Obrador' }

function person(id: string, name: string, groups: { id: string; name: string }[]) {
  return {
    id,
    email: `${id}@test.dev`,
    full_name: name,
    role: 'employee',
    is_active: true,
    learning_profile: 'standard',
    accessibility: {},
    groups,
  }
}

const PEOPLE = [
  person('u1', 'Ana', [TARDE]),
  person('u2', 'Bruno', [TARDE, NORTE]),
  person('u3', 'Carla', [TARDE, NORTE, OBRADOR]),
  person('u4', 'Diego', []),
]

function installFetch(groups: { id: string; name: string }[]): Call[] {
  const calls: Call[] = []
  mockFetch.mockImplementation((input: string, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    calls.push({ method, url })

    if (url.startsWith('/api/v1/user-groups')) {
      const query = new URLSearchParams(url.split('?')[1] ?? '')
      const offset = Number(query.get('offset') ?? 0)
      const limit = Number(query.get('limit') ?? 50)
      const rows = groups.map((g) => ({ ...g, member_count: 1 }))
      return jsonResponse({ items: rows.slice(offset, offset + limit), total: rows.length, offset, limit })
    }
    if (url.startsWith('/api/v1/course-folders')) return jsonResponse([])
    // The per-person read. Served so the detail modal works, and *counted* so the first
    // test can prove the table never reaches for it.
    if (/^\/api\/v1\/users\/[^/?]+\/groups/.test(url)) return jsonResponse([])
    if (/^\/api\/v1\/users(\?|$)/.test(url) && method === 'GET') {
      const query = new URLSearchParams(url.split('?')[1] ?? '')
      const offset = Number(query.get('offset') ?? 0)
      const limit = Number(query.get('limit') ?? 50)
      const groupId = query.get('group_id')
      // The server is what narrows by group. A row is only sent back with its groups
      // when the caller asked for them — the flag has to reach the wire to be tested.
      let rows = PEOPLE
      if (groupId) rows = rows.filter((row) => row.groups.some((g) => g.id === groupId))
      const withGroups = query.get('with_groups') === 'true'
      const items = rows
        .slice(offset, offset + limit)
        .map((row) => (withGroups ? row : { ...row, groups: undefined }))
      return jsonResponse({ items, total: rows.length, offset, limit })
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

/** The desktop table once it has rows — the rail's own group buttons are never in it.
 *
 * Awaited rather than read synchronously: the first paint is the skeleton, and there is
 * no `<table>` in the document until the page read lands. */
async function table(): Promise<HTMLElement> {
  return screen.findByRole('table')
}

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('the group column reads once per page', () => {
  it('carries the memberships on the page read and asks for nothing else', async () => {
    const calls = installFetch([TARDE, NORTE, OBRADOR])
    renderPage()
    await within(await table()).findByText('Ana')

    // Exactly one read of the page carries the flag — not one per row, and not two
    // because a second query key flipped once the group count arrived.
    const pageReads = calls.filter((call) => call.url.includes('with_groups=true'))
    expect(pageReads).toHaveLength(1)
    // And the per-person endpoint, the N+1 this replaces, is never touched.
    expect(calls.filter((call) => /\/users\/[^/?]+\/groups/.test(call.url))).toHaveLength(0)
  })

  it('leaves the count probes alone', async () => {
    const calls = installFetch([TARDE])
    renderPage()
    await within(await table()).findByText('Ana')

    // The one-row probes exist to count, not to render, so they must not have grown a
    // membership join. (They also feed `EmployeesScale`'s helper, which tells them from
    // page reads by the URL ending in `limit=1`.)
    const probes = calls.filter((call) => call.url.endsWith('limit=1'))
    expect(probes.length).toBeGreaterThan(0)
    probes.forEach((call) => expect(call.url).not.toContain('with_groups'))
  })
})

describe('what the cell shows', () => {
  it('shows the one group a person is in, plainly', async () => {
    installFetch([TARDE, NORTE, OBRADOR])
    renderPage()
    const rows = await table()
    await within(rows).findByText('Ana')

    // One membership is the normal case: a name, and nothing counted next to it.
    const ana = within(rows).getByText('Ana').closest('tr') as HTMLElement
    expect(within(ana).getByRole('button', { name: 'Turno de tarde' })).toBeInTheDocument()
    expect(within(ana).queryByText(/^\+/)).not.toBeInTheDocument()
  })

  it('counts the rest from the second group onwards', async () => {
    installFetch([TARDE, NORTE, OBRADOR])
    renderPage()
    const rows = await table()
    await within(rows).findByText('Bruno')

    const bruno = within(rows).getByText('Bruno').closest('tr') as HTMLElement
    expect(within(bruno).getByRole('button', { name: 'Turno de tarde' })).toBeInTheDocument()
    expect(within(bruno).getByText('+1')).toBeInTheDocument()

    // Three groups, still one name: the cell never grows with the membership.
    const carla = within(rows).getByText('Carla').closest('tr') as HTMLElement
    expect(within(carla).getByText('+2')).toBeInTheDocument()
    // The names it does not draw are still reachable — on the overflow, not in the row.
    expect(within(carla).getByTitle('También en: Delegación Norte, Obrador')).toBeInTheDocument()
  })

  it('draws a dash for somebody in no group', async () => {
    installFetch([TARDE])
    renderPage()
    const rows = await table()
    await within(rows).findByText('Diego')

    const diego = within(rows).getByText('Diego').closest('tr') as HTMLElement
    expect(within(diego).getByText('—')).toBeInTheDocument()
    expect(within(diego).queryAllByRole('button')).toHaveLength(0)
  })

  it('is not drawn at all when the organization has no groups', async () => {
    installFetch([])
    renderPage()
    await within(await table()).findByText('Ana')

    // A header over a column of dashes is furniture. The people are still listed.
    expect(screen.queryByRole('columnheader', { name: 'Grupo' })).not.toBeInTheDocument()
    expect(within(await table()).queryByRole('button', { name: 'Turno de tarde' })).not.toBeInTheDocument()
  })
})

describe('clicking a group', () => {
  it('filters the table by that group', async () => {
    const calls = installFetch([TARDE, NORTE, OBRADOR])
    renderPage()
    const rows = await table()
    await within(rows).findByText('Diego')

    const ana = within(rows).getByText('Ana').closest('tr') as HTMLElement
    await userEvent.click(within(ana).getByRole('button', { name: 'Turno de tarde' }))

    await waitFor(() =>
      expect(calls.some((call) => call.url.includes('group_id=g1'))).toBe(true),
    )
    // Diego is in no group, so the filter really applied rather than merely being sent.
    await waitFor(() => expect(within(rows).queryByText('Diego')).not.toBeInTheDocument())
  })

  it('does not open the person while doing it', async () => {
    installFetch([TARDE, NORTE, OBRADOR])
    renderPage()
    await within(await table()).findByText('Ana')

    const ana = within(await table()).getByText('Ana').closest('tr') as HTMLElement
    await userEvent.click(within(ana).getByRole('button', { name: 'Turno de tarde' }))

    // The row opens the detail modal on click. Without `stopPropagation` in the cell the
    // filter would run *and* the modal would cover its result — the easiest way to break
    // this column, and invisible to a test that only checks the request went out.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByText('Restablecer contraseña')).not.toBeInTheDocument()
  })

  it('still opens the person when the row itself is clicked', async () => {
    installFetch([TARDE, NORTE, OBRADOR])
    renderPage()
    await within(await table()).findByText('Ana')

    // The guard above must not have cost the row its own behaviour.
    await userEvent.click(within(await table()).getByText('u1@test.dev'))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
  })
})
