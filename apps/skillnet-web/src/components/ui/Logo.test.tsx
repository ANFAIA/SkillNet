import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Logo } from './Logo'

describe('Logo', () => {
  it('renders the brand mark as a labelled image', () => {
    render(<Logo />)
    const svg = screen.getByRole('img', { name: 'SkillNet' })
    expect(svg.tagName.toLowerCase()).toBe('svg')
  })

  it('accent tone drives colour from var(--color-primary), painting via currentColor', () => {
    render(<Logo tone="accent" />)
    const svg = screen.getByRole('img', { name: 'SkillNet' })
    expect(svg).toHaveStyle({ color: 'var(--color-primary)' })
    // The mark inherits the tone through currentColor rather than a hardcoded fill.
    expect(svg.querySelector('path')).toHaveAttribute('fill', 'currentColor')
  })

  it('on-dark tone forces white', () => {
    render(<Logo tone="on-dark" />)
    expect(screen.getByRole('img', { name: 'SkillNet' })).toHaveStyle({ color: '#ffffff' })
  })

  it('honours an explicit size', () => {
    render(<Logo size={64} />)
    const svg = screen.getByRole('img', { name: 'SkillNet' })
    expect(svg).toHaveAttribute('width', '64')
    expect(svg).toHaveAttribute('height', '64')
  })
})
