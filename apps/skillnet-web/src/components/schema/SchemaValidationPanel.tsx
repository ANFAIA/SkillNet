import { useIntl } from 'react-intl'
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

const KNOWN_RULES = [
  'empty_schema',
  'missing_summary',
  'no_critical_node',
  'orphan_prerequisite',
  'cycle',
  'position_not_contiguous',
  'node_not_reviewed',
  'node_has_progress',
  'unknown_node',
] as const

/** Kept for tests that import SCHEMA_RULE_COPY — keys only, values come from i18n now. */
export const SCHEMA_RULE_COPY: Record<string, RuleCopy> = Object.fromEntries(
  KNOWN_RULES.map((code) => [code, { title: code, detail: `${code}.detail` }]),
)

function useRuleCopy() {
  const intl = useIntl()
  return (code: string): RuleCopy => {
    const titleKey = `schemaRule.${code}`
    const detailKey = `schemaRule.${code}.detail`
    if ((KNOWN_RULES as readonly string[]).includes(code)) {
      return {
        title: intl.formatMessage({ id: titleKey }),
        detail: intl.formatMessage({ id: detailKey }),
      }
    }
    return {
      title: intl.formatMessage({ id: 'schemaValidation.unknownError' }, { code }),
      detail: intl.formatMessage({ id: 'schemaValidation.unknownErrorDetail' }),
    }
  }
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
  const intl = useIntl()
  const ruleCopy = useRuleCopy()

  if (errors.length === 0 && warnings.length === 0) return null

  function label(id: string): string {
    return nodeLabels[id] ?? intl.formatMessage({ id: 'schemaValidation.unknownNode' }, { id: id.slice(0, 8) })
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
              ? intl.formatMessage({ id: 'schemaValidation.problemsSingular' })
              : intl.formatMessage({ id: 'schemaValidation.problemsPlural' }, { count: errors.length })}
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
                      {intl.formatMessage({ id: 'schemaValidation.cycleLabel' })}{' '}
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
            {intl.formatMessage({ id: 'schemaValidation.warnings' })}
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
