import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Setup } from './Setup'
import * as setupApi from '../../api/setup'
import { blocked, caps } from '../../test/fixtures/capabilities'

// Setup needs a QueryClient (its `useSubmitSetup` mutation) and a Router
// (`useNavigate`). Intl is supplied globally by the test setup mock, so — like the
// Storybook decorator — only those two providers are wired here.
//
// The wizard crossfades stages via `AnimatePresence mode="wait"`, so stage swaps are
// asserted with async `findBy*` queries (the outgoing stage unmounts a tick later).
function renderSetup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/setup']}>
        <Setup />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Setup — first-boot wizard', () => {
  it('opens on the welcome stage: title, mascot and the "Comenzar" CTA', () => {
    renderSetup()
    expect(screen.getByRole('heading', { name: 'Bienvenido a la app' })).toBeInTheDocument()
    // The floating brand mascot is present on the welcome hero.
    expect(screen.getByRole('img', { name: 'Mascota de SkillNet' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Comenzar' })).toBeInTheDocument()
    // The mode chooser is not shown yet.
    expect(screen.queryByText('Organizacion')).not.toBeInTheDocument()
  })

  it('advances to the mode chooser when "Comenzar" is clicked', async () => {
    const user = userEvent.setup()
    renderSetup()
    await user.click(screen.getByRole('button', { name: 'Comenzar' }))
    expect(
      await screen.findByRole('heading', { name: 'Como vas a usar SkillNet' }),
    ).toBeInTheDocument()
    // Both workspace-mode cards appear.
    expect(screen.getByRole('heading', { name: 'Organizacion' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Solo yo' })).toBeInTheDocument()
    // Welcome hero is gone once the crossfade settles.
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Comenzar' })).not.toBeInTheDocument(),
    )
  })

  it('"← Anterior" returns from the mode chooser to the welcome stage', async () => {
    const user = userEvent.setup()
    renderSetup()
    await user.click(screen.getByRole('button', { name: 'Comenzar' }))
    // Button label carries a leading "← ".
    await user.click(await screen.findByRole('button', { name: /Anterior/ }))
    expect(await screen.findByRole('heading', { name: 'Bienvenido a la app' })).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'Organizacion' })).not.toBeInTheDocument(),
    )
  })

  it('reveals the owner form once a mode is chosen and "Continuar" pressed', async () => {
    const user = userEvent.setup()
    renderSetup()
    await user.click(screen.getByRole('button', { name: 'Comenzar' }))
    // Pick a mode by clicking its card, then continue.
    await user.click(await screen.findByRole('heading', { name: 'Organizacion' }))
    await user.click(screen.getByRole('button', { name: 'Continuar' }))
    // The owner form surfaces (its submit CTA is "Crear y continuar").
    expect(await screen.findByRole('heading', { name: 'Tu cuenta' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Crear y continuar' })).toBeInTheDocument()
  })

  it('does not warn about a missing AI key when one is configured (default)', async () => {
    const user = userEvent.setup()
    renderSetup()
    await user.click(screen.getByRole('button', { name: 'Comenzar' }))
    await user.click(await screen.findByRole('heading', { name: 'Organizacion' }))
    await user.click(screen.getByRole('button', { name: 'Continuar' }))
    await screen.findByRole('heading', { name: 'Tu cuenta' })
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('warns about a missing AI key on the owner form when the deployment has none', async () => {
    vi.spyOn(setupApi, 'useCapabilities').mockReturnValue(
      caps({ ai: blocked(), generation: blocked(), tutor: blocked() }) as Required<
        setupApi.Capabilities
      >,
    )
    const user = userEvent.setup()
    renderSetup()
    await user.click(screen.getByRole('button', { name: 'Comenzar' }))
    await user.click(await screen.findByRole('heading', { name: 'Organizacion' }))
    await user.click(screen.getByRole('button', { name: 'Continuar' }))
    await screen.findByRole('heading', { name: 'Tu cuenta' })
    expect(screen.getByRole('status')).toHaveTextContent('LLM_API_KEY')
    vi.restoreAllMocks()
  })
})
