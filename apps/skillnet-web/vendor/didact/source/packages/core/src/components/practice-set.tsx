import * as React from "react";
import { Button, Card, CardContent, CardFooter, CardHeader, CardTitle } from "@didact/ui";

import { cn } from "../lib/cn.js";

export type PracticeSetPhase = "attempt" | "review";

export interface PracticeSetItem<TResponse = unknown, TResult = unknown> {
  id: string;
  title?: React.ReactNode;
  render: (context: {
    phase: PracticeSetPhase;
    response: TResponse | undefined;
    result: TResult | undefined;
    setResponse: (response: TResponse) => void;
    disabled: boolean;
  }) => React.ReactNode;
  canSubmit?: (response: TResponse | undefined) => boolean;
  evaluate?: (response: TResponse | undefined) => TResult;
  feedback?: React.ReactNode | ((result: TResult | undefined) => React.ReactNode);
}

export interface PracticeSetAttempt<TResponse = unknown, TResult = unknown> {
  itemId: string;
  itemIndex: number;
  response: TResponse | undefined;
  result: TResult | undefined;
  attemptNumber: number;
}

export interface PracticeSetLabels {
  progress: (current: number, total: number) => string;
  submit: string;
  next: string;
  finish: string;
  reviewHeading: string;
  completeHeading: string;
  completeSummary: (attempted: number, total: number) => string;
  restart: string;
  emptyHeading: string;
  emptyDescription: string;
}

const defaultLabels: PracticeSetLabels = {
  progress: (current, total) => `Question ${current} of ${total}`,
  submit: "Submit answer",
  next: "Next question",
  finish: "Finish practice",
  reviewHeading: "Review your attempt",
  completeHeading: "Practice complete",
  completeSummary: (attempted, total) => `You attempted ${attempted} of ${total} questions.`,
  restart: "Practice again",
  emptyHeading: "No practice items",
  emptyDescription: "Add at least one item to start a practice set.",
};

export interface PracticeSetProps<TResponse = unknown, TResult = unknown>
  extends Omit<React.ComponentPropsWithoutRef<"div">, "children" | "onSubmit"> {
  items?: readonly PracticeSetItem<TResponse, TResult>[];
  index?: number;
  defaultIndex?: number;
  onIndexChange?: (index: number) => void;
  attempts?: readonly PracticeSetAttempt<TResponse, TResult>[];
  defaultAttempts?: readonly PracticeSetAttempt<TResponse, TResult>[];
  onAttemptsChange?: (attempts: readonly PracticeSetAttempt<TResponse, TResult>[]) => void;
  onItemSubmit?: (attempt: PracticeSetAttempt<TResponse, TResult>) => void;
  onComplete?: (attempts: readonly PracticeSetAttempt<TResponse, TResult>[]) => void;
  disabled?: boolean;
  labels?: Partial<PracticeSetLabels>;
}

/**
 * A bounded practice-session orchestrator. Items own their response UI and optional evaluation;
 * PracticeSet owns navigation, submission, review and the terminal summary. It deliberately has no
 * universal score contract: heterogeneous child results remain opaque to the container.
 */
