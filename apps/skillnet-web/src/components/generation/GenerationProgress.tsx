import { useEffect, useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { duration, ease, transition } from '../../lib/motion'
import type { GenerationProgress as GenerationProgressData, GenerationStep } from '../../types'

/**
 * The wait screen of the course wizard (`/admin/content/new`, step 2).
 *
 * It used to be six numbered circles in a row with a caption under each, and it was
 * unreadable in the only situation it exists for: a generation that takes half a
 * minute and where nothing on screen moves between one SSE `step` event and the next.
 * A static diagram of a pipeline is indistinguishable from a hung pipeline.
 *
 * So the shape is now a vertical checklist, and three things move *continuously*
 * rather than only when a step arrives:
 *
 * 1. The bouncing dots next to the phase being worked on — the same `.typing-dots`
 *    the chat uses while an answer is being written (`chat/ChatAnswer.tsx`). Same
 *    meaning in both places: something is being produced right now.
 * 2. A halo expanding out of the active node, so the eye finds "you are here"
 *    without reading.
 * 3. A highlight sweeping *down* the rail segment that leaves the active step and
 *    points at the next one — direction of travel, which the dots alone do not give.
 *
 * And three on each state change: the check landing on the step that just finished,
 * its rail segment drawing downward, and the new active row easing in.
 *
 * The heading and the status line live here rather than in `CreateCourse.tsx`: the
 * title depends on the phase (generating / done / failed), which is state this
 * component already holds.
 */

const STEPS: { key: GenerationStep; label: string }[] = [
  { key: 'pending', label: 'En cola' },
  { key: 'extracting', label: 'Extrayendo temas' },
  { key: 'structuring', label: 'Disenando estructura' },
  { key: 'generating', label: 'Escribiendo contenido' },
  { key: 'reviewing', label: 'Revision de calidad' },
  { key: 'published', label: 'Publicado' },
]

const STEP_ORDER = STEPS.map((s) => s.key)

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

function CrossIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

/** Reused verbatim from the chat, class and markup both. */
function TypingDots() {
  return (
    <span className="typing-dots text-primary" aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  )
}

export function GenerationProgress({ progress }: { progress: GenerationProgressData }) {
  const reduceMotion = useReducedMotion()

  const isFailed = progress.step === 'failed'
  const isDone = progress.step === 'published'
  const index = STEP_ORDER.indexOf(progress.step)

  /**
   * The last step we recognised. Two jobs, both about not losing the picture:
   *
   * - `failed` does not say *where* it failed, so without this the rail would empty
   *   out at the exact moment the operator needs to know which phase broke.
   * - a step name the server grows and this list does not know yet would otherwise
   *   reset the rail to "nothing done" mid-run. Holding position is the honest
   *   answer: the phase is unknown, the progress is not.
   *
   * Written in an effect, so the render that receives `failed` still reads the
   * previous value.
   */
  const lastKnownIndex = useRef(-1)
  useEffect(() => {
    if (index >= 0) lastKnownIndex.current = index
  }, [index])

  const failedIndex = isFailed ? lastKnownIndex.current : -1
  // Clamped at 0: if the very first event is a step we do not know, the job is at
  // least queued, and a rail with no active row would have nothing moving on it.
  const activeIndex = isFailed ? -1 : Math.max(index >= 0 ? index : lastKnownIndex.current, 0)
  const completedThrough = isFailed ? failedIndex : activeIndex

  const title = isFailed ? 'La generacion fallo' : isDone ? 'Curso generado' : 'Generando curso'
  const status = isFailed
    ? null
    : isDone
      ? 'Ya se puede revisar'
      : `Paso ${activeIndex + 1} de ${STEPS.length} · esto puede tomar unos momentos`

  return (
    <div className="max-w-md mx-auto space-y-5" data-reduced-motion={reduceMotion || undefined}>
      <div>
        <h3 className="text-base font-medium text-text">{title}</h3>
        {status && <p className="text-sm text-text-secondary mt-1 tabular-nums">{status}</p>}
      </div>

      <ol>
        {STEPS.map((step, i) => {
          const isCompleted = isDone || i < completedThrough
          const isCurrent = !isDone && !isFailed && i === activeIndex
          const isFailedHere = i === failedIndex
          const isLast = i === STEPS.length - 1

          return (
            <li key={step.key} className="flex gap-3" aria-current={isCurrent ? 'step' : undefined}>
              {/* Rail gutter: the node, then the segment that reaches the next node.
                  The gutter stretches to the row height, so the segment is whatever
                  space the label leaves it — no measured offsets. */}
              <div className="flex flex-col items-center w-6 shrink-0">
                <span
                  className={`relative flex items-center justify-center w-6 h-6 rounded-full shrink-0 transition-colors duration-200 ${
                    isCompleted
                      ? 'bg-primary text-white'
                      : isFailedHere
                        ? 'border-2 border-danger text-danger'
                        : isCurrent
                          ? 'border-2 border-primary'
                          : 'border border-border'
                  }`}
                >
                  {isCurrent && !reduceMotion && (
                    <span aria-hidden="true" className="gen-halo absolute inset-0 rounded-full border-2 border-primary" />
                  )}
                  {isCompleted ? (
                    <motion.span
                      className="flex"
                      initial={reduceMotion ? false : { scale: 0.3, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={{ duration: duration.fast, ease: ease.bounceHard }}
                    >
                      <CheckIcon />
                    </motion.span>
                  ) : isFailedHere ? (
                    <CrossIcon />
                  ) : isCurrent ? (
                    <span className="w-2 h-2 rounded-full bg-primary" />
                  ) : null}
                </span>

                {!isLast && (
                  <span
                    aria-hidden="true"
                    /* `min-h-5` is what guarantees the segment is long enough for the
                       sweep to read as travel rather than as a blink — the label row
                       alone would leave it about ten pixels. */
                    className={`relative flex-1 w-0.5 min-h-5 my-1 rounded-full overflow-hidden transition-colors duration-200 ${
                      isCurrent ? 'bg-primary/15' : 'bg-bg-muted'
                    }`}
                  >
                    {isCompleted && (
                      <motion.span
                        className="absolute inset-0 origin-top rounded-full bg-primary"
                        initial={reduceMotion ? false : { scaleY: 0 }}
                        animate={{ scaleY: 1 }}
                        transition={{ duration: duration.normal, ease: ease.base }}
                      />
                    )}
                    {isCurrent && !reduceMotion && (
                      <span className="gen-sweep absolute inset-x-0 h-1/2 rounded-full bg-linear-to-b from-transparent via-primary to-transparent" />
                    )}
                  </span>
                )}
              </div>

              <div className={`flex-1 min-w-0 ${isLast ? '' : 'mb-5'}`}>
                {/* Keyed on the active flag so the row replays its entrance the moment
                    it becomes the one being worked on. */}
                <motion.div
                  key={isCurrent ? 'current' : 'idle'}
                  /* `w-fit`: the highlight hugs the phase it marks. Stretched across the
                     column it read as an empty input field, not as "you are here". */
                  className={`flex w-fit items-center gap-2 px-3 py-1 rounded-lg transition-colors duration-200 ${
                    isCurrent ? 'bg-bg-subtle' : ''
                  }`}
                  initial={isCurrent && !reduceMotion ? { opacity: 0, y: 4 } : false}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: duration.normal, ease: ease.base }}
                >
                  <span
                    className={`text-sm ${
                      isCurrent
                        ? 'text-text font-medium'
                        : isFailedHere
                          ? 'text-danger'
                          : isCompleted
                            ? 'text-text-secondary'
                            : 'text-text-muted'
                    }`}
                  >
                    {step.label}
                  </span>
                  {isCurrent && <TypingDots />}
                  <span className="sr-only">
                    {isCompleted ? 'completado' : isFailedHere ? 'fallo aqui' : isCurrent ? 'en curso' : 'pendiente'}
                  </span>
                </motion.div>
              </div>
            </li>
          )
        })}
      </ol>

      {/* The server's own sentence for the phase. One live region, and it keeps its
          height while running so a new message crossfades in place instead of pushing
          the rail around. On failure it collapses: the error box below is the message,
          and a reserved empty line would only open a hole above it. */}
      <div className={isFailed ? undefined : 'min-h-5'} aria-live="polite">
        <AnimatePresence mode="wait">
          {progress.message && !isFailed && (
            <motion.p
              key={progress.message}
              className="text-sm text-text-secondary"
              initial={reduceMotion ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduceMotion ? undefined : { opacity: 0 }}
              transition={transition.content}
            >
              {progress.message}
            </motion.p>
          )}
        </AnimatePresence>
      </div>

      {isFailed && (
        <motion.div
          className="text-sm text-danger border border-danger/30 rounded-md p-3"
          initial={reduceMotion ? false : { opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: duration.normal, ease: ease.base }}
        >
          {progress.error ?? 'No se pudo completar la generacion.'}
        </motion.div>
      )}
    </div>
  )
}
