import * as React from "react";
import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@didact/ui";

import { cn } from "../lib/cn.js";

/** A stable id plus the content shown for an exercise item or destination. */
export interface ExerciseChoice {
  id: string;
  content: React.ReactNode;
}

export type ExerciseAssignments = Record<string, string>;

export interface ExerciseSubmission<T> {
  value: T;
  correct: boolean;
}

interface ExerciseBaseProps {
  title: React.ReactNode;
  instructions?: React.ReactNode;
  feedback?: React.ReactNode;
  submitLabel?: string;
  className?: string;
}

function useControllable<T>(
  controlled: T | undefined,
  initial: T,
  onChange?: (value: T) => void,
): [T, (value: T) => void] {
  const isControlled = controlled !== undefined;
  const [uncontrolled, setUncontrolled] = React.useState(initial);
  const current = isControlled ? (controlled as T) : uncontrolled;
  const update = React.useCallback(
    (next: T) => {
      if (!isControlled) setUncontrolled(next);
      onChange?.(next);
    },
    [isControlled, onChange],
  );
  return [current, update];
}

function CheckIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" {...props}>
      <path d="M3 8.5 6.5 12 13 4.5" />
    </svg>
  );
}

function CrossIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" {...props}>
      <path d="M4 4l8 8M12 4l-8 8" />
    </svg>
  );
}

function GripIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" {...props}>
      <circle cx="5" cy="4" r="1" /><circle cx="11" cy="4" r="1" />
      <circle cx="5" cy="8" r="1" /><circle cx="11" cy="8" r="1" />
      <circle cx="5" cy="12" r="1" /><circle cx="11" cy="12" r="1" />
    </svg>
  );
}

function ArrowIcon({ direction, ...props }: React.SVGProps<SVGSVGElement> & { direction: "up" | "down" }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" {...props}>
      <path d={direction === "up" ? "M3 10l5-5 5 5" : "M3 6l5 5 5-5"} />
    </svg>
  );
}

function ExerciseResult({ correct }: { correct: boolean }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex items-center gap-2 rounded-md border p-3 text-sm font-medium",
        correct ? "border-primary/40 bg-primary/5" : "border-destructive/40 bg-destructive/5",
      )}
    >
      {correct ? <CheckIcon className="size-4 text-primary" /> : <CrossIcon className="size-4 text-destructive" />}
      <span>{correct ? "Correct" : "Not quite"}</span>
    </div>
  );
}

interface ExerciseShellProps extends ExerciseBaseProps {
  rootRef?: React.Ref<HTMLDivElement>;
  titleId: string;
  submitted: boolean;
  correct: boolean;
  canSubmit: boolean;
  onSubmit: () => void;
  empty: boolean;
  children: React.ReactNode;
}

