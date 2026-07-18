import type { AttemptResult } from '../../types'

// Shown after an attempt is graded by the server.
export function ExerciseResult({ result }: { result: AttemptResult }) {
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
    </div>
  )
}
