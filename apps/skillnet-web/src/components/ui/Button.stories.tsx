import type { Meta, StoryObj } from '@storybook/react-vite'
import { Button } from './Button'

const meta: Meta<typeof Button> = {
  title: 'UI/Button',
  component: Button,
  argTypes: {
    variant: {
      control: 'select',
      options: ['primary', 'secondary', 'ghost', 'accent', 'danger'],
    },
    size: {
      control: 'select',
      options: ['sm', 'md', 'lg'],
    },
  },
}
export default meta

type Story = StoryObj<typeof Button>

export const Primary: Story = {
  args: { children: 'Crear curso', variant: 'primary' },
}

export const Secondary: Story = {
  args: { children: 'Cancelar', variant: 'secondary' },
}

export const Ghost: Story = {
  args: { children: 'Ver detalles', variant: 'ghost' },
}

export const Accent: Story = {
  args: { children: 'Publicar curso', variant: 'accent' },
}

export const Danger: Story = {
  args: { children: 'Eliminar curso', variant: 'danger' },
}

export const Disabled: Story = {
  args: { children: 'No disponible', variant: 'primary', disabled: true },
}

export const Small: Story = {
  args: { children: 'Filtrar', variant: 'secondary', size: 'sm' },
}

export const Large: Story = {
  args: { children: 'Empezar formacion', variant: 'primary', size: 'lg' },
}

export const AllVariants = () => (
  <div className="space-y-6">
    <div>
      <p className="text-xs text-text-muted mb-2">Variantes</p>
      <div className="flex items-center gap-3">
        <Button variant="primary">Crear curso</Button>
        <Button variant="secondary">Cancelar</Button>
        <Button variant="ghost">Ver detalles</Button>
        <Button variant="accent">Publicar</Button>
        <Button variant="danger">Eliminar</Button>
      </div>
    </div>
    <div>
      <p className="text-xs text-text-muted mb-2">Tamanos</p>
      <div className="flex items-center gap-3">
        <Button size="sm">Filtrar resultados</Button>
        <Button size="md">Asignar curso</Button>
        <Button size="lg">Empezar formacion</Button>
      </div>
    </div>
    <div>
      <p className="text-xs text-text-muted mb-2">Deshabilitados</p>
      <div className="flex items-center gap-3">
        <Button disabled>Crear curso</Button>
        <Button variant="secondary" disabled>Cancelar</Button>
        <Button variant="accent" disabled>Publicar</Button>
      </div>
    </div>
  </div>
)
