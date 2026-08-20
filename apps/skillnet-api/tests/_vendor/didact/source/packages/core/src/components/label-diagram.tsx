import * as React from "react";
import { DndContext, PointerSensor, pointerWithin, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { MdDragIndicator } from "react-icons/md";
import { Button, Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@didact/ui";

import { cn } from "../lib/cn.js";

export interface LabelDiagramTarget {
  id: string;
  label: string;
  description?: React.ReactNode;
  /** Normalized coordinates in the inclusive 0..1 range. */
  x: number;
  y: number;
  /** Omit to collect an ungraded response. */
  correctItemIds?: readonly string[];
}

export interface LabelDiagramItem {
  id: string;
  content?: React.ReactNode;
  accessibleLabel?: string;
}

export type LabelDiagramValue = Readonly<Record<string, string>>;
export type LabelDiagramResultStatus = "correct" | "incorrect" | "partial" | "ungraded";
export type LabelDiagramTargetStatus = "correct" | "incorrect" | "ungraded";

export interface LabelDiagramResult {
  value: LabelDiagramValue;
  status: LabelDiagramResultStatus;
  targets: Readonly<Record<string, LabelDiagramTargetStatus>>;
}

export interface LabelDiagramLabels {
  activity: string;
  titlePending: string;
  instructions: string;
  diagramPending: string;
  targetsPending: string;
  itemsPending: string;
  empty: string;
  targets: string;
  itemBank: string;
  target: (index: number, total: number) => string;
  item: (index: number, total: number) => string;
  emptyTarget: string;
  selectTarget: string;
  selectItem: string;
  assigned: (item: string, target: string) => string;
  remove: string;
  removeFrom: (target: string) => string;
  incomplete: string;
  submit: string;
  dragInstructions: string;
  correct: string;
  incorrect: string;
  partial: string;
  ungraded: string;
  targetCorrect: string;
  targetIncorrect: string;
  targetUngraded: string;
}

const defaultLabels: LabelDiagramLabels = {
  activity: "Label diagram",
  titlePending: "Diagram activity",
  instructions: "Place each label on its destination. Select a label and then a destination, or drag it.",
  diagramPending: "The diagram is still loading.",
  targetsPending: "Destinations are still loading.",
  itemsPending: "Labels are still loading.",
  empty: "There is nothing to label yet.",
  targets: "Destinations",
  itemBank: "Available labels",
  target: (index, total) => `Destination ${index} of ${total}`,
  item: (index, total) => `Label ${index} of ${total}`,
  emptyTarget: "Empty",
  selectTarget: "Selected destination. Now choose a label.",
  selectItem: "Selected label. Now choose a destination.",
  assigned: (item, target) => `${item} assigned to ${target}.`,
  remove: "Remove",
  removeFrom: (target) => `Remove label from ${target}`,
  incomplete: "Label every destination before submitting.",
  submit: "Submit labels",
  dragInstructions: "To move a label, press Space, use the arrow keys, then press Space again. You can also select the label and destination buttons.",
  correct: "Correct",
  incorrect: "Not quite",
  partial: "Partially correct",
  ungraded: "Response submitted",
  targetCorrect: "Correct",
  targetIncorrect: "Review this label",
  targetUngraded: "Submitted for review",
};

interface DragData { kind: "label-diagram-item"; itemId: string }
interface DropData { kind: "label-diagram-target"; targetId: string }

const clamp = (value: number) => Math.max(0, Math.min(1, value));

function evaluate(targets: readonly LabelDiagramTarget[], value: LabelDiagramValue): LabelDiagramResult {
  const outcomes: Record<string, LabelDiagramTargetStatus> = {};
  for (const target of targets) {
    outcomes[target.id] = !target.correctItemIds?.length
      ? "ungraded"
      : target.correctItemIds.includes(value[target.id] ?? "") ? "correct" : "incorrect";
  }
  const statuses = Object.values(outcomes);
  const graded = statuses.filter((status) => status !== "ungraded");
  const correct = graded.filter((status) => status === "correct").length;
  const status: LabelDiagramResultStatus = graded.length === 0
    ? "ungraded"
    : statuses.some((item) => item === "ungraded")
      ? "partial"
      : correct === graded.length ? "correct" : correct === 0 ? "incorrect" : "partial";
  return { value: { ...value }, status, targets: outcomes };
}

function DraggableItem({ item, name, selected, disabled, onClick }: {
  item: LabelDiagramItem; name: string; selected: boolean; disabled: boolean; onClick: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `label-diagram-item:${item.id}`,
    data: { kind: "label-diagram-item", itemId: item.id } satisfies DragData,
    disabled,
  });
  return <Button ref={setNodeRef} type="button" variant={selected ? "default" : "outline"} {...attributes} {...listeners}
    aria-label={name} aria-pressed={selected} disabled={disabled} onClick={onClick}
    style={transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined}
    className={cn("h-auto min-h-10 touch-none whitespace-normal", isDragging && "z-20 opacity-70")}>
    <MdDragIndicator aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
    {item.content}
  </Button>;
}

function TargetButton({ target, number, assigned, selected, disabled, label, onClick, className, style, placement }: {
  target: LabelDiagramTarget; number: number; assigned?: LabelDiagramItem; selected: boolean; disabled: boolean;
  label: string; onClick: () => void; className?: string; style?: React.CSSProperties; placement: "diagram" | "list";
}) {
  const { setNodeRef, isOver } = useDroppable({
    id: `label-diagram-target:${placement}:${target.id}`,
    data: { kind: "label-diagram-target", targetId: target.id } satisfies DropData,
    disabled,
  });
  return <Button ref={setNodeRef} type="button" variant={selected ? "default" : "outline"} aria-label={label}
    aria-pressed={selected} disabled={disabled} onClick={onClick} data-drop-active={isOver || undefined} style={style}
    className={cn("h-auto min-h-10 border-dashed bg-background/95 px-3 py-2 whitespace-normal shadow-sm", assigned && "border-solid", isOver && "border-primary bg-accent outline-2 outline-offset-2 outline-ring", className)}>
    <span aria-hidden="true" className="flex size-5 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">{number}</span>
    <span className="line-clamp-2">{assigned?.content ?? "…"}</span>
  </Button>;
}

export interface LabelDiagramProps extends Omit<React.ComponentPropsWithoutRef<"section">, "children" | "title" | "defaultValue" | "onSubmit"> {
  title?: React.ReactNode;
  description?: React.ReactNode;
  media?: React.ReactNode;
  alt: string;
  longDescription?: React.ReactNode;
  targets?: readonly LabelDiagramTarget[];
  items?: readonly LabelDiagramItem[];
  value?: LabelDiagramValue;
  defaultValue?: LabelDiagramValue;
  onValueChange?: (value: LabelDiagramValue) => void;
  onSubmit?: (result: LabelDiagramResult) => void;
  disabled?: boolean;
  streaming?: boolean;
  labels?: Partial<LabelDiagramLabels>;
}

/** Labels responsive diagrams without making dragging a requirement. */
export const LabelDiagram = React.forwardRef<HTMLElement, LabelDiagramProps>(function LabelDiagram({
  title, description, media, alt, longDescription, targets, items, value: controlledValue,
  defaultValue = {}, onValueChange, onSubmit, disabled = false, streaming = false,
  labels, className, "aria-label": ariaLabel, "aria-labelledby": ariaLabelledby, ...props
}, ref) {
  const copy = { ...defaultLabels, ...labels };
  const titleId = React.useId();
  const descriptionId = React.useId();
  const longDescriptionId = React.useId();
  const incompleteId = React.useId();
  const controlled = controlledValue !== undefined;
  const [localValue, setLocalValue] = React.useState<LabelDiagramValue>(defaultValue);
  const [selectedItemId, setSelectedItemId] = React.useState<string>();
  const [selectedTargetId, setSelectedTargetId] = React.useState<string>();
  const [result, setResult] = React.useState<LabelDiagramResult>();
  const [announcement, setAnnouncement] = React.useState("");
  const value = controlled ? controlledValue : localValue;
  const locked = disabled || result !== undefined;
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));
  const targetList = targets ?? [];
  const itemList = items ?? [];
  const itemById = new Map(itemList.map((item) => [item.id, item]));

  const itemName = (item: LabelDiagramItem, index = itemList.indexOf(item)) => item.accessibleLabel ?? copy.item(index + 1, itemList.length);
  const targetName = (target: LabelDiagramTarget, index = targetList.indexOf(target)) => target.label || copy.target(index + 1, targetList.length);
  const setValue = (next: LabelDiagramValue) => {
    if (locked) return;
    if (!controlled) setLocalValue(next);
    onValueChange?.(next);
  };
  const assign = (targetId: string, itemId: string) => {
    const target = targetList.find((entry) => entry.id === targetId);
    const item = itemById.get(itemId);
    if (!target || !item?.content || locked) return;
    const next = Object.fromEntries(Object.entries(value).filter(([key, assigned]) => key === targetId || assigned !== itemId));
    next[targetId] = itemId;
    setValue(next);
    setSelectedItemId(undefined); setSelectedTargetId(undefined);
    setAnnouncement(copy.assigned(itemName(item), targetName(target)));
  };
  const activateItem = (item: LabelDiagramItem) => {
    if (selectedTargetId) return assign(selectedTargetId, item.id);
    const next = selectedItemId === item.id ? undefined : item.id;
    setSelectedItemId(next); setSelectedTargetId(undefined);
    if (next) setAnnouncement(copy.selectItem);
  };
  const activateTarget = (target: LabelDiagramTarget) => {
    if (selectedItemId) return assign(target.id, selectedItemId);
    const next = selectedTargetId === target.id ? undefined : target.id;
    setSelectedTargetId(next); setSelectedItemId(undefined);
    if (next) setAnnouncement(copy.selectTarget);
  };
  const handleDragEnd = ({ active, over }: DragEndEvent) => {
    const source = active.data.current as DragData | undefined;
    const destination = over?.data.current as DropData | undefined;
    if (source?.kind === "label-diagram-item" && destination?.kind === "label-diagram-target") assign(destination.targetId, source.itemId);
  };
  const complete = targetList.length > 0 && targetList.every((target) => itemById.get(value[target.id] ?? "")?.content !== undefined);
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!complete || locked) return;
    const next = evaluate(targetList, value);
    setResult(next); onSubmit?.(next);
  };
  const overall = result?.status === "correct" ? copy.correct : result?.status === "incorrect" ? copy.incorrect : result?.status === "partial" ? copy.partial : copy.ungraded;
  const isEmpty = !streaming && targets !== undefined && items !== undefined && (targetList.length === 0 || itemList.length === 0);

  return <section ref={ref} data-slot="label-diagram" data-result={result?.status}
    aria-label={ariaLabel ?? (ariaLabelledby === undefined && title === undefined ? copy.activity : undefined)}
    aria-labelledby={ariaLabelledby ?? (title !== undefined ? titleId : undefined)} className={cn("w-full max-w-3xl", className)} {...props}>
    <Card>
      <CardHeader><CardTitle id={titleId}>{title ?? copy.titlePending}</CardTitle><CardDescription id={descriptionId}>{description ?? copy.instructions}</CardDescription></CardHeader>
      <form onSubmit={submit} className="flex flex-col gap-6">
        <DndContext sensors={sensors} collisionDetection={pointerWithin} accessibility={{ screenReaderInstructions: { draggable: copy.dragInstructions } }} onDragEnd={handleDragEnd}>
          <CardContent className="flex flex-col gap-6">
            {isEmpty ? <p className="rounded-md border p-4 text-sm text-muted-foreground">{copy.empty}</p> : <>
              <div>
                <div className="relative min-h-64 w-full overflow-hidden rounded-md border bg-muted/30">
                  <div role="img" aria-label={alt} aria-describedby={longDescription ? longDescriptionId : undefined} className="min-h-64">{media ?? <div className="flex min-h-64 items-center justify-center p-6 text-sm text-muted-foreground">{copy.diagramPending}</div>}</div>
                  {targets === undefined ? null : targetList.map((target, index) => {
                    const assigned = itemById.get(value[target.id] ?? "");
                    return <TargetButton key={target.id} target={target} number={index + 1} assigned={assigned} selected={selectedTargetId === target.id} disabled={locked} placement="diagram"
                      label={`${targetName(target, index)}: ${assigned ? itemName(assigned) : copy.emptyTarget}`} onClick={() => activateTarget(target)}
                      className="absolute max-w-40 -translate-x-1/2 -translate-y-1/2" style={{ left: `${clamp(target.x) * 100}%`, top: `${clamp(target.y) * 100}%` } as React.CSSProperties} />;
                  })}
                </div>
                {longDescription ? <div id={longDescriptionId} className="mt-2 text-sm text-muted-foreground">{longDescription}</div> : null}
              </div>

              <fieldset disabled={locked} aria-describedby={descriptionId} className="grid gap-3"><legend className="mb-1 text-sm font-medium">{copy.targets}</legend>
                {targets === undefined ? <p className="text-sm text-muted-foreground">{copy.targetsPending}</p> : targetList.map((target, index) => {
                  const assigned = itemById.get(value[target.id] ?? "");
                  const status = result?.targets[target.id];
                  const statusCopy = status === "correct" ? copy.targetCorrect : status === "incorrect" ? copy.targetIncorrect : copy.targetUngraded;
                  return <div key={target.id} className="flex flex-wrap items-center gap-3 rounded-md border p-3">
                    <div className="min-w-0 flex-1"><p className="text-sm font-medium">{index + 1}. {targetName(target, index)}</p>{target.description ? <div className="text-sm text-muted-foreground">{target.description}</div> : null}</div>
                    <TargetButton target={target} number={index + 1} assigned={assigned} selected={selectedTargetId === target.id} disabled={locked} placement="list"
                      label={`${targetName(target, index)}: ${assigned ? itemName(assigned) : copy.emptyTarget}`} onClick={() => activateTarget(target)} />
                    {assigned && !locked ? <Button type="button" variant="ghost" size="sm" aria-label={copy.removeFrom(targetName(target, index))} onClick={() => { const next = { ...value }; delete next[target.id]; setValue(next); }}>{copy.remove}</Button> : null}
                    {status ? <p role="status" className="basis-full rounded-md bg-muted p-2 text-sm font-medium">{statusCopy}</p> : null}
                  </div>;
                })}
              </fieldset>

              <fieldset disabled={locked} aria-describedby={descriptionId} className="grid gap-3"><legend className="mb-1 text-sm font-medium">{copy.itemBank}</legend>
                {items === undefined ? <p className="text-sm text-muted-foreground">{copy.itemsPending}</p> : <div className="flex flex-wrap gap-2">{itemList.map((item, index) => {
                  const used = Object.values(value).includes(item.id);
                  return <DraggableItem key={item.id} item={item} name={itemName(item, index)} selected={selectedItemId === item.id} disabled={locked || item.content === undefined || used} onClick={() => activateItem(item)} />;
                })}</div>}
              </fieldset>
            </>}
            {!complete && targetList.length > 0 && !result ? <p id={incompleteId} className="text-sm text-muted-foreground">{copy.incomplete}</p> : null}
            {result ? <div role="status" aria-live="polite" className="rounded-md border bg-muted p-4 text-sm font-medium">{overall}</div> : null}
            <p className="sr-only" role="status" aria-live="polite">{announcement}</p>
          </CardContent>
        </DndContext>
        {!result && !isEmpty ? <CardFooter><Button type="submit" disabled={!complete || locked} aria-describedby={!complete ? incompleteId : undefined}>{copy.submit}</Button></CardFooter> : null}
      </form>
    </Card>
  </section>;
});
