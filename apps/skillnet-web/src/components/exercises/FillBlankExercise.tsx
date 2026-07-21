import { useMemo, useState } from 'react'
import { Button } from '../ui'
import { useSubmitAttempt, useCorrectExercise } from '../../api/exercises'
import { ExerciseResult } from './ExerciseResult'
import type { Exercise, FillBlankContent } from '../../types'

// Blanks in the template are runs of 2+ underscores or {{ }} placeholders.
const BLANK_RE = /_{2,}|\{\{.*?\}\}/g

export function FillBlankExercise({ exercise }: { exercise: Exercise }) {
  const content = exercise.content as FillBlankContent
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
        const blanks = data.correct_answer?.answers as string[] | undefined
        if (blanks) setAnswers(blanks)
      },
    })
  }

  const segments = useMemo(() => content.template.split(BLANK_RE), [content.template])
  const blankCount = Math.max(0, segments.length - 1)

  const [answers, setAnswers] = useState<string[]>(() => Array(blankCount).fill(''))

  function setAnswer(idx: number, value: string) {
    setAnswers((prev) => prev.map((a, i) => (i === idx ? value : a)))
  }

  const allFilled = answers.every((a) => a.trim().length > 0)

  return (
    <div>
      <div className="text-sm text-text leading-8">
        {segments.map((seg, i) => (
          <span key={i}>
            {seg}
            {i < blankCount && (
              <input
                type="text"
                value={answers[i]}
                disabled={done}
                onChange={(e) => setAnswer(i, e.target.value)}
                className="inline-block mx-1 px-2 py-0.5 w-32 text-sm border-b border-border bg-bg-subtle rounded focus:outline-none focus:border-primary disabled:opacity-60"
              />
            )}
          </span>
        ))}
      </div>

      {!done && (
        <Button
          size="sm"
          className="mt-4"
          disabled={!allFilled || submit.isPending}
          onClick={() => submit.mutate({ exerciseId: exercise.id, answer: { answers } })}
        >
          {submit.isPending ? 'Comprobando...' : 'Comprobar'}
        </Button>
      )}

      {submit.isError && (
        <p className="mt-3 text-sm text-danger">No se pudo enviar la respuesta.</p>
      )}
      {result && <ExerciseResult result={result} onRetry={!result.passed ? retry : undefined} onCorrect={!result.passed ? correct : undefined} />}
    </div>
  )
}
