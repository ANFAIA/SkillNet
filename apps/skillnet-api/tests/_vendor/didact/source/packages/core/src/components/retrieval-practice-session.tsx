import * as React from "react";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Label,
  Textarea,
} from "@didact/ui";
import {
  sm2Scheduler,
  type ReviewGrade,
  type ReviewResult,
  type ReviewState,
  type SpacedRepetitionScheduler,
} from "@didact/spaced-repetition";

import { cn } from "../lib/cn.js";

export interface RetrievalPracticeItem {
  id: string;
  title?: React.ReactNode;
  prompt?: React.ReactNode;
  answer?: React.ReactNode;
  state?: ReviewState;
}

export interface RetrievalPracticeReview {
  item: RetrievalPracticeItem;
  index: number;
  response: string;
  grade: ReviewGrade;
  result: ReviewResult;
}

export interface RetrievalPracticePersistence {
  load?: (item: RetrievalPracticeItem) => ReviewState | undefined;
  save: (review: RetrievalPracticeReview) => void | Promise<void>;
}

export interface RetrievalPracticeLabels {
  progress: (current: number, total: number) => string;
  sessionTitle: string;
  instruction: string;
  responseLabel: string;
  responsePlaceholder: string;
  compare: string;
  yourResponse: string;
  modelAnswer: string;
  waitingForPrompt: string;
  waitingForAnswer: string;
  ratingPrompt: string;
  again: string;
  hard: string;
  good: string;
  easy: string;
  completeHeading: string;
  completeSummary: (reviewed: number) => string;
  restart: string;
  emptyHeading: string;
  emptyDescription: string;
}

const defaultLabels: RetrievalPracticeLabels = {
  progress: (current, total) => `Retrieval ${current} of ${total}`,
  sessionTitle: "Retrieval practice",
  instruction: "Write what you can recall before comparing it with the model answer.",
  responseLabel: "Your response",
  responsePlaceholder: "Explain the answer from memory…",
  compare: "Compare with model answer",
  yourResponse: "Your response",
  modelAnswer: "Model answer",
  waitingForPrompt: "This prompt is still loading.",
  waitingForAnswer: "The model answer is still loading.",
  ratingPrompt: "How difficult was this retrieval?",
  again: "Again",
  hard: "Hard",
  good: "Good",
  easy: "Easy",
  completeHeading: "Retrieval session complete",
  completeSummary: (reviewed) => `You completed ${reviewed} retrieval attempts.`,
  restart: "Start another session",
  emptyHeading: "Nothing due for retrieval",
  emptyDescription: "Provide one or more prompts when they are ready to be reviewed.",
};

export interface RetrievalPracticeSessionProps
  extends Omit<React.ComponentPropsWithoutRef<"div">, "onChange"> {
  items?: readonly RetrievalPracticeItem[];
  scheduler?: SpacedRepetitionScheduler;
  persistence?: RetrievalPracticePersistence;
  maxItems?: number;
  index?: number;
  defaultIndex?: number;
  onIndexChange?: (index: number) => void;
  responses?: Readonly<Record<string, string>>;
  defaultResponses?: Readonly<Record<string, string>>;
  onResponseChange?: (payload: {
    item: RetrievalPracticeItem;
    index: number;
    response: string;
  }) => void;
  onReview?: (review: RetrievalPracticeReview) => void;
  onComplete?: (reviews: readonly RetrievalPracticeReview[]) => void;
  renderPrompt?: (item: RetrievalPracticeItem) => React.ReactNode;
  renderAnswer?: (item: RetrievalPracticeItem) => React.ReactNode;
  disabled?: boolean;
  labels?: Partial<RetrievalPracticeLabels>;
}

/** A constructed-retrieval flow: write from memory, compare, self-assess, then schedule. */
export const RetrievalPracticeSession = React.forwardRef<
  HTMLDivElement,
  RetrievalPracticeSessionProps
