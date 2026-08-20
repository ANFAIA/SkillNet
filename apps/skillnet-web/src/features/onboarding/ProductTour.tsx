import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import Joyride, { STATUS, type CallBackProps, type Step } from 'react-joyride'
import { tourSteps, resolveSteps } from './steps'
import { TourTooltip } from './TourTooltip'
import { shouldAutoRun, writeOnboardingState } from './storage'
import { useTourStore } from './useTourStore'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import type { SidebarRole } from '../../components/layout/Sidebar'

const HOME_PATH: Record<SidebarRole, string> = {
  employee: '/empleado',
  admin: '/admin',
}

/** A spotlight target is only usable if it is in the DOM *and* actually painted. */
function isVisible(selector: string): boolean {
  if (typeof document === 'undefined') return false
  const el = document.querySelector(selector)
  return el instanceof HTMLElement && el.getClientRects().length > 0
}

/**
 * The role-aware product tour runner (docs/design/onboarding.md §3, Fase 0/1). One
 * component drives both roles: it reads its steps from the shared declarative list,
 * anchors on the role's home (`/empleado` vs `/admin`), and reuses the same themed
 * tooltip, per-role localStorage, run store and reduced-motion handling — the
 * behaviour is never forked, only the data (steps + home route) differ.
 *
 * - Runs by default for a first-time user of this role (localStorage §2.4, keyed per
 *   role so the two tours never suppress each other).
 * - Fully closeable/skippable at every step; reopenable from the header "?" trigger.
 * - An overlay orthogonal to routing: it never redirects, and closing it just leaves
 *   the user in the (non-empty) app.
 * - Steps whose anchor is not visible right now are dropped, so a workspace that hides
 *   a surface (e.g. no "Empleados" in an individual workspace) simply skips that step.
 *
 * Mounted once inside each shell. The tour only makes sense on its home (its anchors
 * live there), so it auto-runs and reopens only on that route.
 */
export function ProductTour({ role }: { role: SidebarRole }) {
  const location = useLocation()
  const reduce = useReducedMotion()
  const homePath = HOME_PATH[role]
  const onHome = location.pathname === homePath
  const run = useTourStore((s) => s.run)
  const runId = useTourStore((s) => s.runId)
  const start = useTourStore((s) => s.start)
  const stop = useTourStore((s) => s.stop)

  // Re-key Joyride on each (re)start so it always resets to step 0.
  const [mountKey, setMountKey] = useState(0)
  useEffect(() => {
    if (run) setMountKey((k) => k + 1)
  }, [run, runId])

  // Auto-run once for a first-time user of this role, only while on the home route so
  // the spotlight targets exist. A short delay lets the home cards mount first.
  useEffect(() => {
    if (!onHome) return
    if (!shouldAutoRun(role)) return
    if (useTourStore.getState().run) return
    const t = window.setTimeout(() => {
      if (shouldAutoRun(role) && !useTourStore.getState().run) start()
    }, 600)
    return () => window.clearTimeout(t)
  }, [onHome, role, start])

  // Resolve the role's steps and keep only the ones whose anchor is on screen right
  // now. Re-scanned on every (re)start (runId) so late-mounting or mode-specific
  // anchors are picked up. `runId` is an intentional dep for that rescan.
  const visibleSteps = useMemo(
    () => resolveSteps(tourSteps, role).filter((s) => isVisible(s.target)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [role, runId],
  )

  const steps: Step[] = useMemo(
    () =>
      visibleSteps.map((s) => ({
        target: s.target,
        title: s.title,
        content: s.body,
        disableBeacon: true,
        placement: 'auto',
      })),
    [visibleSteps],
  )

  const stepIds = useMemo(() => visibleSteps.map((s) => s.id), [visibleSteps])

  function handleCallback(data: CallBackProps) {
    const { status, index, type } = data

    // Remember where the user was, so a reopen can say "you were here" later.
    if (type === 'step:after' || type === 'tooltip') {
      writeOnboardingState({ lastStepId: stepIds[index] }, role)
    }

    if (status === STATUS.FINISHED) {
      writeOnboardingState({ completed: true, lastStepId: stepIds[stepIds.length - 1] }, role)
      stop()
    } else if (status === STATUS.SKIPPED) {
      // Skip / close is a dismissal, not a completion — reopenable from the header.
      writeOnboardingState({ dismissedAt: new Date().toISOString() }, role)
      stop()
    }
  }

  // Only mount the overlay while running AND on the home route, and only if at least
  // one anchor is present: a route change mid tour must not leave a spotlight hunting
  // for an element that no longer exists.
  if (!run || !onHome || steps.length === 0) return null

  return (
    <Joyride
      key={mountKey}
      steps={steps}
      run={run}
      continuous
      showSkipButton
      disableScrolling={false}
      scrollToFirstStep={!reduce}
      disableOverlayClose
      spotlightPadding={6}
      tooltipComponent={TourTooltip}
      callback={handleCallback}
      floaterProps={{ disableAnimation: reduce }}
      styles={{
        options: {
          // The spotlight arrow is drawn as an SVG fill — a CSS var keeps it on the
          // active theme's surface without recomputing on theme swap.
          arrowColor: 'var(--color-surface)',
          overlayColor: 'rgba(9, 9, 11, 0.55)',
          zIndex: 10_000,
        },
        spotlight: { borderRadius: 12 },
      }}
    />
  )
}
