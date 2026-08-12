import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DidactGlossaryBlock } from './DidactGlossaryBlock'
import { DidactSelfExplanationBlock } from './DidactSelfExplanationBlock'
import { DidactTimelineBlock } from './DidactTimelineBlock'
import { DidactWorkedExampleBlock } from './DidactWorkedExampleBlock'

describe('safe Didact OpenUI adapters', () => {
  it('renders glossary terms against parallel definitions', async () => {
    render(<DidactGlossaryBlock title="Conceptos" terms={['SLA']} definitions={['Acuerdo de servicio']} />)
    expect(await screen.findByText('SLA')).toBeInTheDocument()
  })

  it('renders timeline steps and optional details', async () => {
    render(<DidactTimelineBlock label="Proceso" steps={['Abrir', 'Cerrar']} details={['Registrar']} />)
    expect(await screen.findByText('Abrir')).toBeInTheDocument()
    expect(await screen.findByText('Registrar')).toBeInTheDocument()
  })

  it('renders a progressive worked example', async () => {
    render(<DidactWorkedExampleBlock problem="Caso" steps={['Analizar']} summary="Resultado" />)
    expect(await screen.findByText('Caso')).toBeInTheDocument()
    expect(await screen.findByText('Analizar')).toBeInTheDocument()
  })

  it('renders self explanation without automatic grading', async () => {
    render(<DidactSelfExplanationBlock prompt="Explica tu decisión" scaffold={['Porque…']} model="Ejemplo" />)
    expect(await screen.findByText('Explica tu decisión')).toBeInTheDocument()
    expect(await screen.findByRole('textbox')).toBeInTheDocument()
  })
})