>(function RetrievalPracticeSession(
  {
    items = [],
    scheduler = sm2Scheduler,
    persistence,
    maxItems,
    index: indexProp,
    defaultIndex = 0,
    onIndexChange,
    responses: responsesProp,
    defaultResponses = {},
    onResponseChange,
    onReview,
    onComplete,
    renderPrompt,
    renderAnswer,
    disabled = false,
    labels: labelsProp,
    className,
    ...props
  },
  ref,
) {
  const labels = { ...defaultLabels, ...labelsProp };
  const queue = maxItems === undefined ? items : items.slice(0, Math.max(0, maxItems));
  const indexControlled = indexProp !== undefined;
  const responsesControlled = responsesProp !== undefined;
  const [localIndex, setLocalIndex] = React.useState(defaultIndex);
  const [localResponses, setLocalResponses] = React.useState<Readonly<Record<string, string>>>(
    defaultResponses,
  );
  const [comparing, setComparing] = React.useState(false);
  const [reviews, setReviews] = React.useState<readonly RetrievalPracticeReview[]>([]);
  const index = Math.max(
    0,
    Math.min(indexControlled ? indexProp : localIndex, queue.length),
  );
  const current = index < queue.length ? queue[index] : undefined;
  const responses = responsesControlled ? responsesProp : localResponses;
  const response = current ? (responses[current.id] ?? "") : "";

  const changeIndex = (next: number) => {
    if (!indexControlled) setLocalIndex(next);
    onIndexChange?.(next);
  };

  const changeResponse = (next: string) => {
    if (!current || comparing || disabled) return;
    if (!responsesControlled) {
      setLocalResponses((all) => ({ ...all, [current.id]: next }));
    }
    onResponseChange?.({ item: current, index, response: next });
  };

  const rate = (grade: ReviewGrade) => {
    if (!current || disabled || !comparing) return;
    const state =
      persistence?.load?.(current) ?? current.state ?? scheduler.createInitialState();
    const review: RetrievalPracticeReview = {
      item: current,
      index,
      response,
      grade,
      result: scheduler.schedule(state, grade),
    };
    const nextReviews = [...reviews, review];
    setReviews(nextReviews);
    onReview?.(review);
    void persistence?.save(review);
    const next = index + 1;
    setComparing(false);
    changeIndex(next);
    if (next >= queue.length) onComplete?.(nextReviews);
  };

  const restart = () => {
    setReviews([]);
    setComparing(false);
    if (!responsesControlled) setLocalResponses({});
    changeIndex(0);
  };

  if (queue.length === 0) {
    return (
      <Card
        ref={ref}
        className={cn("w-full max-w-xl", className)}
        data-slot="retrieval-practice-session"
        data-state="empty"
        {...props}
      >
        <CardHeader><CardTitle>{labels.emptyHeading}</CardTitle></CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {labels.emptyDescription}
        </CardContent>
      </Card>
    );
  }

  if (!current) {
    return (
      <Card
        ref={ref}
        className={cn("w-full max-w-xl", className)}
        data-slot="retrieval-practice-session"
        data-state="complete"
        {...props}
      >
        <CardHeader><CardTitle>{labels.completeHeading}</CardTitle></CardHeader>
        <CardContent>
          <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
            {labels.completeSummary(reviews.length)}
          </p>
        </CardContent>
        <CardFooter>
          <Button type="button" onClick={restart} disabled={disabled}>{labels.restart}</Button>
        </CardFooter>
      </Card>
    );
  }

  const responseId = `retrieval-response-${current.id}`;
  const canCompare = response.trim().length > 0
    && (current.answer != null || renderAnswer != null)
    && !disabled;

  return (
    <div
      ref={ref}
      className={cn("flex w-full max-w-xl flex-col gap-3", className)}
      data-slot="retrieval-practice-session"
      data-state={comparing ? "comparison" : "responding"}
      aria-disabled={disabled || undefined}
      {...props}
    >
      <p role="status" aria-live="polite" className="text-sm font-medium text-muted-foreground">
        {labels.progress(index + 1, queue.length)}
      </p>
      <Card>
        <CardHeader>
          <CardTitle>{current.title ?? labels.sessionTitle}</CardTitle>
          <CardDescription>{labels.instruction}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <div className="text-base font-medium">
            {renderPrompt
              ? renderPrompt(current)
              : (current.prompt ?? labels.waitingForPrompt)}
          </div>
          {!comparing ? (
            <div className="grid gap-2">
              <Label htmlFor={responseId}>{labels.responseLabel}</Label>
              <Textarea
                id={responseId}
                value={response}
                placeholder={labels.responsePlaceholder}
                disabled={disabled || (current.prompt == null && renderPrompt == null)}
                onChange={(event) => changeResponse(event.target.value)}
              />
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              <section className="rounded-md border p-4" aria-labelledby={`${responseId}-yours`}>
                <h3 id={`${responseId}-yours`} className="mb-2 text-sm font-semibold">
                  {labels.yourResponse}
                </h3>
                <p className="whitespace-pre-wrap text-sm">{response}</p>
              </section>
              <section
                className="rounded-md border bg-muted/40 p-4"
                aria-labelledby={`${responseId}-model`}
              >
                <h3 id={`${responseId}-model`} className="mb-2 text-sm font-semibold">
                  {labels.modelAnswer}
                </h3>
                <div className="text-sm">
                  {renderAnswer
                    ? renderAnswer(current)
                    : (current.answer ?? labels.waitingForAnswer)}
                </div>
              </section>
            </div>
          )}
        </CardContent>
        <CardFooter className="flex flex-col items-stretch gap-3">
          {!comparing ? (
            <Button type="button" disabled={!canCompare} onClick={() => setComparing(true)}>
              {labels.compare}
            </Button>
          ) : (
            <fieldset disabled={disabled} className="flex flex-col gap-2">
              <legend className="text-sm font-medium">{labels.ratingPrompt}</legend>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {(["again", "hard", "good", "easy"] as const).map((grade) => (
                  <Button
                    key={grade}
                    type="button"
                    variant={grade === "good" ? "default" : "outline"}
                    onClick={() => rate(grade)}
                  >
                    {labels[grade]}
                  </Button>
                ))}
              </div>
            </fieldset>
          )}
        </CardFooter>
      </Card>
    </div>
  );
});
