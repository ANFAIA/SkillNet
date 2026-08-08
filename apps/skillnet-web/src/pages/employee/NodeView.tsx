import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import type { MouseEvent } from 'react'
import { useIntl } from 'react-intl'
import { useCourse } from '../../api/courses'
import { Card, EmptyState, ProgressBar } from '../../components/ui'
import { ClickableSurface, NO_EXPLAIN_SELECTOR } from '../../components/courses/ClickableSurface'
import { UiSpecRenderer } from '../../components/courses/UiSpecRenderer'
import { NodeList } from '../../components/courses/NodeList'
import { stepperContext, coursePositionContext, nextNodeContext, courseIntroContext } from '../../components/courses/blocks/StepperContext'
import type { CourseIntro } from '../../components/courses/blocks/StepperContext'
import { NodeChat } from '../../components/courses/NodeChat'
import { NodeSkeleton, RESERVED_CONTENT_PX } from '../../components/courses/NodeSkeleton'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { transition, duration, ease } from '../../lib/motion'
import { useLearnerProfile } from '../../api/onboarding'
import { post } from '../../api/client'
import { useNodeMorph } from '../../stores/nodeMorph'
import { usePreferences } from '../../stores/preferences'
import type { Locale } from '../../stores/preferences'
import {
  elementForFormat,
  isNodeNotReviewed,
  isNodeSurfaceDisabled,
  isPendingRender,
  isServedRender,
  useCourseNodes,
  useNodeEvents,
  useNodeRender,
  useNodeRenderStream,
  useRequestRender,
} from '../../api/nodes'
import type { LearnerProfileRead } from '../../api/onboarding'
import type { LearningNode } from '../../types'
import type { UiFormat } from '../../types/node-render'

// ── Slide panel types & helpers ─────────────────────────────────

type PanelType = 'map' | 'chat' | 'config'

const PANEL_TITLE_KEY: Record<PanelType, string> = {
  map: 'panel.map',
  chat: 'panel.chat',
  config: 'panel.config',
}

// ── Icons for the sidebar / bottom bar ──────────────────────────

function MapIcon({ active }: { active: boolean }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      className={active ? 'text-primary' : 'text-text-secondary'}
    >
      <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" />
    </svg>
  )
}

function ChatIcon({ active }: { active: boolean }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      className={active ? 'text-primary' : 'text-text-secondary'}
    >
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  )
}

