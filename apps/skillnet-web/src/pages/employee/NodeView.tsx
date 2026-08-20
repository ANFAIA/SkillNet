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
import { stepperContext, coursePositionContext, nextNodeContext, courseIntroContext, stepperProgressContext, lessonFeedbackContext, courseFinishContext, episodePagerContext } from '../../components/courses/blocks/StepperContext'
import type { CourseIntro, StepperProgress, StepperProgressCallback } from '../../components/courses/blocks/StepperContext'
import { NodeChat } from '../../components/courses/NodeChat'
import { NodeSkeleton, RESERVED_CONTENT_PX } from '../../components/courses/NodeSkeleton'
import { MascotaCompanion } from '../../components/mascota'
import { Mascota } from '../../features/mascot'
import { ResultGlow } from '../../components/courses/feedback/ResultGlow'
import type { Resultado } from '../../components/courses/feedback/ResultGlow'
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

// ---------------------------------------------------------------------------
// The content column
// ---------------------------------------------------------------------------

/**
 * La columna de contenido, definida UNA vez.
 *
 * Estaba escrita en dos sitios con el mismo valor, que es justo la forma de que un dia
 * dejen de tenerlo: cambiar uno y olvidar el otro desalinea la pantalla sin que nada
 * falle. Con una sola constante ese desajuste no es representable.
 *
 * La cabecera NO la usa: va a ancho completo con el mismo `px-6`, para que la X siga
 * pegada al borde. Los puntos coinciden igual con el contenido porque `1fr auto 1fr` y
 * `mx-auto` se centran en el mismo eje.
 */
const CONTENT_COLUMN = 'w-full max-w-5xl mx-auto px-6'

// ---------------------------------------------------------------------------
// Course progress dots — one dot per node, active node stretches and fills
// ---------------------------------------------------------------------------

const morphSpring = { type: 'spring' as const, stiffness: 300, damping: 30 }
const DOT_SIZE = 8
const BAR_WIDTH = 40

