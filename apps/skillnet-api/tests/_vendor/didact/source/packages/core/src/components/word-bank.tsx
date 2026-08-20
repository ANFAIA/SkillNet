import * as React from "react";
import {
  DndContext,
  PointerSensor,
  pointerWithin,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
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

export interface WordBankOption {
  /** Stable content id persisted in the learner response. */
  id: string;
  content?: React.ReactNode;
  accessibleLabel?: string;
  /** Defaults to one. Use `null` when the option may be reused without a limit. */
  maxUses?: number | null;
}

export interface WordBankGap {
  /** Stable destination id persisted in the learner response. */
  id: string;
  /** Content immediately before the interactive inline gap. */
  before?: React.ReactNode;
  /** Content immediately after the interactive inline gap. */
  after?: React.ReactNode;
  /** @deprecated Use `before` and `after` to place the gap inside the sentence. */
  prompt?: React.ReactNode;
  accessibleLabel?: string;
  /** More than one id allows semantically equivalent answers. Omit for human grading. */
  correctOptionIds?: readonly string[];
  feedback?: React.ReactNode;
}

export type WordBankValue = Record<string, string>;
export type WordBankGapStatus = "correct" | "incorrect" | "ungraded";
export type WordBankResultStatus = "correct" | "incorrect" | "partial" | "ungraded";

export interface WordBankResult {
  value: WordBankValue;
  status: WordBankResultStatus;
  gaps: Record<string, WordBankGapStatus>;
}

export interface WordBankLabels {
  activity: string;
  titlePending: string;
  instructions: string;
  dragInstructions: string;
  gaps: string;
  gap: (position: number, total: number) => string;
  gapPending: string;
  emptyGap: string;
  remove: string;
  removeFromGap: (gap: string) => string;
  bank: string;
  option: (position: number, total: number) => string;
  optionPending: string;
  usesRemaining: (remaining: number) => string;
  unlimitedUses: string;
  noGaps: string;
  noOptions: string;
  selectGapFirst: string;
  selectOptionFirst: string;
  assigned: (option: string, gap: string) => string;
  selectionCleared: string;
  undo: string;
  clear: string;
  submit: string;
  incomplete: string;
  correct: string;
  incorrect: string;
  partial: string;
  ungraded: string;
  gapCorrect: string;
  gapIncorrect: string;
  gapUngraded: string;
}

const defaultLabels: WordBankLabels = {
  activity: "Word bank activity",
  titlePending: "Activity content is still loading.",
  instructions: "Drag an option into an inline gap, or select a gap and an option in either order.",
  dragInstructions: "Pointer users may drag this option. With a keyboard, press Enter or Space to select it, then select a gap.",
  gaps: "Gaps to complete",
  gap: (position, total) => `Gap ${position} of ${total}`,
  gapPending: "This gap is still loading.",
  emptyGap: "Empty",
  remove: "Remove",
  removeFromGap: (gap) => `Remove answer from ${gap}`,
  bank: "Word bank",
  option: (position, total) => `Option ${position} of ${total}`,
  optionPending: "Option is still loading.",
  usesRemaining: (remaining) => `${remaining} remaining`,
  unlimitedUses: "Unlimited uses",
  noGaps: "No gaps yet.",
  noOptions: "No options yet.",
  selectGapFirst: "Option selected. Now select a gap.",
  selectOptionFirst: "Gap selected. Now select an option.",
  assigned: (option, gap) => `${option} placed in ${gap}.`,
  selectionCleared: "Selection cleared.",
  undo: "Undo",
  clear: "Clear all",
  submit: "Check answers",
  incomplete: "Fill every available gap before checking your answers.",
  correct: "All answers are correct.",
  incorrect: "The answers need revision.",
  partial: "Some answers are correct.",
  ungraded: "Submitted for review.",
  gapCorrect: "Correct",
  gapIncorrect: "Needs revision",
  gapUngraded: "Submitted for review",
};

interface WordBankDragData {
  kind: "word-bank-option";
  optionId: string;
}

interface WordBankDropData {
  kind: "word-bank-gap";
  gapId: string;
}

function DragIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" {...props}>
      <circle cx="5" cy="4" r="1" /><circle cx="11" cy="4" r="1" />
      <circle cx="5" cy="8" r="1" /><circle cx="11" cy="8" r="1" />
      <circle cx="5" cy="12" r="1" /><circle cx="11" cy="12" r="1" />
    </svg>
  );
}

