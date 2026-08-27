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

  /**
   * El caso del volumen de media perdido: la fila dice `done`, el fichero no esta, y el
   * aprendiz veia "Audio no disponible" en rojo por algo que no ha causado ni puede
   * arreglar. El bloque es un extra que el broker ofrecio, no algo que el pidiera, asi que
   * desaparece — el modo `hide` de `<Gated>`. El rastro del fallo esta en el log de la API.
   */
  it('renders nothing at all when the asset cannot be fetched', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('gone', { status: 410 }))

    const { container } = wrap(<PodcastPlayerBlock artifactId="missing" title="X" />)

    await waitFor(() => expect(container.querySelector('audio')).toBeNull())
    // Ni reproductor, ni cabecera, ni aviso rojo: nada.
    await waitFor(() => expect(container).toBeEmptyDOMElement())
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByText(messages['podcast.unavailable'])).toBeNull()
  })
})