export function PracticeSet<TResponse = unknown, TResult = unknown>({
  items = [],
  index: indexProp,
  defaultIndex = 0,
  onIndexChange,
  attempts: attemptsProp,
  defaultAttempts = [],
  onAttemptsChange,
  onItemSubmit,
  onComplete,
  disabled = false,
  labels: labelsProp,
  className,
  ...props
}: PracticeSetProps<TResponse, TResult>) {
  const labels = { ...defaultLabels, ...labelsProp };
  const indexControlled = indexProp !== undefined;
  const attemptsControlled = attemptsProp !== undefined;
  const [localIndex, setLocalIndex] = React.useState(defaultIndex);
  const [localAttempts, setLocalAttempts] = React.useState<readonly PracticeSetAttempt<TResponse, TResult>[]>(defaultAttempts);
  const [responses, setResponses] = React.useState<Record<string, TResponse | undefined>>({});
  const [reviewing, setReviewing] = React.useState(false);
  const index = Math.max(0, Math.min(indexControlled ? indexProp : localIndex, items.length));
  const attempts = attemptsControlled ? attemptsProp : localAttempts;
  const current = index < items.length ? items[index] : undefined;
  const response = current ? responses[current.id] : undefined;

  const changeIndex = (next: number) => {
    if (!indexControlled) setLocalIndex(next);
    onIndexChange?.(next);
  };

  const changeAttempts = (next: readonly PracticeSetAttempt<TResponse, TResult>[]) => {
    if (!attemptsControlled) setLocalAttempts(next);
    onAttemptsChange?.(next);
  };

  const submit = () => {
    if (!current || disabled || reviewing || (current.canSubmit && !current.canSubmit(response))) return;
    const attempt: PracticeSetAttempt<TResponse, TResult> = {
      itemId: current.id,
      itemIndex: index,
      response,
      result: current.evaluate?.(response),
      attemptNumber: attempts.filter((entry) => entry.itemId === current.id).length + 1,
    };
    changeAttempts([...attempts, attempt]);
    onItemSubmit?.(attempt);
    setReviewing(true);
  };

  const advance = () => {
    const next = index + 1;
    setReviewing(false);
    changeIndex(next);
    if (next >= items.length) onComplete?.(attempts);
  };

  const restart = () => {
    setReviewing(false);
    setResponses({});
    changeAttempts([]);
    changeIndex(0);
  };

  if (items.length === 0) {
    return <Card className={cn("w-full max-w-xl", className)} data-slot="practice-set" data-state="empty" {...props}>
      <CardHeader><CardTitle>{labels.emptyHeading}</CardTitle></CardHeader>
      <CardContent className="text-sm text-muted-foreground">{labels.emptyDescription}</CardContent>
    </Card>;
  }

  if (!current) {
    return <Card className={cn("w-full max-w-xl", className)} data-slot="practice-set" data-state="complete" {...props}>
      <CardHeader><CardTitle>{labels.completeHeading}</CardTitle></CardHeader>
      <CardContent><p role="status" aria-live="polite" className="text-sm text-muted-foreground">{labels.completeSummary(attempts.length, items.length)}</p></CardContent>
      <CardFooter><Button type="button" onClick={restart} disabled={disabled}>{labels.restart}</Button></CardFooter>
    </Card>;
  }

  const latest = [...attempts].reverse().find((entry) => entry.itemId === current.id);
  const feedback = typeof current.feedback === "function" ? current.feedback(latest?.result) : current.feedback;
  return <div className={cn("flex w-full max-w-xl flex-col gap-3", className)} data-slot="practice-set" data-state={reviewing ? "review" : "attempt"} aria-disabled={disabled || undefined} {...props}>
    <p role="status" aria-live="polite" className="text-sm font-medium text-muted-foreground">{labels.progress(index + 1, items.length)}</p>
    <Card>
      {current.title ? <CardHeader><CardTitle>{current.title}</CardTitle></CardHeader> : null}
      <CardContent className="flex flex-col gap-4">
        {reviewing ? <h3 className="text-sm font-semibold">{labels.reviewHeading}</h3> : null}
        {current.render({ phase: reviewing ? "review" : "attempt", response, result: latest?.result, setResponse: (next) => { if (!disabled && !reviewing) setResponses((all) => ({ ...all, [current.id]: next })); }, disabled: disabled || reviewing })}
        {reviewing && feedback ? <div className="rounded-md bg-muted p-3 text-sm text-muted-foreground">{feedback}</div> : null}
      </CardContent>
      <CardFooter>
        {reviewing ? <Button type="button" onClick={advance} disabled={disabled}>{index === items.length - 1 ? labels.finish : labels.next}</Button> : <Button type="button" onClick={submit} disabled={disabled || (current.canSubmit ? !current.canSubmit(response) : false)}>{labels.submit}</Button>}
      </CardFooter>
    </Card>
  </div>;
}
