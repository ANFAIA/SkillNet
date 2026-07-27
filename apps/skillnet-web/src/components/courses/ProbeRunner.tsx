import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button } from '../ui'
import { ShimmerSkeletonText } from '../ui/ShimmerSkeleton'
import { useProbe, useSubmitProbeAnswer } from '../../api/nodes'
import type { LearningNode, ProbeAnswerResult, ProbeItemDetail, ProbeSession } from '../../types'

/**
 * The pre-assessment, which **is** the productive wait (§9.1).
 *
 * The design this component implements, and the reason it exists at all: the two probe
 * items cost 10-20 s of human attention, which is the same order as
 * `decide_formato` + `genera_ui`. So the wait is not hidden behind a spinner, it is
 * *spent* on work that teaches by itself (the pre-question effect). The overlap is
 * client-driven: `POST /probe/answer` answers `render_hint: "prefetch"` the moment
 * "mastered" becomes unreachable, and `onPrefetch` fires `POST /render` in the
 * background from here. If the final verdict does come out `mastered`, the server
 * cancels the in-flight render on its own.
 *
 * Two decisions worth naming:
 *
 * - **No per-item correctness reveal.** A probe is a measurement, not practice: showing
 *   "incorrecto" between items anchors the next answer and turns the diagnostic framing
 *   of §7.1 ("vamos a ver que te suena ya") into a run of failures before the learner
 *   has read one line. `feedback` from the closing answer is shown once, with the
 *   verdict.
 * - **The residual "no pre-generated items" case has its own screen** (§9.1): while
 *   `POST /probe` is in flight, the node summary and the deterministic opening line are
 *   on screen. The wait cannot cover the wait, so the only thing left is to make the
 *   uncovered part useful.
 */

export interface ProbeRunnerProps {
  nodeId: string
  node: LearningNode | null
  /** "Esto te sirve para X", derived from `goal` in the client (§6.2 Q2). */
  openingLine?: string | null
  /** Fired once, when the server says the render can start (`render_hint: "prefetch"`). */
  onPrefetch: () => void
  /**
   * The probe is over. `mastered` → the node is skipped and no content is requested;
   * `learning` → the lesson is the next screen.
   */
  onVerdict: (verdict: 'mastered' | 'learning') => void
}

/** Answer payloads `grade()` accepts, by item type (`_norm` unwraps each key). */
function buildAnswer(
  item: ProbeItemDetail,
  selected: number | null,
  text: string,
): Record<string, unknown> | null {
  if (item.item_type === 'test') {
    return selected === null ? null : { selected }
  }
  if (item.item_type === 'true_false') {
    return selected === null ? null : { answer: selected === 0 }
  }
  const trimmed = text.trim()
  if (!trimmed) return null
  // `fill_blank` is graded blank by blank; the prompt fixes a single blank for item c.
  return item.item_type === 'fill_blank' ? { answers: [trimmed] } : { response: trimmed }
}

const TRUE_FALSE_OPTIONS = ['Verdadero', 'Falso']

function itemPrompt(item: ProbeItemDetail): string {
  return item.question ?? item.template ?? ''
}

