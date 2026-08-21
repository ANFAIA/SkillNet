import { useCallback, useState } from 'react'

/**
 * "Has the admin dismissed/finished the onboarding scene?" — persisted per browser
 * in `localStorage`, exactly like the tour's `storage.ts` (docs/design/onboarding.md
 * §2.4; a later phase moves it to a per-user backend field for cross-device). Kept
 * behind this hook so that swap is a one-file change, and so the scene never
 * reappears once the admin has moved past it.
 *
 * Orthogonal to routing and to the real data gate: `Dashboard` decides *whether the
 * panel is empty enough* to warrant the scene; this only records the user's own
 * "I'm done with it" so a first-run panel does not show it forever.
 */
const STORAGE_KEY = 'skillnet-admin-scene'

function readDismissed(): boolean {
  if (typeof window === 'undefined') return false
  try {
    return window.localStorage.getItem(STORAGE_KEY) === 'dismissed'
  } catch {
    // Corrupt / disabled storage must never break the panel — behave as "not seen".
    return false
  }
}

export function useAdminScene(): { dismissed: boolean; dismiss: () => void } {
  const [dismissed, setDismissed] = useState(readDismissed)

  const dismiss = useCallback(() => {
    setDismissed(true)
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.setItem(STORAGE_KEY, 'dismissed')
      } catch {
        /* ignore quota / disabled storage */
      }
    }
  }, [])

  return { dismissed, dismiss }
}

/** Read-only check for other modules (e.g. the tour runner) without the setter. */
export function isAdminSceneDismissed(): boolean {
  return readDismissed()
}