function ConfigIcon({ active }: { active: boolean }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      className={active ? 'text-primary' : 'text-text-secondary'}
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
    >
      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

// ── Config panel ────────────────────────────────────────────────

function ConfigPanel() {
  const intl = useIntl()
  const locale = usePreferences((s) => s.locale)
  const setLocale = usePreferences((s) => s.setLocale)

  return (
    <div className="space-y-4">
      <div>
        <label className="text-sm font-medium text-text block mb-1">
          {intl.formatMessage({ id: 'settings.language' })}
        </label>
        <p className="text-xs text-text-muted mb-2">
          {intl.formatMessage({ id: 'settings.languageDesc' })}
        </p>
        <select
          value={locale}
          onChange={(e) => setLocale(e.target.value as Locale)}
          className="w-full border border-border rounded-md px-3 py-2 text-sm bg-bg text-text focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary"
        >
          <option value="es">{intl.formatMessage({ id: 'settings.langEs' })}</option>
          <option value="en">{intl.formatMessage({ id: 'settings.langEn' })}</option>
        </select>
      </div>
    </div>
  )
}

/**
 * One node of a dynamic course — where the learner finally sees generation happen.
 *
 * ## The two things this screen is
 *
 * 1. **A stable frame** (§5.5). Title, progress and the previous/next buttons never move.
 *    `NodeSkeleton` reserves the content area so the footer does not jump when the
 *    program lands, and the content itself is the *pinned* render: answering an item or
 *    coming back tomorrow returns the same bytes.
 *
 *    The reservation is also *released* rather than dropped: `RESERVED_CONTENT_PX`
 *    animates to zero on the arriving content, so a lesson shorter than the skeleton
 *    settles instead of snapping the footer up under the learner's eyes. And the blocks
 *    themselves resolve in sequence (`arriving`, see `blocks/blockArrival.ts`) whenever
 *    the learner has not asked for less motion — `useReducedMotion()` is the OS setting
 *    *or* the answer given in the onboarding wizard, and it is the only thing that
 *    silences the cadence since `fc6a348` removed the held previous version.
 * 2. **The deterministic opening line** (§6.2 Q2, §3.3). `goal` never travels to the LLM;
 *    it is rendered here, above the lesson, from a template. Rule 7 of §5.2 guarantees
 *    the program itself starts with a `lead` block, so the injected line reads as the
 *    first sentence instead of colliding with one.
 *
 * ## What it deliberately does not do
 *
 * - It **never renders `ui_block` payloads**. Those components come from `parse_partial`,
 *   before `validate_ui`, so the only text handed to `<Renderer>` is `program` from
 *   `GET /render` — re-serialized server-side from the validated `UISpec` (§5.1). The
 *   stream is used for the step message, the format-shaped skeleton and a block counter.
 * - It registers **no tools, no `toolProvider`, no `onAction`, no `onStateUpdate`**, and
 *   `UiSpecRenderer` is what enforces that by omission. Reactivity is off by decision.
 * - It does **not** retry on `error {fallback: false}`. There is nothing to serve, and a
 *   retry loop against a blank screen is worse than a sentence explaining it.
 */

/** i18n key for the deterministic "esto te sirve para X" by `goal` value (§6.2 Q2 options). */
const GOAL_KEY: Record<string, string> = {
  onboarding: 'node.goalOnboarding',
  specific_gap: 'node.goalSpecificGap',
  assigned: 'node.goalAssigned',
}

function openingLineFor(
  profile: LearnerProfileRead | null | undefined,
  intl: ReturnType<typeof useIntl>,
): string | null {
  const goal = profile?.goal?.trim()
  if (!goal) return null
  const key = GOAL_KEY[goal]
  if (key) return intl.formatMessage({ id: key })
  // "Otro" is free text the learner wrote about themselves. It is echoed, never sent to
  // the model, and never used as anything but this sentence.
  return intl.formatMessage({ id: 'node.goalCustom' }, { goal })
}

/** Dwell under this reads as `scroll_fast`; over `SLOW_MS`, as `scroll_slow` (§3.3). */
const FAST_MS = 1000
const SLOW_MS = 3000

type Phase = 'content' | 'mastered'

export function NodeView() {
  const intl = useIntl()
  const { id: courseId, nodeId } = useParams<{ id: string; nodeId: string }>()
  const navigate = useNavigate()

  const clearMorph = useNodeMorph((s) => s.clear)
  /** Which slide panel is open, if any. */
  const [activePanel, setActivePanel] = useState<PanelType | null>(null)

  const nodes = useCourseNodes(courseId)
  const courseQuery = useCourse(courseId)
  const { data: profile } = useLearnerProfile()
  const events = useNodeEvents(nodeId)

  const node: LearningNode | null = useMemo(
    () => nodes.data?.nodes.find((entry) => entry.id === nodeId) ?? null,
    [nodes.data, nodeId],
  )

  const ordered = useMemo(
    () => [...(nodes.data?.nodes ?? [])].sort((a, b) => a.position - b.position),
    [nodes.data],
  )
  const index = ordered.findIndex((entry) => entry.id === nodeId)
  const previousNode = index > 0 ? ordered[index - 1] : null
  const nextNode = index >= 0 && index < ordered.length - 1 ? ordered[index + 1] : null

  // Course intro — only on the first node when learner has zero progress
  const isFirstNode = index === 0
  const hasNoProgress = ordered.every((n) => n.mastery === 0)
  const totalMinutes = ordered.reduce((sum, n) => sum + (n.estimated_minutes ?? 0), 0)
  const courseIntro: CourseIntro | null = useMemo(() => {
    if (!isFirstNode || !hasNoProgress || !courseQuery.data) return null
    return {
      title: courseQuery.data.title,
      subtitle: intl.formatMessage({ id: 'node.introSubtitle' }, { count: ordered.length, minutes: totalMinutes }),
      outcomes: ordered.slice(0, 4).map((n) => n.summary).filter((s): s is string => Boolean(s)),
      buddyMessage: intl.formatMessage({ id: 'node.buddyMessage' }),
    }
  }, [isFirstNode, hasNoProgress, courseQuery.data, ordered, totalMinutes, intl])

  const initialPhase: Phase | null = node ? 'content' : null

  const [phase, setPhase] = useState<Phase | null>(null)
  useEffect(() => {
    setPhase((prev) => prev ?? initialPhase)
  }, [initialPhase])

  const [streamFailure, setStreamFailure] = useState<string | null>(null)

  const requestedRef = useRef(false)
  /** Set once any lesson has been on screen — see `fromSkeleton` further down. */
  const programShownBefore = useRef(false)
  const viewedRenderRef = useRef<string | null>(null)
  const dwellStartRef = useRef<number | null>(null)
  const formatRef = useRef<UiFormat | null>(null)

  // Reset all per-node state when navigating between nodes. React Router does NOT
  // remount NodeView when only :nodeId changes, so state from the previous node
  // would carry over (wrong phase, stale errors, missed render requests).
  const prevNodeId = useRef(nodeId)
  useEffect(() => {
    if (prevNodeId.current === nodeId) return
    prevNodeId.current = nodeId
    setPhase(null)
    setStreamFailure(null)
    setActivePanel(null)
    requestedRef.current = false
    programShownBefore.current = false
    viewedRenderRef.current = null
    dwellStartRef.current = null
    formatRef.current = null
    // prefetchedRef is defined later but initialized to null anyway
  }, [nodeId])

  const render = useNodeRender(nodeId, { enabled: phase === 'content' })
  const requestRender = useRequestRender(nodeId)

  const served = isServedRender(render.data) ? render.data : null
  const pending = isPendingRender(render.data) ? render.data : null

  const reduceMotion = useReducedMotion()

  const stream = useNodeRenderStream({
    onSettled: ({ reason, fallbackAvailable }) => {
      if (reason === 'skipped') {
        setPhase('mastered')
        return
      }
      if (reason === 'error' && !fallbackAvailable) {
        // Nothing was persisted and nothing will be. Asking again is the loop this
        // branch exists to avoid.
        setStreamFailure(intl.formatMessage({ id: 'node.renderFailed' }))
        return
      }
      // `done`, or `error` with a seed waiting: both mean `GET /render` now has
      // something pinned.
      setStreamFailure(null)
      void render.refetch()
    },
  })

  /**
   * Ask for a render and, only when there is work to listen to, open the stream.
   *
   * `request_id === ''` means the render was already pinned or the `cache_key` hit, so
   * subscribing would block on a channel nobody will publish to. The subscription is
   * fired immediately after the `202` because the runner waits just 0.5 s for a
   * subscriber and this pub/sub keeps no backlog (§9.2).
   */
  const startRender = useCallback(
    () => {
      if (!nodeId) return
      requestedRef.current = true
      requestRender.mutate(
        { force: false },
        {
          onSuccess: (accepted) => {
            if (!accepted.request_id) {
              void render.refetch()
              return
            }
            void stream.start(nodeId, accepted.request_id)
          },
        },
      )
    },
    [nodeId, requestRender, render, stream],
  )

  // In the content phase, make sure *something* is on its way: either another tab owns
  // a request we can listen to, or nothing has been asked for yet.
  useEffect(() => {
    if (phase !== 'content' || !nodeId) return
    if (served || streamFailure) return
    if (!pending) return
    if (pending.request_id) {
      // Somebody's task already owns this render (another tab, or our own prefetch in a
      // previous mount). Listen instead of starting a second one.
      if (stream.status === 'idle') void stream.start(nodeId, pending.request_id)
      return
    }
    if (requestedRef.current) return
    startRender()
  }, [phase, nodeId, served, pending, streamFailure, stream, startRender])

  // --- instrumentation (§3.3) -------------------------------------------------

  // One `view` per render actually shown, with the format's vector dimension. Not per
  // mount: a remount of the same pinned render is the same view.
  useEffect(() => {
    if (!served) return
    // A lesson is on screen from here on: the reserved height has been released and
    // must not be re-reserved by whatever replaces it.
    programShownBefore.current = true
    formatRef.current = served.ui_format
    if (viewedRenderRef.current === served.render_id) return
    viewedRenderRef.current = served.render_id
    dwellStartRef.current = Date.now()
    events.record({ type: 'view', element: elementForFormat(served.ui_format) })
  }, [served, events])

  // Dwell, resolved when the learner leaves the node. Per-node rather than per-block:
  // per-block dwell needs an IntersectionObserver over components this screen does not
  // own (they are instantiated by OpenUI's runtime), and §3.3 fixes the two thresholds
  // without fixing the unit. Documented as an interpretation, not as the spec.
  useEffect(
    () => () => {
      const startedAt = dwellStartRef.current
      dwellStartRef.current = null
      if (startedAt === null) return
      const ms = Date.now() - startedAt
      if (ms >= SLOW_MS) {
        events.record({ type: 'scroll_slow', element: elementForFormat(formatRef.current), ms })
      } else if (ms < FAST_MS) {
        events.record({ type: 'scroll_fast', element: elementForFormat(formatRef.current), ms })
      }
    },
    [events],
  )

  /**
   * `explain_click`, observed from the outside.
   *
   * `ClickableSurface` (B7) has no callback and this batch must not change it, so the
   * click is counted here on the way up — using the surface's own
   * `NO_EXPLAIN_SELECTOR`, so a click on a button or a quiz option is not counted as a
   * term either. Same hit test, one source of truth.
   */
  const onSurfaceClick = useCallback(
    (event: MouseEvent<HTMLDivElement>) => {
      const target = event.target as HTMLElement
      if (target.closest(NO_EXPLAIN_SELECTOR)) return
      if (!target.closest('.entity')) return
      events.record({ type: 'explain_click', element: elementForFormat(formatRef.current) })
    },
    [events],
  )

  // --- prefetch next node (fire-and-forget) ------------------------------------
  //
  // When the current node's render is served, pre-render the next unlocked node
  // so the learner does not wait when they navigate forward. The backend is
  // idempotent: if the render already exists or is in-flight, it returns
  // immediately. One fire per node visit, tracked by ref.
  // Sliding window: pre-render the next 3 nodes ahead of the current position.
  // As the learner advances, the window slides forward.
  const prefetchedRef = useRef<string | null>(null)

  useEffect(() => {
    if (!served || !node) return
    const ahead = ordered
      .filter((n) => n.position > node.position)
      .slice(0, 3)
    if (ahead.length === 0) return
    const key = ahead.map(n => n.id).join(',')
    if (prefetchedRef.current === key) return
    prefetchedRef.current = key
    for (const n of ahead) {
      void post(`/nodes/${n.id}/render`, { force: false }).catch(() => undefined)
    }
  }, [served, ordered, node])

  // --- slide panels -----------------------------------------------------------

  const togglePanel = useCallback((panel: PanelType) => {
    setActivePanel((prev) => (prev === panel ? null : panel))
  }, [])

  // --- frame ------------------------------------------------------------------

  const openingLine = openingLineFor(profile, intl)
  const { pathname } = useLocation()
  // Derive base from current URL so links work for both /empleado/curso/:id
  // and /admin/probar-curso/:id
  const backToCourse = pathname.replace(/\/nodo\/[^/]+$/, '')

  if (nodes.isLoading) {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <div className="h-6 w-1/3 rounded bg-bg-muted" />
          <ProgressBar value={0} variant="auto" size="lg" />
        </div>
        <Card>
          <NodeSkeleton />
        </Card>
      </div>
    )
  }

  if (nodes.isError && isNodeSurfaceDisabled(nodes.error)) {
    return (
      <EmptyState
        title={intl.formatMessage({ id: 'node.notNodeBased' })}
        description={intl.formatMessage({ id: 'node.notNodeBasedDesc' })}
        action={{ label: intl.formatMessage({ id: 'node.backToCourse' }), onClick: () => navigate(backToCourse) }}
      />
    )
  }

  if (!node) {
    return (
      <EmptyState
        title={intl.formatMessage({ id: 'node.notFound' })}
        description={intl.formatMessage({ id: 'node.notFoundDesc' })}
        action={{ label: intl.formatMessage({ id: 'node.backToCourse' }), onClick: () => navigate(backToCourse) }}
      />
    )
  }

  const notReviewed = isNodeNotReviewed(render.error) || isNodeNotReviewed(requestRender.error)
  const shownProgram = served?.program ?? null
  const shownFormat = served?.ui_format ?? null

  const arriving = !reduceMotion

  /**
   * Only the *first* program releases the reserved height, and only that one should
   * animate it back.
   */
  const fromSkeleton = !programShownBefore.current

  const shownKey = served?.render_id ?? 'none'

  function handleBack() {
    clearMorph()
    navigate(backToCourse, { state: { fromNode: true } })
  }

  return (
    <div className="flex flex-col flex-1 min-h-0 bg-bg overflow-hidden">

      {/* Top bar — X + title, same height as sidebar icons row */}
      <div className="shrink-0 flex items-center gap-3 h-12 px-6 border-b border-border" data-no-explain="">
        <button
          type="button"
          onClick={handleBack}
          className="p-1.5 text-text-muted hover:text-text transition-colors"
          aria-label={intl.formatMessage({ id: 'panel.close' })}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
        <span className="text-sm font-medium text-text flex-1 truncate">
          {node.title}
        </span>
      </div>

      {/* Main area — flex row for content + spider + sidebar + panel */}
      <div className="flex-1 flex min-h-0 relative overflow-hidden">
        {/* Lesson content — stays in place when panel opens */}
        <div className="flex-1 min-h-0 flex flex-col">
          <div className="flex-1 min-h-0 flex flex-col overflow-y-auto">
            {/* Lesson content */}
            <div className="flex-1 min-h-0 flex flex-col px-6 py-6 max-w-2xl w-full mx-auto">
              {notReviewed ? (
                <div className="space-y-2">
                  <p className="text-sm font-medium text-text">{intl.formatMessage({ id: 'node.pendingReview' })}</p>
                  <p className="text-sm text-text-secondary">
                    {intl.formatMessage({ id: 'node.pendingReviewDesc' })}
                  </p>
                </div>
              ) : phase === 'mastered' ? (
                <div className="space-y-3" role="status">
                  <p className="text-base font-medium text-text">{intl.formatMessage({ id: 'node.mastered' })}</p>
                  <p className="text-sm text-text-secondary">
                    {intl.formatMessage({ id: 'node.masteredDesc' })}
                  </p>
                  {node.summary && <p className="text-sm text-text-secondary">{node.summary}</p>}
                </div>
              ) : streamFailure && !shownProgram ? (
                <div className="space-y-2">
                  <p className="text-sm font-medium text-text">{streamFailure}</p>
                  <p className="text-sm text-text-secondary">
                    {node.summary ?? intl.formatMessage({ id: 'node.renderFailedFallback' })}
                  </p>
                </div>
              ) : (
                <div className="flex-1 min-h-0 flex flex-col">
                  <AnimatePresence mode="wait">
                    {shownProgram ? (
                      <motion.div
                        key="content"
                        className="flex-1 min-h-0 flex flex-col"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: duration.normal, ease: ease.base }}
                      >
                        {openingLine && (
                          <p className="text-base text-text mb-4 shrink-0" data-testid="opening-line">
                            {openingLine}
                          </p>
                        )}
                        <motion.div
                          key={shownKey}
                          onClick={onSurfaceClick}
                          className="flex-1 min-h-0 flex flex-col"
                          initial={arriving && fromSkeleton ? { minHeight: RESERVED_CONTENT_PX } : false}
                          animate={{ minHeight: 0 }}
                          transition={transition.resize}
                        >
                          <ClickableSurface nodeId={node.id} className="flex-1 min-h-0 flex flex-col">
                            <courseIntroContext.Provider value={courseIntro}>
                            <nextNodeContext.Provider value={nextNode ? { navigate: () => navigate(`${backToCourse}/nodo/${nextNode.id}`), title: nextNode.title } : null}>
                            <coursePositionContext.Provider value={{ nodeCount: ordered.length, currentNodeIndex: index }}>
                            <stepperContext.Provider value={true}>
                              <UiSpecRenderer
                                program={shownProgram}
                                nodeId={node.id}
                                renderId={served?.render_id}
                                format={shownFormat ?? undefined}
                                arriving={arriving}
                                recordEvent={events.record}
                              />
                            </stepperContext.Provider>
                            </coursePositionContext.Provider>
                            </nextNodeContext.Provider>
                            </courseIntroContext.Provider>
                          </ClickableSurface>
                        </motion.div>
                      </motion.div>
                    ) : (
                      <motion.div
                        key="intro"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: duration.normal, ease: ease.base }}
                        className="space-y-6"
                        data-testid="node-intro"
                      >
                        {openingLine && (
                          <p className="text-base text-text-secondary leading-relaxed">
                            {openingLine}
                          </p>
                        )}
                        <div>
                          <h3 className="text-lg font-semibold text-text mb-3">
                            {node.title}
                          </h3>
                          {node.summary && (
                            <p className="text-base text-text leading-relaxed">
                              {node.summary}
                            </p>
                          )}
                        </div>
                        <div className="bg-bg-subtle rounded-lg p-4 space-y-3">
                          <div className="flex items-center justify-between text-sm">
                            <span className="text-text-muted">
                              {intl.formatMessage({ id: 'node.counter' }, { current: index + 1, total: ordered.length })}
                              {node.estimated_minutes ? ` · ${node.estimated_minutes} min` : ''}
                            </span>
                            {node.mastery > 0 && (
                              <span className="text-text-secondary font-medium">
                                {intl.formatMessage({ id: 'node.mastery' }, { pct: Math.round(node.mastery * 100) })}
                              </span>
                            )}
                          </div>
                          {previousNode && previousNode.state === 'mastered' && (
                            <p className="text-sm text-text-secondary">
                              {intl.formatMessage({ id: 'node.previousMastered' }, { title: previousNode.title })}
                            </p>
                          )}
                          {node.mastery > 0 && (
                            <ProgressBar
                              value={Math.round(node.mastery * 100)}
                              variant="auto"
                              size="sm"
                            />
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Spider — floats over content, fades out when any panel opens */}
        <AnimatePresence>
          {served && !activePanel && (
            <motion.div
              key="spider"
              className="hidden md:block absolute right-16 top-0 z-10"
              initial={{ opacity: 0, y: -20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ type: 'spring', stiffness: 300, damping: 25 }}
            >
              <div className="flex flex-col items-center">
                {/* Thread from top */}
                <div className="w-px bg-border" style={{ height: 48 }} />
                {/* Spider — clickable, opens chat */}
                <motion.button
                  type="button"
                  onClick={() => togglePanel('chat')}
                  className="w-10 h-10 cursor-pointer"
                  whileHover={{ scale: 1.1, y: 2 }}
                  whileTap={{ scale: 0.95 }}
                  transition={{ type: 'spring', stiffness: 400, damping: 20 }}
                  aria-label={intl.formatMessage({ id: 'panel.chat' })}
                >
                  <img src="/spider.svg" alt="" className="w-full h-full" />
                </motion.button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Right sidebar — width animated directly (no layoutId/scale = no distortion) */}
        <motion.div
          animate={{ width: activePanel ? 400 : 48 }}
          transition={{ type: 'spring', stiffness: 200, damping: 28 }}
          className="hidden md:flex shrink-0 flex-col border-l border-border overflow-hidden"
          data-no-explain=""
        >
          {activePanel ? (
            <motion.div
              key={activePanel}
              className="flex-1 flex flex-col min-h-0"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.3, ease: [0.38, 0.49, 0, 1], delay: 0.25 }}
            >
              {/* Panel header */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
                <span className="font-medium text-sm text-text">
                  {intl.formatMessage({ id: PANEL_TITLE_KEY[activePanel] })}
                </span>
                <button
                  type="button"
                  onClick={() => setActivePanel(null)}
                  className="p-1.5 text-text-muted hover:text-text transition-colors"
                  aria-label={intl.formatMessage({ id: 'panel.close' })}
                >
                  <CloseIcon />
                </button>
              </div>
              {/* Panel content — chat manages its own scroll; others use the wrapper's */}
              <div className={`flex-1 min-h-0 p-4 ${activePanel === 'chat' ? 'flex flex-col' : 'overflow-y-auto'}`}>
                {activePanel === 'map' && nodes.data && (
                  <NodeList data={nodes.data} />
                )}
                {activePanel === 'chat' && (
                  <NodeChat
                    nodeTitle={node?.title ?? undefined}
                    nodeSummary={node?.summary ?? undefined}
                  />
                )}
                {activePanel === 'config' && <ConfigPanel />}
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="icons"
              className="flex-1 flex flex-col items-center justify-center gap-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.25, ease: [0.38, 0.49, 0, 1], delay: 0.2 }}
            >
              <button
                type="button"
                onClick={() => togglePanel('map')}
                className="p-2 rounded-md transition-colors hover:bg-bg-muted"
                aria-label={intl.formatMessage({ id: 'panel.map' })}
              >
                <MapIcon active={false} />
              </button>
              <button
                type="button"
                onClick={() => togglePanel('chat')}
                className="p-2 rounded-md transition-colors hover:bg-bg-muted"
                aria-label={intl.formatMessage({ id: 'panel.chat' })}
              >
                <ChatIcon active={false} />
              </button>
              <button
                type="button"
                onClick={() => togglePanel('config')}
                className="p-2 rounded-md transition-colors hover:bg-bg-muted"
                aria-label={intl.formatMessage({ id: 'panel.config' })}
              >
                <ConfigIcon active={false} />
              </button>
            </motion.div>
          )}
        </motion.div>
      </div>

      {/* Bottom icon bar — mobile only */}
      <div className="flex md:hidden shrink-0 justify-center gap-6 py-2 border-t border-border" data-no-explain="">
        <button
          type="button"
          onClick={() => togglePanel('map')}
          className={`p-2 rounded-md transition-colors ${activePanel === 'map' ? 'bg-primary-subtle' : 'hover:bg-bg-muted'}`}
          aria-label={intl.formatMessage({ id: 'panel.map' })}
        >
          <MapIcon active={activePanel === 'map'} />
        </button>
        <button
          type="button"
          onClick={() => togglePanel('chat')}
          className={`p-2 rounded-md transition-colors ${activePanel === 'chat' ? 'bg-primary-subtle' : 'hover:bg-bg-muted'}`}
          aria-label={intl.formatMessage({ id: 'panel.chat' })}
        >
          <ChatIcon active={activePanel === 'chat'} />
        </button>
        <button
          type="button"
          onClick={() => togglePanel('config')}
          className={`p-2 rounded-md transition-colors ${activePanel === 'config' ? 'bg-primary-subtle' : 'hover:bg-bg-muted'}`}
          aria-label={intl.formatMessage({ id: 'panel.config' })}
        >
          <ConfigIcon active={activePanel === 'config'} />
        </button>
      </div>
    </div>
  )
}
