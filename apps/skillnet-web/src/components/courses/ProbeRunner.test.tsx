import { StrictMode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ProbeRunner } from './ProbeRunner'
import type { ProbeSession } from '../../types'

/**
 * One regression, and it earns the file on its own.
 *
 * The probe used to be adopted from a per-call `onSuccess` handed to `mutate`. Those
 * callbacks hang off the mutation *observer*, and react-query drops them when the
 * observer is torn down before the request settles. `POST /probe` succeeded, the server
 * dealt a hand, nothing read it, and `openedRef` turned the retry into a no-op — so the
 * screen sat on "Preparando dos preguntas rapidas..." forever, with no error anywhere to
 * explain it.
 *
 * `StrictMode` reproduces that teardown every time, which is why these render under it.
 * A concurrent remount in production has the same shape, so this is not a
 * development-only guard.
 */

const NODE_ID = '11111111-1111-4111-8111-111111111111'
const QUESTION = 'Cuantos alergenos son de declaracion obligatoria?'

const PROBE_SESSION: ProbeSession = {
  // `null` is a shape the API really returns (nothing stored past the probe) and the
  // component never reads it — only `items`, `verdict` and `diagnostic`.
  probe: null,
  items: [
    {
      item_id: 'a',
      item_type: 'test',
      question: QUESTION,
      options: ['Siete', 'Catorce', 'Veintiuno'],
    } as ProbeSession['items'][number],
  ],
  reused: false,
  verdict: null,
  diagnostic: false,
}

const mockFetch = vi.fn()

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) })
}

function renderUnderStrictMode() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <StrictMode>
      <QueryClientProvider client={client}>
        <ProbeRunner
          nodeId={NODE_ID}
          node={null}
          openingLine="Esto te sirve para atender en mostrador."
          onPrefetch={() => {}}
          onVerdict={() => {}}
        />
      </QueryClientProvider>
    </StrictMode>,
  )
}

beforeEach(() => {
  vi.stubGlobal('fetch', mockFetch)
  mockFetch.mockImplementation((input: string) => {
    const url = String(input)
    if (url.endsWith('/health')) {
      return jsonResponse(200, { status: 'ok' })
    }
    if (url.includes('/probe')) return jsonResponse(200, PROBE_SESSION)
    return jsonResponse(200, {})
  })
})

afterEach(() => {
  mockFetch.mockReset()
  vi.unstubAllGlobals()
})

describe('ProbeRunner', () => {
  it('shows the first item under StrictMode, where the mutation observer is torn down', async () => {
    renderUnderStrictMode()

    expect(await screen.findByText(QUESTION)).toBeInTheDocument()
    expect(screen.getByTestId('probe-runner')).toBeInTheDocument()
  })

  it('deals one hand per node — a second POST /probe would reshuffle an open probe', async () => {
    renderUnderStrictMode()
    await screen.findByText(QUESTION)

    const probeCalls = () =>
      mockFetch.mock.calls.filter(([url]) => String(url).includes('/probe')).length
    await waitFor(() => expect(probeCalls()).toBe(1))
    expect(probeCalls()).toBe(1)
  })
})
