import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import type { MouseEvent } from 'react'
import { Button, Card, EmptyState, ProgressBar } from '../../components/ui'
import { ClickableSurface, NO_EXPLAIN_SELECTOR } from '../../components/courses/ClickableSurface'
import { UiSpecRenderer } from '../../components/courses/UiSpecRenderer'
import { NodeSkeleton, RESERVED_CONTENT_PX } from '../../components/courses/NodeSkeleton'
import { NodeFeedback } from '../../components/courses/NodeFeedback'
import { ProbeRunner } from '../../components/courses/ProbeRunner'
import { RenderControls } from '../../components/courses/RenderControls'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { transition } from '../../lib/motion'
import { useLearnerProfile } from '../../api/onboarding'
import {
  elementForFormat,
  isNodeNotReviewed,
  isNodeSurfaceDisabled,
  isPendingRender,
  isServedRender,
  useCourseNodes,
  useNodeEvents,
  useNodeRender,
  useNodeRenderHistory,
  useNodeRenderStream,
  useRequestRender,
} from '../../api/nodes'
import type { LearnerProfileRead } from '../../api/onboarding'
import type { LearningNode } from '../../types'
import type { UiFormat } from '../../types/node-render'

/**
 * One node of a dynamic course — where the learner finally sees generation happen.
 *
 * ## The three things this screen is
 *
 * 1. **The productive wait** (§9.1). The pre-assessment is not a gate in front of the
 *    lesson, it *is* the loading screen: `ProbeRunner` asks item A, the server answers
 *    `render_hint: "prefetch"` as soon as mastery is out of reach, this component fires
 *    `POST /render` in the background, and by the time item B is answered the blocks are
 *    usually there. If the verdict comes out `mastered` the node is skipped and the
 *    server cancels the render it had started.
 * 2. **A stable frame** (§5.5). Title, progress and the previous/next buttons never move.
 *    `NodeSkeleton` reserves the content area so the footer does not jump when the
 *    program lands, and the content itself is the *pinned* render: answering an item or
 *    coming back tomorrow returns the same bytes. The only thing that changes it is the
 *    "Actualizar esta leccion" button in `RenderControls`.
 *
 *    The reservation is also *released* rather than dropped: `RESERVED_CONTENT_PX`
 *    animates to zero on the arriving content, so a lesson shorter than the skeleton
 *    settles instead of snapping the footer up under the learner's eyes. And the blocks
 *    themselves resolve in sequence (`arriving`, see `blocks/blockArrival.ts`) — but
 *    **only when the learner waited for them**. A pinned render served from cache paints
 *    on the first frame with no entrance at all, because a node re-opened tomorrow should
 *    feel like it never closed.
 * 3. **The deterministic opening line** (§6.2 Q2, §3.3). `goal` never travels to the LLM;
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

type Phase = 'probe' | 'content' | 'mastered'

interface HeldVersion {
  program: string
  format: UiFormat | null
}

export function NodeView() {
  const { id: courseId, nodeId } = useParams<{ id: string; nodeId: string }>()
  const navigate = useNavigate()

  const nodes = useCourseNodes(courseId)
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

  // `not_started`/`probing` still owe a probe; anything past it goes straight to content
  // (§7.3 transitions 1-5 all happen before the lesson exists).
  const initialPhase: Phase | null = node
    ? node.state === 'not_started' || node.state === 'probing'
      ? 'probe'
      : 'content'
    : null

  const [phase, setPhase] = useState<Phase | null>(null)
  useEffect(() => {
    setPhase((prev) => prev ?? initialPhase)
  }, [initialPhase])

  const [adapted, setAdapted] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [viewingRenderId, setViewingRenderId] = useState<string | null>(null)
  const [held, setHeld] = useState<Record<string, HeldVersion>>({})
  const [streamFailure, setStreamFailure] = useState<string | null>(null)

  const requestedRef = useRef(false)
  /** Set once any lesson has been on screen — see `fromSkeleton` further down. */
  const programShownBefore = useRef(false)
  const viewedRenderRef = useRef<string | null>(null)
  const dwellStartRef = useRef<number | null>(null)
  const formatRef = useRef<UiFormat | null>(null)

  const render = useNodeRender(nodeId, { enabled: phase === 'content' })
  const history = useNodeRenderHistory(nodeId, { enabled: phase === 'content' })
  const requestRender = useRequestRender(nodeId)

  const served = isServedRender(render.data) ? render.data : null
  const pending = isPendingRender(render.data) ? render.data : null

  const reduceMotion = useReducedMotion()

  const stream = useNodeRenderStream({
    onSettled: ({ reason, fallbackAvailable }) => {
      setRefreshing(false)
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
      void history.refetch()
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
    (options: { force?: boolean } = {}) => {
      if (!nodeId) return
      requestedRef.current = true
      requestRender.mutate(
        { force: options.force ?? false },
        {
          onSuccess: (accepted) => {
            if (!accepted.request_id) {
              setRefreshing(false)
              void render.refetch()
              void history.refetch()
              return
            }
            void stream.start(nodeId, accepted.request_id)
          },
          onError: () => setRefreshing(false),
        },
      )
    },
    [nodeId, requestRender, render, history, stream],
  )

  // The prefetch of §9.1: fired by the probe, not by the server.
  const onPrefetch = useCallback(() => {
    if (requestedRef.current) return
    startRender()
  }, [startRender])

  const onVerdict = useCallback(
    (verdict: 'mastered' | 'learning') => {
      if (verdict === 'mastered') {
        setPhase('mastered')
        return
      }
      setPhase('content')
    },
    [],
  )

  // In the content phase, make sure *something* is on its way: either the prefetch
  // already started it, or another tab owns a request we can listen to, or nothing has
  // been asked for yet.
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

  // --- controls ---------------------------------------------------------------

  const onRefresh = useCallback(() => {
    if (!served) return
    // Hold the program that is about to be replaced: it is the "version anterior" the
    // learner can go back to (there is no endpoint that serves a render by id).
    setHeld((prev) => ({
      ...prev,
      [served.render_id]: { program: served.program, format: served.ui_format },
    }))
    setViewingRenderId(null)
    setRefreshing(true)
    setAdapted(true)
    setStreamFailure(null)
    stream.reset()
    requestedRef.current = false
    startRender({ force: true })
  }, [served, stream, startRender])

  // --- frame ------------------------------------------------------------------

  const openingLine = openingLineFor(profile)
  const backToCourse = `/empleado/curso/${courseId}`

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
  const viewingHeld = viewingRenderId ? held[viewingRenderId] : undefined
  const shownProgram = viewingHeld?.program ?? served?.program ?? null
  const shownFormat = viewingHeld?.format ?? served?.ui_format ?? null

  /**
   * A program that is being shown for the first time arrives; a held previous version
   * does not. Going back to something you already read is not an event, and animating
   * it would say it was.
   *
   * The lesson always replaces an empty box — `GET /render` is a request even on a
   * cache hit, so the skeleton is on screen first in every path — which is why there
   * is no "was it instant?" test here. What differs is only how long the box was empty.
   */
  const arriving = !viewingHeld && !reduceMotion

  /**
   * ...but only the *first* program released the reserved height, and only that one
   * should animate it back. A regeneration replaces a lesson that was already sitting
   * at its natural height: re-reserving 22 rem there would grow the card and then
   * shrink it, which is the jump this whole mechanism exists to remove.
   */
  const fromSkeleton = !programShownBefore.current

  /**
   * The subtree remounts when the program does. Without it the CSS entrance would not
   * re-run on a regeneration (a CSS animation fires on element creation, and the vendor
   * runtime reuses the same DOM node when only the text changed) — and keeping a
   * replaced item's local answer state alive is worse than losing it.
   */
  const shownKey = viewingHeld ? `held:${viewingRenderId}` : (served?.render_id ?? 'none')

  return (
    <div className="space-y-6">
      {/* Zona congelada (§5.5): nothing in this header moves while the node is open. */}
      <div data-no-explain="">
        <Link
          to={backToCourse}
          className="text-xs font-medium text-primary hover:text-primary/80 transition-colors"
        >
          {'←'} Volver al curso
        </Link>
        <div className="mt-2 flex items-center gap-3 min-w-0">
          <span className="w-3 h-3 rounded-full shrink-0 bg-primary" />
          <h2 className="text-xl font-semibold text-text truncate">{node.title}</h2>
        </div>
        <div className="mt-2">
          <ProgressBar value={Math.round(node.mastery * 100)} variant="auto" size="lg" showLabel />
        </div>
        <p className="mt-1 text-xs text-text-muted tabular-nums">
          Nodo {index + 1} de {ordered.length} · {node.estimated_minutes} min
        </p>
      </div>

      <Card>
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
        ) : phase === 'probe' ? (
          <ProbeRunner
            nodeId={node.id}
            node={node}
            openingLine={openingLine}
            onPrefetch={onPrefetch}
            onVerdict={onVerdict}
          />
        ) : streamFailure && !shownProgram ? (
          <div className="space-y-2">
            <p className="text-sm font-medium text-text">{streamFailure}</p>
            <p className="text-sm text-text-secondary">
              {node.summary ?? 'Vuelve a intentarlo mas tarde o avisa a la persona responsable.'}
            </p>
          </div>
        ) : (
          <>
            {openingLine && (
              <p className="text-base text-text mb-4" data-testid="opening-line">
                {openingLine}
              </p>
            )}

            {shownProgram ? (
              // `ClickableSurface` keeps wrapping the tree (§8.5): a click on prose
              // explains, a click on a button or a quiz option does not. The hit test
              // lives in the surface; the wrapper only counts the event.
              <motion.div
                key={shownKey}
                onClick={onSurfaceClick}
                className="min-w-0"
                // Hands the skeleton's reserved height back over half a second instead
                // of in one frame. `false` means "no entrance": the box is simply the
                // size of its content from the start.
                initial={arriving && fromSkeleton ? { minHeight: RESERVED_CONTENT_PX } : false}
                animate={{ minHeight: 0 }}
                transition={transition.resize}
              >
                <ClickableSurface nodeId={node.id} className="min-w-0">
                  <UiSpecRenderer
                    program={shownProgram}
                    nodeId={node.id}
                    // A held previous version is read-only: its items belong to a render
                    // that is no longer pinned, so an answer against it would be graded
                    // against a screen the learner is not looking at.
                    renderId={viewingHeld ? undefined : served?.render_id}
                    format={shownFormat ?? undefined}
                    arriving={arriving}
                  />
                </ClickableSurface>
              </motion.div>
            ) : (
              <NodeSkeleton
                format={stream.format}
                message={stream.message}
                blocksReady={stream.blocks}
              />
            )}

            {served && (
              <RenderControls
                refreshing={refreshing}
                onRefresh={onRefresh}
                versions={history.data?.renders ?? []}
                activeRenderId={served.render_id}
                viewableRenderIds={Object.keys(held)}
                onViewVersion={setViewingRenderId}
                onViewCurrent={() => setViewingRenderId(null)}
                viewingPrevious={!!viewingHeld}
                adapted={adapted}
              />
            )}

            {served && !viewingHeld && <NodeFeedback nodeId={node.id} />}
          </>
        )}
      </Card>

      {/* Zona congelada: the two navigation buttons keep their place in every phase. */}
      <div className="flex items-center justify-between gap-3" data-no-explain="">
        <Button
          variant="secondary"
          size="sm"
          disabled={!previousNode}
          onClick={() =>
            previousNode && navigate(`/empleado/curso/${courseId}/nodo/${previousNode.id}`)
          }
        >
          Anterior
        </Button>
        {nextNode ? (
          <Button
            size="sm"
            disabled={nextNode.locked}
            onClick={() => navigate(`/empleado/curso/${courseId}/nodo/${nextNode.id}`)}
          >
            {nextNode.locked ? 'Siguiente bloqueado' : 'Siguiente'}
          </Button>
        ) : (
          <Button size="sm" variant="secondary" onClick={() => navigate(backToCourse)}>
            Volver al curso
          </Button>
        )}
      </div>
    </div>
  )
}
