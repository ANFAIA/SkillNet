import type { Meta } from '@storybook/react-vite'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Setup } from './Setup'

/**
 * The first-run welcome screen. In the real app this only appears on an ownerless
 * deployment (App gates it on `/setup/status`), so it is otherwise impossible to
 * preview. Here we render <Setup /> directly.
 *
 * Providers: the global preview decorator already supplies IntlProvider (with the
 * `es` messages) and imports `src/index.css` — which is where `.setup-welcome-bg`
 * (the brand gradient) lives. Setup additionally needs a QueryClient (for its
 * `useSubmitSetup` mutation) and a Router (for `useNavigate`), so this story wraps
 * those two locally.
 *
 * The story opens on the "welcome" stage (brand gradient + Logo + floating Mascota
 * + "Bienvenido" + "Comenzar"). Click "Comenzar" in the canvas to walk the internal
 * stage state on to the mode chooser (organization / individual → owner form).
 * Submitting the owner form will fail without a backend — expected for a visual
 * preview; the error simply surfaces inline via `submit.error`.
 *
 * Theme: the app themes via `data-theme` / prefers-color-scheme. Storybook has no
 * data-theme toolbar here, so this renders whatever the OS prefers; switch your OS
 * appearance (or the browser's prefers-color-scheme) to check the other theme.
 */
const meta: Meta<typeof Setup> = {
  title: 'Onboarding/Setup (Bienvenida)',
  component: Setup,
  parameters: {
    // Setup is a full-screen route; drop the padded app wrapper margins.
    layout: 'fullscreen',
  },
  decorators: [
    (Story) => {
      // A fresh client per render; no retries so a failed setup submit fails fast.
      const client = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })
      return (
        <QueryClientProvider client={client}>
          <MemoryRouter initialEntries={['/setup']}>
            <Story />
          </MemoryRouter>
        </QueryClientProvider>
      )
    },
  ],
}
export default meta

// Welcome stage (default). Click "Comenzar" to advance to the mode chooser.
export const Bienvenida = () => <Setup />
