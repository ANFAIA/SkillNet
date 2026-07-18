import { Fragment } from 'react'
import type { GenerationProgress as GenerationProgressData, GenerationStep } from '../../types'

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
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

export function GenerationProgress({ progress }: { progress: GenerationProgressData }) {
  const isFailed = progress.step === 'failed'
  const currentIndex = isFailed ? -1 : STEP_ORDER.indexOf(progress.step)

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {STEPS.map((step, i) => {
          const isCompleted = i < currentIndex
          const isCurrent = i === currentIndex && !isFailed

          return (
            <Fragment key={step.key}>
              {i > 0 && (
                <div className={`flex-1 h-0.5 ${isCompleted ? 'bg-primary' : 'bg-bg-muted'}`} />
              )}
              <div className="flex flex-col items-center gap-1">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium shrink-0 ${
                    isCompleted
                      ? 'bg-primary text-white'
                      : isCurrent
                        ? 'border-2 border-primary text-primary'
                        : 'border border-border text-text-muted'
                  }`}
                >
                  {isCompleted ? <CheckIcon /> : i + 1}
                </div>
                <span
                  className={`text-xs text-center ${
                    isCurrent ? 'text-text font-medium' : 'text-text-muted'
                  }`}
                >
                  {step.label}
                </span>
              </div>
            </Fragment>
          )
        })}
      </div>

      {progress.message && !isFailed && (
        <p className="text-sm text-text-secondary text-center">{progress.message}</p>
      )}

      {isFailed && progress.error && (
        <div className="text-sm text-danger border border-danger/30 rounded-md p-3">
          {progress.error}
        </div>
      )}
    </div>
  )
}
