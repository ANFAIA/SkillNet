import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import Joyride, { ACTIONS, EVENTS, STATUS, type CallBackProps, type Step } from 'react-joyride'
import { tourSteps, resolveSteps } from './steps'
import { TourTooltip } from './TourTooltip'
import { shouldAutoRun, writeOnboardingState } from './storage'
import { useTourStore } from './useTourStore'
import { readyFlags, useCapabilities } from '../../api/setup'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import type { SidebarRole } from '../../components/layout/Sidebar'

const EMPLOYEE_HOME = '/empleado'
const ADMIN_HOME = '/admin'

/** A spotlight target is only usable if it is in the DOM *and* actually painted. */
function isVisible(selector: string): boolean {
  if (typeof document === 'undefined') return false
  const el = document.querySelector(selector)
  return el instanceof HTMLElement && el.getClientRects().length > 0
}

/** Shared themed joyride options so both runners read as part of SkillNet. */
const JOYRIDE_STYLES = {
  options: {
    // The spotlight arrow is drawn as an SVG fill — a CSS var keeps it on the active
    // theme's surface without recomputing on theme swap.
    arrowColor: 'var(--color-surface)',
    overlayColor: 'rgba(9, 9, 11, 0.55)',
    zIndex: 10_000,
  },
  spotlight: { borderRadius: 12 },
} as const

/**
 * The employee tour is a hint layer, not a modal — and joyride's overlay is a single
 * full-document `<div>` whose default `pointer-events: auto` swallows every click on the
 * page the tour is teaching. That is why "Empezar" on the home hero did nothing while the
 * tour was open: the click landed on the overlay, and `disableOverlayClose` made it a
 * no-op, so the learner stayed on Inicio. Making the overlay click-through fixes it for
 * the hero *and* for everything else under it (sidebar, course rows, "Ver todos") in one
 * move, because there was only ever one blocker.
 *
 * Two of the library's own hooks do it, and **neither touches stacking** — no z-index is
 * added or reordered here. The tooltip stays interactive because it is a separate portal
 * (react-floater's `.__floater`) that still accepts pointer events; the overlay simply
 * stops being a target, which is a hit-testing property, not a stacking one:
 *
 * - `spotlightClicks` (prop) zeroes pointer events on the spotlight hole itself.
 * - `styles.overlay.pointerEvents` zeroes them on the dim backdrop. joyride spreads the
 *   consumer's `styles.overlay` *after* its own computed `pointerEvents`, so this is the
 *   documented style hook winning as intended, not an override fight.
 *
 * `overlayLegacy*` carries the same value on purpose: joyride falls back to those keys on
 * any browser its UA sniffing does not recognise (jsdom included), and a fix that only
 * held on Chrome/Firefox/Safari would be no fix at all.
 */
const CLICK_THROUGH = { pointerEvents: 'none' } as const
const EMPLOYEE_JOYRIDE_STYLES = {
  ...JOYRIDE_STYLES,
  overlay: CLICK_THROUGH,
  overlayLegacy: CLICK_THROUGH,
  overlayLegacyCenter: CLICK_THROUGH,
} as const

/**
 * The tour's own surfaces, the only clicks that must *not* count as "the learner is using
 * the page": our tooltip card, react-floater's wrapper around it (its arrow and padding
 * sit outside the card), and the header "?" that reopens the tour.
 */
const TOUR_SURFACES = '[data-tour-tooltip], .__floater, [data-tour-trigger]'

/**
 * react-floater (the library behind the tooltip box, via react-joyride) reserves
 * room for its arrow with a default `margin: 8` on top of the arrow's own
 * `length: 16` — that extra margin is what read as a gap between the arrow tip
 * and our tooltip card. This is the library's own documented arrow config
 * (`floaterProps.styles.arrow`), not a hand-tuned distance: zeroing the margin
 * lets the arrow sit flush against the card, as react-floater intends when a
 * consumer supplies its own fully-styled tooltip body (ours already has its own
 * padding/border/shadow, so it doesn't need the library's default breathing room).
 */
