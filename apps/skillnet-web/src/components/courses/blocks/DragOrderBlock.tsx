import { useCallback, useMemo, useState } from 'react'
import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import type { DragEndEvent, DragStartEvent } from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { useIntl } from 'react-intl'
import { Button } from '../../ui'
import { BLOCK_TITLE, INLINE_SURFACE } from './rhythm'
import { useStepperSolve } from './StepperContext'

// Design decision (v1): correctOrder is in the program text (browser-visible).
// Unlike QuizItem (server-side grading), DragOrder validates locally because
// the exercise is formative, not summative. A server-side endpoint can be added
// in v2 if needed for certification scenarios.
export interface DragOrderBlockProps {
  instruction: string
  items: string[]
  correctOrder: string[]
}

type ValidationStatus = 'idle' | 'checked'

interface ItemState {
  id: string
  text: string
}

/**
 * Fisher-Yates shuffle. Returns a new array.
 */
function shuffle<T>(arr: T[]): T[] {
  const copy = [...arr]
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
  }
  return copy
}

function SortableItem({
  item,
  correct,
  status,
  index,
}: {
  item: ItemState
  correct: boolean | null
  status: ValidationStatus
  index: number
}) {
  const intl = useIntl()
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: item.id,
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 10 : undefined,
  }

  let borderClass = 'border-border'
  if (status === 'checked') {
    borderClass = correct ? 'border-accent bg-accent-subtle' : 'border-danger bg-danger/5'
  }

  return (
    <div
      ref={setNodeRef}
      style={{
        ...style,
        transitionProperty: 'border-color, background-color, opacity, transform',
        transitionDuration: '200ms',
        transitionDelay: status === 'checked' ? `${index * 100}ms` : '0ms',
      }}
      className={`flex items-center gap-3 p-4 border rounded-xl bg-bg select-none ${borderClass} ${isDragging ? 'opacity-90' : ''}`}
      {...attributes}
      {...listeners}
    >
      {/* Drag handle indicator */}
      <span
        aria-hidden="true"
        data-no-explain=""
        className="shrink-0 text-text-muted"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <circle cx="5" cy="3" r="1.5" />
          <circle cx="11" cy="3" r="1.5" />
          <circle cx="5" cy="8" r="1.5" />
          <circle cx="11" cy="8" r="1.5" />
          <circle cx="5" cy="13" r="1.5" />
          <circle cx="11" cy="13" r="1.5" />
        </svg>
      </span>
      <span className="text-lesson-body text-text min-w-0 break-words">{item.text}</span>
      {status === 'checked' && (
        <span
          className={`shrink-0 ml-auto text-xs font-medium ${correct ? 'text-accent' : 'text-danger'}`}
          aria-label={correct ? intl.formatMessage({ id: 'drag.positionCorrect' }) : intl.formatMessage({ id: 'drag.positionIncorrect' })}
        >
          {correct ? '\u2713' : '\u2717'}
        </span>
      )}
    </div>
  )
}

export function DragOrderBlock({ instruction, items, correctOrder }: DragOrderBlockProps) {
  const intl = useIntl()
  const safeItems = Array.isArray(items) ? items : []
  const safeCorrect = Array.isArray(correctOrder) ? correctOrder : []
  // Igual que QuizItem: el paso nace cerrado por llevar este bloque dentro
  // (`kit/solvableSteps.ts`) y solo lo abre acertar el orden. Abrir el paso NO
  // avanza: el aprendiz pulsa el boton cuando quiere.
  const solveStep = useStepperSolve()

  const buildItemStates = useCallback(
    () =>
      shuffle(safeItems).map((text, i) => ({
        id: `drag-${i}-${text}`,
        text,
      })),
    // Intentionally only on mount — the identity of safeItems changes every render
    // but the content is stable (props are coerced once from the parsed program).
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

  const [itemStates, setItemStates] = useState<ItemState[]>(buildItemStates)
  const [status, setStatus] = useState<ValidationStatus>('idle')
  const [activeId, setActiveId] = useState<string | null>(null)

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const correctMap = useMemo(() => {
    if (status !== 'checked') return null
    const map = new Map<string, boolean>()
    for (let i = 0; i < itemStates.length; i++) {
      map.set(itemStates[i].id, itemStates[i].text === safeCorrect[i])
    }
    return map
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, itemStates])

  function handleDragStart(event: DragStartEvent) {
    setActiveId(String(event.active.id))
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveId(null)
    const { active, over } = event
    if (!over || active.id === over.id) return

    setItemStates((prev) => {
      const oldIndex = prev.findIndex((item) => item.id === active.id)
      const newIndex = prev.findIndex((item) => item.id === over.id)
      return arrayMove(prev, oldIndex, newIndex)
    })
    // Reset validation when order changes
    if (status === 'checked') setStatus('idle')
  }

  function handleCheck() {
    setStatus('checked')
    // Acertar abre el paso (aparece el boton); no avanza solo.
    const isAllCorrect = itemStates.every((item, i) => item.text === safeCorrect[i])
    if (isAllCorrect) {
      solveStep?.()
    }
  }

  function handleReset() {
    setItemStates(
      shuffle(safeItems).map((text, i) => ({
        id: `drag-reset-${i}-${Date.now()}-${text}`,
        text,
      })),
    )
    setStatus('idle')
  }

  const allCorrect = status === 'checked' && correctMap && [...correctMap.values()].every(Boolean)

  return (
    <div data-no-explain="" className={`${INLINE_SURFACE} bg-bg-subtle`}>
      {instruction ? <p className={BLOCK_TITLE}>{instruction}</p> : null}

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        <SortableContext items={itemStates.map((s) => s.id)} strategy={verticalListSortingStrategy}>
          <div className="space-y-3">
            {itemStates.map((item, idx) => (
              <div
                key={item.id}
                style={{
                  opacity: activeId && activeId !== item.id ? 0.5 : 1,
                  transition: 'opacity 150ms ease',
                }}
              >
                <SortableItem
                  item={item}
                  correct={correctMap?.get(item.id) ?? null}
                  status={status}
                  index={idx}
                />
              </div>
            ))}
          </div>
        </SortableContext>
      </DndContext>

      <div className="flex items-center gap-3 mt-4">
        <Button size="sm" onClick={handleCheck} disabled={status === 'checked'}>
          {intl.formatMessage({ id: 'drag.check' })}
        </Button>
        <Button size="sm" variant="secondary" onClick={handleReset}>
          {intl.formatMessage({ id: 'drag.reset' })}
        </Button>
      </div>

      {status === 'checked' && (
        <div
          role="status"
          className={`mt-4 rounded-xl border p-4 ${
            allCorrect ? 'border-accent bg-accent-subtle' : 'border-danger bg-danger/5'
          }`}
        >
          <span
            className={`text-lesson-body font-medium ${allCorrect ? 'text-accent' : 'text-danger'}`}
          >
            {allCorrect
              ? intl.formatMessage({ id: 'drag.correctOrder' })
              : intl.formatMessage({ id: 'drag.positionsCorrect' }, {
                  count: correctMap ? [...correctMap.values()].filter(Boolean).length : 0,
                  total: safeCorrect.length,
                })}
          </span>
        </div>
      )}
    </div>
  )
}
