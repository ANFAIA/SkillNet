import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { GroupMembersDialog } from './GroupMembersDialog'

/**
 * Editing a group's membership.
 *
 * The thing worth pinning is not the ticking — it is *where the truth comes from*. The
 * dialog never intersects two paginated lists in the browser to work out who is already
 * in: it asks the server twice, `?group_id=` for the members and `?exclude_group_id=`
 * for everyone else, so a row's state cannot be wrong for somebody who happened to fall
 * on another page. These tests assert the requests, because that is the design.
 *
 * The rest is the staging contract: nothing is written until Save, and Save is one
 * request carrying both halves.
 */

const GROUP_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const ANA = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'
const BRUNO = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'
const CARLA = 'ffffffff-ffff-4fff-8fff-ffffffffffff'

const mockFetch = vi.fn()

type Call = { method: string; url: string; body: unknown }

function jsonResponse(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) })
}

function person(id: string, name: string) {
  return { id, email: `${name.toLowerCase()}@example.com`, full_name: name, role: 'employee', is_active: true }
}

/** Ana and Bruno are in; Carla is not. The server, not the client, says so. */
function installFetch(): Call[] {
  const calls: Call[] = []
  mockFetch.mockImplementation((input: string, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined })

    if (method === 'PUT' && url.includes('/members')) {
      return jsonResponse({ added_count: 1, removed_count: 1, member_count: 2 })
    }
    if (url.includes('exclude_group_id')) {
      return jsonResponse({ items: [person(CARLA, 'Carla')], total: 1, offset: 0, limit: 25 })
    }
    if (url.includes('group_id')) {
      return jsonResponse({
        items: [person(ANA, 'Ana'), person(BRUNO, 'Bruno')],
        total: 2,
        offset: 0,
        limit: 25,
      })
    }
    return jsonResponse({ items: [], total: 0, offset: 0, limit: 25 })
  })
  return calls
}

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <GroupMembersDialog
        group={{ id: GROUP_ID, name: 'Turno de tarde', member_count: 2 }}
        onClose={() => {}}
      />
    </QueryClientProvider>,
  )
}

/** The button in the same row as `name`. */
function rowButton(name: string): HTMLButtonElement {
  const row = screen.getByText(name).closest('div')?.parentElement
  const button = row?.querySelector('button')
  if (!button) throw new Error(`no encontré el botón de la fila de ${name}`)
  return button as HTMLButtonElement
}

describe('GroupMembersDialog', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    mockFetch.mockReset()
  })

  it('asks the server for members and non-members separately', async () => {
    const calls = installFetch()
    renderDialog()

    expect(await screen.findByText('Ana')).toBeInTheDocument()
    expect(await screen.findByText('Carla')).toBeInTheDocument()

    const urls = calls.map((call) => call.url)
    expect(urls.some((url) => url.includes(`group_id=${GROUP_ID}`) && !url.includes('exclude'))).toBe(true)
    expect(urls.some((url) => url.includes(`exclude_group_id=${GROUP_ID}`))).toBe(true)
  })

  it('both lists are paginated and never ask for everyone at once', async () => {
    const calls = installFetch()
    renderDialog()
    await screen.findByText('Ana')

    const peopleReads = calls.filter((call) => call.url.includes('/users?'))
    expect(peopleReads.length).toBeGreaterThan(0)
    // The bug this screen inherits: a `/users` read with no `limit` takes the server's
    // default of 50 and reports nothing about the rest.
    peopleReads.forEach((call) => {
      expect(call.url).toMatch(/limit=\d+/)
      expect(call.url).toMatch(/offset=\d+/)
    })
  })

  it('writes nothing until Save, and then sends one request with both halves', async () => {
    const user = userEvent.setup()
    const calls = installFetch()
    renderDialog()

    await screen.findByText('Carla')
    await user.click(rowButton('Carla')) // add
    await user.click(rowButton('Ana')) // remove

    // Staged, not sent.
    expect(calls.some((call) => call.method === 'PUT')).toBe(false)

    await user.click(screen.getByRole('button', { name: /Guardar 2 cambios/i }))

    await waitFor(() => expect(calls.some((call) => call.method === 'PUT')).toBe(true))
    const put = calls.find((call) => call.method === 'PUT')
    expect(put?.url).toContain(`/user-groups/${GROUP_ID}/members`)
    expect(put?.body).toEqual({ add: [CARLA], remove: [ANA] })
  })

  it('lets a staged change be taken back before saving', async () => {
    const user = userEvent.setup()
    const calls = installFetch()
    renderDialog()

    await screen.findByText('Carla')
    await user.click(rowButton('Carla'))
    expect(rowButton('Carla')).toHaveTextContent('Se añadirá')
    await user.click(rowButton('Carla'))
    expect(rowButton('Carla')).toHaveTextContent('Añadir')

    // Nothing left to save, so the button is not offering to save nothing.
    expect(screen.getByRole('button', { name: /Guardar/i })).toBeDisabled()
    expect(calls.some((call) => call.method === 'PUT')).toBe(false)
  })

  it('reports what the server actually did, not what was staged', async () => {
    const user = userEvent.setup()
    installFetch()
    renderDialog()

    await screen.findByText('Carla')
    await user.click(rowButton('Carla'))
    await user.click(screen.getByRole('button', { name: /Guardar 1 cambio/i }))

    // The fake API answers 1 added and 1 removed; the dialog must echo the server.
    expect(await screen.findByText(/1 alta/)).toBeInTheDocument()
    expect(screen.getByText(/1 baja/)).toBeInTheDocument()
  })
})
