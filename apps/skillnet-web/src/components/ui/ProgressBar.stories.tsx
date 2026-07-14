import type { Meta } from '@storybook/react-vite'
import { ProgressBar } from './ProgressBar'

const meta: Meta<typeof ProgressBar> = {
  title: 'UI/ProgressBar',
  component: ProgressBar,
}
export default meta

export const Tamanos = () => (
  <div className="space-y-4 max-w-md">
    <div>
      <p className="text-xs text-text-muted mb-1">Small (h-1) - para listas compactas</p>
      <ProgressBar value={60} size="sm" />
    </div>
    <div>
      <p className="text-xs text-text-muted mb-1">Medium (h-1.5) - por defecto</p>
      <ProgressBar value={60} size="md" />
    </div>
    <div>
      <p className="text-xs text-text-muted mb-1">Large (h-2) - para destacar</p>
      <ProgressBar value={60} size="lg" />
    </div>
  </div>
)

export const Variantes = () => (
  <div className="space-y-4 max-w-md">
    <div>
      <p className="text-xs text-text-muted mb-1">Primary - progreso general</p>
      <ProgressBar value={70} variant="primary" size="lg" />
    </div>
    <div>
      <p className="text-xs text-text-muted mb-1">Accent - cursos completados</p>
      <ProgressBar value={70} variant="accent" size="lg" />
    </div>
    <div>
      <p className="text-xs text-text-muted mb-1">Auto - color segun porcentaje</p>
      <ProgressBar value={70} variant="auto" size="lg" />
    </div>
  </div>
)

export const ColoresPersonalizados = () => (
  <div className="space-y-4 max-w-md">
    <div>
      <p className="text-xs text-text-muted mb-1">Protocolo de devoluciones (#3B82F6)</p>
      <ProgressBar value={40} color="#3B82F6" size="lg" />
    </div>
    <div>
      <p className="text-xs text-text-muted mb-1">Higiene alimentaria (#10B981)</p>
      <ProgressBar value={75} color="#10B981" size="lg" />
    </div>
    <div>
      <p className="text-xs text-text-muted mb-1">Seguridad laboral (#F97316)</p>
      <ProgressBar value={20} color="#F97316" size="lg" />
    </div>
    <div>
      <p className="text-xs text-text-muted mb-1">Liderazgo y gestion (#8B5CF6)</p>
      <ProgressBar value={90} color="#8B5CF6" size="lg" />
    </div>
  </div>
)

export const ColorAutomatico = () => (
  <div className="space-y-3 max-w-md">
    <p className="text-xs text-text-muted mb-1">El color cambia segun el progreso del empleado</p>
    <div className="flex items-center gap-3">
      <span className="text-xs text-text-secondary w-8">20%</span>
      <ProgressBar value={20} variant="auto" size="lg" className="flex-1" />
    </div>
    <div className="flex items-center gap-3">
      <span className="text-xs text-text-secondary w-8">50%</span>
      <ProgressBar value={50} variant="auto" size="lg" className="flex-1" />
    </div>
    <div className="flex items-center gap-3">
      <span className="text-xs text-text-secondary w-8">85%</span>
      <ProgressBar value={85} variant="auto" size="lg" className="flex-1" />
    </div>
  </div>
)

export const ConEtiqueta = () => (
  <div className="max-w-md">
    <p className="text-xs text-text-muted mb-1">Progreso general del equipo</p>
    <ProgressBar value={42} showLabel size="lg" />
  </div>
)
