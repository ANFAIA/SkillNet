import type { Meta, StoryObj } from '@storybook/react-vite'
import { SkillBars } from './SkillBars'

const meta: Meta<typeof SkillBars> = {
  title: 'UI/SkillBars',
  component: SkillBars,
  argTypes: {
    level: {
      control: 'select',
      options: ['low', 'medium', 'high', 'expert'],
    },
  },
}
export default meta

type Story = StoryObj<typeof SkillBars>

export const Low: Story = {
  args: { level: 'low' },
}

export const Medium: Story = {
  args: { level: 'medium' },
}

export const High: Story = {
  args: { level: 'high' },
}

export const Expert: Story = {
  args: { level: 'expert' },
}

export const TodosLosNiveles = () => (
  <div className="space-y-4">
    <p className="text-xs text-text-muted">Indicadores de nivel de competencia</p>
    <div className="space-y-3">
      {(['low', 'medium', 'high', 'expert'] as const).map((level) => (
        <div key={level} className="flex items-center gap-3">
          <SkillBars level={level} />
          <span className="text-sm text-text capitalize">{level}</span>
        </div>
      ))}
    </div>
  </div>
)

export const PerfilEmpleado = () => (
  <div className="space-y-2 max-w-sm">
    <p className="text-xs text-text-muted mb-3">Laura Martinez - Competencias</p>
    {[
      { name: 'Atencion al cliente', level: 'expert' as const },
      { name: 'Protocolo de devoluciones', level: 'high' as const },
      { name: 'Gestion de inventario', level: 'medium' as const },
      { name: 'Seguridad laboral', level: 'low' as const },
    ].map((skill) => (
      <div key={skill.name} className="flex items-center justify-between py-1.5">
        <span className="text-sm text-text">{skill.name}</span>
        <SkillBars level={skill.level} />
      </div>
    ))}
  </div>
)
