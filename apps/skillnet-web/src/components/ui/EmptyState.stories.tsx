import type { Meta } from '@storybook/react-vite'
import { EmptyState } from './EmptyState'

const meta: Meta<typeof EmptyState> = {
  title: 'UI/EmptyState',
  component: EmptyState,
}
export default meta

export const SinCursos = () => (
  <EmptyState
    title="No tienes cursos asignados"
    description="Tu administrador asignara cursos cuando esten listos"
  />
)

export const ConAccion = () => (
  <EmptyState
    title="No hay empleados registrados"
    description="Invita a tu equipo para empezar la formacion"
    action={{ label: 'Invitar empleados', onClick: () => {} }}
  />
)

export const SinResultados = () => (
  <EmptyState
    title="Sin resultados de busqueda"
    description="Prueba con otros terminos o cambia los filtros aplicados"
  />
)

export const DentroDeCard = () => (
  <div className="border border-[--color-border] rounded-xl max-w-md">
    <EmptyState
      title="No hay alertas de skill gaps"
      description="Todos los empleados cumplen los requisitos minimos"
    />
  </div>
)
