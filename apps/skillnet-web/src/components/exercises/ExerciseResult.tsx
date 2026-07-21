import type { AttemptResult } from '../../types'

// Shown after an attempt is graded by the server.
export function ExerciseResult({ result, onRetry, onCorrect }: { result: AttemptResult; onRetry?: () => void; onCorrect?: () => void }) {
  return (
    <div
      className={`mt-4 rounded-lg border p-4 ${
        result.passed ? 'border-accent bg-accent-subtle' : 'border-danger bg-danger/5'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className={`text-sm font-medium ${result.passed ? 'text-accent' : 'text-danger'}`}>
          {result.passed ? 'Correcto' : 'Incorrecto'}
        </span>
        <span className="text-xs text-text-secondary">
          Puntuacion: {Math.round(result.score)}
        </span>
      </div>
      {result.feedback && <p className="text-sm text-text mt-2">{result.feedback}</p>}
      {result.explanation && (
        <p className="text-sm text-text-secondary mt-2">{result.explanation}</p>
      )}
      {!result.passed && (onRetry || onCorrect) && (
        <div className="mt-3 flex items-center gap-4">
          {onRetry && (
            <button type="button" onClick={onRetry} className="text-sm font-medium text-primary hover:text-primary/80 transition-colors">
              Reintentar
            </button>
          )}
          {onCorrect && (
            <button type="button" onClick={onCorrect} className="text-sm font-medium text-accent hover:text-accent/80 transition-colors">
              Corregir
            </button>
          )}
        </div>
      )}
    </div>
  )
}
