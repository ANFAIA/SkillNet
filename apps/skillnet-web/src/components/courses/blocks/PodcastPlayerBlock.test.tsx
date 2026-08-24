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

/**
 * El doble de `fetch` devuelve lo UNICO que consume `useArtifactAsset`: `ok` y `blob()`.
 *
 * Antes construia un `Response` de verdad con un `Blob` como cuerpo, y eso depende de que
 * el `Blob` global de jsdom y el `Response` de undici encajen entre si. En Node 24 encajan;
 * en Node 22 —el del CI— no, y el constructor revienta con
 * `TypeError: object.stream is not a function` antes siquiera de llegar a la asercion.
 * Un objeto plano no tiene esa dependencia y prueba exactamente lo mismo.
 */
function assetResponse(bytes: string, type: string) {
  return { ok: true, status: 200, blob: async () => new Blob([bytes], { type }) } as unknown as Response
}

describe('PodcastPlayerBlock', () => {
  it('fetches the artefact asset and renders a working audio player', async () => {
    const createUrl = vi
      .spyOn(URL, 'createObjectURL')
      .mockReturnValue('blob:podcast-1')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(assetResponse('mp3', 'audio/mpeg'))

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
      assetResponse('mp3', 'audio/mpeg'),
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
