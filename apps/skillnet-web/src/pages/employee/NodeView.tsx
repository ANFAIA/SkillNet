import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import type { MouseEvent } from 'react'
import { useCourse } from '../../api/courses'
import { Card, EmptyState, ProgressBar } from '../../components/ui'
import { ClickableSurface, NO_EXPLAIN_SELECTOR } from '../../components/courses/ClickableSurface'
import { UiSpecRenderer } from '../../components/courses/UiSpecRenderer'
import { stepperContext } from '../../components/courses/blocks/StepperContext'
import { LessonBuddy } from '../../components/courses/blocks/LessonBuddy'
import { NodeSkeleton, RESERVED_CONTENT_PX } from '../../components/courses/NodeSkeleton'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { transition, duration, ease } from '../../lib/motion'
import { useLearnerProfile } from '../../api/onboarding'
import { post } from '../../api/client'
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

/** Deterministic "esto te sirve para X" by `goal` value (§6.2 Q2 options). */
const GOAL_LINES: Record<string, string> = {
  onboarding: 'Esto te sirve para ponerte al dia en tu puesto.',
  specific_gap: 'Esto te sirve para dominar lo que viniste a resolver.',
  assigned: 'Esto te sirve para completar la formacion que te han asignado.',
}

function openingLineFor(profile: LearnerProfileRead | null | undefined): string | null {
  const goal = profile?.goal?.trim()
  if (!goal) return null
  const canned = GOAL_LINES[goal]
  if (canned) return canned
  // "Otro" is free text the learner wrote about themselves. It is echoed, never sent to
  // the model, and never used as anything but this sentence.
  return `Esto te sirve para: ${goal}`
}

/** Dwell under this reads as `scroll_fast`; over `SLOW_MS`, as `scroll_slow` (§3.3). */
const FAST_MS = 1000
const SLOW_MS = 3000

type Phase = 'content' | 'mastered'

export function NodeView() {
  const { id: courseId, nodeId } = useParams<{ id: string; nodeId: string }>()
  const navigate = useNavigate()

  const nodes = useCourseNodes(courseId)
  // Course title used by the sliding-window pre-render; kept for that.
  useCourse(courseId)
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
        setStreamFailure('No se pudo preparar esta leccion.')
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

  // --- frame ------------------------------------------------------------------

  const openingLine = openingLineFor(profile)
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
        title="Este curso no funciona por nodos"
        description="Abrelo desde la lista de cursos para verlo en su formato habitual."
        action={{ label: 'Volver al curso', onClick: () => navigate(backToCourse) }}
      />
    )
  }

  if (!node) {
    return (
      <EmptyState
        title="Nodo no encontrado"
        description="Puede que se haya archivado o que el curso haya cambiado de esquema."
        action={{ label: 'Volver al curso', onClick: () => navigate(backToCourse) }}
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

  return createPortal(
    <motion.div
      className="fixed inset-0 z-[200] bg-bg flex flex-col"
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: duration.medium, ease: [...ease.base] }}
    >
      {/* Minimal top bar — just close + title + progress dots */}
      <div className="shrink-0 flex items-center gap-3 px-6 py-4" data-no-explain="">
        <button
          type="button"
          onClick={() => navigate(backToCourse)}
          className="p-1.5 text-text-muted hover:text-text transition-colors"
          aria-label="Volver al curso"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        <span className="text-sm font-medium text-text flex-1 truncate">{node.title}</span>
      </div>

      {/* Spider buddy — hangs from top-right, outside the content column */}
      {served && (
        <div className="absolute top-14 right-[max(1rem,calc(50%-22rem))]" style={{ zIndex: 10 }}>
          <LessonBuddy
            nodeTitle={node?.title ?? undefined}
            nodeSummary={node?.summary ?? undefined}
            stepIndex={0}
            totalSteps={1}
          />
        </div>
      )}

      {/* Lesson content — fills the rest */}
      <div className="flex-1 min-h-0 flex flex-col px-6 pb-6 max-w-2xl mx-auto w-full">
        {notReviewed ? (
          <div className="space-y-2">
            <p className="text-sm font-medium text-text">Este nodo esta pendiente de revision</p>
            <p className="text-sm text-text-secondary">
              Una persona responsable tiene que revisarlo antes de que se pueda estudiar. No es un
              error temporal: volver a intentarlo no lo desbloquea.
            </p>
          </div>
        ) : phase === 'mastered' ? (
          <div className="space-y-3" role="status">
            <p className="text-base font-medium text-text">Ya dominas este nodo</p>
            <p className="text-sm text-text-secondary">
              Tus respuestas muestran que ya lo sabes, asi que no te hacemos leerlo. Puedes seguir
              con el siguiente.
            </p>
            {node.summary && <p className="text-sm text-text-secondary">{node.summary}</p>}
          </div>
        ) : streamFailure && !shownProgram ? (
          <div className="space-y-2">
            <p className="text-sm font-medium text-text">{streamFailure}</p>
            <p className="text-sm text-text-secondary">
              {node.summary ?? 'Vuelve a intentarlo mas tarde o avisa a la persona responsable.'}
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
                  {/* Opening line — feels like the start of a lesson */}
                  {openingLine && (
                    <p className="text-base text-text-secondary leading-relaxed">
                      {openingLine}
                    </p>
                  )}

                  {/* Topic overview — the actual educational content */}
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

                  {/* Context from the course — where this fits */}
                  <div className="bg-bg-subtle rounded-lg p-4 space-y-3">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-text-muted">
                        Nodo {index + 1} de {ordered.length}
                        {node.estimated_minutes ? ` · ${node.estimated_minutes} min` : ''}
                      </span>
                      {node.mastery > 0 && (
                        <span className="text-text-secondary font-medium">
                          Dominio: {Math.round(node.mastery * 100)}%
                        </span>
                      )}
                    </div>

                    {/* Prereq context — what they already know */}
                    {previousNode && previousNode.state === 'mastered' && (
                      <p className="text-sm text-text-secondary">
                        Ya dominas <span className="font-medium text-text">{previousNode.title}</span>. Esto es el siguiente paso.
                      </p>
                    )}

                    {/* Mastery bar only if they have progress */}
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
    </motion.div>,
    document.body,
  )
}
