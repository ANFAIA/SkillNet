import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ShimmerSkeleton, ShimmerSkeletonText } from './ShimmerSkeleton'
import { shimmer } from '../../lib/motion'

describe('shimmer preset', () => {
  it('animates transform only — animate-pulse is banned (motion-system.md:437,636)', () => {
    expect(shimmer.initial.x).toBe('-100%')
    expect(shimmer.animate.x).toBe('100%')
    // No opacity/filter keys: an opacity loop is exactly the pulse we are avoiding.
    expect(Object.keys(shimmer.initial)).toEqual(['x'])
    expect(Object.keys(shimmer.animate)).toEqual(['x'])
  })

  it('loops forever, since a placeholder outlives one sweep', () => {
    expect(shimmer.transition.repeat).toBe(Infinity)
    expect(shimmer.transition.duration).toBeGreaterThan(0)
  })
})

describe('ShimmerSkeleton', () => {
  it('applies the sizing classes it is given', () => {
    const { container } = render(<ShimmerSkeleton className="h-4 w-1/2" />)
    const root = container.firstElementChild as HTMLElement
    expect(root.className).toContain('h-4')
    expect(root.className).toContain('w-1/2')
    expect(root.className).toContain('bg-bg-muted')
  })

  it('does not use animate-pulse', () => {
    const { container } = render(<ShimmerSkeleton className="h-4" />)
    expect(container.innerHTML).not.toContain('animate-pulse')
  })

  it('is hidden from assistive tech and from click-to-explain', () => {
    const { container } = render(<ShimmerSkeleton />)
    const root = container.firstElementChild as HTMLElement
    expect(root).toHaveAttribute('aria-hidden', 'true')
    expect(root).toHaveAttribute('data-no-explain')
  })

  it('renders one placeholder per requested text line', () => {
    const { container } = render(<ShimmerSkeletonText lines={4} />)
    expect(container.querySelectorAll('[aria-hidden="true"]')).toHaveLength(4)
  })
})
