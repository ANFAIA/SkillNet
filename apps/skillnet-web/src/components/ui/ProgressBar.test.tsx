import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ProgressBar } from './ProgressBar'

describe('ProgressBar', () => {
  it('renders without crashing', () => {
    const { container } = render(<ProgressBar value={50} />)
    expect(container.firstElementChild).toBeInTheDocument()
  })

  it('sets the inner bar width from the value prop', () => {
    const { container } = render(<ProgressBar value={75} />)
    const bar = container.querySelector('[style]') as HTMLElement
    expect(bar.style.width).toBe('75%')
  })

  it('clamps value above 100 to 100%', () => {
    const { container } = render(<ProgressBar value={150} />)
    const bar = container.querySelector('[style]') as HTMLElement
    expect(bar.style.width).toBe('100%')
  })

  it('clamps value below 0 to 0%', () => {
    const { container } = render(<ProgressBar value={-10} />)
    const bar = container.querySelector('[style]') as HTMLElement
    expect(bar.style.width).toBe('0%')
  })

  it('shows the label when showLabel is true', () => {
    render(<ProgressBar value={42} showLabel />)
    expect(screen.getByText('42%')).toBeInTheDocument()
  })

  it('does not show the label by default', () => {
    render(<ProgressBar value={42} />)
    expect(screen.queryByText('42%')).not.toBeInTheDocument()
  })

  it('rounds the label to nearest integer', () => {
    render(<ProgressBar value={33.7} showLabel />)
    expect(screen.getByText('34%')).toBeInTheDocument()
  })

  it('applies primary variant by default', () => {
    const { container } = render(<ProgressBar value={50} />)
    const bar = container.querySelector('[style]') as HTMLElement
    expect(bar.className).toContain('bg-primary')
  })

  it('applies accent variant class', () => {
    const { container } = render(<ProgressBar value={50} variant="accent" />)
    const bar = container.querySelector('[style]') as HTMLElement
    expect(bar.className).toContain('bg-accent')
  })

  it('uses auto color based on value', () => {
    // value >= 80 => bg-accent
    const { container: c1 } = render(<ProgressBar value={85} variant="auto" />)
    const bar1 = c1.querySelector('[style]') as HTMLElement
    expect(bar1.className).toContain('bg-accent')

    // value >= 40 and < 80 => bg-primary
    const { container: c2 } = render(<ProgressBar value={50} variant="auto" />)
    const bar2 = c2.querySelector('[style]') as HTMLElement
    expect(bar2.className).toContain('bg-primary')

    // value < 40 => bg-warning
    const { container: c3 } = render(<ProgressBar value={20} variant="auto" />)
    const bar3 = c3.querySelector('[style]') as HTMLElement
    expect(bar3.className).toContain('bg-warning')
  })

  it('uses custom color via style when color prop is set', () => {
    const { container } = render(<ProgressBar value={60} color="#ff0000" />)
    const bar = container.querySelector('[style]') as HTMLElement
    expect(bar.style.backgroundColor).toBe('rgb(255, 0, 0)')
  })

  it('applies custom className', () => {
    const { container } = render(
      <ProgressBar value={50} className="mt-4" />,
    )
    expect(container.firstElementChild).toHaveClass('mt-4')
  })
})