function ExerciseShell({
  title,
  titleId,
  instructions,
  feedback,
  submitLabel = "Check answer",
  submitted,
  correct,
  canSubmit,
  onSubmit,
  empty,
  className,
  children,
  rootRef,
}: ExerciseShellProps) {
  return (
    <Card ref={rootRef} className={cn("w-full max-w-2xl", className)} data-slot="matching-exercise">
      <CardHeader>
        <CardTitle id={titleId}>{title}</CardTitle>
        {instructions ? <CardDescription>{instructions}</CardDescription> : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4" aria-labelledby={titleId}>
        {empty ? <p className="text-sm text-muted-foreground">There are no items in this exercise.</p> : children}
        {submitted ? <ExerciseResult correct={correct} /> : null}
        {submitted && feedback ? <div className="rounded-md bg-muted p-3 text-sm text-muted-foreground">{feedback}</div> : null}
      </CardContent>
      {!submitted && !empty ? (
        <CardFooter>
          <Button type="button" onClick={onSubmit} disabled={!canSubmit}>{submitLabel}</Button>
        </CardFooter>
      ) : null}
    </Card>
  );
}

function sameAssignments(actual: ExerciseAssignments, expected: ExerciseAssignments, ids: string[]) {
  return ids.every((id) => actual[id] === expected[id]);
}

interface DraggableChoiceProps {
  dragId: string;
  choice: ExerciseChoice;
  selected: boolean;
  assignedLabel?: React.ReactNode;
  disabled: boolean;
  onSelect: () => void;
  matchNodeId?: string;
}

function DraggableChoice({ dragId, choice, selected, assignedLabel, disabled, onSelect, matchNodeId }: DraggableChoiceProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: dragId, disabled });
  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined;
  return (
    <div
      ref={setNodeRef}
      data-match-source={matchNodeId}
      style={style}
      className={cn(
        "flex min-h-10 w-full items-center gap-1 rounded-md border bg-background p-1",
        selected && "border-primary bg-primary/5",
        isDragging && "z-20 opacity-70",
      )}
    >
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label={`Drag ${String(choice.content)}`}
        disabled={disabled}
        {...attributes}
        {...listeners}
      >
        <GripIcon className="size-4 text-muted-foreground" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        aria-label={`Select ${String(choice.content)}`}
        aria-pressed={selected}
        onClick={onSelect}
        disabled={disabled}
        className="h-auto min-h-8 min-w-0 flex-1 justify-start whitespace-normal px-2 py-1 text-left"
      >
        <span className="flex-1">{choice.content}</span>
        {assignedLabel ? <span className="text-xs text-muted-foreground">{assignedLabel}</span> : null}
      </Button>
    </div>
  );
}

interface MatchingNodeProps {
  side: "source" | "target";
  choice: ExerciseChoice;
  dragId?: string;
  dropId?: string;
  selected?: boolean;
  connected?: boolean;
  connectedText?: React.ReactNode;
  disabled: boolean;
  onActivate: () => void;
}

function MatchingNode({
  side,
  choice,
  dragId = `inactive-source:${choice.id}`,
  dropId = `inactive-target:${choice.id}`,
  selected = false,
  connected = false,
  connectedText,
  disabled,
  onActivate,
}: MatchingNodeProps) {
  const draggable = useDraggable({ id: dragId, disabled: disabled || side !== "source" });
  const droppable = useDroppable({ id: dropId, disabled: disabled || side !== "target" });
  const style = draggable.transform
    ? { transform: `translate3d(${draggable.transform.x}px, ${draggable.transform.y}px, 0)` }
    : undefined;
  const point = (
    <span
      data-connected={connected || undefined}
      data-match-source={side === "source" ? choice.id : undefined}
      data-match-target={side === "target" ? choice.id : undefined}
      className={cn(
        "size-3 shrink-0 rounded-full border-2 border-primary bg-background",
        (connected || selected) && "bg-primary",
        droppable.isOver && "bg-primary",
      )}
      aria-hidden="true"
    />
  );
  const content = (
    <>
      {side === "target" ? point : null}
      <span className="flex min-h-9 min-w-0 flex-1 items-center px-2 py-1 text-sm font-medium">
        <span className="flex-1">{choice.content}</span>
        {connectedText ? <span className="sr-only">{connectedText}</span> : null}
      </span>
      {side === "source" ? point : null}
    </>
  );
  const nodeClassName = cn(
    "relative z-20 flex min-h-12 w-full items-center gap-1 rounded-md border border-border bg-background p-1 text-left transition-colors",
    "focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
    selected && "border-primary bg-accent",
    droppable.isOver && "border-primary bg-accent",
  );

  if (side === "source") {
    return (
      <button
        ref={draggable.setNodeRef}
        type="button"
        {...draggable.attributes}
        {...draggable.listeners}
        aria-label={`Select ${String(choice.content)} for matching`}
        aria-pressed={selected}
        onClick={onActivate}
        disabled={disabled}
        style={style}
        className={cn(nodeClassName, "touch-none hover:border-primary/60 hover:bg-accent disabled:pointer-events-none disabled:opacity-50")}
      >
        {content}
      </button>
    );
  }

  return (
    <button
      ref={droppable.setNodeRef}
      type="button"
      aria-label={`Select ${String(choice.content)} for matching`}
      aria-pressed={selected}
      disabled={disabled}
      onClick={onActivate}
      className={cn(nodeClassName, "hover:border-primary/60 hover:bg-accent disabled:pointer-events-none disabled:opacity-50")}
    >
      {content}
    </button>
  );
}

