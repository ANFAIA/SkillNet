import { useEffect, useId, useRef, useState } from 'react'

import type { DidactHostPorts, EvaluationResult } from '../../../lib/didact'
import { Button } from '../../ui/Button'
import { evaluateDidactSubmission } from './didact-evaluation-adapter'
import { usesSecureEvaluationAdapter } from './secure-evaluation-components'

type PublicProps = Readonly<Record<string, unknown>>
type Answer = string | boolean | string[] | Record<string, string>
type Choice = { id: string; content: string }
type QuizOption = { value: string; label: string }

function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item))
    : []
}

function choices(value: unknown): Choice[] {
  return records(value).flatMap((item) => (
    typeof item.id === 'string' && typeof item.content === 'string'
      ? [{ id: item.id, content: item.content }]
      : []
  ))
}

function options(value: unknown): QuizOption[] {
  return records(value).flatMap((item) => (
    typeof item.value === 'string' && typeof item.label === 'string'
      ? [{ value: item.value, label: item.label }]
      : []
  ))
}

function initialAnswer(componentId: string, props: PublicProps): Answer {
  if (componentId === 'didact.sort') return choices(props.items).map((item) => item.id)
  if (componentId === 'didact.quiz.multi-select') return []
  if (componentId === 'didact.quiz.true-false') return ''
  if (
    componentId === 'didact.matching'
    || componentId === 'didact.categorize'
    || componentId === 'didact.completion-problem'
    || componentId === 'didact.word-bank'
  ) return {}
  return ''
}

function titleFor(componentId: string, props: PublicProps): string {
  const value = componentId.startsWith('didact.quiz.')
    ? props.question
    : componentId === 'didact.completion-problem'
      ? props.problem
      : componentId === 'didact.numeric-question'
        ? props.prompt
        : props.title
  return typeof value === 'string' ? value : ''
}

function Result({ result }: { result: EvaluationResult }) {
  const copy = result.outcome === 'correct'
    ? 'Respuesta correcta.'
    : result.outcome === 'partial'
      ? 'Respuesta parcialmente correcta.'
      : result.outcome === 'unscored'
        ? 'Respuesta enviada para revisión.'
        : 'La respuesta necesita revisión.'
  return (
    <div className="rounded-lg border border-border bg-bg-subtle p-3 text-sm" role="status" aria-live="polite">
      <p className="font-medium text-text">{copy}</p>
      {typeof result.feedback === 'string' && result.feedback && (
        <p className="mt-1 text-text-secondary">{result.feedback}</p>
      )}
    </div>
  )
}

function SelectAssignments({
  items,
  destinations,
  value,
  disabled,
  onChange,
}: {
  items: Choice[]
  destinations: Choice[]
  value: Record<string, string>
  disabled: boolean
  onChange: (value: Record<string, string>) => void
}) {
  return (
    <fieldset className="space-y-3" disabled={disabled}>
      <legend className="sr-only">Asigna cada elemento a una opción</legend>
      {items.map((item) => (
        <label className="grid gap-1 text-sm" key={item.id}>
          <span className="font-medium text-text">{item.content}</span>
          <select
            className="rounded-lg border border-border bg-bg px-3 py-2 text-text"
            aria-label={`Asignación para ${item.content}`}
            value={value[item.id] ?? ''}
            onChange={(event) => onChange({ ...value, [item.id]: event.target.value })}
          >
            <option value="">Selecciona una opción</option>
            {destinations.map((destination) => (
              <option key={destination.id} value={destination.id}>{destination.content}</option>
            ))}
          </select>
        </label>
      ))}
    </fieldset>
  )
}