function CourseProgress({
  nodeCount,
  currentNodeIndex,
  currentStep,
  totalSteps,
}: {
  nodeCount: number
  currentNodeIndex: number
  currentStep: number
  totalSteps: number
}) {
  const fillPct = totalSteps > 1 ? (currentStep / (totalSteps - 1)) * 100 : 0

  return (
    <div className="flex items-center justify-center gap-2">
      {Array.from({ length: nodeCount }, (_, i) => {
        const isActive = i === currentNodeIndex
        const isDone = i < currentNodeIndex

        return (
          <motion.div
            key={i}
            className="relative rounded-full overflow-hidden"
            layout
            transition={morphSpring}
            style={{
              width: isActive ? BAR_WIDTH : DOT_SIZE,
              height: DOT_SIZE,
              backgroundColor: isDone
                ? 'var(--color-primary)'
                : 'var(--color-border)',
            }}
          >
            {isActive && (
              <motion.div
                className="absolute inset-y-0 left-0 rounded-full"
                style={{ backgroundColor: 'var(--color-primary)' }}
                animate={{ width: `${fillPct}%` }}
                transition={{ duration: duration.normal, ease: [...ease.base] }}
              />
            )}
          </motion.div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------

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
  const mascotaEnabled = usePreferences((s) => s.mascotaEnabled)

  const clearMorph = useNodeMorph((s) => s.clear)
  /** Which slide panel is open, if any. */
  const [activePanel, setActivePanel] = useState<PanelType | null>(null)
  /** Step progress reported by StepperStack — drives the dots in the top bar. */
  const [stepProgress, setStepProgress] = useState<StepperProgress | null>(null)
  const reportStepProgress = useCallback<StepperProgressCallback>(
    (progress) => setStepProgress(progress),
    [],
  )

  // Feedback ambiental al responder: la luz del borde (ResultGlow) y la reaccion de
  // la mascota. Un bloque interactivo llama a `report`; aqui se traduce a una y otra.
  // `nonce` sube en cada reporte para re-disparar la animacion aunque el resultado
  // sea el mismo (fallar dos veces seguidas debe verse dos veces).
  const [glow, setGlow] = useState<{ resultado: Resultado; nonce: number; definitivo: boolean } | null>(null)
  const [mascotaFx, setMascotaFx] = useState<'celebrar' | 'ups' | null>(null)
  const fxTimer = useRef<number | null>(null)
  const reportResult = useCallback((resultado: Resultado, opts?: { definitivo?: boolean }) => {
    setGlow((prev) => ({ resultado, definitivo: opts?.definitivo ?? false, nonce: (prev?.nonce ?? 0) + 1 }))
    setMascotaFx(resultado === 'fallo' ? 'ups' : 'celebrar')
    if (fxTimer.current) window.clearTimeout(fxTimer.current)
    // La reaccion es un gesto, no un estado: la mascota vuelve a `idle` sola.
    fxTimer.current = window.setTimeout(() => setMascotaFx(null), 1800)
  }, [])
  useEffect(() => () => { if (fxTimer.current) window.clearTimeout(fxTimer.current) }, [])
  const lessonFeedback = useMemo(() => ({ report: reportResult }), [reportResult])

  // Pantalla de fin de curso: el CTA del ultimo nodo la dispara; se reinicia al
  // cambiar de nodo (por si se vuelve a entrar al curso).
  const [finished, setFinished] = useState(false)
  useEffect(() => { setFinished(false) }, [nodeId])
  const finishCourse = useCallback(() => setFinished(true), [])

  // Paginación del episodio multipantalla. NodeView es el dueño del índice de pantalla;
  // el StackBlock raíz solo informa del total y pinta la pantalla actual. Se reinicia por
  // nodo (más abajo, junto al resto de estado por-nodo).
  const [episodeScreen, setEpisodeScreen] = useState(0)
  const [episodeTotal, setEpisodeTotal] = useState(1)
  const episodePager = useMemo(
    () => ({ screen: episodeScreen, reportTotal: setEpisodeTotal }),
    [episodeScreen],
  )

  // Compuerta de arranque: la pantalla de intro es del aprendiz hasta que pulsa
  // "Empezar". Sin esto, la leccion aparecia sola en cuanto el render estaba listo,
  // sin poder quedarse ni avanzar a voluntad. Se reinicia por nodo (mas abajo).
  const [entered, setEntered] = useState(false)

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
  const wasPreparingRef = useRef(false)
  /**
   * Lo que hay EN PANTALLA: el nodo y su leccion, juntos.
   *
   * El parpadeo al cambiar de nodo venia de que la vista se derivaba de dos fuentes que
   * podian discrepar — la URL decia que nodo y la query decia que render — y al saltar,
   * la segunda se quedaba vacia un instante. Con un solo valor no hay hueco posible: la
   * pantalla no cambia hasta que hay una leccion nueva que poner, y cuando cambia lo
   * hace entera, cabecera incluida. Sin esto la cabecera anunciaba "Pantalla 4" sobre el
   * contenido de la 3 mientras durase la espera.
   */
  const [shown, setShown] = useState<{
    node: LearningNode
    program: string
    format: UiFormat | null
    shellMode: 'legacy_stepper' | 'episode'
    key: string
  } | null>(null)

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
    setStepProgress(null)
    setEntered(false)
    setEpisodeScreen(0)
    setEpisodeTotal(1)
    requestedRef.current = false
    wasPreparingRef.current = false
    programShownBefore.current = false
    viewedRenderRef.current = null
    dwellStartRef.current = null
    formatRef.current = null
    // prefetchedRef is defined later but initialized to null anyway
  }, [nodeId])

  const [isPreparing, setIsPreparing] = useState(false)
  const render = useNodeRender(nodeId, {
    enabled: phase === 'content',
    // Poll only while "Preparándose…", so the screen flips to the real episode by itself
    // once the node's knowledge pack lands and the server drops the fallback pin.
    refetchInterval: isPreparing ? 4000 : false,
  })
  const requestRender = useRequestRender(nodeId)

  const rawServed = isServedRender(render.data) ? render.data : null
  // A "preparing" fallback (knowledge pack not ready) is NOT a lesson and must never be
  // shown as content: keep it out of `served` so the intro stays on "Preparándose…" and
  // the poll above swaps in the real episode when it is ready — never a flat fallback.
  const served = rawServed && !rawServed.preparing ? rawServed : null

  useEffect(() => {
    setIsPreparing(!!(rawServed && rawServed.preparing))
  }, [rawServed])

  /**
   * Las dos unicas transiciones de `shown`, y no hay una tercera.
   *
   * Entra cuando hay leccion servida para el nodo pedido: el cambio es atomico, nodo y
   * programa a la vez. Sale cuando el nodo pedido falla, que es el agujero de sostener
   * la anterior sin condiciones — sin esto, un render que nunca llega deja al aprendiz
   * leyendo la pantalla anterior para siempre.
   */
  useEffect(() => {
    if (!served || !node) return
    setShown({
      node,
      program: served.program,
      format: served.ui_format,
      shellMode: served.shell_mode ?? 'legacy_stepper',
      key: served.render_id,
    })
  }, [served, node])

  useEffect(() => {
    if (streamFailure) setShown(null)
  }, [streamFailure])
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

  // Recover from "Preparándose…": while preparing we hold `requestedRef` set so the effect
  // above does not spin. When the pack lands the server drops the fallback pin, `isPreparing`
  // clears and `GET /render` has nothing pinned — re-arm one request so the episode is
  // generated with the now-ready pack instead of leaving the learner on the placeholder.
  useEffect(() => {
    if (phase !== 'content') return
    if (isPreparing) {
      wasPreparingRef.current = true
      requestedRef.current = true
      return
    }
    if (wasPreparingRef.current && !served && pending && !pending.request_id) {
      wasPreparingRef.current = false
      requestedRef.current = false
      startRender()
    }
  }, [phase, isPreparing, served, pending, startRender])

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
  // Sliding window: pre-render the next 4 nodes ahead of the current position.
  // As the learner advances, the window slides forward.
  const prefetchedRef = useRef<string | null>(null)

  useEffect(() => {
    if (!served || !node) return
    const ahead = ordered
      .filter((n) => n.position > node.position && !n.locked && n.state !== 'mastered')
      .slice(0, 4)
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

  // Click-outside to dismiss. While a panel is open, a mousedown anywhere outside the
  // sidebar (i.e. on the lesson content) closes it — the spider that reopens chat is
  // hidden whenever a panel is open, and the mobile bar is `md:hidden`, so neither
  // fights this on the surface it applies to.
  const sidebarRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!activePanel) return
    function onPointerDown(event: PointerEvent) {
      if (sidebarRef.current?.contains(event.target as Node)) return
      setActivePanel(null)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [activePanel])

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
  /**
   * La ultima leccion que estuvo en pantalla.
   *
   * Al cambiar de nodo, la query del render nuevo aun no tiene datos: `served` es `null`
   * y sin esto se caia a la pantalla de titulo. Ese hueco entre soltar lo viejo y recibir
   * lo nuevo es el parpadeo. Sosteniendo la anterior, cambiar de nodo se ve igual que
   * cambiar de paso dentro del nodo: el mismo `AnimatePresence` cruza de una a otra
   * cuando la nueva llega.
   */
  /**
   * La cabecera anuncia el nodo que el aprendiz esta VIENDO, no el que se ha pedido.
   * Mientras la leccion nueva se genera, el titulo, los puntos y el contador siguen
   * siendo los de la que sigue en pantalla. Cuando no hay ninguna —primera carga o
   * fallo— coinciden, porque `shown` es null y se cae al nodo de la URL.
   */
  const headerNode = shown?.node ?? node
  const headerIndex = ordered.findIndex((entry) => entry.id === headerNode.id)

  const shownProgram = shown?.program ?? null
  const shownFormat = shown?.format ?? null
  const shownShellMode = shown?.shellMode ?? 'legacy_stepper'

  const arriving = !reduceMotion

  /**
   * Only the *first* program releases the reserved height, and only that one should
   * animate it back.
   */
  const fromSkeleton = !programShownBefore.current

  const shownKey = shown?.key ?? 'none'

  function handleBack() {
    clearMorph()
    navigate(backToCourse, { state: { fromNode: true } })
  }

  return (
    <div className="flex flex-col flex-1 min-h-0 bg-bg overflow-hidden">

      {/* Main area — flex row for content + spider + sidebar + panel */}
      <div className="flex-1 flex min-h-0 relative overflow-hidden">
        {/* Lesson content — stays in place when panel opens */}
        <div className="flex-1 min-h-0 flex flex-col">
          {/*
            Cabecera: cerrar, titulo y puntos en UNA fila.
            Eran dos filas apiladas, asi que no habia ninguna linea que compartir — de
            ahi que la X quedase por encima de los puntos. Una rejilla de tres columnas
            `1fr auto 1fr` lo resuelve por estructura: `items-center` da la linea comun a
            los tres, y las dos columnas elasticas iguales dejan los puntos centrados sin
            depender de lo que ocupe el titulo. La fila sigue a ancho completo con `px-6`,
            asi que la X no se mueve de donde estaba.
          */}
          <div className="shrink-0 grid grid-cols-[1fr_auto_1fr] items-center gap-3 px-6 pt-4 pb-3" data-no-explain="">
            <div className="flex items-center gap-3 min-w-0">
              <button
                type="button"
                onClick={handleBack}
                className="shrink-0 p-1.5 text-text-muted hover:text-text transition-colors"
                aria-label={intl.formatMessage({ id: 'panel.close' })}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
              <span className="text-sm font-medium text-text truncate">
                {headerNode.title}
              </span>
            </div>
            <CourseProgress
              nodeCount={ordered.length}
              currentNodeIndex={headerIndex}
              currentStep={shownShellMode === 'episode' ? episodeScreen : (stepProgress?.currentStep ?? 0)}
              totalSteps={shownShellMode === 'episode' ? episodeTotal : (stepProgress?.totalSteps ?? 1)}
            />
            {/* Contrapeso de la tercera columna: sin el, los puntos se centran en el
                hueco que sobra a la derecha del titulo, no en la fila. */}
            <div aria-hidden="true" />
          </div>

          <div className="flex-1 min-h-0 flex flex-col overflow-y-auto" data-node-scroll-root="">
            {/* Lesson content */}
            {/*
              La leccion, centrada en los dos ejes.
              Horizontal: `mx-auto` sobre la columna. Vertical: `justify-center` en cada
              envoltorio hasta el contenido. No es redundante — un hijo que crece
              (`flex-1`, el caso del stepper) ignora `justify-center` y ocupa todo el
              alto, y uno que no crece (intro, dominado, fallo) queda centrado. La misma
              regla sirve para los dos sin tener que preguntar cual es.
            */}
            <div className={`flex-1 min-h-0 flex flex-col justify-center pb-6 ${CONTENT_COLUMN}`}>
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
                <div className="flex-1 min-h-0 flex flex-col justify-center">
                  <AnimatePresence mode="wait">
                    {shownProgram && entered ? (
                      <motion.div
                        key="content"
                        className="flex-1 min-h-0 flex flex-col justify-center"
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
                          // `overflow-hidden`: la leccion se desplaza DENTRO de su propia caja
                          // (StepperStack / EpisodeStack tienen su scroll interno). Recortar
                          // aqui impide que un ejercicio alto pinte por encima del pie del
                          // episodio —un hermano `shrink-0` justo debajo—, que era como el
                          // boton de avanzar quedaba tapado en pantallas con contenido alto.
                          className="flex-1 min-h-0 flex flex-col justify-center overflow-hidden"
                          initial={arriving && fromSkeleton ? { minHeight: RESERVED_CONTENT_PX } : false}
                          animate={{ minHeight: 0 }}
                          transition={transition.resize}
                        >
                          <ClickableSurface
                            nodeId={node.id}
                            className="flex-1 min-h-0 flex flex-col justify-center"
                          >
                            <div
                              className="flex-1 min-h-0 flex flex-col justify-center"
                              data-episode-shell={shownShellMode === 'episode' ? '' : undefined}
                              data-shell-mode={shownShellMode}
                            >
                              <stepperProgressContext.Provider value={reportStepProgress}>
                                <courseIntroContext.Provider value={courseIntro}>
                                  <nextNodeContext.Provider value={nextNode ? { navigate: () => navigate(`${backToCourse}/nodo/${nextNode.id}`), title: nextNode.title } : null}>
                                    <coursePositionContext.Provider value={{ nodeCount: ordered.length, currentNodeIndex: headerIndex }}>
                                      <stepperContext.Provider value={shownShellMode === 'legacy_stepper'}>
                                        <lessonFeedbackContext.Provider value={lessonFeedback}>
                                          <courseFinishContext.Provider value={finishCourse}>
                                            <episodePagerContext.Provider value={shownShellMode === 'episode' ? episodePager : null}>
                                              <UiSpecRenderer
                                                program={shownProgram}
                                                nodeId={node.id}
                                                renderId={served?.render_id}
                                                format={shownFormat ?? undefined}
                                                arriving={arriving}
                                                recordEvent={events.record}
                                              />
                                            </episodePagerContext.Provider>
                                          </courseFinishContext.Provider>
                                        </lessonFeedbackContext.Provider>
                                      </stepperContext.Provider>
                                    </coursePositionContext.Provider>
                                  </nextNodeContext.Provider>
                                </courseIntroContext.Provider>
                              </stepperProgressContext.Provider>
                            </div>
                          </ClickableSurface>
                        </motion.div>
                        {/*
                          Pie del episodio. Un episodio es UNA pantalla: se ve entero de
                          golpe y no tiene el stepper que en modo legacy pinta las flechas
                          de avance. Sin este pie, un episodio `support_only` (solo aviso +
                          checklist + resumen, sin ejercicio que resolver) no ofrece NINGUNA
                          forma de salir: el aprendiz queda atrapado. El pie da el mismo
                          avance que daban las flechas del stepper —anterior / siguiente
                          nodo, y "terminar curso" en el ultimo— reutilizando exactamente
                          las mismas rutas de navegacion y `finishCourse` que alimentan
                          nextNodeContext / courseFinishContext. Siempre visible en episodio,
                          asi que un episodio nunca es un callejon sin salida, tenga o no
                          ejercicio interactivo dentro.
                        */}
                        {shownShellMode === 'episode' && (() => {
                          // "Siguiente" avanza de PANTALLA dentro del nodo; en la última
                          // avanza de NODO (o termina el curso). "Anterior" retrocede de
                          // pantalla, y en la primera va al nodo anterior. Avanzar nunca se
                          // bloquea: el resultado ya se registró en el bloque interactivo.
                          const isLastScreen = episodeScreen >= episodeTotal - 1
                          const isFirstScreen = episodeScreen <= 0
                          const goPrev = () => {
                            if (!isFirstScreen) setEpisodeScreen((s) => Math.max(0, s - 1))
                            else if (previousNode) navigate(`${backToCourse}/nodo/${previousNode.id}`)
                          }
                          const goNext = () => {
                            if (!isLastScreen) setEpisodeScreen((s) => Math.min(episodeTotal - 1, s + 1))
                            else if (nextNode) navigate(`${backToCourse}/nodo/${nextNode.id}`)
                            else finishCourse()
                          }
                          const showPrev = !isFirstScreen || Boolean(previousNode)
                          const nextLabel = !isLastScreen
                            ? intl.formatMessage({ id: 'node.nextScreen' })
                            : nextNode
                              ? intl.formatMessage({ id: 'node.nextNode' }, { title: nextNode.title })
                              : intl.formatMessage({ id: 'node.finishCourse' })
                          return (
                            <div
                              className="shrink-0 flex items-center gap-3 pt-6"
                              data-episode-footer=""
                              data-episode-screen={episodeScreen}
                              data-episode-total={episodeTotal}
                            >
                              {showPrev && (
                                <button
                                  type="button"
                                  onClick={goPrev}
                                  className="shrink-0 text-sm font-medium text-text-secondary hover:text-text px-4 py-3 rounded-md transition-colors"
                                >
                                  {isFirstScreen
                                    ? intl.formatMessage({ id: 'node.previousNode' })
                                    : intl.formatMessage({ id: 'node.previousScreen' })}
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={goNext}
                                className={`flex-1 text-white text-sm font-medium px-4 py-3 rounded-md transition-colors ${isLastScreen && !nextNode ? 'bg-accent hover:bg-accent-hover' : 'bg-primary hover:bg-primary-hover'}`}
                              >
                                {nextLabel}
                              </button>
                            </div>
                          )
                        })()}
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
                        {/*
                          La compuerta de arranque. Mientras el render se genera es un
                          boton inhabilitado ("Preparando...") que dice que hay algo en
                          camino; cuando la leccion esta lista pasa a "Empezar" y montar
                          el stepper es una decision del aprendiz, no un salto automatico.
                        */}
                        <button
                          type="button"
                          onClick={() => setEntered(true)}
                          disabled={!shownProgram}
                          className="bg-primary hover:bg-primary-hover text-white text-sm font-medium px-5 py-3 rounded-md transition-colors disabled:opacity-50 disabled:pointer-events-none"
                        >
                          {shownProgram
                            ? intl.formatMessage({ id: 'node.start' })
                            : intl.formatMessage({ id: 'node.preparing' })}
                        </button>
                        {isPreparing && !shownProgram && (
                          <p className="text-xs text-text-muted mt-2" role="status">
                            {intl.formatMessage({ id: 'node.preparingBackground' })}
                          </p>
                        )}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Mascota — compañera abajo a la izquierda, fuera de la columna de lectura
            centrada. Se atenúa cuando se abre un panel. Reacciona al resultado
            (celebrar/ups), abre el chat al pulsarla y, al entrar en cada nodo,
            saluda con una burbuja contextual que ofrece leer la introducción en voz
            alta (estilo "Koji" de Brilliant). Antes colgaba de un hilo arriba a la
            derecha; abajo se posa (sin hilo) y es más grande. */}
        <AnimatePresence>
          {served && !activePanel && mascotaEnabled && (
            <motion.div
              key="spider"
              className="absolute left-4 bottom-6 md:left-12 md:bottom-8 z-10"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 20 }}
              transition={{ type: 'spring', stiffness: 300, damping: 25 }}
            >
              <MascotaCompanion
                nodeId={node.id}
                title={node.title}
                summary={node.summary}
                // In a paginated episode the mascot reads the CURRENT screen's own
                // text; pass the program + screen index so it speaks per page. The
                // legacy shell owns its step internally, so it keeps the node summary.
                program={shownShellMode === 'episode' ? shownProgram : null}
                screen={episodeScreen}
                fx={mascotaFx}
                onOpenChat={() => togglePanel('chat')}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Feedback ambiental al responder: luz en el borde inferior de la ventana.
            Independiente del bloque; se auto-oculta e inerte mientras no haya resultado. */}
        <ResultGlow
          resultado={glow?.resultado ?? null}
          intento={glow?.nonce}
          definitivo={glow?.definitivo}
          // Solo la luz ambiental, sin el pill de texto: flotaba abajo-centro y se
          // superponia al boton. El resultado ya lo dicen la opcion marcada del
          // ejercicio y la reaccion de la mascota, asi que la etiqueta sobra aqui.
          mostrarEtiqueta={false}
        />

        {/* Pantalla de fin de curso: celebracion + dominio + volver. Antes solo salia
            un texto plano "Has completado el curso". Sin blur (solo opacidad). */}
        <AnimatePresence>
          {finished && (
            <motion.div
              key="course-complete"
              className="absolute inset-0 z-30 flex items-center justify-center bg-bg px-6"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: duration.normal, ease: ease.base }}
            >
              <div className="flex flex-col items-center text-center gap-5 max-w-sm">
                <Mascota expression="happy" size={128} />
                <h2 className="text-2xl font-semibold text-text">
                  {intl.formatMessage({ id: 'node.courseCompleteTitle' })}
                </h2>
                {courseQuery.data?.title && (
                  <p className="text-text-secondary">{courseQuery.data.title}</p>
                )}
                <button
                  type="button"
                  onClick={() => navigate(backToCourse, { state: { fromNode: true } })}
                  className="mt-1 bg-primary hover:bg-primary-hover text-white text-sm font-medium px-5 py-3 rounded-md transition-colors"
                >
                  {intl.formatMessage({ id: 'node.backToCourse' })}
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Right sidebar — width animated directly (no layoutId/scale = no distortion) */}
        <motion.div
          ref={sidebarRef}
          animate={{ width: activePanel ? 400 : 48 }}
          transition={{ type: 'spring', stiffness: 200, damping: 28 }}
          className="hidden md:flex shrink-0 flex-col border-l border-border overflow-hidden"
          data-no-explain=""
        >
          {/* mode="wait" makes the close mirror the open: the panel fades out before the
              icons return, instead of snapping away while the width is still collapsing. */}
          <AnimatePresence mode="wait" initial={false}>
          {activePanel ? (
            <motion.div
              key={activePanel}
              className="flex-1 flex flex-col min-h-0"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.22, ease: [0.38, 0.49, 0, 1] }}
            >
              {/* Panel header */}
              <div className="flex items-center justify-between px-4 py-3 shrink-0">
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
                    nodeId={node?.id ?? undefined}
                    courseId={courseId}
                    nodeTitle={node?.title ?? undefined}
                    nodeSummary={node?.summary ?? undefined}
                    step={stepProgress?.currentStep}
                    totalSteps={stepProgress?.totalSteps}
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
              exit={{ opacity: 0 }}
              transition={{ duration: 0.22, ease: [0.38, 0.49, 0, 1] }}
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
          </AnimatePresence>
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
