import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { Badge } from './Badge'

describe('Badge', () => {
  it('renders children text', () => {
    render(<Badge>New</Badge>)
    expect(screen.getByText('New')).toBeInTheDocument()
  })

  it('uses primary variant by default', () => {
    const { container } = render(<Badge>Default</Badge>)
    const span = container.firstElementChild as HTMLElement
    expect(span.className).toContain('text-primary')
  })

  it('applies accent variant classes', () => {
    const { container } = render(<Badge variant="accent">Pro</Badge>)
    const span = container.firstElementChild as HTMLElement
    expect(span.className).toContain('text-accent')
  })

  it('applies warning variant classes', () => {
    const { container } = render(<Badge variant="warning">Warn</Badge>)
    const span = container.firstElementChild as HTMLElement
    expect(span.className).toContain('text-warning')
  })

  it('applies danger variant classes', () => {
    const { container } = render(<Badge variant="danger">Error</Badge>)
    const span = container.firstElementChild as HTMLElement
    expect(span.className).toContain('text-danger')
  })

  it('renders the spider icon in default badgeStyle', () => {
    const { container } = render(<Badge>Status</Badge>)
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
    expect(svg).toHaveAttribute('aria-hidden', 'true')
  })

  it('does not render spider icon in plain badgeStyle', () => {
    const { container } = render(<Badge badgeStyle="plain">Plain</Badge>)
    const svg = container.querySelector('svg')
    expect(svg).not.toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(<Badge className="ml-2">Tag</Badge>)
    const span = container.firstElementChild as HTMLElement
    expect(span.className).toContain('ml-2')
  })
})
