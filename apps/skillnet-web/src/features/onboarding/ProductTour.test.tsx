import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { IntlProvider } from '../../i18n/IntlProvider'
import { Dashboard } from '../../pages/employee/Dashboard'
import { ProductTour } from './ProductTour'
import { readOnboardingState } from './storage'
import { useTourStore } from './useTourStore'

/**
 * The employee tour running *on top of the real learner home*, which is the only place
 * the bug it fixes could be seen: joyride's overlay is one full-document div, so with the
 * library's default `pointer-events: auto` it ate every click on the page the tour was
 * pointing at — the hero's "Empezar" included, so the learner clicked and stayed on
 * Inicio.
 *
 * A note on what these tests can and cannot prove. jsdom does no layout and no hit
 * testing: a `userEvent.click` is dispatched straight at the element, so an overlay
 * covering it changes nothing there and a click-navigates assertion alone would pass even
 * with the bug present. The assertion that actually carries the regression is therefore
 * the overlay's own `pointer-events`, which is the exact property the browser consults —
 * it reads `auto` before the fix and `none` after. The navigation and the dismissal are
 * asserted alongside it because they are the behaviour a person sees.
 */

const COURSE_ID = '22222222-2222-4222-8222-222222222222'

const mockFetch = vi.fn()

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) })
}

function installFetch() {
  mockFetch.mockImplementation((input: string) => {
    const url = String(input)
    if (url.endsWith('/auth/me')) {
      return jsonResponse(200, {
        id: 'u1',
        email: 'ana@skillnet.dev',
        full_name: 'Ana Demo',
        role: 'employee',
      })
    }
    if (url.endsWith('/users/me/skills')) return jsonResponse(200, [])
    if (url.includes('/enrollments')) {
      return jsonResponse(200, {
        items: [
          {
            id: 'e1',
            course_id: COURSE_ID,
            user_id: 'u1',
            status: 'assigned',
            deadline: null,
            score: null,
            progress: 0,
            course_title: 'Como aprende tu cerebro',
            started_at: null,
            completed_at: null,
            delivery_mode: 'dynamic',
          },
        ],
        total: 1,
        page: 1,
        size: 20,
      })
    }
    return jsonResponse(404, { detail: 'Not Found', code: 'NOT_FOUND' })
  })
}

/** The learner home with the tour mounted over it, exactly as `AppShell` does. */
function renderHomeWithTour() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <IntlProvider>
        <MemoryRouter initialEntries={['/empleado']}>
          <ProductTour role="employee" />
          <Routes>
            <Route path="/empleado" element={<Dashboard />} />
            <Route path="/empleado/curso/:id" element={<div>CURSO</div>} />
            <Route path="*" element={<div>FALLBACK</div>} />
          </Routes>
        </MemoryRouter>
      </IntlProvider>
    </QueryClientProvider>,
  )
}

function overlay(): HTMLElement | null {
  return document.querySelector<HTMLElement>('.react-joyride__overlay')
}

/**
 * Start the tour and wait until its overlay is painted. The runner drops any step whose
 * anchor is not on screen, which in jsdom means *every* step unless `getClientRects`
 * reports a box — see the stub in `beforeEach`.
 */
async function startTour() {
  act(() => {
    useTourStore.getState().start()
  })
  await waitFor(() => expect(overlay()).not.toBeNull())
}

/** A plausible painted box for a spotlight anchor. */
const ANCHOR_BOX = {
  x: 24,
  y: 400,
  top: 400,
  left: 24,
  width: 320,
  height: 96,
  bottom: 496,
  right: 344,
  toJSON: () => ({}),
} as DOMRect

let clientRects: ReturnType<typeof vi.spyOn>
let boundingRect: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  window.localStorage.clear()
  useTourStore.setState({ run: false, runId: 0, index: 0 })
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
  installFetch()
  // jsdom lays nothing out, so every element measures 0×0 and reports no client rects.
  // The runner reads exactly that to decide whether a spotlight anchor is painted, so
  // without this the tour resolves to zero steps and never mounts.
  clientRects = vi
    .spyOn(Element.prototype, 'getClientRects')
    .mockReturnValue([ANCHOR_BOX] as unknown as DOMRectList)
  boundingRect = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue(ANCHOR_BOX)
})

afterEach(() => {
  clientRects.mockRestore()
  boundingRect.mockRestore()
  vi.restoreAllMocks()
})

describe('employee tour — the page underneath stays usable', () => {
  it('does not make its overlay a click target', async () => {
    renderHomeWithTour()
    expect(await screen.findByRole('button', { name: /Empezar/ })).toBeInTheDocument()
    await startTour()

    // The regression: `auto` here is the overlay eating the learner's click.
    expect(overlay()?.style.pointerEvents).toBe('none')
    // The spotlight hole is a child of the overlay, so it has to opt out too — a child
    // with `pointer-events: auto` is still hit-tested inside a `none` parent.
    const spotlight = document.querySelector<HTMLElement>('.react-joyride__spotlight')
    if (spotlight) expect(spotlight.style.pointerEvents).toBe('none')
  })

  it('lets a click on the hero CTA navigate while the tour is on screen', async () => {
    const user = userEvent.setup()
    renderHomeWithTour()
    const cta = await screen.findByRole('button', { name: /Empezar/ })
    await startTour()

    await user.click(cta)

    expect(await screen.findByText('CURSO')).toBeInTheDocument()
    expect(screen.queryByText('FALLBACK')).toBeNull()
  })

  it('dismisses itself on that first real interaction, reopenably', async () => {
    const user = userEvent.setup()
    renderHomeWithTour()
    const cta = await screen.findByRole('button', { name: /Empezar/ })
    await startTour()

    await user.click(cta)

    // The learner acted, so the tour steps aside instead of floating over the lesson —
    // and records the same dismissal Skip does, so it never auto-runs again but the
    // header "?" still brings it back.
    await waitFor(() => expect(useTourStore.getState().run).toBe(false))
    expect(readOnboardingState('employee').dismissedAt).toBeTruthy()
    expect(readOnboardingState('employee').completed).toBe(false)
  })

  /*
   * The other half of the reported bug — joyride "brings the first target into view" even
   * when it is already at the top of the scroller, sliding the CTA out from under the
   * pointer (82px, measured on `/empleado`) about half a second after load — is fixed by
   * the per-step `disableScrolling` in the runner and is deliberately NOT asserted here.
   * jsdom has no scrolling: joyride's animated `scrollTop` write never lands, so a spy on
   * it records nothing whether the fix is present or not, and the "test" would pass for
   * the wrong reason. That half was verified in a real browser instead (Chrome, Vite dev
   * server): `main.scrollTop` went 0 → 82.4 when the tour opened, and stays 0 now.
   */

  it('survives a click on its own tooltip', async () => {
    const user = userEvent.setup()
    renderHomeWithTour()
    expect(await screen.findByRole('button', { name: /Empezar/ })).toBeInTheDocument()
    await startTour()

    // Clicking inside the tour box is not "using the page": stepping through the tour
    // must not be read as abandoning it.
    const card = document.querySelector<HTMLElement>('[data-tour-tooltip]')
    expect(card).not.toBeNull()
    await user.click(card!)

    expect(useTourStore.getState().run).toBe(true)
    expect(readOnboardingState('employee').dismissedAt).toBeUndefined()
  })
})
