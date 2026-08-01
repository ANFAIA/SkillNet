import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Button } from '../../ui'
import { duration, ease } from '../../../lib/motion'
import { BLOCK_TITLE, INLINE_SURFACE } from './rhythm'

export interface StepByStepRevealBlockProps {
  title: string
  steps: Array<{ statement: string; explanation: string }>
}

/**
 * Parse raw step data from the OpenUI dialect.
 *
 * Each sub-array is `[statement, explanation]`.
 */
export function parseSteps(raw: unknown): Array<{ statement: string; explanation: string }> {
  if (!Array.isArray(raw)) return []
  return raw
    .filter((entry) => Array.isArray(entry) && entry.length >= 2)
    .map((entry) => ({
      statement: typeof entry[0] === 'string' ? entry[0] : String(entry[0] ?? ''),
      explanation: typeof entry[1] === 'string' ? entry[1] : String(entry[1] ?? ''),
    }))
}

function StepItem({
  step,
  index,
  total,
  state,
}: {
  step: { statement: string; explanation: string }
  index: number
  total: number
  state: 'locked' | 'current' | 'done'
}) {
  const [showExplanation, setShowExplanation] = useState(false)
  const isLast = index === total - 1

  if (state === 'locked') return null

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: duration.normal, ease: ease.base }}
      className="min-w-0"
    >
      <div className="flex gap-4 min-w-0">
        {/* Timeline column */}
        <div className="flex flex-col items-center shrink-0">
          <span
            aria-hidden="true"
            data-no-explain=""
            className={`w-7 h-7 rounded-full text-xs font-semibold flex items-center justify-center ${
              state === 'current'
                ? 'bg-primary text-white shadow-sm'
                : 'bg-bg-muted text-text-muted'
            }`}
          >
            {state === 'done' ? '\u2713' : index + 1}
          </span>
          {!isLast && (
            <div
              aria-hidden="true"
              className={`w-px flex-1 mt-1 ${
                state === 'done' ? 'bg-border-strong' : 'bg-border'
              }`}
            />
          )}
        </div>

        {/* Step content */}
        <div className={`flex-1 min-w-0 ${isLast ? '' : 'pb-5'}`}>
          <p
            className={`text-sm leading-relaxed ${
              state === 'current' ? 'text-text font-medium' : 'text-text-muted'
            }`}
          >
            {step.statement}
          </p>

          {/* Explanation toggle */}
          {state === 'current' && !showExplanation && (
            <button
              type="button"
              onClick={() => setShowExplanation(true)}
              className="mt-2 text-xs font-medium text-primary hover:text-primary-hover transition-colors"
            >
              Mostrar explicacion
            </button>
          )}

          <AnimatePresence>
            {showExplanation && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: duration.fast, ease: ease.base }}
                className="overflow-hidden"
              >
                <p className="mt-2 text-xs text-text-secondary leading-relaxed border-l-2 border-border pl-3">
                  {step.explanation}
                </p>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Show explanation dimmed for completed steps */}
          {state === 'done' && (
            <p className="mt-1 text-xs text-text-muted leading-relaxed">
              {step.explanation}
            </p>
          )}
        </div>
      </div>
    </motion.div>
  )
}

export function StepByStepRevealBlock({ title, steps }: StepByStepRevealBlockProps) {
  const safeSteps = Array.isArray(steps) ? steps : []
  const [currentStep, setCurrentStep] = useState(0)

  function handleNext() {
    if (currentStep < safeSteps.length - 1) {
      setCurrentStep((prev) => prev + 1)
    }
  }

  const isComplete = currentStep >= safeSteps.length - 1

  return (
    <div data-no-explain="" className={`${INLINE_SURFACE} bg-bg-subtle`}>
      <div className="flex items-baseline justify-between gap-3 mb-3">
        {title ? <p className={`${BLOCK_TITLE} mb-0`}>{title}</p> : null}
        <span className="text-xs text-text-muted tabular-nums shrink-0">
          Paso {Math.min(currentStep + 1, safeSteps.length)} de {safeSteps.length}
        </span>
      </div>

      {/* Steps list */}
      <div className="min-w-0">
        {safeSteps.map((step, idx) => {
          let state: 'locked' | 'current' | 'done'
          if (idx < currentStep) state = 'done'
          else if (idx === currentStep) state = 'current'
          else state = 'locked'

          return (
            <StepItem
              key={idx}
              step={step}
              index={idx}
              total={safeSteps.length}
              state={state}

            />
          )
        })}
      </div>

      {/* Next button */}
      {!isComplete && safeSteps.length > 1 && (
        <div className="mt-4">
          <Button size="sm" onClick={handleNext}>
            Siguiente
          </Button>
        </div>
      )}

      {isComplete && safeSteps.length > 0 && (
        <div
          role="status"
          className="mt-4 rounded-lg border border-accent bg-accent-subtle p-3"
        >
          <span className="text-sm font-medium text-accent">
            Todos los pasos completados
          </span>
        </div>
      )}
    </div>
  )
}
