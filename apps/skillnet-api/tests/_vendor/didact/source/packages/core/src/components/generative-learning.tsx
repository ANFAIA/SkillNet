import * as React from "react";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Textarea,
} from "@didact/ui";

import { cn } from "../lib/cn.js";

function useControllable<T>(
  controlled: T | undefined,
  defaultValue: T,
  onChange?: (value: T) => void,
): [T, (value: T) => void] {
  const isControlled = controlled !== undefined;
  const [internalValue, setInternalValue] = React.useState(defaultValue);
  const value = controlled ?? internalValue;
  const setValue = React.useCallback(
    (next: T) => {
      if (!isControlled) setInternalValue(next);
      onChange?.(next);
    },
    [isControlled, onChange],
  );
  return [value, setValue];
}

/* -------------------------------------------------------------------------- */
/* Self-explanation prompt                                                    */

export interface SelfExplanationPromptLabels {
  activity: string;
  promptPending: string;
  response: string;
  responsePlaceholder: string;
  guidance: string;
  scaffold: (position: number) => string;
  submit: string;
  submitted: string;
  modelExplanation: string;
}

const selfExplanationDefaults: SelfExplanationPromptLabels = {
  activity: "Self-explanation",
  promptPending: "The explanation prompt is still loading.",
  response: "Your explanation",
  responsePlaceholder: "Explain the reasoning in your own words…",
  guidance: "Guidance",
  scaffold: (position) => `Prompt ${position}`,
  submit: "Submit explanation",
  submitted: "Explanation submitted.",
  modelExplanation: "Example explanation",
};

export interface SelfExplanationPromptProps
  extends Omit<React.ComponentPropsWithoutRef<"section">, "children" | "onSubmit" | "title"> {
  prompt?: React.ReactNode;
  description?: React.ReactNode;
  scaffolds?: Array<React.ReactNode | undefined>;
  modelExplanation?: React.ReactNode;
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  onSubmit?: (response: { value: string }) => void;
  minLength?: number;
  disabled?: boolean;
  labels?: Partial<SelfExplanationPromptLabels>;
}

/**
 * An open response that asks a learner to articulate reasoning. It records prose but never grades
 * it automatically. An optional example is withheld until the learner submits their own attempt.
 */
