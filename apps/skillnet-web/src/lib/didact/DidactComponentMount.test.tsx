import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DidactComponentMount } from './DidactComponentMount'

describe('DidactComponentMount', () => {
  it('shows a clear unavailable state and does not load a blocked component', () => {
    render(
      <DidactComponentMount
        componentId="didact.quiz.single-choice"
        componentProps={{ question: 'Protected assessment' }}
        ports={{}}
      />,
    )

    expect(screen.getByText('Esta actividad no está disponible en este entorno.')).toBeInTheDocument()
    expect(screen.queryByText('Protected assessment')).not.toBeInTheDocument()
  })

  it('loads a ready component inside the scoped host boundary', async () => {
    const { container } = render(
      <DidactComponentMount
        componentId="didact.timeline-steps"
        componentProps={{
          steps: [{ id: 'one', title: 'First safe step' }],
        }}
        ports={{}}
      />,
    )

    expect(screen.getByText('Cargando actividad…')).toBeInTheDocument()
    await screen.findByText('First safe step')

    const scope = container.querySelector('.didact-scope')
    expect(scope).toHaveAttribute('data-didact-availability', 'ready')
  })

  it('announces degraded mode while still rendering a locally usable component', async () => {
    render(
      <DidactComponentMount
        componentId="didact.flashcard"
        componentProps={{ front: 'Question', back: 'Answer' }}
        ports={{}}
      />,
    )

    await waitFor(() => {
      expect(document.querySelector('[data-didact-availability="degraded"]')).toBeInTheDocument()
    })
    expect(screen.getByText('Algunas funciones de esta actividad no están disponibles.')).toHaveClass('sr-only')
  })
})
