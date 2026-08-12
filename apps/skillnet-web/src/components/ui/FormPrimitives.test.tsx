import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PageHeader } from './PageHeader'
import { SearchField } from './SearchField'
import { Select } from './Select'
import { Switch } from './Switch'

describe('shared interface primitives', () => {
  it('gives every page one semantic top-level heading', () => {
    render(<PageHeader title="Empleados" description="5 miembros" actions={<button>Agregar</button>} />)

    expect(screen.getByRole('heading', { level: 1, name: 'Empleados' })).toBeInTheDocument()
    expect(screen.getByText('5 miembros')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Agregar' })).toBeInTheDocument()
  })

  it('keeps search and select controls accessible with hidden labels', () => {
    render(
      <>
        <SearchField label="Buscar cursos" placeholder="Buscar" />
        <Select label="Estado" hideLabel defaultValue="all"><option value="all">Todos</option></Select>
      </>,
    )

    expect(screen.getByRole('searchbox', { name: 'Buscar cursos' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Estado' })).toBeInTheDocument()
  })

  it('exposes switch state and delegates changes', async () => {
    const user = userEvent.setup()
    const onCheckedChange = vi.fn()
    render(<Switch label="Maquetar respuestas" checked={false} onCheckedChange={onCheckedChange} />)

    await user.click(screen.getByRole('switch', { name: 'Maquetar respuestas' }))
    expect(onCheckedChange).toHaveBeenCalledWith(true)
  })
})
