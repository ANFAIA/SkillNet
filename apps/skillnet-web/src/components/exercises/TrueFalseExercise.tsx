import { useState } from 'react'
import { useIntl } from 'react-intl'
import { Button } from '../ui'
import { useSubmitAttempt, useCorrectExercise } from '../../api/exercises'
import { ExerciseResult } from './ExerciseResult'
import type { Exercise, TrueFalseContent } from '../../types'

export function TrueFalseExercise({ exercise }: { exercise: Exercise }) {
  const intl = useIntl()
  const content = exercise.content as TrueFalseContent
  const [answer, setAnswer] = useState<boolean | null>(null)
  const submit = useSubmitAttempt()
  const correctMut = useCorrectExercise()
  const result = correctMut.data ?? submit.data
  const done = result?.passed ?? false

  function retry() {
    submit.reset()
    correctMut.reset()
  }

  function correct() {
    correctMut.mutate(exercise.id, {
      onSuccess: (data) => {
        const val = data.correct_answer?.answer as boolean | undefined
        if (val != null) setAnswer(val)
      },
    })
  }

  const options: { label: string; value: boolean }[] = [
    { label: intl.formatMessage({ id: 'exercise.true' }), value: true },
    { label: intl.formatMessage({ id: 'exercise.false' }), value: false },
  ]

  return (
    <div>
      <p className="text-sm text-text mb-4">{content.statement}</p>

      <div className="flex gap-2">
        {options.map((opt) => (
          <button
            key={opt.label}
            type="button"
            disabled={done}
            onClick={() => !done && setAnswer(opt.value)}
            className={`flex-1 p-3 text-sm font-medium border rounded-lg transition-colors ${
              answer === opt.value
                ? 'border-primary bg-primary-subtle text-primary'
                : 'border-border text-text hover:bg-bg-subtle'
            } disabled:cursor-default`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {!done && (
        <Button
          size="sm"
          className="mt-4"
          disabled={answer === null || submit.isPending}
          onClick={() =>
            answer !== null &&
            submit.mutate({ exerciseId: exercise.id, answer: { answer } })
          }
        >
          {submit.isPending ? intl.formatMessage({ id: 'exercise.checking' }) : intl.formatMessage({ id: 'exercise.check' })}
        </Button>
      )}

      {submit.isError && (
        <p className="mt-3 text-sm text-danger">{intl.formatMessage({ id: 'exercise.submitError' })}</p>
      )}
      {result && <ExerciseResult result={result} onRetry={!result.passed ? retry : undefined} onCorrect={!result.passed ? correct : undefined} />}
    </div>
  )
}
