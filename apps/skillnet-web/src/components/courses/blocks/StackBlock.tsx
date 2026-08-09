import { Children, isValidElement, useState, useCallback, useEffect, useRef, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useIntl } from 'react-intl'
import { blockArrivalContext, useBlockArrival } from './blockArrival'
import { stepperContext, useStepper, stepperAdvanceContext, stepperSolveContext, useNextNode, useCourseIntro, useStepperProgressReport } from './StepperContext'
import { useReducedMotion } from '../../../hooks/useReducedMotion'
import { duration, ease } from '../../../lib/motion'
import type { StackGap } from '../kit/schemas'

export interface StackBlockProps {
  gap?: StackGap
  children?: ReactNode
}

const gapClasses: Record<StackGap, string> = {
  sm: 'gap-2',
  md: 'gap-4',
  lg: 'gap-6',
}

/**
 * Vertical container. When `stepperContext` is active this is the root Stack
 * and children render one at a time — Brilliant-style.
 */
export function StackBlock({ gap = 'md', children }: StackBlockProps) {
  const arriving = useBlockArrival()
  const stepper = useStepper()
  const reduceMotion = useReducedMotion()

  if (stepper) {
    return (
      <stepperContext.Provider value={false}>
        <blockArrivalContext.Provider value={false}>
          <StepperStack>{children}</StepperStack>
        </blockArrivalContext.Provider>
      </stepperContext.Provider>
    )
  }

  const arrival = arriving && !reduceMotion ? ' block-arrival' : ''
  return (
    <blockArrivalContext.Provider value={false}>
      <div className={`flex flex-col justify-center min-w-0 ${gapClasses[gap] ?? gapClasses.md}${arrival}`}>
        {children}
      </div>
    </blockArrivalContext.Provider>
  )
}

// ---------------------------------------------------------------------------
// StackItem — un hijo del Stack, etiquetado
// ---------------------------------------------------------------------------

export interface StackItemProps {
  /**
   * True si en el subarbol de este hijo hay un bloque que exige resolverse (QuizItem,
   * DragOrder). Lo calcula `kit/solvableSteps.ts` sobre el programa YA PARSEADO, asi
   * que llega como un dato, no como un descubrimiento en tiempo de ejecucion.
   */
  solvable?: boolean
  children?: ReactNode
}

/**
 * Envoltorio sin DOM cuyo unico trabajo es llevar `solvable` en el elemento React.
 *
 * El stepper necesita saber si el paso actual es un ejercicio ANTES de pintarlo, y no
 * puede averiguarlo mirando lo que pinta: el bloque real es `QuizItemRenderer`, dos
 * indirecciones por debajo del runtime de OpenUI, y con `AnimatePresence mode="wait"`
 * ni siquiera esta montado todavia. Preguntarselo al hijo por un efecto llega siempre
 * tarde. Etiquetarlo aqui lo convierte en algo que se lee en render.
 *
 * Fuera del stepper no hace absolutamente nada, ni siquiera un `<div>`.
 */
export function StackItem({ children }: StackItemProps) {
  return <>{children}</>
}

/** Lee la etiqueta del paso. Un hijo sin etiquetar (Storybook, admin) no cierra nada. */
function stepNeedsSolving(item: ReactNode): boolean {
  return isValidElement<StackItemProps>(item) && item.type === StackItem && item.props.solvable === true
}

// ---------------------------------------------------------------------------
// Stepper — one child at a time, progress bar, tap to advance
// ---------------------------------------------------------------------------