export const SelfExplanationPrompt = React.forwardRef<HTMLElement, SelfExplanationPromptProps>(
  function SelfExplanationPrompt(
    {
      prompt,
      description,
      scaffolds = [],
      modelExplanation,
      value: valueProp,
      defaultValue = "",
      onValueChange,
      onSubmit,
      minLength = 1,
      disabled = false,
      labels,
      className,
      "aria-label": ariaLabel,
      "aria-labelledby": ariaLabelledby,
      ...props
    },
    ref,
  ) {
    const copy = { ...selfExplanationDefaults, ...labels };
    const titleId = React.useId();
    const responseId = React.useId();
    const guidanceId = React.useId();
    const [value, setValue] = useControllable(valueProp, defaultValue, onValueChange);
    const [submitted, setSubmitted] = React.useState(false);
    const availableScaffolds = scaffolds.filter(
      (item): item is React.ReactNode => item !== undefined,
    );
    const canSubmit = value.trim().length >= Math.max(1, minLength) && !disabled && !submitted;

    const submit = (event: React.FormEvent) => {
      event.preventDefault();
      if (!canSubmit) return;
      setSubmitted(true);
      onSubmit?.({ value });
    };

    return (
      <section
        ref={ref}
        data-slot="self-explanation-prompt"
        aria-label={ariaLabel ?? (ariaLabelledby === undefined && prompt === undefined ? copy.activity : undefined)}
        aria-labelledby={ariaLabelledby ?? (prompt !== undefined ? titleId : undefined)}
        className={cn("w-full max-w-2xl", className)}
        {...props}
      >
        <Card>
          <CardHeader>
            <CardTitle id={titleId}>{prompt ?? copy.promptPending}</CardTitle>
            {description !== undefined ? <CardDescription>{description}</CardDescription> : null}
          </CardHeader>
          {/* The form is one direct Card child, so it must restore the Card's vertical rhythm
              between its nested content and action slots. */}
          <form onSubmit={submit} className="flex flex-col gap-6">
            <CardContent className="flex flex-col gap-4">
              {availableScaffolds.length > 0 ? (
                <aside aria-labelledby={guidanceId} className="rounded-md border bg-muted p-4">
                  <p id={guidanceId} className="mb-2 text-sm font-medium text-foreground">
                    {copy.guidance}
                  </p>
                  <ul className="flex list-disc flex-col gap-1 pl-5 text-sm text-muted-foreground">
                    {availableScaffolds.map((scaffold, index) => (
                      <li key={index}>
                        <span className="sr-only">{copy.scaffold(index + 1)}: </span>
                        {scaffold}
                      </li>
                    ))}
                  </ul>
                </aside>
              ) : null}

              <div className="flex flex-col gap-2">
                <Label htmlFor={responseId}>{copy.response}</Label>
                <Textarea
                  id={responseId}
                  value={value}
                  placeholder={copy.responsePlaceholder}
                  onChange={(event) => setValue(event.target.value)}
                  disabled={disabled || submitted}
                  aria-describedby={availableScaffolds.length > 0 ? guidanceId : undefined}
                  rows={5}
                />
              </div>

              {submitted ? (
                <div role="status" aria-live="polite" className="rounded-md border p-3 text-sm">
                  <p className="font-medium text-foreground">{copy.submitted}</p>
                  {modelExplanation !== undefined ? (
                    <div className="mt-3 border-t pt-3">
                      <p className="mb-1 font-medium text-foreground">{copy.modelExplanation}</p>
                      <div className="text-muted-foreground">{modelExplanation}</div>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </CardContent>
            {!submitted ? (
              <CardFooter>
                <Button type="submit" disabled={!canSubmit}>{copy.submit}</Button>
              </CardFooter>
            ) : null}
          </form>
        </Card>
      </section>
    );
  },
);

/* -------------------------------------------------------------------------- */
/* Worked example                                                             */

export interface WorkedExampleStep {
  id: string;
  title?: React.ReactNode;
  content?: React.ReactNode;
  rationale?: React.ReactNode;
}

export interface WorkedExampleLabels {
  example: string;
  problemPending: string;
  step: (position: number, total: number) => string;
  stepPending: string;
  rationale: string;
  nextStep: string;
  complete: string;
  noSteps: string;
}

const workedExampleDefaults: WorkedExampleLabels = {
  example: "Worked example",
  problemPending: "The example problem is still loading.",
  step: (position, total) => `Step ${position} of ${total}`,
  stepPending: "Step content is still loading.",
  rationale: "Why this step?",
  nextStep: "Show next step",
  complete: "All steps are visible.",
  noSteps: "No solution steps yet.",
};

export interface WorkedExampleProps
  extends Omit<React.ComponentPropsWithoutRef<"section">, "children" | "title"> {
  problem?: React.ReactNode;
  description?: React.ReactNode;
  steps?: WorkedExampleStep[];
  summary?: React.ReactNode;
  mode?: "static" | "progressive";
  revealedStepCount?: number;
  defaultRevealedStepCount?: number;
  onRevealedStepCountChange?: (count: number) => void;
  disabled?: boolean;
  labels?: Partial<WorkedExampleLabels>;
}

/** A solved process. Progressive disclosure is navigation through content, never assessment. */
export const WorkedExample = React.forwardRef<HTMLElement, WorkedExampleProps>(
  function WorkedExample(
    {
      problem,
      description,
      steps = [],
      summary,
      mode = "static",
      revealedStepCount: revealedCountProp,
      defaultRevealedStepCount = 1,
      onRevealedStepCountChange,
      disabled = false,
      labels,
      className,
      "aria-label": ariaLabel,
      "aria-labelledby": ariaLabelledby,
      ...props
    },
    ref,
  ) {
    const copy = { ...workedExampleDefaults, ...labels };
    const titleId = React.useId();
    const stepsId = React.useId();
    const [requestedCount, setRequestedCount] = useControllable(
      revealedCountProp,
      defaultRevealedStepCount,
      onRevealedStepCountChange,
    );
    const visibleCount = mode === "static"
      ? steps.length
      : Math.max(0, Math.min(requestedCount, steps.length));
    const visibleSteps = steps.slice(0, visibleCount);
    const canReveal = mode === "progressive" && visibleCount < steps.length;

    return (
      <section
        ref={ref}
        data-slot="worked-example"
        data-mode={mode}
        aria-label={ariaLabel ?? (ariaLabelledby === undefined && problem === undefined ? copy.example : undefined)}
        aria-labelledby={ariaLabelledby ?? (problem !== undefined ? titleId : undefined)}
        className={cn("w-full max-w-2xl", className)}
        {...props}
      >
        <Card>
          <CardHeader>
            <CardTitle id={titleId}>{problem ?? copy.problemPending}</CardTitle>
            {description !== undefined ? <CardDescription>{description}</CardDescription> : null}
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {steps.length === 0 ? (
              <p className="rounded-md border p-4 text-sm text-muted-foreground">{copy.noSteps}</p>
            ) : (
              <ol id={stepsId} className="flex flex-col gap-3" aria-live="polite">
                {visibleSteps.map((step, index) => (
                  <li key={step.id} className="rounded-md border p-4">
                    <p className="text-xs font-medium text-muted-foreground">
                      {copy.step(index + 1, steps.length)}
                    </p>
                    {step.title !== undefined ? (
                      <h3 className="mt-1 text-sm font-medium text-foreground">{step.title}</h3>
                    ) : null}
                    <div className="mt-2 text-sm leading-relaxed text-foreground">
                      {step.content ?? copy.stepPending}
                    </div>
                    {step.rationale !== undefined ? (
                      <div className="mt-3 border-t pt-3 text-sm">
                        <p className="mb-1 font-medium text-foreground">{copy.rationale}</p>
                        <div className="text-muted-foreground">{step.rationale}</div>
                      </div>
                    ) : null}
                  </li>
                ))}
              </ol>
            )}
            {!canReveal && steps.length > 0 && summary !== undefined ? (
              <div className="rounded-md bg-muted p-4 text-sm">
                <span className="sr-only">{copy.complete} </span>
                {summary}
              </div>
            ) : null}
          </CardContent>
          {canReveal ? (
            <CardFooter>
              <Button
                type="button"
                aria-controls={stepsId}
                disabled={disabled}
                onClick={() => setRequestedCount(visibleCount + 1)}
              >
                {copy.nextStep}
              </Button>
            </CardFooter>
          ) : null}
        </Card>
      </section>
    );
  },
);

/* -------------------------------------------------------------------------- */
/* Completion problem                                                         */

export interface CompletionWorkedStep {
  id: string;
  kind: "worked";
  title?: React.ReactNode;
  content?: React.ReactNode;
  rationale?: React.ReactNode;
}

export interface CompletionMissingStep {
  id: string;
  kind: "completion";
  title?: React.ReactNode;
  prompt?: React.ReactNode;
  acceptedAnswers?: string[];
  caseSensitive?: boolean;
  multiline?: boolean;
  placeholder?: string;
  feedback?: React.ReactNode;
}

export type CompletionProblemStep = CompletionWorkedStep | CompletionMissingStep;
export type CompletionProblemValue = Record<string, string>;
export type CompletionStepStatus = "correct" | "incorrect" | "ungraded";

export interface CompletionProblemResult {
  value: CompletionProblemValue;
  status: "correct" | "incorrect" | "partial" | "ungraded";
  steps: Record<string, CompletionStepStatus>;
}

export interface CompletionProblemLabels {
  activity: string;
  problemPending: string;
  step: (position: number, total: number) => string;
  workedStep: string;
  missingStep: string;
  response: (position: number) => string;
  submit: string;
  correct: string;
  incorrect: string;
  ungraded: string;
  acceptedAnswer: string;
  noSteps: string;
  incomplete: string;
}

const completionDefaults: CompletionProblemLabels = {
  activity: "Completion problem",
  problemPending: "The problem is still loading.",
  step: (position, total) => `Step ${position} of ${total}`,
  workedStep: "Worked step",
  missingStep: "Complete this step",
  response: (position) => `Your response for step ${position}`,
  submit: "Check responses",
  correct: "Correct",
  incorrect: "Needs revision",
  ungraded: "Submitted for review",
  acceptedAnswer: "Accepted answer",
  noSteps: "No problem steps yet.",
  incomplete: "Complete every missing step before submitting.",
};

function normalize(value: string, caseSensitive: boolean): string {
  const normalized = value.trim().replace(/\s+/g, " ");
  return caseSensitive ? normalized : normalized.toLocaleLowerCase();
}

function evaluateCompletion(
  steps: CompletionProblemStep[],
  value: CompletionProblemValue,
): CompletionProblemResult {
  const outcomes: Record<string, CompletionStepStatus> = {};
  for (const step of steps) {
    if (step.kind !== "completion") continue;
    if (!step.acceptedAnswers || step.acceptedAnswers.length === 0) {
      outcomes[step.id] = "ungraded";
      continue;
    }
    const candidate = normalize(value[step.id] ?? "", step.caseSensitive ?? false);
    outcomes[step.id] = step.acceptedAnswers.some(
      (answer) => normalize(answer, step.caseSensitive ?? false) === candidate,
    ) ? "correct" : "incorrect";
  }
  const statuses = Object.values(outcomes);
  const graded = statuses.filter((status) => status !== "ungraded");
  const correctCount = graded.filter((status) => status === "correct").length;
  const status = graded.length === 0
    ? "ungraded"
    : statuses.some((stepStatus) => stepStatus === "ungraded")
      ? "partial"
    : correctCount === graded.length
      ? "correct"
      : correctCount === 0
          ? "incorrect"
          : "partial";
  return { value: { ...value }, status, steps: outcomes };
}

export interface CompletionProblemProps
  extends Omit<
    React.ComponentPropsWithoutRef<"section">,
    "children" | "defaultValue" | "onSubmit" | "title"
  > {
  problem?: React.ReactNode;
  description?: React.ReactNode;
  steps?: CompletionProblemStep[];
  value?: CompletionProblemValue;
  defaultValue?: CompletionProblemValue;
  onValueChange?: (value: CompletionProblemValue) => void;
  onSubmit?: (result: CompletionProblemResult) => void;
  disabled?: boolean;
  labels?: Partial<CompletionProblemLabels>;
}

/** A partly solved sequence with text gaps and per-step informative feedback. */
export const CompletionProblem = React.forwardRef<HTMLElement, CompletionProblemProps>(
  function CompletionProblem(
    {
      problem,
      description,
      steps = [],
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
    const copy = { ...completionDefaults, ...labels };
    const titleId = React.useId();
    const errorId = React.useId();
    const [value, setValue] = useControllable(valueProp, defaultValue, onValueChange);
    const [result, setResult] = React.useState<CompletionProblemResult>();
    const missingSteps = steps.filter(
      (step): step is CompletionMissingStep => step.kind === "completion",
    );
    const complete = missingSteps.length > 0 && missingSteps.every(
      (step) => (value[step.id] ?? "").trim().length > 0,
    );

    const update = (id: string, response: string) => setValue({ ...value, [id]: response });
    const submit = (event: React.FormEvent) => {
      event.preventDefault();
      if (!complete || disabled || result !== undefined) return;
      const next = evaluateCompletion(steps, value);
      setResult(next);
      onSubmit?.(next);
    };

    return (
      <section
        ref={ref}
        data-slot="completion-problem"
        data-result={result?.status}
        aria-label={ariaLabel ?? (ariaLabelledby === undefined && problem === undefined ? copy.activity : undefined)}
        aria-labelledby={ariaLabelledby ?? (problem !== undefined ? titleId : undefined)}
        className={cn("w-full max-w-2xl", className)}
        {...props}
      >
        <Card>
          <CardHeader>
            <CardTitle id={titleId}>{problem ?? copy.problemPending}</CardTitle>
            {description !== undefined ? <CardDescription>{description}</CardDescription> : null}
          </CardHeader>
          {/* Card's own gap only separates direct children; both slots live inside this form. */}
          <form onSubmit={submit} className="flex flex-col gap-6">
            <CardContent>
              {steps.length === 0 ? (
                <p className="rounded-md border p-4 text-sm text-muted-foreground">{copy.noSteps}</p>
              ) : (
                <ol className="flex flex-col gap-3">
                  {steps.map((step, index) => {
                    const position = index + 1;
                    const status = result?.steps[step.id];
                    const inputId = `${titleId}-response-${index}`;
                    const feedbackId = `${inputId}-feedback`;
                    return (
                      <li key={step.id} data-kind={step.kind} data-status={status} className="rounded-md border p-4">
                        <p className="text-xs font-medium text-muted-foreground">
                          {copy.step(position, steps.length)} · {step.kind === "worked" ? copy.workedStep : copy.missingStep}
                        </p>
                        {step.title !== undefined ? <h3 className="mt-1 text-sm font-medium">{step.title}</h3> : null}
                        {step.kind === "worked" ? (
                          <>
                            {step.content !== undefined ? <div className="mt-2 text-sm">{step.content}</div> : null}
                            {step.rationale !== undefined ? <div className="mt-2 text-sm text-muted-foreground">{step.rationale}</div> : null}
                          </>
                        ) : (
                          <div className="mt-3 flex flex-col gap-2">
                            <Label htmlFor={inputId}>{step.prompt ?? copy.response(position)}</Label>
                            {step.multiline ? (
                              <Textarea
                                id={inputId}
                                value={value[step.id] ?? ""}
                                placeholder={step.placeholder}
                                onChange={(event) => update(step.id, event.target.value)}
                                disabled={disabled || result !== undefined}
                                aria-invalid={status === "incorrect" || undefined}
                                aria-describedby={status !== undefined ? feedbackId : undefined}
                              />
                            ) : (
                              <Input
                                id={inputId}
                                value={value[step.id] ?? ""}
                                placeholder={step.placeholder}
                                onChange={(event) => update(step.id, event.target.value)}
                                disabled={disabled || result !== undefined}
                                aria-invalid={status === "incorrect" || undefined}
                                aria-describedby={status !== undefined ? feedbackId : undefined}
                              />
                            )}
                            {status !== undefined ? (
                              <div id={feedbackId} role="status" className="rounded-md bg-muted p-3 text-sm">
                                <p className="font-medium">
                                  {status === "correct" ? copy.correct : status === "incorrect" ? copy.incorrect : copy.ungraded}
                                </p>
                                {step.feedback !== undefined ? <div className="mt-1 text-muted-foreground">{step.feedback}</div> : null}
                                {status === "incorrect" && step.acceptedAnswers?.[0] !== undefined ? (
                                  <p className="mt-1 text-muted-foreground">{copy.acceptedAnswer}: <span className="font-medium text-foreground">{step.acceptedAnswers[0]}</span></p>
                                ) : null}
                              </div>
                            ) : null}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ol>
              )}
              {missingSteps.length > 0 && !complete && result === undefined ? (
                <p id={errorId} className="mt-3 text-sm text-muted-foreground">{copy.incomplete}</p>
              ) : null}
            </CardContent>
            {missingSteps.length > 0 && result === undefined ? (
              <CardFooter>
                <Button type="submit" disabled={!complete || disabled} aria-describedby={!complete ? errorId : undefined}>
                  {copy.submit}
                </Button>
              </CardFooter>
            ) : null}
          </form>
        </Card>
      </section>
    );
  },
);
