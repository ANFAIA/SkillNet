import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SlideCanvas, type SlideCanvasSpec } from './SlideCanvas'

const base: SlideCanvasSpec = {
  title: 'Una idea clara',
  subtitle: 'Contexto suficiente para entenderla sin un presentador',
  blocks: [{ type: 'text', text: 'El contenido sigue siendo texto real.', variant: 'lead' }],
}

/** Every composition the renderer knows, each in its with- and without-image form. */
const everyComposition: { slide: SlideCanvasSpec; imageUrl?: string }[] = [
  { slide: { ...base, composition: 'cover', blocks: [] } },
  { slide: { ...base, composition: 'cover', blocks: [] }, imageUrl: '/i.png' },
  { slide: { ...base, composition: 'statement' } },
  { slide: { ...base, composition: 'statement' }, imageUrl: '/i.png' },
  { slide: { ...base, composition: 'split' } },
  { slide: { ...base, composition: 'split' }, imageUrl: '/i.png' },
  {
    slide: {
      ...base,
      composition: 'comparison',
      blocks: [
        { type: 'text', text: 'Antes.' },
        { type: 'table', headers: ['Tecnica', 'Descripcion', 'Uso'], rows: [['Esquiva', 'Gira', 'Contra']] },
      ],
    },
  },
  {
    slide: {
      ...base,
      composition: 'grid',
      blocks: [
        { type: 'card', title: 'Comprender', text: 'Leer.' },
        { type: 'card', title: 'Actuar', text: 'Decidir.' },
      ],
    },
  },
  {
    slide: {
      ...base,
      composition: 'process',
      blocks: [{ type: 'steps', title: 'Proceso', steps: ['Primero', 'Despues'] }],
    },
  },
  {
    slide: {
      ...base,
      composition: 'data',
      blocks: [{ type: 'chart', kind: 'bar', title: 'Datos', labels: ['A'], values: [1] }],
    },
  },
]

/** A Tailwind viewport-breakpoint variant (`sm:…`), never a container one (`@2xl:…`). */
const VIEWPORT_VARIANT = /(?:^|\s)(?:sm|md|lg|xl|2xl):/

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

  /**
   * The regression this file exists to hold: the canvas used to be `sm:aspect-video` over
   * `overflow-hidden`, so its height was a function of its width and eight of the nine
   * slides of a real deck were cut off — the worst one showing 315 px of 1223 px. A slide
   * is sized by its content now, with a width-independent floor so a one-line cover still
   * reads as a slide.
   */
  it('sizes every composition by its content instead of a fixed aspect ratio', () => {
    for (const { slide, imageUrl } of everyComposition) {
      const { container, unmount } = render(<SlideCanvas slide={slide} imageUrl={imageUrl} />)
      const canvas = container.querySelector('[data-slide-composition]')!

      expect(canvas.className).not.toMatch(/(?:^|\s)\S*aspect-/)
      expect(canvas.className).not.toMatch(/(?:^|\s)\S*h-\[/)
      // A floor, not a cage: presence when the slide is short, growth when it is not.
      expect(canvas.className).toMatch(/(?:^|\s)min-h-\d/)

      unmount()
    }
  })

  /**
   * "It deforms depending on the view you look at it in": the deck always lives inside
   * something narrower than the window (a `max-w-2xl` modal, a library panel), so viewport
   * breakpoints made the same ~560 px box lay out differently as the window changed around
   * it. The canvas is its own query container and every breakpoint under it is a container
   * query, so a slide's layout depends on the slide's width and nothing else.
   */
  it('decides its layout from its own width, never from the window', () => {
    for (const { slide, imageUrl } of everyComposition) {
      const { container, unmount } = render(<SlideCanvas slide={slide} imageUrl={imageUrl} />)
      const canvas = container.querySelector('[data-slide-composition]')!

      expect(canvas.className.split(/\s+/)).toContain('@container')

      const offenders = [canvas, ...canvas.querySelectorAll('*')]
        .map((el) => el.getAttribute('class') ?? '')
        .filter((className) => VIEWPORT_VARIANT.test(className))
      expect(offenders).toEqual([])

      unmount()
    }
  })
})
