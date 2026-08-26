import type { IntlShape } from 'react-intl'
import type { Capability, CapabilityName } from '../api/setup'

/**
 * The sentence shown when a control is inert because a capability is missing.
 *
 * Role-aware on purpose (docs/design/degraded-mode-ux.md): a learner is told the
 * feature is unavailable *in this installation* and nothing more — the shape of the
 * deployment's `.env` is not their business and they can do nothing with it. An
 * admin is told the same thing plus the one actionable detail that ends the problem.
 *
 * The copy is assembled from three flat catalogue keys rather than written out for
 * every (capability × reason × role) combination, which would be sixty strings that
 * nobody keeps in sync:
 *
 *   1. **base** — what is unavailable (`capability.images.unavailable`).
 *   2. **detail** — the role's half. Learner: a reason clause that never mentions
 *      keys (`capability.reason.provider_quota`). Admin: the actionable one
 *      (`capability.images.admin.missing_api_key`, falling back to the generic
 *      `capability.admin.missing_api_key`).
 *   3. **hint** — the backend's admin-only free text, when it sent one. Never for a
 *      learner: it is English, unlocalised, and always null on the public payload.
 *
 * Each level falls back to a generic key, so a capability or reason added on the
 * backend before the catalogue catches up still produces a sentence instead of a
 * react-intl "missing message" hole.
 */
export function capabilityExplanation(
  intl: IntlShape,
  name: CapabilityName,
  capability: Capability,
  isAdmin: boolean,
): string {
  const reason = capability.reason ?? null

  const base = firstPresent(intl, [
    ...(reason ? [`capability.${name}.${reason}`] : []),
    `capability.${name}.unavailable`,
    'capability.unavailable',
  ])

  const detail = isAdmin
    ? firstPresent(intl, [
        ...(reason ? [`capability.${name}.admin.${reason}`, `capability.admin.${reason}`] : []),
        'capability.admin.unknown',
      ])
    : firstPresent(intl, [
        ...(reason ? [`capability.reason.${reason}`] : []),
        'capability.reason.unknown',
      ])

  const hint = isAdmin && capability.hint ? capability.hint : null

  return [base, detail, hint].filter(Boolean).join(' ')
}

/**
 * The sentence shown next to a control that WILL run, but with less than it should —
 * a `degraded` requirement. Deliberately a different function from
 * {@link capabilityExplanation}: "no está disponible" is a lie about a podcast that
 * is about to be generated in an offline voice, and the difference between refusing
 * and warning is the whole point of having three statuses instead of two.
 *
 * Short by design. It is read in passing, next to the button, at the moment it
 * changes what the result will be — not a place to explain the deployment.
 */
export function capabilityReduced(intl: IntlShape, name: CapabilityName): string {
  return (
    firstPresent(intl, [`capability.${name}.degraded`, 'capability.degraded']) ?? ''
  )
}

/**
 * A two-or-three-word tag for a capability that is not `ready` — "Falta la clave",
 * "Limite del proveedor". The deployment-level banner already carries a full sentence
 * per capability; what it lacked was the *reason*, and a tag adds it without
 * restating the per-control explanation next to it.
 *
 * Falls back to the status when the reason is one the catalogue does not know, and to
 * an empty string for a `ready` capability, which has nothing to tag.
 */
export function capabilityTag(intl: IntlShape, capability: Capability): string {
  const reason = capability.reason ?? null
  return (
    firstPresent(intl, [
      ...(reason ? [`capability.reasonLabel.${reason}`] : []),
      `capability.statusLabel.${capability.status}`,
    ]) ?? ''
  )
}

/** The first id the catalogue actually has, formatted. `null` when it has none. */
function firstPresent(intl: IntlShape, ids: string[]): string | null {
  for (const id of ids) {
    if (intl.messages[id]) return intl.formatMessage({ id })
  }
  return null
}
