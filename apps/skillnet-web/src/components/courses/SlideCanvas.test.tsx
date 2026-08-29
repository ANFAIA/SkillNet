import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SlideCanvas, type SlideCanvasSpec } from './SlideCanvas'

const base: SlideCanvasSpec = {
  title: 'Una idea clara',
  subtitle: 'Contexto suficiente para entenderla sin un presentador',
  blocks: [{ type: 'text', text: 'El contenido sigue siendo texto real.', variant: 'lead' }],
}

describe('SlideCanvas', () => {
  it('keeps structured copy visible when a generated illustration exists', () => {
    const { container } = render(
      <SlideCanvas slide={{ ...base, composition: 'split' }} imageUrl="/illustration.png" />,
    )

    expect(screen.getByText('Una idea clara')).toBeInTheDocument()
    expect(container.firstChild).toHaveTextContent('El contenido sigue siendo texto real.')
    expect(container.querySelector('img')).toHaveAttribute('alt', '')
    expect(container.querySelector('[data-slide-composition]')).toHaveAttribute(
      'data-slide-composition',
      'split',
    )
  })

  it('does not add decorative imagery to data compositions', () => {
    const { container } = render(
      <SlideCanvas
        slide={{
          ...base,
          composition: 'data',
          blocks: [
            { type: 'chart', kind: 'bar', title: 'Datos', labels: ['A'], values: [1] },
          ],
        }}
        imageUrl="/unused-illustration.png"
      />,
    )

    expect(container.querySelector('img')).toBeNull()
    expect(container.firstChild).toHaveTextContent('Datos')
  })

  it('infers process and data compositions for legacy artifacts', () => {
    const { container, rerender } = render(
      <SlideCanvas
        slide={{
        ...base,
        blocks: [{ type: 'steps', title: 'Proceso', steps: ['Primero', 'Después'] }],
        }}
      />,
    )
    expect(container.querySelector('[data-slide-composition]')).toHaveAttribute(
      'data-slide-composition',
      'process',
    )

    rerender(
      <SlideCanvas
        slide={{
          ...base,
          blocks: [
            { type: 'chart', kind: 'bar', title: 'Datos', labels: ['A'], values: [1] },
          ],
        }}
      />,
    )
    expect(container.querySelector('[data-slide-composition]')).toHaveAttribute(
      'data-slide-composition',
      'data',
    )
  })

  it('renders comparison blocks in the same controlled canvas', () => {
    const { container } = render(
      <SlideCanvas
        slide={{
          ...base,
          composition: 'comparison',
          blocks: [
            { type: 'text', text: 'Antes: trabajo manual.' },
            { type: 'text', text: 'Después: proceso claro.' },
          ],
        }}
      />,
    )

    expect(container.firstChild).toHaveTextContent('Antes: trabajo manual.')
    expect(container.firstChild).toHaveTextContent('Después: proceso claro.')
  })

  it('renders concept grids and explained timelines with course components', async () => {
    const { container, rerender } = render(
      <SlideCanvas
        slide={{
          ...base,
          composition: 'grid',
          blocks: [
            { type: 'card', title: 'Comprender', text: 'Leer el contexto.' },
            { type: 'card', title: 'Actuar', text: 'Acordar el siguiente paso.' },
          ],
        }}
      />,
    )

    expect(container.firstChild).toHaveTextContent('Comprender')
    expect(container.firstChild).toHaveTextContent('Acordar el siguiente paso.')

    rerender(
      <SlideCanvas
        slide={{
          ...base,
          composition: 'timeline',
          blocks: [
            {
              type: 'timeline',
              label: 'Ciclo',
              steps: ['Recibir', 'Cerrar'],
              details: ['Recopilar contexto', 'Confirmar el resultado'],
            },
          ],
        }}
      />,
    )

    expect(await screen.findByText('Recibir')).toBeInTheDocument()
    expect(screen.getByText('Confirmar el resultado')).toBeInTheDocument()
  })
})
