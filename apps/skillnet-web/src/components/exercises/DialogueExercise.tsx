import { useState } from 'react'
import { Button } from '../ui'
import { useSubmitAttempt } from '../../api/exercises'
import { ExerciseResult } from './ExerciseResult'
import type { Exercise, DialogueContent } from '../../types'

interface Turn {
  role: 'user' | 'assistant'
  content: string
}

export function DialogueExercise({ exercise }: { exercise: Exercise }) {
  const content = exercise.content as DialogueContent
  const [messages, setMessages] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const submit = useSubmitAttempt()
  const result = submit.data
  const done = !!result

  function addTurn() {
    const text = input.trim()
    if (!text) return
    setMessages((prev) => [...prev, { role: 'user', content: text }])
    setInput('')
  }

  return (
    <div>
      <div className="rounded-lg bg-bg-subtle border border-border p-3 mb-3">
        <p className="text-sm text-text-secondary">{content.context}</p>
      </div>

      {messages.length > 0 && (
        <div className="space-y-2 mb-3">
          {messages.map((m, i) => (
            <div key={i} className="flex justify-end">
              <div className="max-w-[80%] px-3 py-2 text-sm bg-primary text-white rounded-xl rounded-br-sm">
                {m.content}
              </div>
            </div>
          ))}
        </div>
      )}

      {!done && (
        <>
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  addTurn()
                }
              }}
              placeholder="Escribe tu intervencion..."
              className="flex-1 px-3 py-2 text-sm text-text border border-border rounded-lg bg-bg placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors"
            />
            <Button size="sm" variant="secondary" onClick={addTurn} disabled={!input.trim()}>
              Añadir
            </Button>
          </div>

          <Button
            size="sm"
            className="mt-4"
            disabled={messages.length === 0 || submit.isPending}
            onClick={() => submit.mutate({ exerciseId: exercise.id, answer: { messages } })}
          >
            {submit.isPending ? 'Enviando...' : 'Enviar dialogo'}
          </Button>
        </>
      )}

      {submit.isError && (
        <p className="mt-3 text-sm text-danger">No se pudo enviar la respuesta.</p>
      )}
      {result && <ExerciseResult result={result} />}
    </div>
  )
}
