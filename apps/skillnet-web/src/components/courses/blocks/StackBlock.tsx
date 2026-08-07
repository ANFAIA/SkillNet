import { Children, useState, useCallback, useEffect, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { blockArrivalContext, useBlockArrival } from './blockArrival'
import { stepperContext, useStepper, stepperAdvanceContext } from './StepperContext'
import { useReducedMotion } from '../../../hooks/useReducedMotion'
import { LessonBuddy } from './LessonBuddy'
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
      <div className={`flex flex-col min-w-0 ${gapClasses[gap] ?? gapClasses.md}${arrival}`}>
        {children}
      </div>
    </blockArrivalContext.Provider>
  )
}

// ---------------------------------------------------------------------------
// Stepper — one child at a time, progress bar, tap to advance
// ---------------------------------------------------------------------------

function StepperStack({ children }: { children?: ReactNode }) {
  const items = Children.toArray(children).filter(Boolean)
  const total = items.length
  const [step, setStep] = useState(0)
  const safeStep = Math.min(step, total - 1)
  const isLast = safeStep >= total - 1

  const next = useCallback(() => {
    if (!isLast) setStep((s) => s + 1)
  }, [isLast])

  const back = useCallback(() => {
    setStep((s) => Math.max(0, s - 1))
  }, [])

  // Auto-advance: interactive blocks call this after success (quiz correct, drag complete)
  const advance = useCallback(() => {
    // Small delay so the learner sees the success feedback before moving on
    setTimeout(() => {
      if (!isLast) setStep((s) => s + 1)
    }, 1200)
  }, [isLast])

  // Keyboard navigation: left/right arrow keys
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault()
        if (!isLast) setStep((s) => s + 1)
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault()
        setStep((s) => Math.max(0, s - 1))
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [isLast])

  if (total === 0) return null
  if (total === 1) {
    return <div className="flex flex-col min-w-0">{items[0]}</div>
  }

  return (
    <stepperAdvanceContext.Provider value={advance}>
      <div className="flex flex-col h-full min-w-0">
        {/* Top: step dots */}
        <div className="shrink-0 flex items-center justify-center gap-2 pb-4">
          {items.map((_, i) => (
            <motion.div
              key={i}
              className={`rounded-full transition-colors ${
                i === safeStep
                  ? 'w-2 h-2 bg-primary'
                  : i < safeStep
                    ? 'w-1.5 h-1.5 bg-primary/40'
                    : 'w-1.5 h-1.5 bg-border'
              }`}
              layout
              transition={{ duration: duration.fast }}
            />
          ))}
        </div>

        {/* Middle: chevrons on sides, content centered vertically */}
        <div className="flex-1 min-h-0 flex items-center justify-center gap-2">
          {/* Left chevron */}
          <button
            type="button"
            onClick={back}
            disabled={safeStep === 0}
            className="shrink-0 p-2 text-text-muted hover:text-text disabled:opacity-0 disabled:pointer-events-none transition-all"
            aria-label="Paso anterior"
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

          {/* Right chevron */}
          {!isLast ? (
            <button
              type="button"
              onClick={next}
              className="shrink-0 p-2 text-text-muted hover:text-text transition-all"
              aria-label="Siguiente paso"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </button>
          ) : (
            <span className="shrink-0 w-9" />
          )}
        </div>

        {/* Bottom: buddy — always pinned at the bottom */}
        <div className="shrink-0 pt-4">
          <LessonBuddy stepIndex={safeStep} totalSteps={total} />
        </div>
      </div>
    </stepperAdvanceContext.Provider>
  )
}
