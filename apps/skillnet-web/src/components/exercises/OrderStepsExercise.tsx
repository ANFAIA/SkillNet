import { useState } from 'react'
import { useIntl } from 'react-intl'
import { Button } from '../ui'
import { useSubmitAttempt, useCorrectExercise } from '../../api/exercises'
import { ExerciseResult } from './ExerciseResult'
import type { Exercise, OrderStepsContent } from '../../types'

export function OrderStepsExercise({ exercise }: { exercise: Exercise }) {
  const intl = useIntl()
  const content = exercise.content as OrderStepsContent
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
        const order = data.correct_answer?.order as number[] | undefined
        if (order) setOrder(order)
      },
    })
  }

  // Track the original index of each step; user reorders the arrangement.
  const [order, setOrder] = useState<number[]>(() => content.steps.map((_, i) => i))

  function move(pos: number, dir: -1 | 1) {
    const target = pos + dir
    if (target < 0 || target >= order.length) return
    setOrder((prev) => {
      const next = [...prev]
      ;[next[pos], next[target]] = [next[target], next[pos]]
      return next
    })
  }

  return (
    <div>
      <p className="text-sm text-text mb-4">{content.instruction}</p>

      <ol className="space-y-2">
        {(order ?? []).map((originalIdx, pos) => (
          <li
            key={originalIdx}
            className="flex items-center gap-3 p-3 border border-border rounded-lg"
          >
            <span className="text-xs font-medium text-text-muted w-5 shrink-0">{pos + 1}</span>
            <span className="text-sm text-text flex-1 min-w-0">{content.steps[originalIdx]}</span>
            {!done && (
              <span className="flex flex-col shrink-0">
                <button
                  type="button"
                  aria-label={intl.formatMessage({ id: 'exercise.moveUp' })}
                  disabled={pos === 0}
                  onClick={() => move(pos, -1)}
                  className="text-text-muted hover:text-text disabled:opacity-30 cursor-pointer"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="18 15 12 9 6 15" /></svg>
                </button>
                <button
                  type="button"
                  aria-label={intl.formatMessage({ id: 'exercise.moveDown' })}
                  disabled={pos === order.length - 1}
                  onClick={() => move(pos, 1)}
                  className="text-text-muted hover:text-text disabled:opacity-30 cursor-pointer"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9" /></svg>
                </button>
              </span>
            )}
          </li>
        ))}
      </ol>

      {!done && (
        <Button
          size="sm"
          className="mt-4"
          disabled={submit.isPending}
          onClick={() => submit.mutate({ exerciseId: exercise.id, answer: { order } })}
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
