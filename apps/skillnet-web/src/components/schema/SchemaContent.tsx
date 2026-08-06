import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { DndContext, closestCenter, PointerSensor, KeyboardSensor, useSensor, useSensors } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { ease, duration } from '../../lib/motion'
import { Button } from '../ui'
import { ShimmerSkeleton } from '../ui/ShimmerSkeleton'
import { SortableTreeNode } from './SortableTreeNode'
import type { ProposedNode } from '../../pages/admin/createCourseTypes'

// ── Skeleton for loading state ──────────────────────────────

function TreeNodeSkeleton({ opacity }: { opacity: number }) {
  return (
    <div className="flex items-center gap-0 px-2 py-1.5" style={{ opacity }}>
      <div className="w-5 shrink-0" />
      <ShimmerSkeleton className="w-5 h-5 rounded-full shrink-0" />
      <ShimmerSkeleton className="h-3.5 ml-2 rounded w-3/5" />
      <ShimmerSkeleton className="h-3 w-10 ml-auto rounded" />
    </div>
  )
}

function PlusIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

// ── Props ───────────────────────────────────────────────────

export interface SchemaContentProps {
  proposing: boolean
  proposeError: string | null
  nodes: ProposedNode[]
  density: number
  onDensityChange: (v: number) => void
  totalMinutes: number
  criticalCount: number
  onNodeChange: (i: number, patch: Partial<ProposedNode>) => void
  onNodeDelete: (i: number) => void
  onNodeAdd: () => void
  onNodeReorder: (from: number, to: number) => void
  onCreateCourse: () => void
  creating: boolean
  startError: string | null
}

// ── Component ───────────────────────────────────────────────

