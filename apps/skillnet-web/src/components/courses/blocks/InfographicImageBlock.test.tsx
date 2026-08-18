import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { IntlProvider } from 'react-intl'
import type { ReactNode } from 'react'

import { InfographicImageBlock } from './InfographicImageBlock'
import { es as messages } from '../../../i18n/es'

function wrap(node: ReactNode) {
  return render(
    <IntlProvider locale="es" messages={messages}>
      {node}
    </IntlProvider>,
  )
}

afterEach(() => vi.restoreAllMocks())

describe('InfographicImageBlock', () => {
  it('fetches the artefact asset and renders a responsive image with the alt text', async () => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:info-1')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(new Blob(['png'], { type: 'image/png' }), { status: 200 }))

    wrap(<InfographicImageBlock artifactId="art-9" alt="Flujo de caja del cafe" />)

    const img = (await screen.findByAltText('Flujo de caja del cafe')) as HTMLImageElement
    expect(img.getAttribute('src')).toBe('blob:info-1')
    expect(img.className).toContain('w-full')
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/v1/media/artifacts/art-9/asset',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('falls back to a default alt when none is given', async () => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:info-2')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob(['png'], { type: 'image/png' }), { status: 200 }),
    )

    wrap(<InfographicImageBlock artifactId="art-10" alt="" />)
    expect(await screen.findByAltText(messages['infographic.title'])).toBeInTheDocument()
  })

  it('shows an error state when the asset cannot be fetched', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('nope', { status: 500 }))

    const { container } = wrap(<InfographicImageBlock artifactId="missing" alt="X" />)

    expect(await screen.findByRole('alert')).toHaveTextContent(messages['infographic.unavailable'])
    expect(container.querySelector('img')).toBeNull()
  })
})
