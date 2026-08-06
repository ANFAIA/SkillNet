import { motion } from 'framer-motion'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { duration } from '../../lib/motion'
import { InfoTooltip } from '../ui/InfoTooltip'
import type { ProposedNode } from '../../pages/admin/createCourseTypes'

// ── Icons (local, not worth a separate file) ────────────────

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`transition-transform ${open ? 'rotate-90' : ''}`}
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  )
}

function XIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

// ── Option constants ────────────────────────────────────────

const CRITICALITY_OPTIONS: { value: string; label: string }[] = [
  { value: 'critical', label: 'Imprescindible' },
  { value: 'recommended', label: 'Recomendado' },
  { value: 'contextual', label: 'Contexto' },
]


// ── Component ───────────────────────────────────────────────

export interface SortableTreeNodeProps {
  id: string
  index: number
  node: ProposedNode
  nodes: ProposedNode[]
  expanded: boolean
  onToggle: () => void
  onChange: (patch: Partial<ProposedNode>) => void
  onDelete: () => void
}

export function SortableTreeNode({
  id,
  index,
  node,
  nodes,
  expanded,
  onToggle,
  onChange,
  onDelete,
}: SortableTreeNodeProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition: dndTransition,
    isDragging,
  } = useSortable({ id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition: dndTransition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 10 : undefined,
  }

  const critClass =
    node.criticality === 'critical'
      ? 'bg-primary-subtle text-primary'
      : node.criticality === 'recommended'
        ? 'bg-accent-subtle text-accent'
        : 'bg-bg-muted text-text-muted'

  const critLabel = CRITICALITY_OPTIONS.find((o) => o.value === node.criticality)?.label ?? ''

  return (
    <div ref={setNodeRef} style={style}>
      {/* Row: always visible */}
      <div
        className={`flex items-start gap-0 px-2 py-1.5 rounded-md group transition-colors ${
          expanded ? 'bg-bg-subtle' : 'hover:bg-bg-muted'
        }`}
      >
        {/* Drag handle */}
        <button
          {...attributes}
          {...listeners}
          className="w-5 shrink-0 flex flex-col items-center gap-0.5 cursor-grab text-text-muted opacity-0 group-hover:opacity-100 transition-opacity mt-0.5"
          title="Arrastrar"
        >
          <span className="block w-2.5 h-0.5 bg-current rounded-full" />
          <span className="block w-2.5 h-0.5 bg-current rounded-full" />
          <span className="block w-2.5 h-0.5 bg-current rounded-full" />
        </button>

        {/* Toggle */}
        <button type="button" onClick={onToggle} className="text-text-muted hover:text-text shrink-0 mt-0.5">
          <ChevronIcon open={expanded} />
        </button>

        {/* Number dot (colored by criticality) */}
        <span className={`text-xs font-medium rounded-full w-5 h-5 flex items-center justify-center shrink-0 ml-1 mt-0.5 ${critClass}`}>
          {index + 1}
        </span>

        {/* Title + summary (collapsed: two-line block) */}
        <div className="flex-1 min-w-0 ml-2">
          <input
            className="w-full text-sm font-medium text-text bg-transparent border-none focus:outline-none focus:ring-0 p-0 focus:bg-bg focus:shadow-[0_0_0_1px_var(--color-primary)] focus:rounded focus:px-1 focus:-mx-1"
            value={node.title}
            onChange={(e) => onChange({ title: e.target.value })}
            placeholder="Titulo del nodo"
          />
          {!expanded && node.summary && (
            <p className="text-xs text-text-muted truncate mt-0.5">{node.summary}</p>
          )}
        </div>

        {/* Meta: prereq chips + criticality pill + time */}
        <div className="flex items-center gap-2 shrink-0 ml-2 mt-0.5">
          {!expanded && node.prerequisites.length > 0 && (
            <div className="flex gap-0.5">
              {node.prerequisites.map((idx) => (
                <span
                  key={idx}
                  className="w-4 h-4 rounded-full text-[9px] font-semibold border border-border text-text-muted flex items-center justify-center"
                  title={`Depende de: ${nodes[idx]?.title || `Nodo ${idx + 1}`}`}
                >
                  {idx + 1}
                </span>
              ))}
            </div>
          )}
          {!expanded && critLabel && (
            <span className={`text-xs px-2 py-0.5 rounded-full whitespace-nowrap ${critClass}`}>
              {critLabel}
            </span>
          )}
          <span className="text-xs text-text-muted whitespace-nowrap">{node.estimated_minutes} min</span>
          <button
            type="button"
            onClick={onDelete}
            className="text-text-muted hover:text-danger p-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
            title="Eliminar nodo"
          >
            <XIcon size={14} />
          </button>
        </div>
      </div>

      {/* Expanded children -- tree indent with left border */}
      {expanded && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1, transition: { duration: duration.fast } }}
          className="ml-[42px] pl-4 border-l border-border space-y-1 pb-2"
        >
          {/* Summary */}
          <div className="flex items-start gap-0 px-2 py-1 rounded hover:bg-bg-muted">
            <span className="w-24 shrink-0 text-xs text-text-muted pt-0.5">Resumen</span>
            <textarea
              className="flex-1 min-w-0 text-sm text-text bg-transparent border-none focus:outline-none p-0 resize-none leading-relaxed focus:bg-bg focus:shadow-[0_0_0_1px_var(--color-primary)] focus:rounded focus:px-1.5 focus:py-0.5 focus:-mx-1.5 focus:-my-0.5"
              value={node.summary}
              onChange={(e) => onChange({ summary: e.target.value })}
              rows={1}
              onInput={(e) => {
                const t = e.target as HTMLTextAreaElement
                t.style.height = 'auto'
                t.style.height = t.scrollHeight + 'px'
              }}
            />
          </div>

          {/* Outcome */}
          <div className="flex items-start gap-0 px-2 py-1 rounded hover:bg-bg-muted">
            <span className="w-24 shrink-0 text-xs text-text-muted pt-0.5">Objetivo</span>
            <input
              className="flex-1 min-w-0 text-sm text-text bg-transparent border-none focus:outline-none p-0 focus:bg-bg focus:shadow-[0_0_0_1px_var(--color-primary)] focus:rounded focus:px-1.5 focus:-mx-1.5"
              value={node.outcome ?? ''}
              onChange={(e) => onChange({ outcome: e.target.value || null })}
              placeholder="Que sabra hacer el alumno"
            />
          </div>

          {/* Criticality */}
          <div className="flex items-center gap-0 px-2 py-1 rounded hover:bg-bg-muted">
            <span className="w-24 shrink-0 text-xs text-text-muted flex items-center">
              Importancia
              <InfoTooltip text="Imprescindible: el alumno debe dominar este tema para completar el curso. Recomendado: importante pero no obligatorio. Contexto: material complementario que enriquece pero no se evalua." />
            </span>
            <div className="flex gap-1">
              {CRITICALITY_OPTIONS.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => onChange({ criticality: o.value })}
                  className={`text-xs px-2.5 py-0.5 rounded-full border transition-colors ${
                    node.criticality === o.value
                      ? o.value === 'critical'
                        ? 'bg-primary-subtle text-primary border-primary'
                        : o.value === 'recommended'
                          ? 'bg-accent-subtle text-accent border-accent'
                          : 'bg-bg-muted text-text-muted border-border-strong'
                      : 'border-border text-text-muted hover:border-primary'
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>

          {/* Minutes */}
          <div className="flex items-center gap-0 px-2 py-1 rounded hover:bg-bg-muted">
            <span className="w-24 shrink-0 text-xs text-text-muted">Minutos</span>
            <input
              type="number"
              min={1}
              max={120}
              className="w-16 text-sm text-text bg-transparent border-none focus:outline-none p-0 focus:bg-bg focus:shadow-[0_0_0_1px_var(--color-primary)] focus:rounded focus:px-1.5 focus:-mx-1.5"
              value={node.estimated_minutes}
              onChange={(e) => onChange({ estimated_minutes: Math.max(1, Math.min(120, Number(e.target.value) || 1)) })}
            />
          </div>

          {/* Prerequisites */}
          <div className="flex items-center gap-0 px-2 py-1 rounded hover:bg-bg-muted">
            <span className="w-24 shrink-0 text-xs text-text-muted">Depende de</span>
            <div className="flex flex-wrap gap-1">
              {node.prerequisites.map((idx) => (
                <span key={idx} className="text-xs bg-primary-subtle text-primary px-2 py-0.5 rounded-full inline-flex items-center gap-1">
                  {idx + 1}. {nodes[idx]?.title ? nodes[idx].title.slice(0, 20) : `Nodo ${idx + 1}`}
                  <button
                    type="button"
                    onClick={() => onChange({ prerequisites: node.prerequisites.filter((p) => p !== idx) })}
                    className="opacity-60 hover:opacity-100"
                  >
                    &times;
                  </button>
                </span>
              ))}
              <button
                type="button"
                onClick={() => {
                  const available = nodes
                    .map((_, j) => j)
                    .filter((j) => j !== index && !node.prerequisites.includes(j))
                  if (available.length > 0) onChange({ prerequisites: [...node.prerequisites, available[0]] })
                }}
                className="text-xs border border-dashed border-border text-text-muted px-2 py-0.5 rounded-full hover:border-primary hover:text-primary transition-colors"
              >
                + Anadir
              </button>
            </div>
          </div>
        </motion.div>
      )}
    </div>
  )
}