interface ConnectorPath {
  sourceId: string;
  d: string;
  startX: number;
  startY: number;
  endX: number;
  endY: number;
}

function MatchingConnectors({
  wrapperRef,
  matches,
}: {
  wrapperRef: React.RefObject<HTMLDivElement | null>;
  matches: ExerciseAssignments;
}) {
  const [paths, setPaths] = React.useState<ConnectorPath[]>([]);

  React.useLayoutEffect(() => {
    const measure = () => {
      const wrapper = wrapperRef.current;
      if (!wrapper) return;
      const origin = wrapper.getBoundingClientRect();
      const sources = new Map(
        Array.from(wrapper.querySelectorAll<HTMLElement>("[data-match-source]"))
          .map((node) => [node.dataset.matchSource!, node] as const),
      );
      const targets = new Map(
        Array.from(wrapper.querySelectorAll<HTMLElement>("[data-match-target]"))
          .map((node) => [node.dataset.matchTarget!, node] as const),
      );
      const next = Object.entries(matches).flatMap(([sourceId, targetId]) => {
        const source = sources.get(sourceId);
        const target = targets.get(targetId);
        if (!source || !target) return [];
        const sourceRect = source.getBoundingClientRect();
        const targetRect = target.getBoundingClientRect();
        const startX = sourceRect.left + sourceRect.width / 2 - origin.left;
        const startY = sourceRect.top + sourceRect.height / 2 - origin.top;
        const endX = targetRect.left + targetRect.width / 2 - origin.left;
        const endY = targetRect.top + targetRect.height / 2 - origin.top;
        const bend = Math.max(24, (endX - startX) / 2);
        return [{
          sourceId,
          startX,
          startY,
          endX,
          endY,
          d: `M ${startX} ${startY} C ${startX + bend} ${startY}, ${endX - bend} ${endY}, ${endX} ${endY}`,
        }];
      });
      setPaths(next);
    };

    measure();
    window.addEventListener("resize", measure);
    const observer = typeof ResizeObserver === "undefined" ? undefined : new ResizeObserver(measure);
    if (wrapperRef.current) observer?.observe(wrapperRef.current);
    wrapperRef.current?.querySelectorAll<HTMLElement>("[data-match-source], [data-match-target]")
      .forEach((node) => observer?.observe(node));
    return () => {
      window.removeEventListener("resize", measure);
      observer?.disconnect();
    };
  }, [matches, wrapperRef]);

  return (
    <svg data-slot="matching-connectors" className="pointer-events-none absolute inset-0 z-0 size-full overflow-visible" aria-hidden="true">
      {paths.map((path) => (
        <g key={path.sourceId} className="stroke-primary text-primary">
          <path d={path.d} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />
          <circle cx={path.startX} cy={path.startY} r="3" fill="currentColor" stroke="none" />
          <circle cx={path.endX} cy={path.endY} r="3" fill="currentColor" stroke="none" />
        </g>
      ))}
    </svg>
  );
}

export interface MatchingExerciseProps extends ExerciseBaseProps {
  sources: ExerciseChoice[];
  targets: ExerciseChoice[];
  correctMatches: ExerciseAssignments;
  value?: ExerciseAssignments;
  defaultValue?: ExerciseAssignments;
  onValueChange?: (value: ExerciseAssignments) => void;
  onSubmit?: (submission: ExerciseSubmission<ExerciseAssignments>) => void;
}

interface MatchingSelection {
  side: "source" | "target";
  id: string;
}

