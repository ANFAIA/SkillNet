import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { IntlProvider } from 'react-intl'
import type { ReactNode } from 'react'

import { SourceImageBlock } from './SourceImageBlock'
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
 * Same plain-object double as `InfographicImageBlock.test.tsx`: `useCredentialedAsset`
 * only reads `ok` and `blob()`, and building a real `Response` around a jsdom `Blob`
 * breaks on Node 22 (`object.stream is not a function`) before the assertion runs.
 */
function assetResponse(bytes: string, type: string) {
  return { ok: true, status: 200, blob: async () => new Blob([bytes], { type }) } as unknown as Response
}

describe('SourceImageBlock', () => {
  it('fetches the image through the document-scoped route and shows it with its alt text', async () => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:src-1')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(assetResponse('png', 'image/png'))

    wrap(
      <SourceImageBlock
        imageId="img-7"
        alt="Pantalla de devoluciones"
        caption="Fuente: manual.pdf, pág. 7"
        documentId="doc-3"
      />,
    )

    const img = (await screen.findByAltText('Pantalla de devoluciones')) as HTMLImageElement
    expect(img.getAttribute('src')).toBe('blob:src-1')
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/v1/documents/doc-3/images/img-7',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  /**
   * The whole reason this block is not a copy of `InfographicImageBlock`: the provenance
   * line is the record that this picture is the customer's own material, so it is on
   * screen and not in a title attribute.
   */
  it('renders the provenance caption next to the image', async () => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:src-2')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(assetResponse('png', 'image/png'))

    const { container } = wrap(
      <SourceImageBlock
        imageId="img-7"
        alt="Pantalla de devoluciones"
        caption="Fuente: manual.pdf, pág. 7"
        documentId="doc-3"
      />,
    )

    await screen.findByAltText('Pantalla de devoluciones')
    expect(screen.getByText('Fuente: manual.pdf, pág. 7')).toBeInTheDocument()
    expect(container.querySelector('figcaption')?.textContent).toBe('Fuente: manual.pdf, pág. 7')
  })

  it('falls back to generic provenance and a generic alt when neither is given', async () => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:src-3')
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(assetResponse('png', 'image/png'))

    wrap(<SourceImageBlock imageId="img-8" alt="" caption="" documentId="doc-3" />)

    expect(await screen.findByAltText(messages['sourceImage.title'])).toBeInTheDocument()
    expect(screen.getByText(messages['sourceImage.fromDocument'])).toBeInTheDocument()
  })

  /**
   * Un fichero que ya no esta en el almacen de subidas es un fallo del despliegue, no de
   * quien lee la leccion. El bloque desaparece —el modo `hide` de `<Gated>`— en vez de
   * pintar un aviso rojo sobre algo que el aprendiz no puede arreglar.
   */
  it('renders nothing when the bytes cannot be fetched', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('nope', { status: 404 }))

    const { container } = wrap(
      <SourceImageBlock imageId="missing" alt="X" caption="Fuente: manual.pdf" documentId="doc-3" />,
    )

    await waitFor(() => expect(container).toBeEmptyDOMElement())
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByText(messages['sourceImage.unavailable'])).toBeNull()
  })

  it('degrades the same way when the broker sends no document id', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')

    const { container } = wrap(
      <SourceImageBlock imageId="img-9" alt="X" caption="" documentId="" />,
    )

    await waitFor(() => expect(container).toBeEmptyDOMElement())
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('never throws at its caller when fetch itself rejects', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network down'))

    const { container } = wrap(
      <SourceImageBlock imageId="img-10" alt="X" caption="" documentId="doc-3" />,
    )

    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })
})
