import { useState } from 'react'
import { useIntl } from 'react-intl'
import { Button } from '../ui'
import { useSubmitAttempt } from '../../api/exercises'
import { ExerciseResult } from './ExerciseResult'
import type { Exercise, PracticalCaseContent } from '../../types'

export function PracticalCaseExercise({ exercise }: { exercise: Exercise }) {
  const intl = useIntl()
  const content = exercise.content as PracticalCaseContent
  const [response, setResponse] = useState('')
  const submit = useSubmitAttempt()
  const result = submit.data
  const done = result?.passed ?? false

  function retry() {
    submit.reset()
  }

  return (
    <div>
      <div className="rounded-lg bg-bg-subtle border border-border p-3 mb-3">
        <p className="text-sm text-text-secondary">{content.context}</p>
      </div>
      <p className="text-sm font-medium text-text mb-3">{content.question}</p>

      <textarea
        value={response}
        disabled={done}
        onChange={(e) => setResponse(e.target.value)}
        rows={5}
        placeholder={intl.formatMessage({ id: 'exercise.responsePlaceholder' })}
        className="w-full px-3 py-2 text-sm text-text border border-border rounded-lg bg-bg placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors disabled:opacity-60 resize-y"
      />

      {!done && (
        <Button
          size="sm"
          className="mt-4"
          disabled={!response.trim() || submit.isPending}
          onClick={() =>
            submit.mutate({ exerciseId: exercise.id, answer: { response: response.trim() } })
          }
        >
          {submit.isPending ? intl.formatMessage({ id: 'exercise.submitting' }) : intl.formatMessage({ id: 'exercise.submitResponse' })}
        </Button>
      )}

      {submit.isError && (
        <p className="mt-3 text-sm text-danger">{intl.formatMessage({ id: 'exercise.submitError' })}</p>
      )}
      {result && <ExerciseResult result={result} onRetry={!result.passed ? retry : undefined} />}
    </div>
  )
}
