import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { GenerationStep } from '../../types'

/**
 * What the wait screen has to keep true while a generation runs for half a minute.
 *
 * The visual claim — "something is happening" — is made by three loops, and each one
 * is invisible when it breaks: nobody notices a missing halo, they notice that the
 * screen looks hung. So the assertions here are about the loops *existing* on the
 * active step and nowhere else, and about the rail keeping its position when the
 * server says something we did not plan for.
 */

let reduceMotion = false

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual<typeof import('framer-motion')>('framer-motion')
  return { ...actual, useReducedMotion: () => reduceMotion }
})

const { GenerationProgress } = await import('./GenerationProgress')

const halos = (c: HTMLElement) => c.querySelectorAll('.gen-halo')
const sweeps = (c: HTMLElement) => c.querySelectorAll('.gen-sweep')
const dots = (c: HTMLElement) => c.querySelectorAll('.typing-dots')

describe('GenerationProgress', () => {
  it('owns its heading and names the phase it is on', () => {
    reduceMotion = false
    render(<GenerationProgress progress={{ step: 'structuring' }} />)

    // The heading used to live in CreateCourse.tsx; losing it would leave the wizard
    // step with no title at all.
    expect(screen.getByRole('heading', { name: 'Generando curso' })).toBeInTheDocument()
    expect(screen.getByText(/Paso 3 de 6/)).toBeInTheDocument()
    expect(screen.getByText('Disenando estructura')).toBeInTheDocument()
  })

  it('moves exactly one step: dots, halo and sweep all sit on the active one', () => {
    reduceMotion = false
    const { container } = render(<GenerationProgress progress={{ step: 'generating' }} />)

    expect(dots(container)).toHaveLength(1)
    expect(halos(container)).toHaveLength(1)
    expect(sweeps(container)).toHaveLength(1)
    // Three done, one running, two to go.
    expect(screen.getAllByText('completado')).toHaveLength(3)
    expect(screen.getAllByText('en curso')).toHaveLength(1)
    expect(screen.getAllByText('pendiente')).toHaveLength(2)
  })

  it('shows the live message from the server', () => {
    reduceMotion = false
    render(<GenerationProgress progress={{ step: 'reviewing', message: 'Revisando el modulo 2' }} />)

    expect(screen.getByText('Revisando el modulo 2')).toBeInTheDocument()
  })

  it('holds its position when the server sends a step it does not know', () => {
    reduceMotion = false
    const { container, rerender } = render(<GenerationProgress progress={{ step: 'generating' }} />)
    rerender(<GenerationProgress progress={{ step: 'polishing' as GenerationStep, message: 'Afinando' }} />)

    // The phase is unknown; the progress is not. Rail keeps three completed steps and
    // keeps moving, rather than collapsing back to "nothing done".
    expect(screen.getAllByText('completado')).toHaveLength(3)
    expect(dots(container)).toHaveLength(1)
    expect(screen.getByText('Afinando')).toBeInTheDocument()
  })

  it('stops moving and says where it broke when the job fails', () => {
    reduceMotion = false
    const { container, rerender } = render(<GenerationProgress progress={{ step: 'reviewing' }} />)
    rerender(<GenerationProgress progress={{ step: 'failed', error: 'El modelo no respondio' }} />)

    expect(screen.getByRole('heading', { name: 'La generacion fallo' })).toBeInTheDocument()
    expect(screen.getByText('El modelo no respondio')).toBeInTheDocument()
    // `failed` carries no step name, so the last one seen is the one marked.
    expect(screen.getByText('fallo aqui')).toBeInTheDocument()
    expect(dots(container)).toHaveLength(0)
    expect(halos(container)).toHaveLength(0)
    expect(sweeps(container)).toHaveLength(0)
  })

  it('says something on failure even when no error text arrived', () => {
    reduceMotion = false
    render(<GenerationProgress progress={{ step: 'failed' }} />)

    expect(screen.getByText('No se pudo completar la generacion.')).toBeInTheDocument()
  })

  it('lands every check and stops all motion once published', () => {
    reduceMotion = false
    const { container } = render(<GenerationProgress progress={{ step: 'published' }} />)

    expect(screen.getByRole('heading', { name: 'Curso generado' })).toBeInTheDocument()
    expect(screen.getAllByText('completado')).toHaveLength(6)
    expect(dots(container)).toHaveLength(0)
    expect(halos(container)).toHaveLength(0)
    expect(sweeps(container)).toHaveLength(0)
  })

  it('drops the loops under reduced motion but keeps the rail legible', () => {
    reduceMotion = true
    const { container } = render(<GenerationProgress progress={{ step: 'generating' }} />)

    expect(halos(container)).toHaveLength(0)
    expect(sweeps(container)).toHaveLength(0)
    // The dots stay — they are the indicator, not decoration. The declared
    // preference reaches their CSS through this attribute.
    expect(dots(container)).toHaveLength(1)
    expect(container.querySelector('[data-reduced-motion]')).not.toBeNull()
    expect(screen.getAllByText('completado')).toHaveLength(3)
  })
})