interface DraggableOptionButtonProps {
  optionId: string;
  selected: boolean;
  disabled: boolean;
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}

function DraggableOptionButton({
  optionId,
  selected,
  disabled,
  label,
  onClick,
  children,
}: DraggableOptionButtonProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `word-bank-option:${optionId}`,
    data: { kind: "word-bank-option", optionId } satisfies WordBankDragData,
    disabled,
  });
  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined;

  return (
    <Button
      ref={setNodeRef}
      type="button"
      variant={selected ? "default" : "outline"}
      {...attributes}
      {...listeners}
      aria-label={label}
      aria-pressed={selected}
      disabled={disabled}
      onClick={onClick}
      style={style}
      data-drag-option-id={optionId}
      className={cn(
        "h-auto min-h-10 touch-none whitespace-normal",
        isDragging && "z-20 opacity-70",
      )}
    >
      <DragIcon className="size-4 shrink-0 text-muted-foreground" />
      {children}
    </Button>
  );
}

interface DroppableGapButtonProps {
  gapId: string;
  disabled: boolean;
  selected: boolean;
  assigned: boolean;
  invalid: boolean;
  describedBy?: string;
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}

function DroppableGapButton({
  gapId,
  disabled,
  selected,
  assigned,
  invalid,
  describedBy,
  label,
  onClick,
  children,
}: DroppableGapButtonProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: `word-bank-gap:${gapId}`,
    data: { kind: "word-bank-gap", gapId } satisfies WordBankDropData,
    disabled,
  });
  return (
    <Button
      ref={setNodeRef}
      type="button"
      variant={selected ? "default" : "outline"}
      aria-label={label}
      aria-pressed={selected}
      aria-invalid={invalid || undefined}
      aria-describedby={describedBy}
      disabled={disabled}
      onClick={onClick}
      data-gap-id={gapId}
      data-drop-active={isOver || undefined}
      data-assigned={assigned || undefined}
      className={cn(
        "h-auto min-h-10 min-w-28 border-dashed px-3 py-1 align-middle whitespace-normal",
        assigned && "border-solid",
        isOver && "border-primary bg-accent text-accent-foreground outline-2 outline-offset-2 outline-ring",
      )}
    >
      {children}
    </Button>
  );
}

function hasGapContent(gap: WordBankGap): boolean {
  return gap.before !== undefined || gap.after !== undefined || gap.prompt !== undefined;
}

function useControllableValue(
  controlled: WordBankValue | undefined,
  initial: WordBankValue,
  onChange?: (value: WordBankValue) => void,
) {
  const isControlled = controlled !== undefined;
  const [uncontrolled, setUncontrolled] = React.useState(initial);
  const value = isControlled ? controlled : uncontrolled;
  const setValue = React.useCallback((next: WordBankValue) => {
    if (!isControlled) setUncontrolled(next);
    onChange?.(next);
  }, [isControlled, onChange]);
  return [value, setValue] as const;
}

function allowedUses(option: WordBankOption): number {
  if (option.maxUses === null) return Number.POSITIVE_INFINITY;
  if (option.maxUses === undefined) return 1;
  return Math.max(0, Math.floor(option.maxUses));
}

function usageFor(value: WordBankValue, optionId: string): number {
  return Object.values(value).filter((id) => id === optionId).length;
}