export const MatchingExercise = React.forwardRef<HTMLDivElement, MatchingExerciseProps>(function MatchingExercise(
  { sources, targets, correctMatches, value, defaultValue = {}, onValueChange, onSubmit, ...shellProps },
  ref,
) {
  const titleId = React.useId();
  const [matches, setMatches] = useControllable(value, defaultValue, onValueChange);
  const [selected, setSelected] = React.useState<MatchingSelection>();
  const [submitted, setSubmitted] = React.useState(false);
  const [correct, setCorrect] = React.useState(false);
  const [announcement, setAnnouncement] = React.useState("");
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor),
  );
  const sourceById = new Map(sources.map((item) => [item.id, item]));
  const targetById = new Map(targets.map((item) => [item.id, item]));
  const boardRef = React.useRef<HTMLDivElement>(null);

  const assign = React.useCallback((sourceId: string, targetId: string) => {
    const next = Object.fromEntries(Object.entries(matches).filter(([source, target]) => source === sourceId || target !== targetId));
    next[sourceId] = targetId;
    setMatches(next);
    setSelected(undefined);
    setAnnouncement("Match assigned.");
  }, [matches, setMatches]);

  const activate = (side: MatchingSelection["side"], id: string, label: React.ReactNode) => {
    if (selected && selected.side !== side) {
      if (side === "source") assign(id, selected.id);
      else assign(selected.id, id);
      return;
    }

    const next = selected?.side === side && selected.id === id ? undefined : { side, id };
    setSelected(next);
    setAnnouncement(next ? `${String(label)} selected. Choose an item on the other side.` : "Selection cleared.");
  };

  const handleDragEnd = ({ active, over }: DragEndEvent) => {
    const sourceId = String(active.id).replace("matching-source:", "");
    const targetId = over ? String(over.id).replace("matching-target:", "") : "";
    if (sourceById.has(sourceId) && targetById.has(targetId)) assign(sourceId, targetId);
  };

  const submit = () => {
    const result = sameAssignments(matches, correctMatches, sources.map((item) => item.id));
    setCorrect(result);
    setSubmitted(true);
    onSubmit?.({ value: matches, correct: result });
  };

  return (
    <ExerciseShell {...shellProps} rootRef={ref} titleId={titleId} submitted={submitted} correct={correct} canSubmit={sources.length > 0 && sources.every((item) => matches[item.id])} onSubmit={submit} empty={sources.length === 0}>
      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        <div ref={boardRef} className="relative grid grid-cols-2 gap-10">
          <MatchingConnectors wrapperRef={boardRef} matches={matches} />
          <div className="relative z-10 flex flex-col gap-2" aria-label="Items to match">
            {sources.map((source) => (
              <MatchingNode
                key={source.id}
                side="source"
                dragId={`matching-source:${source.id}`}
                choice={source}
                selected={selected?.side === "source" && selected.id === source.id}
                connected={Boolean(matches[source.id])}
                disabled={submitted}
                connectedText={matches[source.id] ? <>Matched with {targetById.get(matches[source.id]!)?.content}</> : undefined}
                onActivate={() => activate("source", source.id, source.content)}
              />
            ))}
          </div>
          <div className="relative z-10 flex flex-col gap-2" aria-label="Match destinations">
            {targets.map((target) => {
              const sourceId = Object.keys(matches).find((id) => matches[id] === target.id);
              return (
                <MatchingNode
                  key={target.id}
                  side="target"
                  dropId={`matching-target:${target.id}`}
                  choice={target}
                  selected={selected?.side === "target" && selected.id === target.id}
                  connected={Boolean(sourceId)}
                  disabled={submitted}
                  connectedText={sourceId ? <>Matched with {sourceById.get(sourceId)?.content}</> : undefined}
                  onActivate={() => activate("target", target.id, target.content)}
                />
              );
            })}
          </div>
        </div>
      </DndContext>
      <p className="sr-only" role="status" aria-live="polite">{announcement}</p>
    </ExerciseShell>
  );
});

interface SortableRowProps {
  item: ExerciseChoice;
  index: number;
  total: number;
  disabled: boolean;
  move: (from: number, to: number) => void;
}