const FLOATER_PROPS = (reduce: boolean) => ({
  disableAnimation: reduce,
  styles: { arrow: { length: 12, spread: 20, margin: 0 } },
})

/**
 * Close the tour on the learner's first real interaction with the page beneath it.
 *
 * This is the other half of making the overlay click-through: the page below is live now,
 * so "Saltar" can no longer be the only way out. A spotlight left hovering over a screen
 * the learner is already using is noise, and because `run` lives in a module store it
 * would pop back up on the next visit to `/empleado` — the learner would have started a
 * lesson and still be told to start one. Doing beats reading: a pointerdown anywhere
 * outside the tour's own surfaces is treated as "understood", and it writes exactly the
 * state Skip writes, so the tour stays reopenable from the header "?" and never auto-runs
 * again.
 *
 * Capture phase, and deliberately no `preventDefault`/`stopPropagation`: we only need to
 * hear the interaction first, the click itself must still reach whatever the learner
 * aimed at. `pointerdown` covers mouse, touch and pen with one listener.
 */
function useDismissOnPageInteraction(active: boolean) {
  const stop = useTourStore((s) => s.stop)

  useEffect(() => {
    if (!active) return
    function handlePointerDown(event: Event) {
      const target = event.target
      if (target instanceof Element && target.closest(TOUR_SURFACES)) return
      writeOnboardingState({ dismissedAt: new Date().toISOString() }, 'employee')
      stop()
    }
    document.addEventListener('pointerdown', handlePointerDown, true)
    return () => document.removeEventListener('pointerdown', handlePointerDown, true)
  }, [active, stop])
}

/**
 * The employee product tour: a single-page walkthrough of `/empleado`. Every step
 * anchors to the employee home, so it auto-runs and reopens only on that route and
 * drops any anchor that is not painted. This is the original tour behaviour, left
 * intact — the admin flow is a separate runner below.
 */
