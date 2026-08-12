import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DidactLab } from './DidactLab'

describe('DidactLab', () => {
  it('shows the complete 34-type inventory without mounting every module eagerly', () => {
    render(<DidactLab />)

    expect(screen.getAllByRole('article')).toHaveLength(34)
    expect(screen.getByText('34 visibles · 7 fixtures controlados')).toBeInTheDocument()
    expect(screen.getByText('Flashcard')).toBeInTheDocument()
    expect(screen.getByText('SimulationLab')).toBeInTheDocument()
  })

  it('filters by educational type, export or registry module', () => {
    render(<DidactLab />)

    fireEvent.change(screen.getByPlaceholderText('Buscar por tipo, export o módulo…'), {
      target: { value: 'branching' },
    })

    expect(screen.getAllByRole('article')).toHaveLength(1)
    expect(screen.getByText('BranchingScenario')).toBeInTheDocument()
  })

  it('loads and mounts a controlled fixture only after its detail opens', async () => {
    render(<DidactLab />)
    const flashcard = screen.getByText('Flashcard').closest('article')
    expect(flashcard).not.toBeNull()

    fireEvent.click(flashcard!.querySelector('summary')!)

    await waitFor(() => {
      expect(
        screen.getByText('¿Qué debe ocurrir antes de revelar una respuesta?'),
      ).toBeInTheDocument()
    }, { timeout: 15_000 })
  })

  it('explains host requirements instead of inventing a simulation fixture', () => {
    render(<DidactLab />)
    const simulation = screen.getByText('SimulationLab').closest('article')

    expect(simulation).toHaveTextContent('Requiere host: simulation, clock')
    expect(simulation).toHaveTextContent('contrato pendiente')
  })

  it('loads a host-required export but does not mount it with invented state', async () => {
    render(<DidactLab />)
    const simulation = screen.getByText('SimulationLab').closest('article')

    fireEvent.click(simulation!.querySelector('summary')!)

    await waitFor(() => {
      expect(simulation).toHaveTextContent('Módulo y export cargados correctamente')
      expect(simulation).toHaveTextContent('No se monta sin sus puertos y datos protegidos')
    }, { timeout: 15_000 })
  })

  it('keeps all 34 cards alive after opening several function-component exports', async () => {
    render(<DidactLab />)
    const names = ['SingleChoiceQuiz', 'MatchingExercise', 'SimulationLab']

    for (const name of names) {
      const card = screen.getByText(name).closest('article')
      fireEvent.click(card!.querySelector('summary')!)
    }

    await waitFor(() => {
      for (const name of names) {
        expect(screen.getByText(name).closest('article')).toHaveTextContent(
          'Módulo y export cargados correctamente',
        )
      }
    }, { timeout: 20_000 })

    expect(screen.getAllByRole('article')).toHaveLength(34)
    expect(screen.queryByText('Algo salio mal')).not.toBeInTheDocument()
  }, 25_000)
})
