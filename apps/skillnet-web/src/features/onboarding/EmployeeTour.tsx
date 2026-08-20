import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import Joyride, { STATUS, type CallBackProps, type Step } from 'react-joyride'
import { employeeTourSteps, resolveSteps } from './steps'
import { TourTooltip } from './TourTooltip'
import { shouldAutoRun, writeOnboardingState } from './storage'
import { useTourStore } from './useTourStore'
import { useReducedMotion } from '../../hooks/useReducedMotion'

const HOME_PATH = '/empleado'

/**
 * The employee tour runner (docs/design/onboarding.md §3.1, Fase 0). Renders a themed
 * react-joyride over the home; it is an overlay orthogonal to routing — it never
 * redirects and closing it just leaves the learner in the (non-empty) app.
 *
 * - Runs by default for an employee who has not seen it (localStorage §2.4).
 * - Fully closeable/skippable at every step (persistent skip + close in the tooltip).
 * - Reopenable from the header "?" trigger via `useTourStore`.
 *
 * Mounted once inside the employee shell. The tour only makes sense on the home
 * (its anchors live there), so it auto-runs and reopens only on `/empleado`.
 */
export function EmployeeTour() {
  const location = useLocation()
  const reduce = useReducedMotion()
  const onHome = location.pathname === HOME_PATH
  const run = useTourStore((s) => s.run)
  const runId = useTourStore((s) => s.runId)
  const start = useTourStore((s) => s.start)
  const stop = useTourStore((s) => s.stop)

  // Re-key Joyride on each (re)start so it always resets to step 0.
  const [mountKey, setMountKey] = useState(0)
  useEffect(() => {
    if (run) setMountKey((k) => k + 1)
  }, [run, runId])

  // Auto-run once for a first-time employee, only while on the home route so the
  // spotlight targets exist. A short delay lets the dashboard cards mount first.
  useEffect(() => {
    if (!onHome) return
    if (!shouldAutoRun()) return
    if (useTourStore.getState().run) return
    const t = window.setTimeout(() => {
      if (shouldAutoRun() && !useTourStore.getState().run) start()
    }, 600)
    return () => window.clearTimeout(t)
  }, [onHome, start])

  const steps: Step[] = useMemo(
    () =>
      resolveSteps(employeeTourSteps, 'employee').map((s) => ({
        target: s.target,
        title: s.title,
        content: s.body,
        disableBeacon: true,
        placement: 'auto',
      })),
    [],
  )

  const stepIds = useMemo(() => resolveSteps(employeeTourSteps, 'employee').map((s) => s.id), [])

  function handleCallback(data: CallBackProps) {
    const { status, index, type } = data

    // Remember where the learner was, so a reopen can say "you were here" later.
    if (type === 'step:after' || type === 'tooltip') {
      writeOnboardingState({ lastStepId: stepIds[index] })
    }

    if (status === STATUS.FINISHED) {
      writeOnboardingState({ completed: true, lastStepId: stepIds[stepIds.length - 1] })
      stop()
    } else if (status === STATUS.SKIPPED) {
      // Skip / close is a dismissal, not a completion — reopenable from the header.
      writeOnboardingState({ dismissedAt: new Date().toISOString() })
      stop()
    }
  }

  // Only mount the overlay while running AND on the home route: a route change mid
  // tour must not leave a spotlight hunting for an element that no longer exists.
  if (!run || !onHome) return null

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