function SortableRow({ item, index, total, disabled, move }: SortableRowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.id, disabled });
  const style = transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`, transition } : undefined;
  return (
    <li ref={setNodeRef} style={style} className={cn("flex items-center gap-2 rounded-md border bg-background p-2", isDragging && "z-20 opacity-70")}>
      <Button type="button" variant="ghost" size="icon-sm" aria-label={`Drag ${String(item.content)}`} disabled={disabled} {...attributes} {...listeners}><GripIcon className="size-4" /></Button>
      <span className="min-w-0 flex-1 text-sm">{item.content}</span>
      <span className="text-xs tabular-nums text-muted-foreground">{index + 1}/{total}</span>
      <Button type="button" variant="outline" size="icon-sm" aria-label={`Move ${String(item.content)} up`} disabled={disabled || index === 0} onClick={() => move(index, index - 1)}><ArrowIcon direction="up" className="size-4" /></Button>
      <Button type="button" variant="outline" size="icon-sm" aria-label={`Move ${String(item.content)} down`} disabled={disabled || index === total - 1} onClick={() => move(index, index + 1)}><ArrowIcon direction="down" className="size-4" /></Button>
    </li>
  );
}

export interface SortExerciseProps extends ExerciseBaseProps {
  items: ExerciseChoice[];
  correctOrder: string[];
  value?: string[];
  defaultValue?: string[];
  onValueChange?: (value: string[]) => void;
  onSubmit?: (submission: ExerciseSubmission<string[]>) => void;
}

export const SortExercise = React.forwardRef<HTMLDivElement, SortExerciseProps>(function SortExercise(
  { items, correctOrder, value, defaultValue, onValueChange, onSubmit, ...shellProps },
  ref,
) {
  const titleId = React.useId();
  const initial = defaultValue ?? items.map((item) => item.id);
  const [order, setOrder] = useControllable(value, initial, onValueChange);
  const [submitted, setSubmitted] = React.useState(false);
  const [correct, setCorrect] = React.useState(false);
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const itemById = new Map(items.map((item) => [item.id, item]));
  const normalizedOrder = order.filter((id) => itemById.has(id));
  for (const item of items) if (!normalizedOrder.includes(item.id)) normalizedOrder.push(item.id);

  const move = (from: number, to: number) => setOrder(arrayMove(normalizedOrder, from, to));
  const handleDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    const from = normalizedOrder.indexOf(String(active.id));
    const to = normalizedOrder.indexOf(String(over.id));
    if (from >= 0 && to >= 0) move(from, to);
  };
  const submit = () => {
    const result = normalizedOrder.length === correctOrder.length && normalizedOrder.every((id, index) => id === correctOrder[index]);
    setCorrect(result);
    setSubmitted(true);
    onSubmit?.({ value: normalizedOrder, correct: result });
  };

  return (
    <ExerciseShell {...shellProps} rootRef={ref} titleId={titleId} submitted={submitted} correct={correct} canSubmit={items.length > 0} onSubmit={submit} empty={items.length === 0}>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={normalizedOrder} strategy={verticalListSortingStrategy}>
          <ol className="flex flex-col gap-2" aria-label="Items in current order">
            {normalizedOrder.map((id, index) => {
              const item = itemById.get(id)!;
              return <SortableRow key={id} item={item} index={index} total={normalizedOrder.length} disabled={submitted} move={move} />;
            })}
          </ol>
        </SortableContext>
      </DndContext>
    </ExerciseShell>
  );
});

export interface CategorizeExerciseProps extends ExerciseBaseProps {
  items: ExerciseChoice[];
  categories: ExerciseChoice[];
  correctCategories: ExerciseAssignments;
  value?: ExerciseAssignments;
  defaultValue?: ExerciseAssignments;
  onValueChange?: (value: ExerciseAssignments) => void;
  onSubmit?: (submission: ExerciseSubmission<ExerciseAssignments>) => void;
}

interface CategoryColumnProps {
  dropId: string;
  title: React.ReactNode;
  count: number;
  selected: boolean;
  disabled: boolean;
  onAssign: () => void;
  children: React.ReactNode;
}

function CategoryColumn({ dropId, title, count, selected, disabled, onAssign, children }: CategoryColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id: dropId, disabled });
  return (
    <section
      ref={setNodeRef}
      className={cn(
        "flex min-h-44 min-w-0 flex-col gap-3 rounded-lg border bg-muted/30 p-3",
        isOver && "border-primary bg-primary/5",
      )}
    >
      {selected && !disabled ? (
        <Button type="button" variant="outline" size="sm" onClick={onAssign} className="w-full justify-between">
          <span>Move selected here</span>
          <span className="text-xs tabular-nums text-muted-foreground">{count}</span>
          <span className="sr-only">: {title}</span>
        </Button>
      ) : (
        <div className="flex min-h-8 items-center justify-between gap-2 px-1">
          <h3 className="truncate text-sm font-medium">{title}</h3>
          <span className="text-xs tabular-nums text-muted-foreground">{count}</span>
        </div>
      )}
      <div className="flex flex-1 flex-col gap-2">
        {count === 0 ? <p className="py-4 text-center text-xs text-muted-foreground">Drop items here</p> : children}
      </div>
    </section>
  );
}

export const CategorizeExercise = React.forwardRef<HTMLDivElement, CategorizeExerciseProps>(function CategorizeExercise(
  { items, categories, correctCategories, value, defaultValue = {}, onValueChange, onSubmit, ...shellProps },
  ref,
) {
  const titleId = React.useId();
  const [assignments, setAssignments] = useControllable(value, defaultValue, onValueChange);
  const [selected, setSelected] = React.useState<string>();
  const [submitted, setSubmitted] = React.useState(false);
  const [correct, setCorrect] = React.useState(false);
  const [announcement, setAnnouncement] = React.useState("");
  const sensors = useSensors(useSensor(PointerSensor), useSensor(KeyboardSensor));
  const itemById = new Map(items.map((item) => [item.id, item]));
  const categoryById = new Map(categories.map((item) => [item.id, item]));

  const assign = React.useCallback((itemId: string, categoryId: string | undefined) => {
    const next = { ...assignments };
    if (categoryId === undefined) delete next[itemId];
    else next[itemId] = categoryId;
    setAssignments(next);
    setSelected(undefined);
    setAnnouncement(categoryId === undefined ? "Item moved to unassigned." : "Category assigned.");
  }, [assignments, setAssignments]);
  const handleDragEnd = ({ active, over }: DragEndEvent) => {
    const itemId = String(active.id).replace("category-item:", "");
    const categoryId = over ? String(over.id).replace("category-target:", "") : "";
    if (!itemById.has(itemId)) return;
    if (categoryId === "unassigned") assign(itemId, undefined);
    else if (categoryById.has(categoryId)) assign(itemId, categoryId);
  };
  const submit = () => {
    const result = sameAssignments(assignments, correctCategories, items.map((item) => item.id));
    setCorrect(result);
    setSubmitted(true);
    onSubmit?.({ value: assignments, correct: result });
  };

  return (
    <ExerciseShell {...shellProps} rootRef={ref} titleId={titleId} submitted={submitted} correct={correct} canSubmit={items.length > 0 && items.every((item) => assignments[item.id])} onSubmit={submit} empty={items.length === 0}>
      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-3" aria-label="Category board">
          {[{ id: undefined, content: "Unassigned" } as const, ...categories].map((category) => {
            const columnItems = items.filter((item) => category.id === undefined ? !assignments[item.id] : assignments[item.id] === category.id);
            const columnId = category.id ?? "unassigned";
            return (
              <CategoryColumn
                key={columnId}
                dropId={`category-target:${columnId}`}
                title={category.content}
                count={columnItems.length}
                selected={Boolean(selected)}
                disabled={submitted}
                onAssign={() => selected && assign(selected, category.id)}
              >
                {columnItems.map((item) => (
                  <DraggableChoice
                    key={item.id}
                    dragId={`category-item:${item.id}`}
                    choice={item}
                    selected={selected === item.id}
                    disabled={submitted}
                    onSelect={() => setSelected(selected === item.id ? undefined : item.id)}
                  />
                ))}
              </CategoryColumn>
            );
          })}
        </div>
      </DndContext>
      <p className="sr-only" role="status" aria-live="polite">{announcement}</p>
    </ExerciseShell>
  );
});
