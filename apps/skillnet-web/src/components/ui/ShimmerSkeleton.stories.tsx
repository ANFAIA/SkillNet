import type { Meta } from '@storybook/react-vite'
import { ShimmerSkeleton, ShimmerSkeletonText } from './ShimmerSkeleton'

const meta: Meta<typeof ShimmerSkeleton> = {
  title: 'UI/ShimmerSkeleton',
  component: ShimmerSkeleton,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const Piezas = () => (
  <div className="space-y-6 max-w-md">
    <div>
      <p className="text-xs text-text-muted mb-2">Linea de texto</p>
      <ShimmerSkeleton className="h-3.5 w-4/5" />
    </div>
    <div>
      <p className="text-xs text-text-muted mb-2">Titulo</p>
      <ShimmerSkeleton className="h-5 w-2/5" />
    </div>
    <div>
      <p className="text-xs text-text-muted mb-2">Bloque</p>
      <ShimmerSkeleton className="h-24 w-full rounded-lg" />
    </div>
  </div>
)

export const Parrafo = () => (
  <div className="max-w-md">
    <ShimmerSkeletonText lines={4} />
  </div>
)

/**
 * The canonical node shape of §9.2 — title, three text bars, one block. Kept
 * here as the reference `NodeSkeleton` (B9) is built against.
 */
export const FormaDeNodo = () => (
  <div className="max-w-2xl space-y-5">
    <ShimmerSkeleton className="h-6 w-1/2" />
    <ShimmerSkeletonText lines={3} />
    <ShimmerSkeleton className="h-32 w-full rounded-lg" />
  </div>
)

/**
 * `ui/Skeleton.tsx` (v1, `animate-pulse`) next to the new one. Both stay: v1
 * pages must not change with the flag off (§9.2).
 */
export const ComparadoConV1 = () => (
  <div className="space-y-6 max-w-md">
    <div>
      <p className="text-xs text-text-muted mb-2">ShimmerSkeleton (v2) — barrido por transform</p>
      <ShimmerSkeleton className="h-3.5 w-full" />
    </div>
    <div>
      <p className="text-xs text-text-muted mb-2">Skeleton (v1) — animate-pulse, sin tocar</p>
      <div className="animate-pulse bg-bg-muted rounded h-3.5 w-full" />
    </div>
  </div>
)
