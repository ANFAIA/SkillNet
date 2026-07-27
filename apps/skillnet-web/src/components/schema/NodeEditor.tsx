import { Button } from '../ui'
import type { NodeCriticality } from '../../types'
import type { UiFormat } from '../../types/node-render'
import {
  CRITICALITY,
  CRITICALITY_ORDER,
  CriticalityBadge,
  DEFAULT_MASTERY_THRESHOLD,
} from './CriticalityBadge'
import { PrerequisitePicker, type PrerequisiteOption } from './PrerequisitePicker'

/**
 * One node of the draft schema, edited locally until the creator saves.
 *
 * `key` exists because a brand-new node has no `id` until the first `PUT`, and React
 * still needs stable identity while it is being typed into.
 */
export interface DraftNode {
  key: string
  id: string | null
  title: string
  summary: string
  outcome: string
  criticality: NodeCriticality
  masteryThreshold: number
  estimatedMinutes: number | null
  defaultUiFormat: UiFormat
  skillId: string | null
  seedLessonId: string | null
  sourceDocumentId: string | null
  sourceHeadings: string[]
  prerequisiteNodeIds: string[]
  archived: boolean
}

/**
 * The formats a creator may pick.
 *
 * `simulation` is deliberately absent: the value exists in the `ui_format` enum but is
 * reserved and never emitted (§1.3 — a `Simulation` component needs data binding the
 * IR does not have). Offering it would let a creator pin a node to a format the
 * renderer cannot produce.
 */
export const SELECTABLE_UI_FORMATS: { value: UiFormat; label: string; hint: string }[] = [
  { value: 'explanation', label: 'Explicacion', hint: 'Texto y ejemplos' },
  { value: 'exercise', label: 'Ejercicio', hint: 'Practica con correccion' },
  { value: 'chart', label: 'Grafico', hint: 'Datos o comparativa visual' },
  { value: 'mixed', label: 'Mixto', hint: 'Explicacion y practica en el mismo nodo' },
]

const textareaClasses =
  'w-full px-3 py-2 text-sm text-text border border-border rounded-lg bg-bg placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors duration-150 resize-y disabled:opacity-50 disabled:cursor-not-allowed'

const fieldClasses =
  'w-full px-3 py-2 text-sm text-text border border-border rounded-lg bg-bg focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed'

function FieldLabel({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="block text-sm font-medium text-text mb-1">
      {children}
    </label>
  )
}

export interface NodeEditorProps {
  node: DraftNode
  index: number
  total: number
  prerequisiteOptions: PrerequisiteOption[]
  /** Server-side review stamp. `null` while the node has never been signed off. */
  reviewedAt: string | null
  /** The draft differs from what the server holds, so review would be cleared anyway. */
  dirty: boolean
  /** The schema is validated: editing is refused by the server (§11.1 rule 1). */
  locked: boolean
  onChange: (patch: Partial<DraftNode>) => void
  onMove: (direction: -1 | 1) => void
  onArchiveToggle: () => void
  onRemove: () => void
}

