import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { IntlProvider } from 'react-intl'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'

import { CapabilityHealthBanner } from './CapabilityHealthBanner'
import { es } from '../../i18n/es'
import type { Capabilities, SetupStatus } from '../../api/setup'
import { blocked, caps, degraded } from '../../test/fixtures/capabilities'

/** Render the banner with the setup-status query pre-seeded with these capabilities. */
function renderWith(capabilities?: Partial<Capabilities>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const status: SetupStatus = { initialized: true }
  if (capabilities) status.capabilities = capabilities as Capabilities
  client.setQueryData(['setup', 'status'], status)
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <IntlProvider locale="es" messages={es}>
        {children}
      </IntlProvider>
    </QueryClientProvider>
  )
  return render(<CapabilityHealthBanner />, { wrapper })
}

describe('<CapabilityHealthBanner>', () => {
  it('shows nothing when every capability is present', () => {
    const { container } = renderWith(caps())
    expect(container).toBeEmptyDOMElement()
  })

  it('shows only the audio line when TTS is the sole missing capability', () => {
    renderWith(caps({ tts: blocked() }))
    expect(screen.getByText(es['capabilityBanner.tts'])).toBeInTheDocument()
    expect(screen.queryByText(es['capabilityBanner.ai'])).not.toBeInTheDocument()
    expect(screen.queryByText(es['capabilityBanner.images'])).not.toBeInTheDocument()
  })

  it('shows the AI line when AI is missing', () => {
    renderWith(caps({ ai: blocked(), generation: blocked(), tutor: blocked(), tts: blocked(), images: blocked() }))
    expect(screen.getByText(es['capabilityBanner.ai'])).toBeInTheDocument()
    // All three degraded lines are consolidated into one banner.
    expect(screen.getByText(es['capabilityBanner.tts'])).toBeInTheDocument()
    expect(screen.getByText(es['capabilityBanner.images'])).toBeInTheDocument()
    expect(screen.getAllByRole('status')).toHaveLength(1)
  })

  it('tags each line with the reason the backend named', () => {
    renderWith(caps({ tts: degraded('provider_quota'), images: blocked('missing_api_key') }))
    expect(screen.getByText(es['capability.reasonLabel.provider_quota'])).toBeInTheDocument()
    expect(screen.getByText(es['capability.reasonLabel.missing_api_key'])).toBeInTheDocument()
    // The tag complements the deployment-level sentence; it does not replace it.
    expect(screen.getByText(es['capabilityBanner.images'])).toBeInTheDocument()
  })

  it('falls back to the status when there is no reason to name', () => {
    renderWith(caps({ images: blocked() }))
    expect(screen.getByText(es['capability.statusLabel.blocked'])).toBeInTheDocument()
  })

  it('shows the admin-only hint when the backend sent one', () => {
    renderWith(
      caps({
        images: { status: 'blocked', reason: 'missing_api_key', hint: 'OPENROUTER_API_KEY unset' },
      }),
    )
    expect(screen.getByText('OPENROUTER_API_KEY unset')).toBeInTheDocument()
  })

  it('can be dismissed with its button', async () => {
    const user = userEvent.setup()
    renderWith(caps({ ai: blocked(), generation: blocked(), tutor: blocked() }))
    expect(screen.getByText(es['capabilityBanner.ai'])).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: es['capabilityBanner.dismiss'] }))
    expect(screen.queryByText(es['capabilityBanner.ai'])).not.toBeInTheDocument()
  })
})
