import { useState } from 'react'
import { Button } from '../ui'
import { useSubmitAttempt, useCorrectExercise } from '../../api/exercises'
import { ExerciseResult } from './ExerciseResult'
import type { Exercise, TestContent } from '../../types'

export function TestExercise({ exercise }: { exercise: Exercise }) {
  const content = exercise.content as TestContent
  const [selected, setSelected] = useState<number | null>(null)
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
        const idx = data.correct_answer?.selected as number | undefined
        if (idx != null) setSelected(idx)
      },
    })
  }

  return (
    <div>
      <p className="text-sm text-text mb-4">{content.question}</p>

      <div className="space-y-2">
        {(content.options ?? []).map((option, idx) => (
          <label
            key={idx}
            className={`flex items-center gap-3 p-3 border rounded-lg transition-colors ${
              done ? 'cursor-default' : 'cursor-pointer'
            } ${selected === idx && !done ? 'border-primary' : 'border-border'}`}
          >
            <input
              type="radio"
              name={exercise.id}
              checked={selected === idx}
              onChange={() => !done && setSelected(idx)}
              disabled={done}
              className="accent-primary"
            />
            <span className="text-sm text-text break-words min-w-0">{option}</span>
          </label>
        ))}
      </div>

      {!done && (
        <Button
          size="sm"
          className="mt-4"
          disabled={selected === null || submit.isPending}
          onClick={() =>
            selected !== null &&
            submit.mutate({ exerciseId: exercise.id, answer: { selected } })
          }
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
