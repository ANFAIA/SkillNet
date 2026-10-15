import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { IntlProvider } from '../../i18n/IntlProvider'
import { BugReportSection } from './BugReportSection'

/**
 * The form a person uses to report a problem, and the list that shows what happened to it.
 * The page and the browser are added by the component, so the person only writes the text.
 */

const mockFetch = vi.fn()

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) })
}

const MINE = [
  {
    id: 'r1',
    title: 'Save does nothing',
    status: 'issue',
    severity: 'medium',
    reason: 'A feature is broken.',
    issue_url: 'https://github.com/o/r/issues/9',
    page_path: '/lesson/1',
    environment: null,
    created_at: '2026-10-15T10:00:00Z',
  },
]

function installFetch({ mine = MINE, postStatus = 202 }: { mine?: unknown[]; postStatus?: number } = {}) {
  mockFetch.mockImplementation((input: string, options?: RequestInit) => {
    const url = String(input)
    const method = options?.method ?? 'GET'
    if (url.endsWith('/bugs/mine')) return jsonResponse(200, mine)
    if (url.endsWith('/bugs') && method === 'POST') {
      return postStatus < 400
        ? jsonResponse(postStatus, { id: 'r2', status: 'queued' })
        : jsonResponse(postStatus, { detail: 'limit', code: 'RATE_LIMITED' })
    }
    return jsonResponse(404, { detail: 'Not Found', code: 'NOT_FOUND' })
  })
}

function renderSection() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <IntlProvider>
        <BugReportSection />
      </IntlProvider>
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

describe('BugReportSection', () => {
  it('lists my reports with their status and the issue link', async () => {
    installFetch()
    renderSection()
    expect(await screen.findByText('Save does nothing')).toBeInTheDocument()
    expect(screen.getByText('Enviado al equipo')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ver issue' })).toHaveAttribute(
      'href',
      'https://github.com/o/r/issues/9',
    )
  })

  it('keeps the send button off until there is a title and a description', async () => {
    installFetch({ mine: [] })
    renderSection()
    const button = await screen.findByRole('button', { name: 'Enviar reporte' })
    expect(button).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Título'), 'Algo falla')
    expect(button).toBeDisabled()
    await userEvent.type(screen.getByLabelText('¿Qué pasó y qué esperabas?'), 'Pulso y no pasa nada')
    expect(button).toBeEnabled()
  })

  it('sends the text with the page and the browser, then clears the form', async () => {
    installFetch({ mine: [] })
    renderSection()
    await userEvent.type(await screen.findByLabelText('Título'), 'Algo falla')
    await userEvent.type(screen.getByLabelText('¿Qué pasó y qué esperabas?'), 'Pulso y no pasa nada')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar reporte' }))

    expect(await screen.findByText(/Reporte enviado/)).toBeInTheDocument()
    const post = mockFetch.mock.calls.find(([u, o]) => String(u).endsWith('/bugs') && o?.method === 'POST')
    const sent = JSON.parse(post![1].body as string)
    expect(sent.title).toBe('Algo falla')
    expect(sent.body).toBe('Pulso y no pasa nada')
    expect(sent.page_path).toBe(window.location.pathname)
    expect(sent.environment).toMatch(/px, /)
    expect(screen.getByLabelText('Título')).toHaveValue('')
  })

  it('says so when the report cannot be sent and keeps what was written', async () => {
    installFetch({ mine: [], postStatus: 429 })
    renderSection()
    await userEvent.type(await screen.findByLabelText('Título'), 'Algo falla')
    await userEvent.type(screen.getByLabelText('¿Qué pasó y qué esperabas?'), 'Pulso')
    await userEvent.click(screen.getByRole('button', { name: 'Enviar reporte' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByLabelText('Título')).toHaveValue('Algo falla')
  })
})