export function SchemaContent({
  proposing,
  proposeError,
  nodes,
  density,
  onDensityChange,
  totalMinutes,
  criticalCount,
  onNodeChange,
  onNodeDelete,
  onNodeAdd,
  onNodeReorder,
  onCreateCourse,
  creating,
  startError,
}: SchemaContentProps) {
  const [expandedNodes, setExpandedNodes] = useState<Set<number>>(new Set())
  const [hasInteracted, setHasInteracted] = useState(false)
  const hasEverHadNodes = useRef(false)
  const [pendingDensity, setPendingDensity] = useState<number | null>(null)

  useEffect(() => {
    if (nodes.length > 0) hasEverHadNodes.current = true
  }, [nodes.length])

  const handleNodeChange = (i: number, patch: Partial<ProposedNode>) => {
    setHasInteracted(true)
    onNodeChange(i, patch)
  }

  const toggleNode = (i: number) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })
  }

  // Wrap onNodeDelete to also clean up expandedNodes indices
  const handleDelete = (deleted: number) => {
    onNodeDelete(deleted)
    setExpandedNodes((prev) => {
      const next = new Set<number>()
      for (const idx of prev) {
        if (idx === deleted) continue
        next.add(idx > deleted ? idx - 1 : idx)
      }
      return next
    })
  }

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor),
  )
  const nodeIds = nodes.map((_, i) => `schema-node-${i}`)

  function handleDragEnd(event: { active: { id: string | number }; over: { id: string | number } | null }) {
    if (!event.over || event.active.id === event.over.id) return
    const from = nodeIds.indexOf(String(event.active.id))
    const to = nodeIds.indexOf(String(event.over.id))
    if (from !== -1 && to !== -1) {
      onNodeReorder(from, to)
      // Update expanded set to follow moved nodes
      setExpandedNodes((prev) => {
        const arr = Array.from(prev)
        const next = new Set(
          arr.map((idx) => {
            if (idx === from) return to
            if (from < to && idx > from && idx <= to) return idx - 1
            if (from > to && idx >= to && idx < from) return idx + 1
            return idx
          }),
        )
        return next
      })
    }
  }

  // Loading state
  if (proposing) {
    return (
      <div className="flex gap-6">
        <div className="shrink-0 space-y-4" style={{ width: 180 }}>
          <ShimmerSkeleton className="h-4 w-20" />
          <ShimmerSkeleton className="h-2 w-full rounded-full" />
          <div className="space-y-2">
            <ShimmerSkeleton className="h-3.5 w-full" />
            <ShimmerSkeleton className="h-3.5 w-full" />
            <ShimmerSkeleton className="h-3.5 w-full" />
          </div>
          <ShimmerSkeleton className="h-9 w-full rounded-md" />
        </div>
        <div className="flex-1 min-w-0">
          {Array.from({ length: 5 }).map((_, i) => (
            <TreeNodeSkeleton key={i} opacity={1 - i * 0.15} />
          ))}
        </div>
      </div>
    )
  }

  // Error state
  if (proposeError) {
    return (
      <div className="text-center py-12">
        <p className="text-sm text-danger mb-3">{proposeError}</p>
      </div>
    )
  }

  // Empty state — distinguish "never proposed" vs "user deleted all"
  if (nodes.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-sm text-text">
          {hasEverHadNodes.current ? 'Has eliminado todos los nodos' : 'No se generaron nodos'}
        </p>
        <p className="text-xs text-text-muted mt-1">
          {hasEverHadNodes.current
            ? 'Puedes reproponer el esquema o anadir nodos manualmente'
            : 'Prueba a cambiar la densidad o el titulo del curso'}
        </p>
        <div className="flex items-center justify-center gap-3 mt-4">
          {hasEverHadNodes.current && (
            <Button variant="secondary" size="sm" onClick={() => onDensityChange(density)}>
              Reproponer
            </Button>
          )}
          <button type="button" onClick={onNodeAdd} className="text-sm text-primary hover:underline">
            Anadir nodo
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-6">
      {/* Left sidebar */}
      <div className="shrink-0" style={{ width: 180 }}>
        <div className="space-y-5">
          <div>
            <label className="block text-xs font-medium text-text-muted uppercase tracking-wide mb-2">
              Densidad
            </label>
            <input
              type="range"
              min={1}
              max={5}
              step={1}
              value={pendingDensity ?? density}
              onChange={(e) => {
                const v = Number(e.target.value)
                if (hasInteracted) {
                  setPendingDensity(v)
                } else {
                  onDensityChange(v)
                }
              }}
              className="w-full accent-primary"
            />
            <div className="flex justify-between text-xs text-text-muted mt-1">
              <span>Breve</span>
              <span>{pendingDensity ?? density}</span>
              <span>Detallado</span>
            </div>
            {pendingDensity !== null && (
              <div className="mt-2">
                <p className="text-xs text-warning">Esto reemplazara tus cambios</p>
                <div className="flex gap-2 mt-1.5">
                  <button
                    type="button"
                    onClick={() => { setHasInteracted(false); onDensityChange(pendingDensity); setPendingDensity(null) }}
                    className="text-xs text-primary hover:underline"
                  >
                    Reproponer
                  </button>
                  <button
                    type="button"
                    onClick={() => setPendingDensity(null)}
                    className="text-xs text-text-muted hover:underline"
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-text-muted">Nodos</span>
              <span className="text-text font-medium">{nodes.length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Imprescindibles</span>
              <span className="text-text font-medium">{criticalCount}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Tiempo est.</span>
              <span className="text-text font-medium">{totalMinutes} min</span>
            </div>
          </div>

          {startError && <p className="text-xs text-danger">{startError}</p>}

          <Button variant="primary" className="w-full" onClick={onCreateCourse} disabled={creating || nodes.length === 0}>
            {creating ? 'Creando...' : 'Crear curso'}
          </Button>
        </div>
      </div>

      {/* Right: tree */}
      <div className="flex-1 min-w-0">
        {/* AI proposal banner — disappears after first edit */}
        <AnimatePresence>
          {!hasInteracted && nodes.length > 0 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1, transition: { duration: duration.normal } }}
              exit={{ opacity: 0, transition: { duration: duration.fast } }}
              className="border-l-4 border-accent bg-accent-subtle px-4 py-2.5 rounded-r-md mb-4"
            >
              <p className="text-sm text-text">La IA propone {nodes.length} nodos. Revisalos y ajustalos antes de crear el curso.</p>
            </motion.div>
          )}
        </AnimatePresence>

        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={nodeIds} strategy={verticalListSortingStrategy}>
            <AnimatePresence initial={false}>
              {nodes.map((node, i) => (
                <motion.div
                  key={`node-${node._key}`}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{
                    opacity: 1,
                    y: 0,
                    transition: { duration: duration.normal, ease: ease.base, delay: i * 0.04 },
                  }}
                  exit={{ opacity: 0, x: -32, transition: { duration: duration.fast, ease: ease.snapOut } }}
                >
                  <SortableTreeNode
                    id={nodeIds[i]}
                    index={i}
                    node={node}
                    nodes={nodes}
                    expanded={expandedNodes.has(i)}
                    onToggle={() => toggleNode(i)}
                    onChange={(patch) => handleNodeChange(i, patch)}
                    onDelete={() => handleDelete(i)}
                  />
                </motion.div>
              ))}
            </AnimatePresence>
          </SortableContext>
        </DndContext>

        {/* Add node */}
        <button
          type="button"
          onClick={onNodeAdd}
          className="w-full mt-2 px-2 py-1.5 rounded-md text-sm text-text-muted hover:text-primary hover:bg-bg-muted transition-colors flex items-center gap-2"
        >
          <PlusIcon size={14} />
          Anadir nodo
        </button>
      </div>
    </div>
  )
}
