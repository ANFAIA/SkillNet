import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

/**
 * The two promises of the wait screen (§9.2), which are both invisible when they break.
 *
 * 1. **Spatial stability.** The placeholder reserves the content area, so the footer does
 *    not jump up the page and get pushed back down when the program lands. A skeleton that
 *    is one line tall looks fine in isolation and ruins the screen in motion.
 * 2. **`prefers-reduced-motion`.** The sweep is dropped entirely, not slowed down. The
 *    shape has to survive without it — the skeleton is what the learner looks at for the
 *    seconds the lesson takes, so it cannot degrade into nothing.
 */

let reduceMotion = false

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual<typeof import('framer-motion')>('framer-motion')
  return { ...actual, useReducedMotion: () => reduceMotion }
})

// Imported after the mock so the component closes over it.
const { NodeSkeleton } = await import('./NodeSkeleton')

/** The sweeping band, identified by the class `ShimmerSkeleton` gives it. */
function sweeps(container: HTMLElement) {
  return container.querySelectorAll('.absolute.inset-y-0')
}

describe('NodeSkeleton', () => {
  it('reserves the height the content will need', () => {
    reduceMotion = false
    render(<NodeSkeleton />)

    expect(screen.getByTestId('node-skeleton').className).toContain('min-h-[22rem]')
  })

  it('is announced as busy, once, instead of per shimmer repaint', () => {
    reduceMotion = false
    render(<NodeSkeleton message="Escribiendo la leccion..." />)

    const skeleton = screen.getByTestId('node-skeleton')
    expect(skeleton).toHaveAttribute('aria-busy', 'true')
    expect(skeleton).toHaveAttribute('aria-live', 'polite')
    expect(skeleton).toHaveTextContent('Escribiendo la leccion...')
  })

  it('takes the shape the `ui_format` event announced', () => {
    reduceMotion = false
    const { container } = render(<NodeSkeleton format="exercise" />)

    expect(screen.getByTestId('node-skeleton')).toHaveAttribute('data-ui-format', 'exercise')
    // The exercise shape is four option-sized blocks; prose is not.
    expect(container.querySelectorAll('.h-9')).toHaveLength(4)
  })

  it('drops the sweep under prefers-reduced-motion but keeps the shape', () => {
    reduceMotion = true
    const { container } = render(<NodeSkeleton format="explanation" />)

    expect(sweeps(container)).toHaveLength(0)
    // Same placeholders, no animation: a static muted block is the accessible
    // degradation, not a slower sweep and not an empty box.
    expect(container.querySelectorAll('[aria-hidden="true"]').length).toBeGreaterThan(4)

    reduceMotion = false
    const { container: animated } = render(<NodeSkeleton format="explanation" />)
    expect(sweeps(animated).length).toBeGreaterThan(0)
  })

  it('counts finished blocks in singular and plural', () => {
    reduceMotion = false
    const { rerender } = render(<NodeSkeleton blocksReady={1} />)
    expect(screen.getByTestId('node-skeleton')).toHaveTextContent('1 bloque listo')

    rerender(<NodeSkeleton blocksReady={3} />)
    expect(screen.getByTestId('node-skeleton')).toHaveTextContent('3 bloques listos')
  })
})
