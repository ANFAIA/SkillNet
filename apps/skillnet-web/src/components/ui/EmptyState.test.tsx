import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { EmptyState } from './EmptyState'

describe('EmptyState', () => {
  it('renders the title', () => {
    render(<EmptyState title="No courses yet" />)
    expect(screen.getByText('No courses yet')).toBeInTheDocument()
  })

  it('renders the description when provided', () => {
    render(
      <EmptyState
        title="No courses"
        description="Create your first course to get started"
      />,
    )
    expect(
      screen.getByText('Create your first course to get started'),
    ).toBeInTheDocument()
  })

  it('does not render description when omitted', () => {
    const { container } = render(<EmptyState title="Empty" />)
    // Only the title paragraph should be present
    const paragraphs = container.querySelectorAll('p')
    expect(paragraphs).toHaveLength(1)
  })

  it('renders an icon when provided', () => {
    render(
      <EmptyState
        title="No data"
        icon={<span data-testid="custom-icon">icon</span>}
      />,
    )
    expect(screen.getByTestId('custom-icon')).toBeInTheDocument()
  })

  it('renders an action button that fires onClick', async () => {
    const user = userEvent.setup()
    const handleClick = vi.fn()

    render(
      <EmptyState
        title="Nothing here"
        action={{ label: 'Add item', onClick: handleClick }}
      />,
    )

    const button = screen.getByText('Add item')
    expect(button).toBeInTheDocument()

    await user.click(button)
    expect(handleClick).toHaveBeenCalledOnce()
  })

  it('does not render action button when omitted', () => {
    render(<EmptyState title="Empty" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(
      <EmptyState title="Test" className="my-custom-class" />,
    )
    expect(container.firstElementChild).toHaveClass('my-custom-class')
  })
})
