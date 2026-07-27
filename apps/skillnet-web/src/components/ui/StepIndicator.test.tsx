import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { StepIndicator } from './StepIndicator'

/**
 * The extraction out of `pages/admin/CreateCourse.tsx` claims "no functional
 * change" (§13, B8). These are the observable properties that claim rests on.
 */
describe('StepIndicator', () => {
  it('draws one bubble per step and a rail between them', () => {
    const { container } = render(<StepIndicator current={0} total={5} />)
    expect(container.querySelectorAll('.rounded-full')).toHaveLength(5)
    expect(container.querySelectorAll('.h-px')).toHaveLength(4)
  })

  it('marks past steps done, the current one active and the rest idle', () => {
    const { container } = render(<StepIndicator current={2} total={4} />)
    const bubbles = Array.from(container.querySelectorAll('.rounded-full'))
    expect(bubbles[0].className).toContain('bg-accent')
    expect(bubbles[1].className).toContain('bg-accent')
    expect(bubbles[2].className).toContain('bg-primary')
    expect(bubbles[3].className).toContain('bg-bg-muted')
  })

  it('numbers pending steps from 1 and swaps completed ones for a check', () => {
    const { container } = render(<StepIndicator current={1} total={3} />)
    const bubbles = Array.from(container.querySelectorAll('.rounded-full'))
    expect(bubbles[0].querySelector('svg')).not.toBeNull()
    expect(bubbles[1]).toHaveTextContent('2')
    expect(bubbles[2]).toHaveTextContent('3')
  })
})
