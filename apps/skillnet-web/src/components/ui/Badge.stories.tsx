import type { Meta } from '@storybook/react-vite'
import { Badge } from './Badge'

const meta: Meta<typeof Badge> = {
  title: 'UI/Badge',
  component: Badge,
}
export default meta

export const Default = () => (
  <div className="space-y-6">
    <div>
      <p className="text-xs text-text-muted mb-2">Default (icono arana + texto)</p>
      <div className="flex items-center gap-4">
        <Badge variant="primary">Asignado</Badge>
        <Badge variant="accent">Completado</Badge>
        <Badge variant="warning">Pendiente</Badge>
        <Badge variant="danger">Suspendido</Badge>
      </div>
    </div>
  </div>
)

export const Plain = () => (
  <div className="space-y-6">
    <div>
      <p className="text-xs text-text-muted mb-2">Plain (texto coloreado, sin icono)</p>
      <div className="flex items-center gap-4">
        <Badge variant="primary" badgeStyle="plain">En progreso</Badge>
        <Badge variant="accent" badgeStyle="plain">Publicado</Badge>
        <Badge variant="warning" badgeStyle="plain">Borrador</Badge>
        <Badge variant="danger" badgeStyle="plain">Archivado</Badge>
      </div>
    </div>
  </div>
)

export const EstadoDelCurso = () => (
  <div className="space-y-6">
    <div>
      <p className="text-xs text-text-muted mb-3">Estado del curso del empleado</p>
      <div className="flex items-center gap-4">
        <Badge variant="accent">Completado</Badge>
        <Badge variant="primary">En progreso</Badge>
        <Badge variant="warning">Sin empezar</Badge>
      </div>
    </div>
    <div>
      <p className="text-xs text-text-muted mb-3">Gestion de contenido</p>
      <div className="flex items-center gap-4">
        <Badge variant="warning" badgeStyle="plain">Borrador</Badge>
        <Badge variant="accent" badgeStyle="plain">Publicado</Badge>
        <Badge variant="danger" badgeStyle="plain">Retirado</Badge>
      </div>
    </div>
    <div>
      <p className="text-xs text-text-muted mb-3">Verificacion de skill</p>
      <div className="flex items-center gap-4">
        <Badge variant="accent">Verificado</Badge>
        <Badge variant="danger">No verificado</Badge>
      </div>
    </div>
  </div>
)

export const EnContexto = () => (
  <div className="space-y-3">
    <p className="text-sm text-text">
      Laura Martinez ha sido marcada como <Badge variant="accent" badgeStyle="plain">Completado</Badge> en Protocolo de devoluciones.
    </p>
    <p className="text-sm text-text">
      El curso de Higiene alimentaria tiene estado <Badge variant="warning">Pendiente de revision</Badge>
    </p>
    <p className="text-sm text-text">
      Carlos Ruiz necesita completar <Badge variant="danger" badgeStyle="plain">3 cursos vencidos</Badge> antes del viernes.
    </p>
  </div>
)