function evaluate(gaps: readonly WordBankGap[], value: WordBankValue): WordBankResult {
  const outcomes: Record<string, WordBankGapStatus> = {};
  for (const gap of gaps) {
    const accepted = gap.correctOptionIds;
    outcomes[gap.id] = !accepted || accepted.length === 0
      ? "ungraded"
      : accepted.includes(value[gap.id] ?? "")
        ? "correct"
        : "incorrect";
  }

  const statuses = Object.values(outcomes);
  const graded = statuses.filter((status) => status !== "ungraded");
  const correct = graded.filter((status) => status === "correct").length;
  const status: WordBankResultStatus = graded.length === 0
    ? "ungraded"
    : statuses.some((item) => item === "ungraded")
      ? "partial"
      : correct === graded.length
        ? "correct"
        : correct === 0
          ? "incorrect"
          : "partial";
  return { value: { ...value }, status, gaps: outcomes };
}

export interface WordBankProps extends Omit<
  React.ComponentPropsWithoutRef<"section">,
  "children" | "defaultValue" | "onSubmit" | "title"
> {
  title?: React.ReactNode;
  description?: React.ReactNode;
  gaps?: readonly WordBankGap[];
  options?: readonly WordBankOption[];
  value?: WordBankValue;
  defaultValue?: WordBankValue;
  onValueChange?: (value: WordBankValue) => void;
  onSubmit?: (result: WordBankResult) => void;
  disabled?: boolean;
  labels?: Partial<WordBankLabels>;
}

/**
 * Assigns reusable or consumable options from a bank to stable semantic gaps.
 * Click and keyboard selection are the primary interaction; dragging is never required.
 */