export function ProbeRunner({
  nodeId,
  node,
  openingLine = null,
  onPrefetch,
  onVerdict,
}: ProbeRunnerProps) {
  const probe = useProbe(nodeId)
  const submit = useSubmitProbeAnswer(nodeId)

  const [session, setSession] = useState<ProbeSession | null>(null)
  const [currentItemId, setCurrentItemId] = useState<string | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [text, setText] = useState('')
  const [closing, setClosing] = useState<ProbeAnswerResult | null>(null)
  //: Whether opening the probe failed. Component state and not `probe.isError`, for the
  //: same reason `adopt` runs off `mutateAsync` below: the observer's flags do not
  //: survive a remount, and a probe that failed silently is worse than one that failed.
  const [openFailed, setOpenFailed] = useState(false)

  // The probe opens exactly once per mounted node. A query would re-fire on every
  // cache decision, and `POST /probe` for a node whose probe is unfinished and
  // *unscored* deals a fresh hand — so "once" is a correctness requirement, not an
  // optimization.
  const openedRef = useRef(false)
  const prefetchedRef = useRef(false)
  const verdictSentRef = useRef(false)
  const openedAt = useRef(Date.now())

  const emitVerdict = useCallback(
    (verdict: 'mastered' | 'learning') => {
      if (verdictSentRef.current) return
      verdictSentRef.current = true
      onVerdict(verdict)
    },
    [onVerdict],
  )

  const prefetch = useCallback(() => {
    if (prefetchedRef.current) return
    prefetchedRef.current = true
    onPrefetch()
  }, [onPrefetch])

  const adopt = useCallback(
    (next: ProbeSession) => {
      setSession(next)
      if (next.verdict === 'mastered' || next.verdict === 'learning') {
        emitVerdict(next.verdict)
        return
      }
      // A replayed session with no items left and no verdict cannot be answered; the
      // lesson is the only place left to go.
      if (next.items.length === 0) {
        emitVerdict('learning')
        return
      }
      setCurrentItemId((prev) => prev ?? next.items[0]?.item_id ?? null)
    },
    [emitVerdict],
  )

  // `mutateAsync` and a promise, and **not** a per-call `onSuccess` handed to `mutate`.
  //
  // Those callbacks hang off the mutation *observer*, and react-query drops them when the
  // observer is torn down before the request settles. Reading `probe.data` instead does
  // not help either: a remount builds a **new** observer, which is not attached to the
  // mutation that already finished, so `data` stays `undefined`. Either way the request
  // succeeded, the server dealt a hand, nothing read it, and `openedRef` turned the retry
  // into a no-op — the screen sat on "Preparando dos preguntas rapidas..." for good, with
  // no error to explain it. StrictMode reproduces it every time, which is how it was
  // found; a concurrent remount in production is the same shape.
  //
  // The promise from `mutateAsync` belongs to the call, not to the observer, and `adopt`
  // writes component state, which does survive the simulated remount. Nothing cancels on
  // cleanup on purpose: cancelling is precisely what loses the only result there will be,
  // because `openedRef` guarantees no second request.
  useEffect(() => {
    if (openedRef.current || !nodeId) return
    openedRef.current = true
    probe
      .mutateAsync({})
      .then(adopt)
      .catch(() => setOpenFailed(true))
    // `probe` and `adopt` are fresh objects on every render, so this effect re-runs
    // often; `openedRef` is what makes every run after the first a no-op. The guard is
    // the mechanism, the dependency list is not.
  }, [nodeId, probe, adopt])

  const items = useMemo(() => session?.items ?? [], [session])
  const answeredRef = useRef<Set<string>>(new Set())
  const current = useMemo(
    () => items.find((item) => item.item_id === currentItemId) ?? null,
    [items, currentItemId],
  )

  const answer = current ? buildAnswer(current, selected, text) : null

  function advance(result: ProbeAnswerResult) {
    if (result.render_hint === 'prefetch') prefetch()

    if (result.verdict === 'mastered' || result.verdict === 'learning') {
      setClosing(result)
      // The render, if any, is cancelled server-side for `mastered`; for `learning`
      // the parent starts (or adopts) it.
      emitVerdict(result.verdict)
      return
    }

    const nextId = result.next_item_id
    if (!nextId) {
      // No verdict and nothing left to ask: the probe cannot close from the client, so
      // the lesson is the honest next screen.
      emitVerdict('learning')
      return
    }

    setSelected(null)
    setText('')
    openedAt.current = Date.now()

    if (items.some((item) => item.item_id === nextId)) {
      setCurrentItemId(nextId)
      return
    }

    // The tie-break item (§7.1): on a non-critical node item `c` is withheld until the
    // verdict falls into the doubt band, so it is not in the hand we were dealt. Asking
    // for the probe again returns the SAME row with `c` now exposed — but only for a
    // *scored* probe, which is the only row `get_scored` can find again. For an unscored
    // diagnostic probe a second POST would deal a new hand, so we go to the lesson
    // instead (a diagnostic probe persists nothing, so nothing is lost).
    if (session?.probe?.scored) {
      probe.mutate(
        {},
        {
          onSuccess: (next) => {
            setSession(next)
            if (next.verdict === 'mastered' || next.verdict === 'learning') {
              emitVerdict(next.verdict)
              return
            }
            const served = next.items.find((item) => item.item_id === nextId)
            if (served) setCurrentItemId(nextId)
            else emitVerdict('learning')
          },
          onError: () => emitVerdict('learning'),
        },
      )
      return
    }
    emitVerdict('learning')
  }

  function send() {
    const probeId = session?.probe?.id
    if (!current || !answer || !probeId || submit.isPending) return
    answeredRef.current.add(current.item_id)
    submit.mutate(
      {
        probe_id: probeId,
        item_id: current.item_id,
        answer,
        latency_ms: Math.max(0, Date.now() - openedAt.current),
      },
      { onSuccess: advance },
    )
  }

  // --- the residual wait: items being generated (§9.1) ------------------------
  // Keyed off `session`/`openFailed` rather than `probe.isPending`, which reads `false`
  // both before the opening effect has run and after a remount has replaced the observer.
  if (!session && !openFailed) {
    return (
      <div className="space-y-4" data-testid="probe-loading" aria-busy="true">
        {openingLine && <p className="text-base text-text">{openingLine}</p>}
        {node?.summary && <p className="text-sm text-text-secondary">{node.summary}</p>}
        <p className="text-sm text-text-muted">Preparando dos preguntas rapidas...</p>
        <ShimmerSkeletonText lines={2} />
      </div>
    )
  }

  if (openFailed) {
    // A probe that cannot open must not block the lesson: §7 measures what the learner
    // already knows, and not measuring it costs an unnecessary node, not a wrong one.
    return (
      <div className="space-y-3">
        <p className="text-sm text-text">
          No se pudo preparar el diagnostico inicial de este nodo.
        </p>
        <Button size="sm" variant="secondary" onClick={() => emitVerdict('learning')}>
          Ir a la leccion
        </Button>
      </div>
    )
  }

  if (closing) {
    const mastered = closing.verdict === 'mastered'
    return (
      <div className="space-y-3" role="status">
        <p className="text-base font-medium text-text">
          {mastered ? 'Ya dominas este nodo' : 'Vamos a trabajarlo'}
        </p>
        {closing.feedback && <p className="text-sm text-text-secondary">{closing.feedback}</p>}
        {!mastered && (
          <p className="text-sm text-text-secondary">Preparando la leccion con lo que has respondido.</p>
        )}
      </div>
    )
  }

  if (!current) return null

  const isSingleChoice = current.item_type === 'test' || current.item_type === 'true_false'
  const options =
    current.item_type === 'true_false' && (current.options ?? []).length === 0
      ? TRUE_FALSE_OPTIONS
      : (current.options ?? [])
  const answeredCount = answeredRef.current.size
  const total = Math.max(items.length, answeredCount + 1)

  return (
    <div
      className="space-y-4"
      // §8.5: a probe item is a control surface, not prose. Explaining a word inside
      // the correct option would be a free hint on the item that decides the verdict.
      data-no-explain=""
      data-testid="probe-runner"
    >
      {openingLine && <p className="text-base text-text">{openingLine}</p>}

      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-medium text-text">
          {session?.diagnostic
            ? 'Vamos a ver que te suena ya'
            : 'Antes de empezar, dos preguntas'}
        </p>
        <span className="text-xs text-text-muted tabular-nums shrink-0">
          {answeredCount + 1} / {total}
        </span>
      </div>

      {session?.diagnostic && (
        <p className="text-sm text-text-secondary">
          No cuenta para tu nota: solo sirve para no explicarte lo que ya sabes.
        </p>
      )}

      <div className="rounded-lg border border-border bg-bg-subtle p-4 space-y-4">
        <p className="text-sm font-medium text-text">{itemPrompt(current)}</p>
        {current.context && <p className="text-sm text-text-secondary">{current.context}</p>}

        {isSingleChoice ? (
          <div className="space-y-2">
            {options.map((option, idx) => (
              <label
                key={idx}
                className={`flex items-center gap-3 p-3 border rounded-lg cursor-pointer transition-colors ${
                  selected === idx ? 'border-primary' : 'border-border'
                }`}
              >
                <input
                  type="radio"
                  name={`probe:${nodeId}:${current.item_id}`}
                  checked={selected === idx}
                  onChange={() => setSelected(idx)}
                  disabled={submit.isPending}
                  className="accent-primary"
                />
                <span className="text-sm text-text break-words min-w-0">{option}</span>
              </label>
            ))}
          </div>
        ) : (
          <textarea
            value={text}
            rows={current.item_type === 'fill_blank' ? 2 : 5}
            disabled={submit.isPending}
            onChange={(event) => setText(event.target.value)}
            placeholder="Escribe tu respuesta..."
            aria-label="Tu respuesta"
            className="w-full px-3 py-2 text-sm text-text border border-border rounded-lg bg-bg placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors disabled:opacity-60 resize-y"
          />
        )}

        <div className="flex items-center gap-3">
          <Button size="sm" disabled={!answer || submit.isPending} onClick={send}>
            {submit.isPending ? 'Enviando...' : 'Responder'}
          </Button>
          {/* No time limit on any item (§7.4): time pressure is extraneous load. */}
          <span className="text-xs text-text-muted">Sin limite de tiempo</span>
        </div>

        {submit.isError && (
          <p className="text-sm text-danger">No se pudo registrar la respuesta. Intentalo otra vez.</p>
        )}
      </div>
    </div>
  )
}
