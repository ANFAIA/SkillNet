/**
 * Which nodes must be mastered before this one (`course_node_prerequisites`, §3.2).
 *
 * Two rules from the server are visible here rather than discovered by failure:
 *
 * - A node cannot be its own prerequisite (`CHECK (node_id <> prerequisite_node_id)`),
 *   so it is not in the list.
 * - Prerequisites are real uuids. A node created in the current draft has no id yet,
 *   so it cannot be anybody's prerequisite until the schema is saved — the server
 *   drops such edges with a warning, and saying so up front is cheaper than letting
 *   the creator wonder why their edge vanished.
 *
 * Cycles are **not** checked here: `POST /schema/validate` owns that verdict with a
 * real topological sort, and a second, weaker implementation in the browser would
 * only be a second thing to keep in sync.
 */

export interface PrerequisiteOption {
  /** `null` for a node that only exists in the draft. */
  id: string | null
  key: string
  position: number
  title: string
}

export function PrerequisitePicker({
  options,
  selected,
  onChange,
  disabled = false,
}: {
  options: PrerequisiteOption[]
  selected: string[]
  onChange: (next: string[]) => void
  disabled?: boolean
}) {
  const selectable = options.filter((option) => option.id !== null)
  const unsaved = options.length - selectable.length

  function toggle(id: string) {
    onChange(selected.includes(id) ? selected.filter((v) => v !== id) : [...selected, id])
  }

  return (
    <fieldset className="min-w-0" disabled={disabled}>
      <legend className="text-sm font-medium text-text">Prerrequisitos</legend>
      <p className="text-xs text-text-muted mt-0.5 mb-2">
        El aprendiz no ve este nodo hasta dominar los que marques.
      </p>

      {selectable.length === 0 ? (
        <p className="text-xs text-text-muted border border-border rounded-lg px-3 py-2.5">
          No hay otros nodos guardados que puedan ser prerrequisito.
        </p>
      ) : (
        <div className="border border-border rounded-lg max-h-48 overflow-y-auto">
          {selectable.map((option) => (
            <label
              key={option.key}
              className={`flex items-center gap-3 px-3 py-2 border-b border-border last:border-b-0 transition-colors ${
                disabled ? 'opacity-50' : 'hover:bg-bg-subtle cursor-pointer'
              }`}
            >
              <input
                type="checkbox"
                className="accent-primary shrink-0"
                checked={selected.includes(option.id as string)}
                disabled={disabled}
                onChange={() => toggle(option.id as string)}
              />
              <span className="text-xs text-text-muted shrink-0 tabular-nums">
                {option.position}.
              </span>
              <span className="text-sm text-text-secondary truncate min-w-0">
                {option.title || 'Sin titulo'}
              </span>
            </label>
          ))}
        </div>
      )}

      <p className="text-xs text-text-muted mt-1">
        {selected.length === 0 ? 'Ninguno seleccionado' : `${selected.length} seleccionados`}
      </p>

      {unsaved > 0 && (
        <p className="text-xs text-warning mt-1">
          {unsaved === 1
            ? 'Hay 1 nodo sin guardar: guarda el esquema para poder usarlo como prerrequisito.'
            : `Hay ${unsaved} nodos sin guardar: guarda el esquema para poder usarlos como prerrequisito.`}
        </p>
      )}
    </fieldset>
  )
}