export function NodeEditor({
  node,
  index,
  total,
  prerequisiteOptions,
  reviewedAt,
  dirty,
  locked,
  onChange,
  onMove,
  onArchiveToggle,
  onRemove,
}: NodeEditorProps) {
  const disabled = locked
  const idBase = `node-${node.key}`
  const thresholdIsDefault =
    Math.abs(node.masteryThreshold - DEFAULT_MASTERY_THRESHOLD[node.criticality]) < 0.001

  /**
   * Changing the criticality moves the threshold with it **only** while the threshold
   * is still the old criticality's default. A creator who typed 0.95 by hand keeps it;
   * one who never touched it gets the §3.2 default for the new criticality instead of
   * a number that silently belongs to the previous one.
   */
  function changeCriticality(next: NodeCriticality) {
    const wasDefault =
      Math.abs(node.masteryThreshold - DEFAULT_MASTERY_THRESHOLD[node.criticality]) < 0.001
    onChange({
      criticality: next,
      masteryThreshold: wasDefault ? DEFAULT_MASTERY_THRESHOLD[next] : node.masteryThreshold,
    })
  }

  return (
    <div className="min-w-0">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-border">
        <div className="min-w-0">
          <p className="text-xs text-text-muted">
            Nodo {index + 1} de {total}
          </p>
          <div className="flex items-center gap-2 mt-1 min-w-0">
            <h3 className="text-base font-medium text-text truncate min-w-0">
              {node.title || 'Nodo sin titulo'}
            </h3>
            <CriticalityBadge criticality={node.criticality} />
            {node.archived && (
              <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-bg-muted text-text-secondary shrink-0">
                Archivado
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onMove(-1)}
            disabled={disabled || index === 0}
            aria-label="Subir el nodo"
            title="Subir el nodo"
          >
            Subir
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onMove(1)}
            disabled={disabled || index === total - 1}
            aria-label="Bajar el nodo"
            title="Bajar el nodo"
          >
            Bajar
          </Button>
        </div>
      </div>

      <p className="text-xs mt-3">
        {reviewedAt && !dirty ? (
          <span className="text-accent">
            Revisado el {new Date(reviewedAt).toLocaleDateString('es-ES')}
          </span>
        ) : dirty ? (
          <span className="text-warning">
            Cambios sin guardar. Guarda el esquema y vuelve a marcarlo como revisado.
          </span>
        ) : (
          <span className="text-text-muted">
            Sin revisar. Marcalo en la lista de revision cuando lo hayas leido.
          </span>
        )}
      </p>

      <div className="mt-4 space-y-4">
        {/* Every field here builds its own `label`+`id` pair rather than using
            `ui/Input`, whose label is a sibling with no `htmlFor`: on a form this
            dense, an unlabelled control is unusable with a screen reader. */}
        <div>
          <FieldLabel htmlFor={`${idBase}-title`}>Titulo</FieldLabel>
          <input
            id={`${idBase}-title`}
            type="text"
            className={fieldClasses}
            value={node.title}
            disabled={disabled}
            onChange={(e) => onChange({ title: e.target.value })}
          />
        </div>

        <div>
          <FieldLabel htmlFor={`${idBase}-summary`}>Resumen</FieldLabel>
          <textarea
            id={`${idBase}-summary`}
            className={`${textareaClasses} min-h-[88px]`}
            rows={3}
            value={node.summary}
            disabled={disabled}
            onChange={(e) => onChange({ summary: e.target.value })}
          />
          <p className="text-xs text-text-muted mt-1">
            Obligatorio. El tutor lee el arbol de resumenes para decidir que nodo es
            relevante, asi que un resumen vacio bloquea la validacion.
          </p>
        </div>

        <div>
          <FieldLabel htmlFor={`${idBase}-outcome`}>Objetivo de aprendizaje</FieldLabel>
          <textarea
            id={`${idBase}-outcome`}
            className={`${textareaClasses} min-h-[64px]`}
            rows={2}
            value={node.outcome}
            disabled={disabled}
            placeholder="Que sabra hacer el aprendiz al terminar este nodo"
            onChange={(e) => onChange({ outcome: e.target.value })}
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <FieldLabel htmlFor={`${idBase}-criticality`}>Criticidad</FieldLabel>
            <select
              id={`${idBase}-criticality`}
              className={fieldClasses}
              value={node.criticality}
              disabled={disabled}
              onChange={(e) => changeCriticality(e.target.value as NodeCriticality)}
            >
              {CRITICALITY_ORDER.map((value) => (
                <option key={value} value={value}>
                  {CRITICALITY[value].label}
                </option>
              ))}
            </select>
            <p className="text-xs text-text-muted mt-1">
              {CRITICALITY[node.criticality].hint}.
            </p>
          </div>

          <div>
            <FieldLabel htmlFor={`${idBase}-format`}>Formato por defecto</FieldLabel>
            <select
              id={`${idBase}-format`}
              className={fieldClasses}
              value={node.defaultUiFormat}
              disabled={disabled}
              onChange={(e) => onChange({ defaultUiFormat: e.target.value as UiFormat })}
            >
              {SELECTABLE_UI_FORMATS.map((format) => (
                <option key={format.value} value={format.value}>
                  {format.label}
                </option>
              ))}
            </select>
            <p className="text-xs text-text-muted mt-1">
              Formato canonico del nodo: es el que se sirve mientras el perfil del
              aprendiz aun se esta calibrando.
            </p>
          </div>

          <div>
            <FieldLabel htmlFor={`${idBase}-threshold`}>Umbral de maestria</FieldLabel>
            <input
              id={`${idBase}-threshold`}
              type="number"
              min={0.5}
              max={1}
              step={0.05}
              className={fieldClasses}
              value={node.masteryThreshold}
              disabled={disabled}
              onChange={(e) => {
                const parsed = Number(e.target.value)
                if (Number.isNaN(parsed)) return
                onChange({ masteryThreshold: parsed })
              }}
            />
            <p className="text-xs text-text-muted mt-1">
              {thresholdIsDefault
                ? `Valor por defecto para ${CRITICALITY[node.criticality].label.toLowerCase()}.`
                : `Sobreescrito: el defecto para ${CRITICALITY[node.criticality].label.toLowerCase()} es ${DEFAULT_MASTERY_THRESHOLD[node.criticality]}.`}
            </p>
          </div>

          <div>
            <FieldLabel htmlFor={`${idBase}-minutes`}>Minutos estimados</FieldLabel>
            <input
              id={`${idBase}-minutes`}
              type="number"
              min={1}
              max={240}
              step={1}
              className={fieldClasses}
              value={node.estimatedMinutes ?? ''}
              disabled={disabled}
              placeholder="Opcional"
              onChange={(e) => {
                const raw = e.target.value.trim()
                if (raw === '') {
                  onChange({ estimatedMinutes: null })
                  return
                }
                const parsed = Number(raw)
                if (Number.isNaN(parsed)) return
                onChange({ estimatedMinutes: parsed })
              }}
            />
          </div>
        </div>

        <div>
          <FieldLabel htmlFor={`${idBase}-headings`}>Apartados del documento</FieldLabel>
          <textarea
            id={`${idBase}-headings`}
            className={`${textareaClasses} min-h-[64px] font-mono text-xs`}
            rows={3}
            value={node.sourceHeadings.join('\n')}
            disabled={disabled}
            placeholder={'Devoluciones\nPlazo'}
            onChange={(e) =>
              onChange({
                sourceHeadings: e.target.value
                  .split('\n')
                  .map((line) => line.trim())
                  .filter(Boolean),
              })
            }
          />
          <p className="text-xs text-text-muted mt-1">
            Un apartado por linea. Se guardan los titulos, no los fragmentos: los
            fragmentos se destruyen al reprocesar el documento y los titulos sobreviven.
          </p>
        </div>

        <PrerequisitePicker
          options={prerequisiteOptions}
          selected={node.prerequisiteNodeIds}
          onChange={(next) => onChange({ prerequisiteNodeIds: next })}
          disabled={disabled}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2 mt-6 pt-4 border-t border-border">
        <Button variant="secondary" size="sm" onClick={onArchiveToggle} disabled={disabled}>
          {node.archived ? 'Desarchivar' : 'Archivar'}
        </Button>
        <Button variant="ghost" size="sm" onClick={onRemove} disabled={disabled}>
          Quitar del esquema
        </Button>
        <p className="text-xs text-text-muted basis-full">
          Un nodo con progreso de aprendices no se borra: el servidor lo archiva para no
          tirar la maestria ni el rastro de auditoria de quien ya trabajo en el.
        </p>
      </div>
    </div>
  )
}
