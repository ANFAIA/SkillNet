import type { Meta } from '@storybook/react-vite'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Gated } from './Gated'
import type { Capabilities, SetupStatus } from '../api/setup'
import type { User, UserRole } from '../types'

/**
 * The capability gate, in both modes (docs/design/degraded-mode-ux.md).
 *
 * `explain` is the one worth looking at: the control stays visible and keeps its
 * place in the tab order, but it cannot be activated, and hovering, focusing or
 * tapping it says why. Tab to it and the screen reader reads the same sentence the
 * bubble shows — it lives permanently in the DOM, not only while the bubble is up.
 *
 * Both the capabilities and the viewer's identity come off seeded queries, since the
 * copy is role-aware: the admin story appends the one actionable detail, the learner
 * story never mentions a key.
 */
function seeded(capabilities: Capabilities, role: UserRole) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const status: SetupStatus = { initialized: true, capabilities }
  client.setQueryData(['setup', 'status'], status)
  client.setQueryData(['users', 'me'], {
    id: 'u1',
    email: 'quien@sea.test',
    full_name: 'Quien Sea',
    role,
  } satisfies User)
  return client
}

const meta: Meta<typeof Gated> = {
  title: 'Admin/Gated',
  component: Gated,
}
export default meta

const READY = { status: 'ready' } as const
const NO_IMAGE_KEY = { status: 'blocked', reason: 'missing_api_key' } as const

const CAPABILITIES: Capabilities = {
  ai: READY,
  generation: READY,
  tutor: READY,
  tts: READY,
  images: NO_IMAGE_KEY,
}

/** The tile a media studio would render for a kind that needs an image model. */
function Tile() {
  return (
    <button
      type="button"
      className="group flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-border bg-surface px-3 py-4 transition-colors hover:border-primary hover:bg-bg-subtle"
    >
      <span className="text-xs font-medium text-text">Infografia</span>
    </button>
  )
}

function Story({ role, mode }: { role: UserRole; mode: 'hide' | 'explain' }) {
  return (
    <QueryClientProvider client={seeded(CAPABILITIES, role)}>
      <div className="max-w-xs p-12">
        <Gated requires="images" mode={mode}>
          <Tile />
        </Gated>
      </div>
    </QueryClientProvider>
  )
}

/** A learner: visible, inert, and told only that it is unavailable here. */
export const ExplainToLearner = () => <Story role="employee" mode="explain" />

/** An admin: the same sentence, plus the environment variable that fixes it. */
export const ExplainToAdmin = () => <Story role="admin" mode="explain" />

/** The default mode, unchanged: nothing renders at all. Empty canvas is expected. */
export const Hidden = () => <Story role="admin" mode="hide" />
