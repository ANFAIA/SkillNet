import type { NodeCriticality } from '../../types'

/**
 * Default mastery threshold per criticality — mirrors `CRITICALITY_THRESHOLDS` in
 * `src/models/course_node.py` (§3.2). The creator can override it per node, so this
 * is only used to seed the field and to tell them when they are off the default.
 */
export const DEFAULT_MASTERY_THRESHOLD: Record<NodeCriticality, number> = {
  critical: 0.9,
  recommended: 0.8,
  contextual: 0.7,
}

interface Descriptor {
  label: string
  hint: string
  /** Status-pill colours only, per the design system: no decorative badges. */
  className: string
}

export const CRITICALITY: Record<NodeCriticality, Descriptor> = {
  critical: {
    label: 'Critico',
    hint: 'Obligatorio: el curso no se cierra hasta que se domina',
    className: 'bg-primary-subtle text-primary',
  },
  recommended: {
    label: 'Recomendado',
    hint: 'No bloquea el cierre del curso',
    className: 'bg-accent-subtle text-accent',
  },
  contextual: {
    label: 'Contextual',
    hint: 'Contexto de apoyo: no bloquea el cierre del curso',
    className: 'bg-bg-muted text-text-secondary',
  },
}

export const CRITICALITY_ORDER: NodeCriticality[] = [
  'critical',
  'recommended',
  'contextual',
]

export function CriticalityBadge({
  criticality,
  className = '',
}: {
  criticality: NodeCriticality
  className?: string
}) {
  const descriptor = CRITICALITY[criticality]

  return (
    <span
      title={descriptor.hint}
      className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full shrink-0 ${descriptor.className} ${className}`}
    >
      {descriptor.label}
    </span>
  )
}