function SecureInteraction({
  componentId,
  props,
  answer,
  disabled,
  onChange,
  groupName,
}: {
  componentId: string
  props: PublicProps
  answer: Answer
  disabled: boolean
  onChange: (answer: Answer) => void
  groupName: string
}) {
  if (componentId === 'didact.matching') {
    return <SelectAssignments items={choices(props.sources)} destinations={choices(props.targets)} value={answer as Record<string, string>} disabled={disabled} onChange={onChange} />
  }
  if (componentId === 'didact.categorize') {
    return <SelectAssignments items={choices(props.items)} destinations={choices(props.categories)} value={answer as Record<string, string>} disabled={disabled} onChange={onChange} />
  }
  if (componentId === 'didact.word-bank') {
    const gaps = records(props.gaps).map((gap) => ({
      id: String(gap.id ?? ''),
      content: [gap.before, gap.prompt, '____', gap.after].filter((part) => typeof part === 'string' && part).join(' '),
    })).filter((gap) => gap.id)
    return <SelectAssignments items={gaps} destinations={choices(props.options)} value={answer as Record<string, string>} disabled={disabled} onChange={onChange} />
  }
  if (componentId === 'didact.sort') {
    const itemById = new Map(choices(props.items).map((item) => [item.id, item]))
    const order = answer as string[]
    const move = (index: number, offset: number) => {
      const next = [...order]
      const target = index + offset
      if (target < 0 || target >= next.length) return
      ;[next[index], next[target]] = [next[target], next[index]]
      onChange(next)
    }
    return (
      <ol className="space-y-2" aria-label="Elementos en el orden actual">
        {order.map((id, index) => (
          <li className="flex items-center gap-2 rounded-lg border border-border p-2" key={id}>
            <span className="min-w-0 flex-1 text-sm text-text">{itemById.get(id)?.content}</span>
            <Button type="button" variant="secondary" size="sm" disabled={disabled || index === 0} aria-label={`Subir ${itemById.get(id)?.content}`} onClick={() => move(index, -1)}>↑</Button>
            <Button type="button" variant="secondary" size="sm" disabled={disabled || index === order.length - 1} aria-label={`Bajar ${itemById.get(id)?.content}`} onClick={() => move(index, 1)}>↓</Button>
          </li>
        ))}
      </ol>
    )
  }
  if (componentId === 'didact.quiz.single-choice') {
    return (
      <fieldset disabled={disabled} className="space-y-2">
        <legend className="sr-only">Elige una respuesta</legend>
        {options(props.options).map((option) => (
          <label className="flex items-center gap-2 text-sm text-text" key={option.value}>
            <input type="radio" name={groupName} value={option.value} checked={answer === option.value} onChange={() => onChange(option.value)} />
            {option.label}
          </label>
        ))}
      </fieldset>
    )
  }
  if (componentId === 'didact.quiz.multi-select') {
    const selected = answer as string[]
    return (
      <fieldset disabled={disabled} className="space-y-2">
        <legend className="sr-only">Elige todas las respuestas aplicables</legend>
        {options(props.options).map((option) => (
          <label className="flex items-center gap-2 text-sm text-text" key={option.value}>
            <input
              type="checkbox"
              checked={selected.includes(option.value)}
              onChange={(event) => onChange(event.target.checked ? [...selected, option.value] : selected.filter((value) => value !== option.value))}
            />
            {option.label}
          </label>
        ))}
      </fieldset>
    )
  }
  if (componentId === 'didact.quiz.true-false') {
    return (
      <fieldset disabled={disabled} className="space-y-2">
        <legend className="sr-only">Indica si es verdadero o falso</legend>
        {[['true', 'Verdadero'], ['false', 'Falso']].map(([value, label]) => (
          <label className="flex items-center gap-2 text-sm text-text" key={value}>
            <input type="radio" name={groupName} checked={typeof answer === 'boolean' && answer === (value === 'true')} onChange={() => onChange(value === 'true')} />
            {label}
          </label>
        ))}
      </fieldset>
    )
  }
  if (componentId === 'didact.completion-problem') {
    const values = answer as Record<string, string>
    return (
      <div className="space-y-3">
        {records(props.steps).map((step) => {
          const id = String(step.id ?? '')
          if (step.kind === 'worked') return <p className="rounded-lg bg-bg-subtle p-3 text-sm text-text" key={id}>{String(step.content ?? '')}</p>
          return (
            <label className="grid gap-1 text-sm" key={id}>
              <span className="font-medium text-text">{String(step.prompt ?? '')}</span>
              <input className="rounded-lg border border-border bg-bg px-3 py-2 text-text" disabled={disabled} value={values[id] ?? ''} onChange={(event) => onChange({ ...values, [id]: event.target.value })} />
            </label>
          )
        })}
      </div>
    )
  }
  const multiline = componentId === 'didact.quiz.short-answer'
  const unit = props.unit && typeof props.unit === 'object' && !Array.isArray(props.unit)
    ? props.unit as Record<string, unknown>
    : undefined
  const input = multiline ? (
    <textarea className="min-h-28 w-full rounded-lg border border-border bg-bg px-3 py-2 text-text" disabled={disabled} value={String(answer)} onChange={(event) => onChange(event.target.value)} />
  ) : (
    <input
      className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-text"
      inputMode={componentId === 'didact.numeric-question' ? 'decimal' : 'text'}
      disabled={disabled}
      value={String(answer)}
      onChange={(event) => onChange(event.target.value)}
    />
  )
  return (
    <label className="grid gap-1 text-sm">
      <span className="font-medium text-text">Tu respuesta{unit?.policy === 'required' ? ` (incluye ${String(unit.symbol)})` : ''}</span>
      <span className="flex items-center gap-2">{input}{unit?.policy === 'display' && <span>{String(unit.symbol)}</span>}</span>
    </label>
  )
}

