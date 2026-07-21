import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { Input } from './Input'

describe('Input', () => {
  it('renders an input element', () => {
    render(<Input placeholder="Enter text" />)
    expect(screen.getByPlaceholderText('Enter text')).toBeInTheDocument()
  })

  it('renders a label when provided', () => {
    render(<Input label="Email" />)
    expect(screen.getByText('Email')).toBeInTheDocument()
  })

  it('does not render a label when omitted', () => {
    const { container } = render(<Input />)
    expect(container.querySelector('label')).not.toBeInTheDocument()
  })

  it('displays an error message', () => {
    render(<Input error="This field is required" />)
    expect(screen.getByText('This field is required')).toBeInTheDocument()
  })

  it('applies error styling to the input', () => {
    render(<Input error="Required" />)
    const input = screen.getByRole('textbox')
    expect(input.className).toContain('border-danger')
  })

  it('does not show error styling when no error', () => {
    render(<Input />)
    const input = screen.getByRole('textbox')
    expect(input.className).not.toContain('border-danger')
  })

  it('forwards native input props', () => {
    const { container } = render(<Input type="email" disabled name="email" />)
    const input = container.querySelector('input') as HTMLInputElement
    expect(input).toBeDisabled()
    expect(input).toHaveAttribute('name', 'email')
    expect(input).toHaveAttribute('type', 'email')
  })

  it('accepts user input', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()

    render(<Input onChange={handleChange} />)
    const input = screen.getByRole('textbox')

    await user.type(input, 'hello')
    expect(handleChange).toHaveBeenCalled()
    expect(input).toHaveValue('hello')
  })

  it('applies custom className to the input', () => {
    render(<Input className="w-64" />)
    const input = screen.getByRole('textbox')
    expect(input.className).toContain('w-64')
  })
})
