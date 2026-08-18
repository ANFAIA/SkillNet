import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { IntlProvider } from 'react-intl'
import type { ReactNode } from 'react'

import { PodcastPlayerBlock } from './PodcastPlayerBlock'
import { es as messages } from '../../../i18n/es'

function wrap(node: ReactNode) {
  return render(
    <IntlProvider locale="es" messages={messages}>
      {node}
    </IntlProvider>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('PodcastPlayerBlock', () => {
  it('fetches the artefact asset and renders a working audio player', async () => {
    const createUrl = vi
      .spyOn(URL, 'createObjectURL')
      .mockReturnValue('blob:podcast-1')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(new Blob(['mp3'], { type: 'audio/mpeg' }), { status: 200 }))

    const { container } = wrap(<PodcastPlayerBlock artifactId="art-1" title="Repaso en audio" />)

    // The title is shown over the player.
    expect(screen.getByText('Repaso en audio')).toBeInTheDocument()

    const audio = await waitFor(() => {
      const el = container.querySelector('audio[data-testid="podcast-block-audio"]')
      expect(el).not.toBeNull()
      return el as HTMLAudioElement
    })
    expect(audio.getAttribute('src')).toBe('blob:podcast-1')
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/v1/media/artifacts/art-1/asset',
      expect.objectContaining({ credentials: 'include' }),
    )
    expect(createUrl).toHaveBeenCalledOnce()
  })

  it('falls back to the default title when none is given', async () => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:podcast-2')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob(['mp3'], { type: 'audio/mpeg' }), { status: 200 }),
    )

    wrap(<PodcastPlayerBlock artifactId="art-2" title="" />)
    expect(screen.getByText(messages['podcast.title'])).toBeInTheDocument()
  })

  it('shows an error state when the asset cannot be fetched', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('nope', { status: 404 }))

    const { container } = wrap(<PodcastPlayerBlock artifactId="missing" title="X" />)

    expect(await screen.findByRole('alert')).toHaveTextContent(messages['podcast.unavailable'])
    expect(container.querySelector('audio')).toBeNull()
  })
})