function EmployeeTourRunner() {
  const location = useLocation()
  const reduce = useReducedMotion()
  const onHome = location.pathname === EMPLOYEE_HOME
  const run = useTourStore((s) => s.run)
  const runId = useTourStore((s) => s.runId)
  const start = useTourStore((s) => s.start)
  const stop = useTourStore((s) => s.stop)
  const capabilities = useCapabilities()

  // Re-key Joyride on each (re)start so it always resets to step 0.
  const [mountKey, setMountKey] = useState(0)
  useEffect(() => {
    if (run) setMountKey((k) => k + 1)
  }, [run, runId])

  // Auto-run once for a first-time user, only while on the home route so the spotlight
  // targets exist. A short delay lets the home cards mount first.
  useEffect(() => {
    if (!onHome) return
    if (!shouldAutoRun('employee')) return
    if (useTourStore.getState().run) return
    const t = window.setTimeout(() => {
      if (shouldAutoRun('employee') && !useTourStore.getState().run) start()
    }, 600)
    return () => window.clearTimeout(t)
  }, [onHome, start])

  // Resolve the employee steps and keep only the ones whose anchor is on screen right
  // now. Re-scanned on every (re)start (runId) so late-mounting anchors are picked up.
  const visibleSteps = useMemo(
    () => resolveSteps(tourSteps, 'employee', readyFlags(capabilities)).filter((s) => isVisible(s.target)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [runId, capabilities],
  )

  const steps: Step[] = useMemo(
    () =>
      visibleSteps.map((s, i) => ({
        target: s.target,
        title: s.title,
        content: s.body,
        disableBeacon: true,
        placement: 'auto',
        /*
          No scroll on the way IN. The first step anchors the home hero, which is already
          at the top of the scroller, so joyride's "bring the target into view" had nothing
          to bring — it just slid the page (82px, measured on /empleado) about half a second
          after load, moving "Continuar" out from under a pointer already aiming at it. That
          is the second half of the reported bug: even with the overlay no longer eating the
          click, an unprompted jump makes the learner miss the button.

          Per-step rather than the global `disableScrolling`, because scrolling to the *next*
          step is still wanted: the Skill Map card can sit below the fold, and that scroll is
          a response to the learner pressing Next, not a surprise. `scrollToFirstStep` cannot
          express this — joyride's own `shouldScroll` ignores it once the first step reaches
          the TOOLTIP lifecycle, so `step.disableScrolling` is the only lever that holds.
        */
        disableScrolling: i === 0,
      })),
    [visibleSteps],
  )

  const stepIds = useMemo(() => visibleSteps.map((s) => s.id), [visibleSteps])

  // Live only while the overlay is actually on screen — same condition as the render
  // guard below, so the listener never outlives what it is dismissing.
  useDismissOnPageInteraction(run && onHome && steps.length > 0)

  function handleCallback(data: CallBackProps) {
    const { status, index, type } = data

    if (type === 'step:after' || type === 'tooltip') {
      writeOnboardingState({ lastStepId: stepIds[index] }, 'employee')
    }

    if (status === STATUS.FINISHED) {
      writeOnboardingState({ completed: true, lastStepId: stepIds[stepIds.length - 1] }, 'employee')
      stop()
    } else if (status === STATUS.SKIPPED) {
      writeOnboardingState({ dismissedAt: new Date().toISOString() }, 'employee')
      stop()
    }
  }

  if (!run || !onHome || steps.length === 0) return null

  return (
    <Joyride
      key={mountKey}
      steps={steps}
      run={run}
      continuous
      showSkipButton
      /*
        Later steps may need to scroll their anchor into view; the first one must not — see
        the per-step `disableScrolling` above, which is what actually holds.
      */
      disableScrolling={false}
      scrollToFirstStep={false}
      /*
        Kept for intent, though it can no longer fire: the backdrop is not a click target
        at all now (see EMPLOYEE_JOYRIDE_STYLES), and dismissal by interaction is handled
        explicitly by `useDismissOnPageInteraction`, which lets the click through.
      */
      disableOverlayClose
      spotlightClicks
      spotlightPadding={6}
      tooltipComponent={TourTooltip}
      callback={handleCallback}
      floaterProps={FLOATER_PROPS(reduce)}
      styles={EMPLOYEE_JOYRIDE_STYLES}
    />
  )
}

/**
 * The admin product tour: a guided, multi-screen sequence. Each step lives on its own
 * real onboarding screen (see `adminTourSteps`), so joyride runs in CONTROLLED mode:
 *
 * - The store holds the current step index, surviving the client-side navigation from
 *   one step's route to the next (the store is a module singleton).
 * - We only render the overlay when the current step's `route` matches the pathname
 *   AND its target is actually painted (a short poll after navigation). Otherwise we
 *   render nothing, so no spotlight ever hunts for an element on the wrong screen.
 * - "Next" advances the index and, when the next step sits on a different screen,
 *   navigates there; the box reappears once that screen mounts its anchor.
 * - `spotlightClicks` keeps the highlighted element interactive; `disableOverlayClose`
 *   makes the box dismissible via Skip / ✕ only.
 */
function AdminTourRunner() {
  const location = useLocation()
  const navigate = useNavigate()
  const reduce = useReducedMotion()
  const run = useTourStore((s) => s.run)
  const runId = useTourStore((s) => s.runId)
  const index = useTourStore((s) => s.index)
  const setIndex = useTourStore((s) => s.setIndex)
  const start = useTourStore((s) => s.start)
  const stop = useTourStore((s) => s.stop)
  const capabilities = useCapabilities()

  // The admin steps are stable (only capability-gating drops one), so resolve once.
  const adminSteps = useMemo(
    () => resolveSteps(tourSteps, 'admin', readyFlags(capabilities)),
    [capabilities],
  )

  const joyrideSteps: Step[] = useMemo(
    () =>
      adminSteps.map((s) => ({
        target: s.target,
        title: s.title,
        content: s.body,
        disableBeacon: true,
        placement: 'auto',
      })),
    [adminSteps],
  )

  // Auto-run once for a first-time admin, only from the first step's route.
  useEffect(() => {
    if (location.pathname !== ADMIN_HOME) return
    if (!shouldAutoRun('admin')) return
    if (useTourStore.getState().run) return
    const t = window.setTimeout(() => {
      if (shouldAutoRun('admin') && !useTourStore.getState().run) start()
    }, 600)
    return () => window.clearTimeout(t)
  }, [location.pathname, start])

  const current = adminSteps[index]
  const onRoute = Boolean(current) && current.route === location.pathname

  // The box appears only once the router has landed on the step's screen and the
  // anchor is painted. After a navigation the target can mount a beat late, so poll
  // briefly before showing.
  const [ready, setReady] = useState(false)
  useEffect(() => {
    if (!run || !onRoute || !current) {
      setReady(false)
      return
    }
    if (isVisible(current.target)) {
      setReady(true)
      return
    }
    setReady(false)
    let tries = 0
    const id = window.setInterval(() => {
      tries += 1
      if (isVisible(current.target)) {
        setReady(true)
        window.clearInterval(id)
      } else if (tries >= 25) {
        window.clearInterval(id)
      }
    }, 100)
    return () => window.clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, onRoute, current?.target, runId])

  // Move to step `i`: persist, update the index, and navigate if it lives elsewhere.
  function goTo(i: number) {
    const target = adminSteps[i]
    if (!target) return
    setIndex(i)
    writeOnboardingState({ lastStepId: target.id }, 'admin')
    if (target.route && target.route !== location.pathname) navigate(target.route)
  }

  function handleCallback(data: CallBackProps) {
    const { action, index: jIndex, status, type } = data

    // Skip / ✕ is a dismissal, not a completion — reopenable from the header.
    if (status === STATUS.SKIPPED || action === ACTIONS.CLOSE) {
      writeOnboardingState({ dismissedAt: new Date().toISOString() }, 'admin')
      stop()
      return
    }

    // Controlled stepping: joyride reports where it wants to go, we drive the index.
    if (type === EVENTS.STEP_AFTER) {
      if (action === ACTIONS.PREV) {
        goTo(Math.max(0, jIndex - 1))
        return
      }
      const next = jIndex + 1
      if (next >= adminSteps.length) {
        writeOnboardingState(
          { completed: true, lastStepId: adminSteps[adminSteps.length - 1]?.id },
          'admin',
        )
        stop()
      } else {
        goTo(next)
      }
    }
  }

  if (!run || !onRoute || !ready || joyrideSteps.length === 0) return null

  return (
    <Joyride
      steps={joyrideSteps}
      run={run}
      stepIndex={index}
      continuous
      showSkipButton
      disableScrolling={false}
      scrollToFirstStep={false}
      disableOverlayClose
      spotlightClicks
      spotlightPadding={6}
      tooltipComponent={TourTooltip}
      callback={handleCallback}
      floaterProps={FLOATER_PROPS(reduce)}
      styles={JOYRIDE_STYLES}
    />
  )
}

/**
 * The role-aware product tour runner (docs/design/onboarding.md §3, Fase 0/1). Mounted
 * once inside each shell. The employee tour is a single-page walkthrough of `/empleado`;
 * the admin tour is a guided, multi-screen sequence that walks the owner through the
 * real onboarding screens, navigating between them as they advance. Both auto-run for a
 * first-time user of the role, are fully closeable, and reopen from the header "?".
 */
export function ProductTour({ role }: { role: SidebarRole }) {
  return role === 'admin' ? <AdminTourRunner /> : <EmployeeTourRunner />
}