export const WordBank = React.forwardRef<HTMLElement, WordBankProps>(function WordBank(
  {
    title,
    description,
    gaps = [],
    options = [],
    value: valueProp,
    defaultValue = {},
    onValueChange,
    onSubmit,
    disabled = false,
    labels,
    className,
    "aria-label": ariaLabel,
    "aria-labelledby": ariaLabelledby,
    ...props
  },
  ref,
) {
  const copy = { ...defaultLabels, ...labels };
  const titleId = React.useId();
  const instructionsId = React.useId();
  const incompleteId = React.useId();
  const [value, setValue] = useControllableValue(valueProp, defaultValue, onValueChange);
  const [selectedGapId, setSelectedGapId] = React.useState<string>();
  const [selectedOptionId, setSelectedOptionId] = React.useState<string>();
  const [history, setHistory] = React.useState<WordBankValue[]>([]);
  const [result, setResult] = React.useState<WordBankResult>();
  const [announcement, setAnnouncement] = React.useState("");
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );
  const optionById = new Map(options.map((option) => [option.id, option]));
  const gapById = new Map(gaps.map((gap) => [gap.id, gap]));
  const locked = disabled || result !== undefined;

  const gapName = (gap: WordBankGap, index = gaps.indexOf(gap)) =>
    gap.accessibleLabel ?? copy.gap(index + 1, gaps.length);
  const optionName = (option: WordBankOption, index = options.indexOf(option)) =>
    option.accessibleLabel ?? copy.option(index + 1, options.length);

  const applyValue = React.useCallback((next: WordBankValue) => {
    setHistory((previous) => [...previous, { ...value }]);
    setValue(next);
  }, [setValue, value]);

  const assign = (gapId: string, optionId: string) => {
    const gap = gapById.get(gapId);
    const option = optionById.get(optionId);
    if (!gap || !option || !hasGapContent(gap) || option.content === undefined || locked) return;
    const currentForGap = value[gapId];
    const used = usageFor(value, optionId) - (currentForGap === optionId ? 1 : 0);
    if (used >= allowedUses(option)) return;
    applyValue({ ...value, [gapId]: optionId });
    setSelectedGapId(undefined);
    setSelectedOptionId(undefined);
    setAnnouncement(copy.assigned(optionName(option), gapName(gap)));
  };

  const activateGap = (gap: WordBankGap) => {
    if (locked || !hasGapContent(gap)) return;
    if (selectedOptionId) {
      assign(gap.id, selectedOptionId);
      return;
    }
    const next = selectedGapId === gap.id ? undefined : gap.id;
    setSelectedGapId(next);
    setSelectedOptionId(undefined);
    setAnnouncement(next ? copy.selectOptionFirst : copy.selectionCleared);
  };

  const activateOption = (option: WordBankOption) => {
    if (locked || option.content === undefined) return;
    if (selectedGapId) {
      assign(selectedGapId, option.id);
      return;
    }
    const next = selectedOptionId === option.id ? undefined : option.id;
    setSelectedOptionId(next);
    setSelectedGapId(undefined);
    setAnnouncement(next ? copy.selectGapFirst : copy.selectionCleared);
  };

  const handleDragEnd = ({ active, over }: DragEndEvent) => {
    const source = active.data.current as WordBankDragData | undefined;
    const destination = over?.data.current as WordBankDropData | undefined;
    if (source?.kind !== "word-bank-option" || destination?.kind !== "word-bank-gap") return;
    assign(destination.gapId, source.optionId);
  };

  const remove = (gap: WordBankGap) => {
    const next = { ...value };
    delete next[gap.id];
    applyValue(next);
    setAnnouncement(copy.selectionCleared);
  };

  const undo = () => {
    const previous = history.at(-1);
    if (!previous || locked) return;
    setValue(previous);
    setHistory((items) => items.slice(0, -1));
    setSelectedGapId(undefined);
    setSelectedOptionId(undefined);
  };

  const clear = () => {
    if (locked || Object.keys(value).length === 0) return;
    applyValue({});
    setSelectedGapId(undefined);
    setSelectedOptionId(undefined);
  };

  const validGaps = gaps.filter(hasGapContent);
  const complete = validGaps.length === gaps.length && gaps.length > 0 && gaps.every((gap) => {
    const option = optionById.get(value[gap.id] ?? "");
    return option?.content !== undefined;
  });
  const cardinalityValid = options.every((option) => usageFor(value, option.id) <= allowedUses(option));
  const canSubmit = complete && cardinalityValid && !locked;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    const next = evaluate(gaps, value);
    setResult(next);
    setSelectedGapId(undefined);
    setSelectedOptionId(undefined);
    onSubmit?.(next);
  };

  const overallCopy = result?.status === "correct"
    ? copy.correct
    : result?.status === "incorrect"
      ? copy.incorrect
      : result?.status === "partial"
        ? copy.partial
        : copy.ungraded;

  return (
    <section
      ref={ref}
      data-slot="word-bank"
      data-interaction-type="gap-match"
      data-result={result?.status}
      aria-label={ariaLabel ?? (ariaLabelledby === undefined && title === undefined ? copy.activity : undefined)}
      aria-labelledby={ariaLabelledby ?? (title !== undefined ? titleId : undefined)}
      className={cn("w-full max-w-2xl", className)}
      {...props}
    >
      <Card>
        <CardHeader>
          <CardTitle id={titleId}>{title ?? copy.titlePending}</CardTitle>
          <CardDescription id={instructionsId}>
            {description ?? copy.instructions}
          </CardDescription>
        </CardHeader>
        <form onSubmit={submit} className="flex flex-col gap-6">
          <DndContext
            sensors={sensors}
            collisionDetection={pointerWithin}
            accessibility={{ screenReaderInstructions: { draggable: copy.dragInstructions } }}
            onDragEnd={handleDragEnd}
          >
          <CardContent className="flex flex-col gap-5">
            <fieldset disabled={locked} aria-describedby={instructionsId} className="flex flex-col gap-3">
              <legend className="mb-2 text-sm font-medium text-foreground">{copy.gaps}</legend>
              {gaps.length === 0 ? (
                <p className="rounded-md border p-4 text-sm text-muted-foreground">{copy.noGaps}</p>
              ) : gaps.map((gap, index) => {
                const name = gapName(gap, index);
                const assigned = optionById.get(value[gap.id] ?? "");
                const status = result?.gaps[gap.id];
                const feedbackId = `${titleId}-gap-${index}-feedback`;
                const statusCopy = status === "correct"
                  ? copy.gapCorrect
                  : status === "incorrect"
                    ? copy.gapIncorrect
                    : copy.gapUngraded;
                return (
                  <div
                    key={gap.id}
                    data-status={status}
                    className="flex flex-wrap items-center gap-x-2 gap-y-3 py-2 text-sm leading-relaxed"
                  >
                    {!hasGapContent(gap) ? (
                      <span className="text-muted-foreground">{copy.gapPending}</span>
                    ) : <span>{gap.before ?? gap.prompt}</span>}
                    <DroppableGapButton
                      gapId={gap.id}
                      assigned={assigned !== undefined}
                      selected={selectedGapId === gap.id}
                      invalid={status === "incorrect"}
                      describedBy={status ? feedbackId : undefined}
                      label={`${name}: ${assigned ? optionName(assigned) : copy.emptyGap}`}
                      disabled={locked || !hasGapContent(gap)}
                      onClick={() => activateGap(gap)}
                    >
                      {assigned?.content ?? <span aria-hidden="true" className="tracking-widest">····</span>}
                    </DroppableGapButton>
                    {hasGapContent(gap) && gap.after !== undefined ? <span>{gap.after}</span> : null}
                    {assigned && !locked ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        aria-label={copy.removeFromGap(name)}
                        onClick={() => remove(gap)}
                      >
                        {copy.remove}
                      </Button>
                    ) : null}
                    {status ? (
                      <div id={feedbackId} role="status" className="basis-full rounded-md bg-muted p-3 text-sm">
                        <p className="font-medium">{statusCopy}</p>
                        {gap.feedback !== undefined ? (
                          <div className="mt-1 text-muted-foreground">{gap.feedback}</div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </fieldset>

            <fieldset disabled={locked} aria-describedby={instructionsId} className="flex flex-col gap-3">
              <legend className="mb-2 text-sm font-medium text-foreground">{copy.bank}</legend>
              {options.length === 0 ? (
                <p className="rounded-md border p-4 text-sm text-muted-foreground">{copy.noOptions}</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {options.map((option, index) => {
                    const maximum = allowedUses(option);
                    const remaining = maximum - usageFor(value, option.id);
                    const selected = selectedOptionId === option.id;
                    const available = maximum === Number.POSITIVE_INFINITY || remaining > 0;
                    const name = optionName(option, index);
                    return (
                      <DraggableOptionButton
                        key={option.id}
                        optionId={option.id}
                        label={`${name}, ${maximum === Number.POSITIVE_INFINITY
                          ? copy.unlimitedUses
                          : copy.usesRemaining(Math.max(0, remaining))}`}
                        selected={selected}
                        disabled={locked || option.content === undefined || !available}
                        onClick={() => activateOption(option)}
                      >
                        <span>{option.content ?? copy.optionPending}</span>
                        <span className="text-xs opacity-70">
                          {maximum === Number.POSITIVE_INFINITY
                            ? copy.unlimitedUses
                            : copy.usesRemaining(Math.max(0, remaining))}
                        </span>
                      </DraggableOptionButton>
                    );
                  })}
                </div>
              )}
            </fieldset>

            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" disabled={locked || history.length === 0} onClick={undo}>
                {copy.undo}
              </Button>
              <Button type="button" variant="ghost" size="sm" disabled={locked || Object.keys(value).length === 0} onClick={clear}>
                {copy.clear}
              </Button>
            </div>

            {!complete && gaps.length > 0 && !result ? (
              <p id={incompleteId} className="text-sm text-muted-foreground">{copy.incomplete}</p>
            ) : null}
            {result ? (
              <div role="status" aria-live="polite" className="rounded-md border bg-muted p-4 text-sm font-medium">
                {overallCopy}
              </div>
            ) : null}
            <p className="sr-only" role="status" aria-live="polite">{announcement}</p>
          </CardContent>
          </DndContext>
          {!result && gaps.length > 0 ? (
            <CardFooter>
              <Button type="submit" disabled={!canSubmit} aria-describedby={!canSubmit ? incompleteId : undefined}>
                {copy.submit}
              </Button>
            </CardFooter>
          ) : null}
        </form>
      </Card>
    </section>
  );
});
