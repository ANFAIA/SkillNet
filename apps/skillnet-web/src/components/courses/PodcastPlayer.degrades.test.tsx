import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { IntlProvider } from 'react-intl'
import type { ReactNode } from 'react'

import { PodcastPlayer } from './PodcastPlayer'
import { es as messages } from '../../i18n/es'

/**
 * Cuando el mp3 no se puede servir, el reproductor de curso **degrada a su transcripcion**.
 *
 * El caso real: el volumen `media_assets` se pierde, las filas siguen diciendo `done`, y la
 * ruta del asset responde 410 (`asset_missing`). Antes de esto la superficie pintaba el
 * mensaje en `text-danger` con `role="alert"` — una alarma por un fallo del despliegue que el
 * aprendiz no ha causado ni puede arreglar. Aqui el audio desaparece, el aviso queda en tono
 * apagado y lo que si hay (transcripcion y fuentes) sigue delante.
 */
function wrap(node: ReactNode) {
  return render(
    <IntlProvider locale="es" messages={messages}>
      {node}
    </IntlProvider>,
  )
}

afterEach(() => vi.restoreAllMocks())

const TURNS = [
  { speaker: 'A' as const, text: 'La memoria se consolida al dormir.', citation_ids: ['c1'] },
  { speaker: 'B' as const, text: 'Y el repaso espaciado la sostiene.', citation_ids: [] },
]

describe('PodcastPlayer when the audio asset is gone', () => {
  it('keeps the transcript and says so without alarming the learner', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('gone', { status: 410 }))

    const { container } = wrap(
      <PodcastPlayer artifactId="lost" turns={TURNS} citations={[]} title="Audio overview" />,
    )

    // El aviso llega, en tono apagado y sin alarma.
    const notice = await screen.findByText(/no está disponible/i)
    expect(notice.textContent).toMatch(/transcripci/i)
    expect(notice.className).toContain('text-text-muted')
    expect(screen.queryByRole('alert')).toBeNull()
    expect(container.querySelector('.text-danger')).toBeNull()

    // No hay reproductor que no pueda reproducir...
    expect(container.querySelector('audio')).toBeNull()
    // ...pero si esta todo lo que el aprendiz puede leer.
    expect(screen.getByText(TURNS[0].text)).toBeInTheDocument()
    expect(screen.getByText(TURNS[1].text)).toBeInTheDocument()
    expect(screen.getByText(messages['podcast.transcript'])).toBeInTheDocument()
  })

  it('still renders the audio element when the asset is served', async () => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:podcast-ok')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => new Blob(['mp3'], { type: 'audio/mpeg' }),
    } as unknown as Response)

    const { container } = wrap(
      <PodcastPlayer artifactId="ready" turns={TURNS} citations={[]} />,
    )

    const audio = await waitFor(() => {
      const el = container.querySelector('audio')
      expect(el).not.toBeNull()
      return el as HTMLAudioElement
    })
    expect(audio.getAttribute('src')).toBe('blob:podcast-ok')
  })
})
