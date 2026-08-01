import { useCallback, useMemo, useState } from 'react'
import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import type { DragEndEvent } from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Button } from '../../ui'
import { BLOCK_TITLE, INLINE_SURFACE } from './rhythm'

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
}: {
  item: ItemState
  correct: boolean | null
  status: ValidationStatus
}) {
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
      style={style}
      className={`flex items-center gap-3 p-3 border rounded-lg bg-bg select-none ${borderClass} ${isDragging ? 'shadow-md opacity-75' : ''}`}
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
      <span className="text-sm text-text min-w-0 break-words">{item.text}</span>
      {status === 'checked' && (
        <span
          className={`shrink-0 ml-auto text-xs font-medium ${correct ? 'text-accent' : 'text-danger'}`}
          aria-label={correct ? 'Posicion correcta' : 'Posicion incorrecta'}
        >
          {correct ? '\u2713' : '\u2717'}
        </span>
      )}
    </div>
  )
}

export function DragOrderBlock({ instruction, items, correctOrder }: DragOrderBlockProps) {
  const safeItems = Array.isArray(items) ? items : []
  const safeCorrect = Array.isArray(correctOrder) ? correctOrder : []

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

  function handleDragEnd(event: DragEndEvent) {
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

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={itemStates.map((s) => s.id)} strategy={verticalListSortingStrategy}>
          <div className="space-y-2">
            {itemStates.map((item) => (
              <SortableItem
                key={item.id}
                item={item}
                correct={correctMap?.get(item.id) ?? null}
                status={status}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>

      <div className="flex items-center gap-3 mt-4">
        <Button size="sm" onClick={handleCheck} disabled={status === 'checked'}>
          Comprobar
        </Button>
        <Button size="sm" variant="secondary" onClick={handleReset}>
          Reiniciar
        </Button>
      </div>

      {status === 'checked' && (
        <div
          role="status"
          className={`mt-4 rounded-lg border p-3 ${
            allCorrect ? 'border-accent bg-accent-subtle' : 'border-danger bg-danger/5'
          }`}
        >
          <span
            className={`text-sm font-medium ${allCorrect ? 'text-accent' : 'text-danger'}`}
          >
            {allCorrect
              ? 'Orden correcto'
              : `${correctMap ? [...correctMap.values()].filter(Boolean).length : 0} de ${safeCorrect.length} en la posicion correcta`}
          </span>
        </div>
      )}
    </div>
  )
}
