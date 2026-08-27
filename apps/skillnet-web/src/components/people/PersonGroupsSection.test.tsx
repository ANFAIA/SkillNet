import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { IntlProvider } from '../../i18n/IntlProvider'
import { PersonGroupsSection } from './PersonGroupsSection'
import type { User } from '../../types'

/**
 * Putting a person into a group from their own record.
 *
 * This half of the screen used to be a `<select>` holding every group the organization
 * had, fetched in one unpaginated read. At three groups that is a dropdown; at two
 * hundred it is a scroll of identical options with no way to type a name, and the
 * request behind it grows without limit. What is pinned here is where the answers come
 * from: the page is bounded, the search term travels to the server, and the groups the
 * person already belongs to are excluded **by the server** — filtering them out of the
 * page in the browser would leave the ones on other pages offered, and adding somebody
 * to a group they are already in is a no-op reported as a success.
 */

const PERSON_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const MINE = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'

const person: User = {
  id: PERSON_ID,
  email: 'ana@example.com',
  full_name: 'Ana',
  role: 'employee',
  is_active: true,
} as User

/** Thirty groups, one of which the person is already in. */
const ALL_GROUPS = [
  { id: MINE, name: 'Turno de tarde', member_count: 4 },
  ...Array.from({ length: 29 }, (_, index) => ({
    id: `g${index}`,
    name: index === 28 ? 'Delegacion Norte' : `Grupo ${index}`,
    member_count: index,
  })),
]

const mockFetch = vi.fn()

type Call = { method: string; url: string; body: unknown }

function jsonResponse(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) })
}

/** A server that honours `exclude_user_id`, `search` and the page window. */
function installFetch(): Call[] {
  const calls: Call[] = []
  mockFetch.mockImplementation((input: string, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined })

    if (method === 'PUT' && url.includes('/members')) {
      return jsonResponse({ added_count: 1, removed_count: 0, member_count: 5 })
    }
    if (url.includes(`/users/${PERSON_ID}/groups`)) {
      return jsonResponse([{ id: MINE, name: 'Turno de tarde', member_count: 4 }])
    }
    if (url.includes('/user-groups')) {
      const query = new URLSearchParams(url.split('?')[1] ?? '')
      const offset = Number(query.get('offset') ?? 0)
      const limit = Number(query.get('limit') ?? 50)
      const search = (query.get('search') ?? '').toLowerCase()
      let rows = ALL_GROUPS
      if (query.get('exclude_user_id')) rows = rows.filter((row) => row.id !== MINE)
      if (search) rows = rows.filter((row) => row.name.toLowerCase().includes(search))
      return jsonResponse({
        items: rows.slice(offset, offset + limit),
        total: rows.length,
        offset,
        limit,
      })
    }
    return jsonResponse({ items: [], total: 0, offset: 0, limit: 25 })
  })
  return calls
}

function renderSection() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <IntlProvider>
        <PersonGroupsSection person={person} />
      </IntlProvider>
    </QueryClientProvider>,
  )
}

function pickerReads(calls: Call[]): Call[] {
  return calls.filter((call) => call.url.includes('/user-groups?'))
}

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('PersonGroupsSection', () => {
  it('asks for a bounded page of groups and lets the server do the excluding', async () => {
    const calls = installFetch()
    renderSection()
    await screen.findByPlaceholderText('Buscar un grupo por nombre')

    const reads = pickerReads(calls)
    expect(reads.length).toBeGreaterThan(0)
    reads.forEach((call) => {
      expect(call.url).toMatch(/limit=\d+/)
      expect(call.url).toMatch(/offset=\d+/)
      // The exclusion is a query parameter. A `.filter()` here would only drop the
      // person's groups from the page they happened to land on.
      expect(call.url).toContain(`exclude_user_id=${PERSON_ID}`)
    })
    // Twenty-nine offerable out of thirty, and the line that says how many did not fit.
    expect(await screen.findByText('1-5 de 29')).toBeInTheDocument()
  })

  it('never offers a group the person is already in', async () => {
    installFetch()
    renderSection()
    // It is on screen once — in the list of what they belong to, with a Quitar button.
    expect(await screen.findByText('Turno de tarde')).toBeInTheDocument()

    await userEvent.type(screen.getByPlaceholderText('Buscar un grupo por nombre'), 'turno')

    // Searching for it by name still does not turn it into something to add.
    await waitFor(() => expect(screen.getAllByText('Turno de tarde')).toHaveLength(1))
  })

  it('searches on the server, not on the page already in hand', async () => {
    const calls = installFetch()
    renderSection()
    await screen.findByPlaceholderText('Buscar un grupo por nombre')

    await userEvent.type(screen.getByPlaceholderText('Buscar un grupo por nombre'), 'delegacion')

    await waitFor(() =>
      expect(pickerReads(calls).some((call) => call.url.includes('search=delegacion'))).toBe(true),
    )
    // Last of twenty-nine: a filter over the first five could never have found it.
    expect(await screen.findByText('Delegacion Norte')).toBeInTheDocument()
  })

  it('adding writes through the one membership endpoint', async () => {
    const calls = installFetch()
    renderSection()
    await screen.findByText('Grupo 0')

    await userEvent.click(screen.getAllByRole('button', { name: 'Añadir' })[0])

    await waitFor(() => {
      const put = calls.find((call) => call.method === 'PUT')
      expect(put?.url).toContain('/user-groups/g0/members')
      expect(put?.body).toEqual({ add: [PERSON_ID], remove: [] })
    })
  })
})