function canSubmit(componentId: string, props: PublicProps, answer: Answer): boolean {
  if (typeof answer === 'string') return answer.trim().length > 0
  if (typeof answer === 'boolean') return true
  if (Array.isArray(answer)) return answer.length > 0
  const expectedCount = componentId === 'didact.matching'
    ? choices(props.sources).length
    : componentId === 'didact.categorize'
      ? choices(props.items).length
      : componentId === 'didact.word-bank'
        ? records(props.gaps).length
        : componentId === 'didact.completion-problem'
          ? records(props.steps).filter((step) => step.kind === 'completion').length
          : 0
  return expectedCount > 0 && Object.values(answer).filter((value) => value.trim()).length === expectedCount
}

export function SecureEvaluatedActivity({
  activityId,
  componentId,
  componentProps,
  ports,
}: {
  activityId: string
  componentId: string
  componentProps: PublicProps
  ports: DidactHostPorts
}) {
  const titleId = useId()
  const groupName = useId()
  const startedEventId = useRef(crypto.randomUUID())
  const title = titleFor(componentId, componentProps)
  const [answer, setAnswer] = useState<Answer>(() => initialAnswer(componentId, componentProps))
  const [result, setResult] = useState<EvaluationResult>()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    void ports.events?.emit({
      version: 1,
      eventId: startedEventId.current,
      activityId,
      type: 'started',
      occurredAt: new Date().toISOString(),
      scope: { organizationId: '', courseId: '' },
      componentId,
      payload: {},
    }).catch(() => undefined)
  }, [activityId, componentId, ports.events])

  if (!usesSecureEvaluationAdapter(componentId) || !title) {
    return <div role="status" data-didact-status="blocked">La actividad no tiene una definición pública válida.</div>
  }

  const submit = async () => {
    setPending(true)
    setError(false)
    try {
      setResult(await evaluateDidactSubmission(activityId, componentId, ports, answer))
    } catch {
      setError(true)
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="w-full max-w-2xl rounded-lg border border-border bg-bg p-5" aria-labelledby={titleId} data-didact-secure-adapter={componentId}>
      <h3 className="mb-1 text-lg font-semibold text-text" id={titleId}>{title}</h3>
      {typeof componentProps.instructions === 'string' && <p className="mb-4 text-sm text-text-secondary">{componentProps.instructions}</p>}
      <div className="mt-4">
        <SecureInteraction componentId={componentId} props={componentProps} answer={answer} disabled={pending || Boolean(result)} onChange={setAnswer} groupName={groupName} />
      </div>
      <div className="mt-4 space-y-3">
        {result ? <Result result={result} /> : (
          <Button type="button" disabled={pending || !canSubmit(componentId, componentProps, answer)} onClick={() => void submit()}>
            {pending ? 'Comprobando…' : 'Comprobar respuesta'}
          </Button>
        )}
        {error && <p className="text-sm text-danger" role="alert">No se pudo evaluar la respuesta. Inténtalo de nuevo.</p>}
      </div>
    </section>
  )
}
