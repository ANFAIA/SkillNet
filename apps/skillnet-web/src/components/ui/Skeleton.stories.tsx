import type { Meta } from '@storybook/react-vite'
import { Skeleton, SkeletonText, SkeletonCard, SkeletonRow } from './Skeleton'

const meta: Meta = {
  title: 'UI/Skeleton',
}
export default meta

export const Basico = () => (
  <div className="space-y-3 max-w-sm">
    <Skeleton className="h-8 w-1/2" />
    <Skeleton className="h-4 w-full" />
    <Skeleton className="h-4 w-3/4" />
  </div>
)

export const BloqueTexto = () => (
  <div className="max-w-md">
    <SkeletonText lines={4} />
  </div>
)

export const Tarjetas = () => (
  <div className="grid grid-cols-2 gap-4 max-w-xl">
    <SkeletonCard />
    <SkeletonCard />
    <SkeletonCard />
    <SkeletonCard />
  </div>
)

export const ListaEmpleados = () => (
  <div className="max-w-md border border-border rounded-lg divide-y divide-border">
    <div className="px-4"><SkeletonRow /></div>
    <div className="px-4"><SkeletonRow /></div>
    <div className="px-4"><SkeletonRow /></div>
    <div className="px-4"><SkeletonRow /></div>
  </div>
)

export const DashboardCargando = () => (
  <div className="max-w-2xl space-y-6">
    <div>
      <Skeleton className="h-7 w-48 mb-2" />
      <Skeleton className="h-4 w-32" />
    </div>
    <div className="grid grid-cols-3 gap-4">
      <SkeletonCard />
      <SkeletonCard />
      <SkeletonCard />
    </div>
    <SkeletonCard />
  </div>
)
