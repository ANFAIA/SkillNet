import { render, renderHook, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { Gated } from './Gated'
import { useCapability, type Capabilities, type SetupStatus } from '../api/setup'
import { es } from '../i18n/es'
import { blocked, caps, degraded } from '../test/fixtures/capabilities'
import type { User, UserRole } from '../types'

/**
 * A client whose setup-status query is pre-seeded with the given capabilities, and
 * whose `/auth/me` is pre-seeded too — the explain mode asks who is looking, and a
 * seeded identity keeps the test off the network.
 */
function wrapperWith(capabilities?: Partial<Capabilities>, role: UserRole = 'employee') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const status: SetupStatus = { initialized: true }
  if (capabilities) status.capabilities = capabilities as Capabilities
  client.setQueryData(['setup', 'status'], status)
  client.setQueryData(['users', 'me'], {
    id: 'u1',
    email: 'quien@sea.test',
    full_name: 'Quien Sea',
    role,
  } satisfies User)
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

/** What a learner is told when there is no image key. Base sentence + reason clause. */
const LEARNER_TEXT = `${es['capability.images.unavailable']} ${es['capability.reason.missing_api_key']}`
/** The admin sees the same opening, then the one thing they can act on. */
const ADMIN_TEXT = `${es['capability.images.unavailable']} ${es['capability.images.admin.missing_api_key']}`

describe('<Gated> (hide, the default)', () => {
  it('renders children when the capability is present', () => {
    render(
      <Gated requires="tutor">
        <span>tutor chip</span>
      </Gated>,
      { wrapper: wrapperWith(caps()) },
    )
    expect(screen.getByText('tutor chip')).toBeInTheDocument()
  })

  it('renders nothing (not an error) when the capability is blocked', () => {
    render(
      <Gated requires="tutor">
        <span>tutor chip</span>
      </Gated>,
      { wrapper: wrapperWith(caps({ tutor: blocked() })) },
    )
    expect(screen.queryByText('tutor chip')).not.toBeInTheDocument()
  })

  it('still renders children when the capability is only degraded', () => {
    // A degraded capability is still there — the offline voice speaks. Hiding its UI
    // would be the degraded-mode policy backwards.
    render(
      <Gated requires="tts">
        <span>podcast</span>
      </Gated>,
      { wrapper: wrapperWith(caps({ tts: degraded('provider_quota') })) },
    )
    expect(screen.getByText('podcast')).toBeInTheDocument()
  })

  it('renders the fallback when provided and the capability is absent', () => {
    render(
      <Gated requires="images" fallback={<span>connect a key</span>}>
        <span>infographic</span>
      </Gated>,
      { wrapper: wrapperWith(caps({ images: blocked() })) },
    )
    expect(screen.queryByText('infographic')).not.toBeInTheDocument()
    expect(screen.getByText('connect a key')).toBeInTheDocument()
  })

  it('accepts the legacy boolean payload an older backend still sends', () => {
    render(
      <Gated requires="images">
        <span>infographic</span>
      </Gated>,
      { wrapper: wrapperWith({ images: false } as unknown as Partial<Capabilities>) },
    )
    expect(screen.queryByText('infographic')).not.toBeInTheDocument()
  })
})

describe('<Gated mode="explain">', () => {
  const onClick = vi.fn()

  function renderExplain(capabilities: Partial<Capabilities>, role: UserRole = 'employee') {
    onClick.mockClear()
    return render(
      <Gated requires="images" mode="explain">
        <button type="button" onClick={onClick}>
          Infografia
        </button>
      </Gated>,
      { wrapper: wrapperWith(capabilities, role) },
    )
  }

  it('renders the child untouched when the capability is ready', () => {
    renderExplain(caps())
    const button = screen.getByRole('button', { name: 'Infografia' })
    expect(button).not.toHaveAttribute('aria-disabled')
    expect(button).not.toHaveAttribute('aria-describedby')
  })

  it('renders the child visibly, marked aria-disabled and still focusable', () => {
    renderExplain(caps({ images: blocked('missing_api_key') }))
    const button = screen.getByRole('button', { name: 'Infografia' })
    expect(button).toBeVisible()
    expect(button).toHaveAttribute('aria-disabled', 'true')
    // NOT the `disabled` attribute: that would drop it from the tab order and take
    // the explanation with it.
    expect(button).not.toBeDisabled()
    button.focus()
    expect(button).toHaveFocus()
  })

  it('wires aria-describedby to text that is really in the document', () => {
    renderExplain(caps({ images: blocked('missing_api_key') }))
    const button = screen.getByRole('button', { name: 'Infografia' })
    const id = button.getAttribute('aria-describedby')
    expect(id).toBeTruthy()
    const description = document.getElementById(id as string)
    expect(description).not.toBeNull()
    expect(description).toHaveTextContent(LEARNER_TEXT)
  })

  it('swallows the click', async () => {
    const user = userEvent.setup()
    renderExplain(caps({ images: blocked('missing_api_key') }))
    await user.click(screen.getByRole('button', { name: 'Infografia' }))
    expect(onClick).not.toHaveBeenCalled()
  })

  it('swallows Enter and Space', async () => {
    const user = userEvent.setup()
    renderExplain(caps({ images: blocked('missing_api_key') }))
    screen.getByRole('button', { name: 'Infografia' }).focus()
    await user.keyboard('{Enter}')
    await user.keyboard(' ')
    expect(onClick).not.toHaveBeenCalled()
  })

  it('shows the reason on hover, on top of the permanent description', async () => {
    const user = userEvent.setup()
    renderExplain(caps({ images: blocked('missing_api_key') }))
    // Before hovering only the sr-only description carries the sentence.
    expect(screen.getAllByText(LEARNER_TEXT)).toHaveLength(1)
    await user.hover(screen.getByRole('button', { name: 'Infografia' }))
    expect(await screen.findAllByText(LEARNER_TEXT)).toHaveLength(2)
  })

  it('explains a degraded capability too — a maybe is not a yes', () => {
    renderExplain(caps({ images: degraded('provider_quota') }))
    expect(screen.getByRole('button', { name: 'Infografia' })).toHaveAttribute(
      'aria-disabled',
      'true',
    )
  })

  it('gives an admin the actionable detail and a learner none of it', () => {
    const { unmount } = renderExplain(caps({ images: blocked('missing_api_key') }), 'admin')
    expect(screen.getByText(ADMIN_TEXT)).toBeInTheDocument()
    expect(screen.queryByText(LEARNER_TEXT)).not.toBeInTheDocument()
    unmount()

    renderExplain(caps({ images: blocked('missing_api_key') }), 'employee')
    expect(screen.getByText(LEARNER_TEXT)).toBeInTheDocument()
    expect(screen.queryByText(ADMIN_TEXT)).not.toBeInTheDocument()
    // The learner is never shown the deployment's plumbing.
    expect(screen.queryByText(/OPENROUTER_API_KEY/)).not.toBeInTheDocument()
  })
})

describe('useCapability', () => {
  it('defaults to available (safe) when the field is missing', () => {
    const { result } = renderHook(() => useCapability('generation'), {
      wrapper: wrapperWith(undefined),
    })
    expect(result.current.status).toBe('ready')
  })

  it('reflects an explicit block', () => {
    const { result } = renderHook(() => useCapability('generation'), {
      wrapper: wrapperWith(caps({ generation: blocked('missing_api_key') })),
    })
    expect(result.current.status).toBe('blocked')
    expect(result.current.reason).toBe('missing_api_key')
  })

  it('keeps google_login off by default', () => {
    const { result } = renderHook(() => useCapability('google_login'), {
      wrapper: wrapperWith(undefined),
    })
    expect(result.current.status).toBe('blocked')
  })
})
