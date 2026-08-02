import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Button } from '../../ui'
import { duration, ease } from '../../../lib/motion'
import { BLOCK_TITLE, INLINE_SURFACE } from './rhythm'

export interface DiagramStep {
  label: string
  svgFragment: string
  explanation: string
}

export interface DiagramBuilderBlockProps {
  title: string
  steps: DiagramStep[]
}

/**
 * Strip dangerous elements from LLM-generated SVG before rendering.
 */
function sanitizeSvg(svg: string): string {
  return svg
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<foreignObject[\s\S]*?<\/foreignObject>/gi, '')
    .replace(/\bon\w+\s*=\s*["'][^"']*["']/gi, '')
    .replace(/javascript\s*:/gi, '')
}

export function DiagramBuilderBlock({ title, steps }: DiagramBuilderBlockProps) {
  const safeSteps = Array.isArray(steps) ? steps : []
  const [currentStep, setCurrentStep] = useState(0)

  const clampedStep = Math.min(currentStep, Math.max(0, safeSteps.length - 1))

  // Accumulate SVG fragments up to and including the current step.
  // eslint-disable-next-line react-hooks/exhaustive-deps -- safeSteps identity changes
  // every render but content is stable (props coerced once from the parsed program).
  const cumulativeSvg = useMemo(() => {
    return safeSteps
      .slice(0, clampedStep + 1)
      .map((s) => s.svgFragment)
      .join('\n')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [safeSteps.length, clampedStep])

  const currentStepData = safeSteps[clampedStep]

  function handlePrev() {
    setCurrentStep((prev) => Math.max(0, prev - 1))
  }

  function handleNext() {
    setCurrentStep((prev) => Math.min(safeSteps.length - 1, prev + 1))
  }

  if (safeSteps.length === 0) {
    return (
      <div data-no-explain="" className={`${INLINE_SURFACE} bg-bg-subtle`}>
        {title ? <p className={BLOCK_TITLE}>{title}</p> : null}
        <p className="text-sm text-text-muted">Sin pasos definidos</p>
      </div>
    )
  }

  return (
    <div data-no-explain="" className={`${INLINE_SURFACE} bg-bg-subtle`}>
      {title ? <p className={BLOCK_TITLE}>{title}</p> : null}

      {/* SVG container */}
      <div className="rounded-lg border border-border bg-bg p-3 mb-4 overflow-auto">
        <svg
          viewBox="0 0 400 300"
          className="w-full h-auto max-h-72"
          role="img"
          aria-label={currentStepData?.label ?? title}
          dangerouslySetInnerHTML={{ __html: sanitizeSvg(cumulativeSvg) }}
        />
      </div>

      {/* Current step info */}
      <AnimatePresence mode="wait">
        <motion.div
          key={clampedStep}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: duration.fast, ease: ease.base }}
          className="mb-4"
        >
          {currentStepData && (
            <>
              <p className="text-sm font-medium text-text mb-1">
                {currentStepData.label}
              </p>
              <p className="text-xs text-text-secondary leading-relaxed">
                {currentStepData.explanation}
              </p>
            </>
          )}
        </motion.div>
      </AnimatePresence>

      {/* Navigation */}
      <div className="flex items-center justify-between">
        <Button
          size="sm"
          variant="secondary"
          onClick={handlePrev}
          disabled={clampedStep === 0}
        >
          Anterior
        </Button>

        <span className="text-xs text-text-muted tabular-nums">
          Paso {clampedStep + 1} de {safeSteps.length}
        </span>

        <Button
          size="sm"
          onClick={handleNext}
          disabled={clampedStep >= safeSteps.length - 1}
        >
          Siguiente
        </Button>
      </div>
    </div>
  )
}