function StepperStack({ children }: { children?: ReactNode }) {
  const intl = useIntl()
  const intro = useCourseIntro()
  const reportProgress = useStepperProgressReport()
  const nodeItems = Children.toArray(children).filter(Boolean)

  // Prepend one course intro slide if this is the first node with no progress
  const introSlides: ReactNode[] = intro ? [
    <div key="intro" className="text-center space-y-5 max-w-md mx-auto">
      <div className="space-y-1.5">
        <h1 className="text-2xl font-semibold text-text">{intro.title}</h1>
        <p className="text-sm text-text-muted">{intro.subtitle}</p>
      </div>
      <ul className="space-y-2 text-left">
        {intro.outcomes.slice(0, 3).map((outcome, i) => (
          <li key={i} className="flex gap-2.5 text-sm text-text-secondary">
            <span className="shrink-0 w-5 h-5 rounded-full bg-primary/10 text-primary text-xs flex items-center justify-center font-medium">{i + 1}</span>
            <span className="line-clamp-2">{outcome}</span>
          </li>
        ))}
      </ul>
    </div>,
  ] : []

  const items = [...introSlides, ...nodeItems]
  const total = items.length
  const [step, setStep] = useState(0)
  const safeStep = Math.min(step, total - 1)
  const isLast = safeStep >= total - 1
  const nextNodeInfo = useNextNode()
  const goNextNode = nextNodeInfo?.navigate ?? null

  // Report step progress up to NodeView so it can render the dots in its top bar
  useEffect(() => {
    reportProgress?.({ currentStep: safeStep, totalSteps: total })
  }, [safeStep, total, reportProgress])

  /**
   * El paso cuyo ejercicio ya esta resuelto, o `null`.
   *
   * Se guarda el INDICE y no un booleano para que resolver un paso no valga como haber
   * resuelto otro. Y se borra en CUALQUIER cambio de paso (`move`), incluido volver
   * atras: al reentrar en un paso el ejercicio se monta de cero, sin respuesta, asi que
   * el permiso de salir tampoco puede sobrevivir.
   *
   * Que el paso este cerrado NO es un estado: se deduce en render de la etiqueta del
   * hijo. Nadie tiene que avisar de que hay que cerrar, y por eso no hay ninguna ventana
   * en la que el paso este abierto por no haberse enterado todavia.
   */
  const [solvedStep, setSolvedStep] = useState<number | null>(null)
  const stepRef = useRef(safeStep)
  stepRef.current = safeStep
  const solve = useCallback(() => setSolvedStep(stepRef.current), [])
  const isGated = stepNeedsSolving(items[safeStep]) && solvedStep !== safeStep

  const move = useCallback((delta: number) => {
    setSolvedStep(null)
    setStep((s) => Math.max(0, s + delta))
  }, [])

  const next = useCallback(() => {
    if (isGated) return
    if (!isLast) move(1)
    else if (goNextNode) goNextNode()
  }, [isGated, isLast, goNextNode, move])

  const back = useCallback(() => {
    move(-1)
  }, [move])

  // Auto-advance: interactive blocks call this after success (quiz correct, drag complete)
  const advance = useCallback(() => {
    setTimeout(() => {
      if (!isLast) move(1)
      else if (goNextNode) goNextNode()
    }, 1200)
  }, [isLast, goNextNode, move])

  // Keyboard navigation: same behavior as chevrons
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      // Don't hijack arrows when user is typing in an input/textarea
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault()
        if (isGated) return
        if (!isLast) move(1)
        else if (goNextNode) goNextNode()
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault()
        move(-1)
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
    // `isGated` va en las dependencias o el listener se queda con el valor de cuando se
    // registro —falso— y la flecha derecha salta el ejercicio aunque el chevron no.
  }, [isGated, isLast, goNextNode, move])

  if (total === 0) return null
  if (total === 1) {
    // `justify-center` como en el stepper: `UiSpecRenderer` fuerza `flex-1 min-h-0`
    // sobre este div, asi que llena el alto y sin esto su contenido queda pegado arriba.
    return <div className="flex flex-col justify-center min-w-0">{items[0]}</div>
  }

  return (
    <stepperAdvanceContext.Provider value={advance}>
      <stepperSolveContext.Provider value={solve}>
      <div className="flex flex-col h-full min-w-0" data-stepper-root>
        {/* Middle: chevrons on sides, content centered vertically */}
        <div className="flex-1 min-h-0 flex items-center justify-center gap-2">
          {/* Left chevron */}
          <button
            type="button"
            onClick={back}
            disabled={safeStep === 0}
            className="shrink-0 p-2 text-text-muted hover:text-text disabled:opacity-0 disabled:pointer-events-none transition-opacity"
            aria-label={intl.formatMessage({ id: 'stepper.previousStep' })}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>

          {/* Content */}
          <div className="flex-1 min-w-0 overflow-y-auto max-h-full">
            <AnimatePresence mode="wait">
              <motion.div
                key={safeStep}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: duration.normal, ease: [...ease.base] }}
                className="min-w-0"
              >
                {items[safeStep]}
              </motion.div>
            </AnimatePresence>
          </div>

          {/* Right chevron — advances step or goes to next node */}
          <button
            type="button"
            onClick={next}
            disabled={isGated || (isLast && !goNextNode)}
            className="shrink-0 p-2 text-text-muted hover:text-text disabled:opacity-0 disabled:pointer-events-none transition-opacity"
            aria-label={isLast ? intl.formatMessage({ id: 'stepper.nextNode' }) : intl.formatMessage({ id: 'stepper.nextStep' })}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </div>

        {/* Next-node CTA — prominent button at end of lesson */}
        <AnimatePresence>
          {isLast && !isGated && (
            <motion.div
              key="next-cta"
              className="shrink-0 px-4 pb-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: duration.normal, ease: [...ease.base] }}
            >
              {nextNodeInfo ? (
                <button
                  type="button"
                  onClick={nextNodeInfo.navigate}
                  className="w-full bg-primary hover:bg-primary-hover text-white text-sm font-medium px-4 py-3 rounded-md transition-colors"
                >
                  {intl.formatMessage({ id: 'node.nextNode' }, { title: nextNodeInfo.title })}
                </button>
              ) : (
                <div className="w-full text-center text-sm font-medium text-text-secondary bg-bg-subtle rounded-md px-4 py-3">
                  {intl.formatMessage({ id: 'node.courseComplete' })}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

      </div>
      </stepperSolveContext.Provider>
    </stepperAdvanceContext.Provider>
  )
}
