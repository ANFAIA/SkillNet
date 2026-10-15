import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { IntlProvider } from '../../i18n/IntlProvider'
import { BugReportEntry, BugReportsAdminEntry } from './BugReportEntry'

/** Settings only shows a quiet row; the form and the lists live in a window it opens. */

const mockFetch = vi.fn()

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) })
}

function renderEntry(entry: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <IntlProvider>{entry}</IntlProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  mockFetch.mockReset()
  mockFetch.mockImplementation(() => jsonResponse(200, []))
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('BugReportEntry', () => {
  it('shows only a row until the button is pressed, then the form', async () => {
    renderEntry(<BugReportEntry />)
    expect(screen.queryByLabelText('Título')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Reportar un problema' }))
    expect(await screen.findByLabelText('Título')).toBeInTheDocument()
  })
})

describe('BugReportsAdminEntry', () => {
  it('opens the organization reports from its own row', async () => {
    renderEntry(<BugReportsAdminEntry />)
    await userEvent.click(screen.getByRole('button', { name: 'Ver reportes' }))
    expect(await screen.findByText('Nadie ha reportado nada.')).toBeInTheDocument()
  })
})
