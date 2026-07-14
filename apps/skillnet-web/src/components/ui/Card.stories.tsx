import type { Meta, StoryObj } from '@storybook/react-vite'
import { Card, CardTitle } from './Card'
import { Button } from './Button'
import { ProgressBar } from './ProgressBar'
import { Badge } from './Badge'

const meta: Meta<typeof Card> = {
  title: 'UI/Card',
  component: Card,
  argTypes: {
    variant: {
      control: 'select',
      options: ['default', 'interactive'],
    },
  },
}
export default meta

type Story = StoryObj<typeof Card>

export const Default: Story = {
  render: (args) => (
    <Card {...args}>
      <CardTitle>Protocolo de devoluciones</CardTitle>
      <p className="text-sm text-text-secondary mt-1">3 modulos, 12 ejercicios. Generado desde Manual_Devoluciones_v3.pdf</p>
    </Card>
  ),
  args: { variant: 'default' },
}

export const Interactive: Story = {
  render: (args) => (
    <Card {...args}>
      <CardTitle>Atencion al cliente avanzada</CardTitle>
      <p className="text-sm text-text-secondary mt-1">Modulo 2 de 5. Ultima sesion: ayer</p>
    </Card>
  ),
  args: { variant: 'interactive' },
}

export const WithAction = () => (
  <Card className="max-w-sm">
    <CardTitle>Protocolo de devoluciones</CardTitle>
    <p className="text-sm text-text-secondary mt-1">Al terminar, podras procesar cualquier devolucion sin consultar al encargado</p>
    <div className="mt-4">
      <Button size="sm">Continuar modulo</Button>
    </div>
  </Card>
)

export const CourseCard = () => (
  <Card className="max-w-sm">
    <div className="flex items-center justify-between mb-2">
      <CardTitle>Higiene alimentaria</CardTitle>
      <Badge variant="primary">En progreso</Badge>
    </div>
    <p className="text-xs text-text-secondary">Modulo 3 de 6</p>
    <ProgressBar value={50} variant="accent" size="sm" className="mt-3" />
    <p className="text-xs text-text-muted mt-2">Ultima sesion: hace 2 dias</p>
  </Card>
)

export const AllVariants = () => (
  <div className="grid grid-cols-2 gap-4 max-w-2xl">
    <Card variant="default">
      <CardTitle>Default</CardTitle>
      <p className="text-sm text-text-secondary mt-1">Borde fino, fondo blanco, rounded-xl</p>
    </Card>
    <Card variant="interactive">
      <CardTitle>Interactive</CardTitle>
      <p className="text-sm text-text-secondary mt-1">Hover cambia color del borde a primary</p>
    </Card>
  </div>
)
