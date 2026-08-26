import type { Meta } from '@storybook/react-vite'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CapabilityHealthBanner } from './CapabilityHealthBanner'
import type { Capabilities, CapabilityReason, SetupStatus } from '../../api/setup'

/**
 * The admin-facing degraded-mode notice (docs/design/degraded-mode-ux.md §1). It reads
 * the deployment capabilities off the `/setup/status` query, so each story seeds a fresh
 * QueryClient cache with a different capability combination. IntlProvider (with `es`
 * messages) comes from the global preview decorator.
 *
 * When everything is present the banner renders nothing — that "AllPresent" story is
 * intentionally an empty canvas.
 */
function seeded(capabilities: Capabilities) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const status: SetupStatus = { initialized: true, capabilities }
  client.setQueryData(['setup', 'status'], status)
  return client
}

const meta: Meta<typeof CapabilityHealthBanner> = {
  title: 'Admin/CapabilityHealthBanner',
  component: CapabilityHealthBanner,
}
export default meta

const READY = { status: 'ready' } as const
const blocked = (reason: CapabilityReason) => ({ status: 'blocked', reason }) as const

const ALL: Capabilities = {
  ai: READY,
  generation: READY,
  tutor: READY,
  tts: READY,
  images: READY,
}

function Story({ capabilities }: { capabilities: Capabilities }) {
  return (
    <QueryClientProvider client={seeded(capabilities)}>
      <div className="max-w-xl">
        <CapabilityHealthBanner />
      </div>
    </QueryClientProvider>
  )
}

/** Everything configured: the banner renders nothing (empty canvas is expected). */
export const AllPresent = () => <Story capabilities={ALL} />

/** No LLM key: the most severe line, plus voice and images also off. */
export const NoAi = () => (
  <Story
    capabilities={{
      ai: blocked('missing_api_key'),
      generation: blocked('missing_api_key'),
      tutor: blocked('missing_api_key'),
      tts: blocked('missing_api_key'),
      images: blocked('missing_api_key'),
    }}
  />
)

/** Only voice is degraded — offline robotic fallback. */
export const NoTts = () => (
  <Story capabilities={{ ...ALL, tts: blocked('missing_api_key') }} />
)

/** Only image generation is off — infographics without a poster. */
export const NoImages = () => (
  <Story capabilities={{ ...ALL, images: blocked('missing_api_key') }} />
)
