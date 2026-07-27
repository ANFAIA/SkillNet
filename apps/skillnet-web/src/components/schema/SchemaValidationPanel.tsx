import type { SchemaRuleError } from '../../types'

/**
 * What the server refused, in the creator's words.
 *
 * `POST /schema/validate` returns **every** blocking violation at once
 * (`422 {"detail": {"code": "schema_invalid", "errors": [...]}}`), so this panel lists
 * them all rather than showing one error per round trip. The alternative — collapsing
 * the structured body into "no se pudo validar" — is the failure this component exists
 * to prevent: a cycle in the prerequisite graph means no node can ever start, and the
 * only person who can fix it is looking at this screen.
 */

interface RuleCopy {
  title: string
  /** Why it blocks, so the creator knows what to change and not just that it failed. */
  detail: string
}

export const SCHEMA_RULE_COPY: Record<string, RuleCopy> = {
  empty_schema: {
    title: 'El esquema no tiene ningun nodo',
    detail: 'Propon un esquema desde el documento o anade nodos a mano.',
  },
  missing_summary: {
    title: 'Hay nodos sin resumen',
    detail:
      'El tutor lee el arbol de resumenes para decidir que nodo es relevante: sin resumen ese nodo es invisible para el.',
  },
  missing_source: {
    title: 'Hay nodos sin fuente',
    detail:
      'Cada nodo necesita un documento de origen o una leccion semilla. Sin fuente no hay de donde generar contenido.',
  },
  no_critical_node: {
    title: 'Ningun nodo es critico',
    detail:
      'El curso se cierra cuando se dominan todos los nodos criticos. Sin ninguno, nunca podria completarse.',
  },
  orphan_prerequisite: {
    title: 'Hay prerrequisitos imposibles',
    detail:
      'Estos prerrequisitos apuntan a nodos que ya no estan en el esquema, asi que nunca se podrian cumplir.',
  },
  cycle: {
    title: 'Los prerrequisitos forman un ciclo',
    detail:
      'Cada nodo del ciclo espera a otro del mismo ciclo, asi que ninguno podria empezar nunca. Quita uno de los prerrequisitos de la cadena.',
  },
  position_not_contiguous: {
    title: 'El orden de los nodos tiene huecos',
    detail: 'Las posiciones deben ir del 1 al ultimo nodo sin saltos.',
  },
  node_not_reviewed: {
    title: 'Hay nodos sin revisar',
    detail:
      'Un nodo sin revisar no se sirve nunca. Marcalos como revisados en la lista de revision.',
  },
  node_has_progress: {
    title: 'Hay nodos con progreso de aprendices',
    detail:
      'Archivalos en lugar de borrarlos: borrarlos tiraria la maestria y el rastro de auditoria de quien ya trabajo en ellos.',
  },
  unknown_node: {
    title: 'El esquema referencia nodos que este curso no tiene',
    detail: 'Recarga la pantalla para volver a leer el esquema del servidor.',
  },
}

function ruleCopy(code: string): RuleCopy {
  return (
    SCHEMA_RULE_COPY[code] ?? {
      title: `El servidor rechazo el esquema (${code})`,
      detail: 'No se pudo traducir este error. Revisa el esquema completo.',
    }
  )
}

export function SchemaValidationPanel({
  errors,
  warnings,
  nodeLabels,
  className = '',
}: {
  errors: SchemaRuleError[]
  warnings: string[]
  /** node id → the label the creator sees, e.g. `"3. Plazo de devolucion"`. */
  nodeLabels: Record<string, string>
  className?: string
}) {
  if (errors.length === 0 && warnings.length === 0) return null

  function label(id: string): string {
    return nodeLabels[id] ?? `Nodo desconocido (${id.slice(0, 8)})`
  }

  return (
    <div className={`space-y-3 ${className}`}>
      {errors.length > 0 && (
        <div
          role="alert"
          className="border border-danger/40 bg-danger/5 rounded-lg p-4 min-w-0"
        >
          <p className="text-sm font-medium text-danger">
            {errors.length === 1
              ? 'No se puede validar todavia: 1 problema'
              : `No se puede validar todavia: ${errors.length} problemas`}
          </p>
          <ul className="mt-3 space-y-3">
            {errors.map((error, index) => {
              const copy = ruleCopy(error.code)
              return (
                <li key={`${error.code}-${index}`} className="min-w-0">
                  <p className="text-sm text-text">{copy.title}</p>
                  <p className="text-xs text-text-secondary mt-0.5">{copy.detail}</p>
                  {error.code === 'cycle' && error.node_ids && error.node_ids.length > 0 ? (
                    // The server returns the cycle as an ordered path and does NOT
                    // repeat the first id, so the chain is closed here to make the
                    // loop visible instead of reading as a straight line.
                    <p className="text-xs text-text mt-1 break-words">
                      Ciclo:{' '}
                      {[...error.node_ids, error.node_ids[0]]
                        .map((id) => label(id))
                        .join(' -> ')}
                    </p>
                  ) : (
                    error.node_ids &&
                    error.node_ids.length > 0 && (
                      <ul className="mt-1 space-y-0.5">
                        {error.node_ids.map((id) => (
                          <li key={id} className="text-xs text-text truncate">
                            {label(id)}
                          </li>
                        ))}
                      </ul>
                    )
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="border border-warning/40 bg-warning/5 rounded-lg p-4 min-w-0">
          <p className="text-sm font-medium text-warning">
            Avisos del disenador (no bloquean la validacion)
          </p>
          <ul className="mt-2 space-y-1">
            {warnings.map((warning, index) => (
              <li key={index} className="text-xs text-text-secondary">
                {warning}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
