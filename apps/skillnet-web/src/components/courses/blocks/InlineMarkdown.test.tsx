import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { InlineMarkdown } from './InlineMarkdown'

describe('InlineMarkdown', () => {
  it('renders a bare domain (no protocol) as a clickable link', () => {
    render(<InlineMarkdown>{'Entra en events.ticketrona.com y accede al panel.'}</InlineMarkdown>)
    const link = screen.getByRole('link', { name: 'events.ticketrona.com' })
    expect(link).toHaveAttribute('href', 'https://events.ticketrona.com')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('renders a www.-prefixed bare URL via remark-gfm autolink', () => {
    render(<InlineMarkdown>{'Visita www.ticketrona.com para mas info.'}</InlineMarkdown>)
    const link = screen.getByRole('link', { name: 'www.ticketrona.com' })
    expect(link).toHaveAttribute('href', 'https://www.ticketrona.com')
  })

  it('still renders an explicit markdown link', () => {
    render(<InlineMarkdown>{'Consulta el [manual](https://example.com/manual).'}</InlineMarkdown>)
    const link = screen.getByRole('link', { name: 'manual' })
    expect(link).toHaveAttribute('href', 'https://example.com/manual')
  })

  it('still renders plain bold/italic text unaffected', () => {
    render(<InlineMarkdown>{'Esto es **importante** y esto *tambien*.'}</InlineMarkdown>)
    expect(screen.getByText('importante')).toBeInTheDocument()
    expect(screen.getByText('tambien')).toBeInTheDocument()
  })
})
