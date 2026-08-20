import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { IntlProvider } from 'react-intl'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'

import { CapabilityHealthBanner } from './CapabilityHealthBanner'
import { es } from '../../i18n/es'
import type { Capabilities, SetupStatus } from '../../api/setup'

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
    const { container } = renderWith({
      ai: true,
      generation: true,
      tutor: true,
      tts: true,
      images: true,
    })
    expect(container).toBeEmptyDOMElement()
  })

  it('shows only the audio line when TTS is the sole missing capability', () => {
    renderWith({ ai: true, generation: true, tutor: true, tts: false, images: true })
    expect(screen.getByText(es['capabilityBanner.tts'])).toBeInTheDocument()
    expect(screen.queryByText(es['capabilityBanner.ai'])).not.toBeInTheDocument()
    expect(screen.queryByText(es['capabilityBanner.images'])).not.toBeInTheDocument()
  })

  it('shows the AI line when AI is missing', () => {
    renderWith({ ai: false, generation: false, tutor: false, tts: false, images: false })
    expect(screen.getByText(es['capabilityBanner.ai'])).toBeInTheDocument()
    // All three degraded lines are consolidated into one banner.
    expect(screen.getByText(es['capabilityBanner.tts'])).toBeInTheDocument()
    expect(screen.getByText(es['capabilityBanner.images'])).toBeInTheDocument()
    expect(screen.getAllByRole('status')).toHaveLength(1)
  })

  it('can be dismissed with its button', async () => {
    const user = userEvent.setup()
    renderWith({ ai: false, generation: false, tutor: false, tts: true, images: true })
    expect(screen.getByText(es['capabilityBanner.ai'])).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: es['capabilityBanner.dismiss'] }))
    expect(screen.queryByText(es['capabilityBanner.ai'])).not.toBeInTheDocument()
  })
})
