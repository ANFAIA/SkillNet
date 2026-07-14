import type { Meta, StoryObj } from '@storybook/react-vite'
import { MetricCard } from './MetricCard'

const meta: Meta<typeof MetricCard> = {
  title: 'UI/MetricCard',
  component: MetricCard,
  argTypes: {
    color: {
      control: 'select',
      options: ['blue', 'green', 'orange', 'purple'],
    },
  },
}
export default meta

type Story = StoryObj<typeof MetricCard>

const UsersIcon = (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
  </svg>
)

const BookIcon = (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
  </svg>
)

const CheckIcon = (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12" />
  </svg>
)

const AlertIcon = (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
    <line x1="12" y1="9" x2="12" y2="13" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
)

export const EmpleadosActivos: Story = {
  args: {
    value: '24',
    label: 'Empleados activos',
    icon: UsersIcon,
    color: 'blue',
  },
}

export const CursosPublicados: Story = {
  args: {
    value: '12',
    label: 'Cursos publicados',
    icon: BookIcon,
    color: 'green',
  },
}

export const SkillGaps: Story = {
  args: {
    value: '3',
    label: 'Skills gaps detectados',
    icon: AlertIcon,
    color: 'orange',
  },
}

export const TasaCompletado: Story = {
  args: {
    value: '87%',
    label: 'Tasa de completado',
    icon: CheckIcon,
    color: 'purple',
  },
}

export const PanelDashboard = () => (
  <div className="grid grid-cols-4 gap-4 max-w-3xl">
    <MetricCard
      value="24"
      label="Empleados activos"
      icon={UsersIcon}
      color="blue"
    />
    <MetricCard
      value="12"
      label="Cursos publicados"
      icon={BookIcon}
      color="green"
    />
    <MetricCard
      value="3"
      label="Skills gaps"
      icon={AlertIcon}
      color="orange"
    />
    <MetricCard
      value="87%"
      label="Tasa de completado"
      icon={CheckIcon}
      color="purple"
    />
  </div>
)
