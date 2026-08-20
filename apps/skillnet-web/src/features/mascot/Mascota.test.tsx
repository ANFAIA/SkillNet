import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { declaredReducedMotionContext } from '../../hooks/useReducedMotion'
import { Mascota } from './Mascota'

describe('Mascota', () => {
  it('renders idle (default) as a labelled mascot', () => {
    render(<Mascota />)
    expect(screen.getByRole('img', { name: 'Mascota de SkillNet' })).toBeInTheDocument()
  })

  it('renders the happy expression', () => {
    render(<Mascota expression="happy" ariaLabel="Feliz" />)
    expect(screen.getByRole('img', { name: 'Feliz' })).toBeInTheDocument()
  })

  it('honours an explicit size', () => {
    render(<Mascota size={220} />)
    const svg = screen.getByRole('img', { name: 'Mascota de SkillNet' })
    expect(svg).toHaveAttribute('width', '220')
    expect(svg).toHaveAttribute('height', '220')
  })

  it('renders static (no float loop) when reduced motion is declared', () => {
    // The declared preference alone must silence motion — the hook ORs it with the OS
    // setting, so a provider value of true is enough. The reduced-motion branch drops the
    // float keyframes entirely; we assert it takes that path without crashing and still
    // renders the mascot.
    render(
      <declaredReducedMotionContext.Provider value={true}>
        <Mascota />
      </declaredReducedMotionContext.Provider>,
    )
    const svg = screen.getByRole('img', { name: 'Mascota de SkillNet' })
    expect(svg).toBeInTheDocument()
    // The outer float wrapper carries no repeating transform: under reduced motion the
    // element is not left mid-animation on a translate/rotate.
    const wrapper = svg.parentElement as HTMLElement
    expect(wrapper.style.transform ?? '').not.toMatch(/rotate|translateY/)
  })
})
