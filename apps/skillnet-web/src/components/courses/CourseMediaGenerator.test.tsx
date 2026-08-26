import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CourseMediaGenerator } from './CourseMediaGenerator'
import { es } from '../../i18n/es'
import type { Capabilities, MediaRequirements, SetupStatus } from '../../api/setup'
import { blocked, caps, degraded } from '../../test/fixtures/capabilities'
import type { User } from '../../types'

const mutate = vi.fn()

// Only the network-facing half of the media API is replaced; `MEDIA_KINDS` and the
// types stay real, because the list of kinds is exactly what is under test.
vi.mock('../../api/media', async () => {
  const actual = await vi.importActual<typeof import('../../api/media')>('../../api/media')
  return {
    ...actual,
    useCreateArtifact: () => ({ mutate, isPending: false }),
    useMediaArtifact: () => ({ data: undefined }),
    useMediaStream: () => ({ status: 'idle', step: null, error: null, start: vi.fn() }),
  }
})

/** The table the backend sends on `/setup/status`. An infographic needs a poster. */
const REQUIREMENTS: MediaRequirements = {
  podcast: ['ai', 'tts'],
  video: ['ai', 'images'],
  infographic: ['ai', 'images'],
  slides: ['ai'],
}

function renderGenerator(
  capabilities: Partial<Capabilities>,
  // `null` (not `undefined`) means "the backend sent no table": an explicit
  // `undefined` would silently fall back to the default parameter.
  requirements: MediaRequirements | null = REQUIREMENTS,
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const status: SetupStatus = {
    initialized: true,
    capabilities: capabilities as Capabilities,
    media_requirements: requirements ?? undefined,
  }
  client.setQueryData(['setup', 'status'], status)
  client.setQueryData(['users', 'me'], {
    id: 'u1',
    email: 'ana@demo.test',
    full_name: 'Ana',
    role: 'employee',
  } satisfies User)
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return render(<CourseMediaGenerator courseId="c1" />, { wrapper })
}

const infographic = () => screen.getByRole('button', { name: es['overviews.kind.infographic'] })
const noteField = () => screen.queryByLabelText(es['overviews.steeringLabel'])

describe('<CourseMediaGenerator> with every capability ready', () => {
  beforeEach(() => mutate.mockClear())

  it('offers all four kinds, none of them inert', () => {
    renderGenerator(caps())
    for (const kind of ['podcast', 'video', 'infographic', 'slides'] as const) {
      const tile = screen.getByRole('button', { name: es[`overviews.kind.${kind}`] })
      expect(tile).toBeInTheDocument()
      expect(tile).not.toHaveAttribute('aria-disabled')
    }
  })

  it('opens the steering field when a kind is picked', async () => {
    const user = userEvent.setup()
    renderGenerator(caps())
    expect(noteField()).not.toBeInTheDocument()
    await user.click(infographic())
    expect(await screen.findByLabelText(es['overviews.steeringLabel'])).toBeInTheDocument()
  })
})

describe('<CourseMediaGenerator> with images blocked', () => {
  beforeEach(() => mutate.mockClear())

  it('keeps the infographic tile visible, inert and explained', () => {
    renderGenerator(caps({ images: blocked('missing_api_key') }))
    const tile = infographic()
    expect(tile).toBeVisible()
    expect(tile).toHaveAttribute('aria-disabled', 'true')
    // Focusable on purpose — the explanation has to be reachable by keyboard.
    expect(tile).not.toBeDisabled()
    const description = document.getElementById(tile.getAttribute('aria-describedby') as string)
    expect(description).toHaveTextContent(es['capability.images.unavailable'])
  })

  it('does not open the steering field nor fire a generation when clicked', async () => {
    const user = userEvent.setup()
    renderGenerator(caps({ images: blocked('missing_api_key') }))
    await user.click(infographic())
    expect(noteField()).not.toBeInTheDocument()
    expect(mutate).not.toHaveBeenCalled()
    // No steering field means no generate button either — the whole path is closed.
    expect(
      screen.queryByRole('button', { name: es['overviews.generate'] }),
    ).not.toBeInTheDocument()
  })

  it('blocks every kind that needs images, and leaves the others alone', async () => {
    const user = userEvent.setup()
    renderGenerator(caps({ images: blocked('missing_api_key') }))
    expect(screen.getByRole('button', { name: es['overviews.kind.video'] })).toHaveAttribute(
      'aria-disabled',
      'true',
    )
    const podcast = screen.getByRole('button', { name: es['overviews.kind.podcast'] })
    expect(podcast).not.toHaveAttribute('aria-disabled')
    await user.click(podcast)
    expect(await screen.findByLabelText(es['overviews.steeringLabel'])).toBeInTheDocument()
  })

  it('gates nothing when the backend sent no requirements table', () => {
    // An older API omits `media_requirements`; an absent table constrains nothing,
    // exactly like an absent capability defaults to available.
    renderGenerator(caps({ images: blocked('missing_api_key') }), null)
    expect(infographic()).not.toHaveAttribute('aria-disabled')
  })
})

describe('<CourseMediaGenerator> with a degraded requirement', () => {
  beforeEach(() => mutate.mockClear())

  // The offline eSpeak voice sits under the podcast chain unconditionally, so a
  // keyless TTS still produces audio and the API refuses only `blocked`. A tile made
  // inert here would take away a feature that works.
  it('keeps the podcast usable and says what will be reduced', async () => {
    renderGenerator(caps({ tts: degraded('not_configured') }))
    const podcast = screen.getByRole('button', { name: es['overviews.kind.podcast'] })
    expect(podcast).not.toHaveAttribute('aria-disabled')

    await userEvent.click(podcast)
    expect(noteField()).toBeInTheDocument()
    expect(screen.getByText(es['capability.tts.degraded'])).toBeInTheDocument()
  })
})
