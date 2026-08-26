import { useIntl } from 'react-intl'
import { useCapability, type CapabilityName } from '../api/setup'
import { capabilityExplanation } from '../lib/capabilityCopy'
import { useAuth } from './useAuth'

/**
 * Why a control that needs `name` is inert, phrased for whoever is looking.
 *
 * The role comes from `/auth/me` through {@link useAuth} — the same place every
 * other role check in the app reads it (`user.role === 'admin'`). There is no second
 * source of truth for "is this an admin", and this hook must not become one. Before
 * the identity resolves, and on the pre-auth screens where there is none, the learner
 * wording is the safe answer: it never leaks deployment detail.
 */
export function useCapabilityExplanation(name: CapabilityName): string {
  const intl = useIntl()
  const capability = useCapability(name)
  const { user } = useAuth()
  return capabilityExplanation(intl, name, capability, user?.role === 'admin')
}
