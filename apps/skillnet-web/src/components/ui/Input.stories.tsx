import type { Meta, StoryObj } from '@storybook/react-vite'
import { Input } from './Input'

const meta: Meta<typeof Input> = {
  title: 'UI/Input',
  component: Input,
}
export default meta

type Story = StoryObj<typeof Input>

export const Default: Story = {
  args: { placeholder: 'Buscar cursos...' },
}

export const WithLabel: Story = {
  args: { label: 'Email corporativo', placeholder: 'laura@restaurante-elsabor.com' },
}

export const WithError: Story = {
  args: { label: 'Email corporativo', placeholder: 'laura@restaurante-elsabor.com', error: 'Este email ya esta registrado en otra cuenta' },
}

export const Disabled: Story = {
  args: { label: 'Empresa', value: 'Restaurante El Buen Sabor', disabled: true },
}

export const FormularioCurso = () => (
  <div className="space-y-6 max-w-sm">
    <Input label="Nombre del curso" placeholder="Ej: Protocolo de devoluciones en tienda" />
    <Input label="Buscar empleado" placeholder="Nombre o email del empleado..." />
    <Input label="Email corporativo" placeholder="laura@empresa.com" error="Campo obligatorio" />
    <Input label="Empresa" value="Restaurante El Buen Sabor" disabled />
  </div>
)
