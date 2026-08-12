import * as React from "react";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Checkbox,
  Input,
  Label,
  RadioGroup,
  RadioGroupItem,
  Textarea,
  ToggleGroup,
  ToggleGroupItem,
} from "@didact/ui";

import { cn } from "../lib/cn.js";

/**
 * QuizItem family (RF-4) -- quiz variants beyond single-choice, all sharing one shell and one set
 * of interaction/accessibility norms:
 *
 * - `SingleChoiceQuiz`   -- multiple-choice, exactly one correct option (RadioGroup).
 * - `MultiSelectQuiz`    -- "select all that apply", a set of correct options (Checkboxes).
 * - `TrueFalseQuiz`      -- a statement judged true or false (RadioGroup of two).
 * - `FillInTheBlankQuiz` -- a short exact answer typed into an Input, verified against accepted
 *                            answers with configurable normalization.
 * - `ShortAnswerQuiz`    -- an open answer typed into a Textarea, "assisted verification": on
 *                            submit it reveals a model answer and the learner self-assesses (free
 *                            text cannot be graded reliably, RF-4's "assisted" wording).
 *
 * Shared contract (documented once here, honored by every variant):
 *
 * - **Controlled / uncontrolled answer state** (same pattern as `Flashcard`): pass `value`
 *   (updating it from `onAnswer`) to own the answer yourself, or leave it out and let the variant
 *   track its own, seeded from `defaultValue`. `onAnswer` fires on every answer change; `onSubmit`
 *   fires once when the learner submits, with the answer and the computed correctness.
 * - **Optional informative feedback** (RF-4): every variant accepts an optional `feedback` node,
 *   rendered only AFTER submission. This is the evidence-backed "why this is correct / what
 *   strategy to use" area -- supported, never required.
 * - **Correct/incorrect is never color-only** (RF-12, WCAG 1.4.1): the result is always an icon +
 *   text ("Correct" / "Not quite"), and per-option markers are icon + text ("Correct answer" /
 *   "Your answer") -- background color, where present, only reinforces text that already stands on
 *   its own.
 * - **No answer key leaked before submission** (RNF-3-adjacent): for the auto-graded variants the
 *   correct answer is never rendered into the DOM (no marker attribute, no revealed text) until
 *   the learner submits. It lives only in component props/closure until then.
 * - **Composition** (docs/interface-norms.md): the shell is `@didact/ui`'s `Card`, submit is a
 *   single primary `Button` (Action hierarchy: one primary per view), inputs are `@didact/ui`'s
 *   `RadioGroup`/`Checkbox`/`Input`/`Textarea`. No bespoke primitives; standard utilities only.
 * - **Motion** (RF-13): the only transition this family adds -- the result banner's appearance --
 *   uses a standard `duration-*` utility guarded by `motion-reduce:transition-none`, so
 *   `prefers-reduced-motion` turns it into an instant change with no separate branch.
 * - **After submission the inputs lock** so an answer can't be changed once its correctness is
 *   shown; the primary submit action is replaced by the result.
 */

/* ------------------------------------------------------------------ shared helpers */

/** Correctness of a submitted answer. `undefined` = submitted but not yet graded (short answer). */
export type QuizCorrectness = boolean | undefined;

/** Minimal controlled/uncontrolled state helper, matching Flashcard's inline pattern. */
function useControllable<T>(
  controlled: T | undefined,
  defaultValue: T,
  onChange?: (value: T) => void,
): [T, (value: T) => void] {
  const isControlled = controlled !== undefined;
  const [uncontrolled, setUncontrolled] = React.useState<T>(defaultValue);
  const value = isControlled ? (controlled as T) : uncontrolled;
  const setValue = React.useCallback(
    (next: T) => {
      if (!isControlled) setUncontrolled(next);
      onChange?.(next);
    },
    [isControlled, onChange],
  );
  return [value, setValue];
}

function CheckIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      <path d="M3 8.5 6.5 12 13 4.5" />
    </svg>
  );
}

function CrossIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      <path d="M4 4l8 8M12 4l-8 8" />
    </svg>
  );
}

/**
 * The result banner shown after submission. Correctness is carried by BOTH an icon and text, never
 * color alone (RF-12). The subtle border/background tint only reinforces the text. `role="status"`
 * + `aria-live="polite"` announces the outcome to screen readers without moving focus.
 */
function QuizResult({ correct }: { correct: QuizCorrectness }) {
  if (correct === undefined) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      data-correct={correct}
      className={cn(
        "flex items-center gap-2 rounded-md border p-3 text-sm font-medium transition-opacity duration-200 motion-reduce:transition-none",
        correct
          ? "border-primary/40 bg-primary/5 text-foreground"
          : "border-destructive/40 bg-destructive/5 text-foreground",
      )}
    >
      {correct ? (
        <CheckIcon className="size-4 text-primary" />
      ) : (
        <CrossIcon className="size-4 text-destructive" />
      )}
      <span>{correct ? "Correct" : "Not quite"}</span>
    </div>
  );
}

/** Per-option marker after submission: icon + text, never color-only. */
function OptionMarker({ kind }: { kind: "correct" | "yours" }) {
  return (
    <span className="ml-2 inline-flex items-center gap-1 text-xs font-medium text-muted-foreground">
      {kind === "correct" ? (
        <>
          <CheckIcon className="size-3 text-primary" />
          Correct answer
        </>
      ) : (
        <>
          <CrossIcon className="size-3 text-destructive" />
          Your answer
        </>
      )}
    </span>
  );
}

interface QuizShellProps {
  titleId: string;
  question: React.ReactNode;
  instructions?: React.ReactNode;
  submitted: boolean;
  correct: QuizCorrectness;
  canSubmit: boolean;
  submitLabel: string;
  onSubmit: () => void;
  feedback?: React.ReactNode;
  /** Extra content rendered after the result banner (e.g. short-answer's model + self-assessment). */
  afterResult?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}

/**
 * Shared Card shell for every quiz variant: header (question + optional instructions), content
 * (the inputs, then the result + feedback once submitted), and a footer holding the single primary
 * submit action until submission.
 */
function QuizShell({
  titleId,
  question,
  instructions,
  submitted,
  correct,
  canSubmit,
  submitLabel,
  onSubmit,
  feedback,
  afterResult,
  className,
  children,
  ...props
}: QuizShellProps & Omit<React.ComponentPropsWithoutRef<"div">, "children">) {
  return (
    <Card className={cn("w-full max-w-md", className)} data-slot="quiz-item" {...props}>
      <CardHeader>
        <CardTitle id={titleId}>{question}</CardTitle>
        {instructions ? <CardDescription>{instructions}</CardDescription> : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {children}
        {submitted ? <QuizResult correct={correct} /> : null}
        {submitted ? afterResult : null}
        {submitted && feedback ? (
          <div className="rounded-md bg-muted p-3 text-sm text-muted-foreground">{feedback}</div>
        ) : null}
      </CardContent>
      {!submitted ? (
        <CardFooter>
          <Button type="button" onClick={onSubmit} disabled={!canSubmit}>
            {submitLabel}
          </Button>
        </CardFooter>
      ) : null}
    </Card>
  );
}

/* ------------------------------------------------------------------ shared prop bits */

export interface QuizOption {
  /** The value stored/compared for this option. */
  value: string;
  /** The visible label. */
  label: React.ReactNode;
}

interface QuizVariantBaseProps {
  /** The prompt/question. */
  question: React.ReactNode;
  /** Optional informative feedback shown only AFTER submission (RF-4). */
  feedback?: React.ReactNode;
  /** Disable all interaction. */
  disabled?: boolean;
  /** Label for the primary submit button. Defaults to "Submit". */
  submitLabel?: string;
  className?: string;
}

/* ------------------------------------------------------------------ SingleChoiceQuiz */

export interface SingleChoiceQuizProps extends QuizVariantBaseProps {
  options: QuizOption[];
  /** The single correct option's value. Never rendered to the DOM before submission. */
  correctValue: string;
  value?: string;
  defaultValue?: string;
  onAnswer?: (value: string) => void;
  onSubmit?: (result: { value: string | undefined; correct: boolean }) => void;
}

export function SingleChoiceQuiz({
  question,
  options,
  correctValue,
  value: valueProp,
  defaultValue,
  onAnswer,
  onSubmit,
  feedback,
  disabled = false,
  submitLabel = "Submit",
  className,
}: SingleChoiceQuizProps) {
  const titleId = React.useId();
  const [value, setValue] = useControllable<string | undefined>(
    valueProp,
    defaultValue,
    onAnswer ? (next) => next !== undefined && onAnswer(next) : undefined,
  );
  const [submitted, setSubmitted] = React.useState(false);
  const correct = submitted ? value === correctValue : undefined;

  const submit = () => {
    if (value === undefined) return;
    setSubmitted(true);
    onSubmit?.({ value, correct: value === correctValue });
  };

  return (
    <QuizShell
      titleId={titleId}
      question={question}
      submitted={submitted}
      correct={correct}
      canSubmit={value !== undefined && !disabled}
      submitLabel={submitLabel}
      onSubmit={submit}
      feedback={feedback}
      className={className}
    >
      <RadioGroup
        aria-labelledby={titleId}
        value={value ?? ""}
        onValueChange={(next) => setValue(next)}
        disabled={disabled || submitted}
      >
        {options.map((option) => {
          const optionId = `${titleId}-${option.value}`;
          const showCorrect = submitted && option.value === correctValue;
          const showYoursWrong = submitted && option.value === value && value !== correctValue;
          return (
            <div key={option.value} className="flex items-center gap-2">
              <RadioGroupItem value={option.value} id={optionId} />
              <Label htmlFor={optionId} className="font-normal">
                {option.label}
                {showCorrect ? <OptionMarker kind="correct" /> : null}
                {showYoursWrong ? <OptionMarker kind="yours" /> : null}
              </Label>
            </div>
          );
        })}
      </RadioGroup>
    </QuizShell>
  );
}

/* ------------------------------------------------------------------ MultiSelectQuiz */

function sameSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const set = new Set(a);
  return b.every((value) => set.has(value));
}

export interface MultiSelectQuizProps extends QuizVariantBaseProps {
  options: QuizOption[];
  /** The set of correct option values. Never rendered to the DOM before submission. */
  correctValues: string[];
  value?: string[];
  defaultValue?: string[];
  onAnswer?: (value: string[]) => void;
  onSubmit?: (result: { value: string[]; correct: boolean }) => void;
  /** Header instruction. Defaults to "Select all that apply." */
  instructions?: React.ReactNode;
}

export function MultiSelectQuiz({
  question,
  options,
  correctValues,
  value: valueProp,
  defaultValue = [],
  onAnswer,
  onSubmit,
  feedback,
  disabled = false,
  submitLabel = "Submit",
  instructions = "Select all that apply.",
  className,
}: MultiSelectQuizProps) {
  const titleId = React.useId();
  const [value, setValue] = useControllable<string[]>(valueProp, defaultValue, onAnswer);
  const [submitted, setSubmitted] = React.useState(false);
  const correct = submitted ? sameSet(value, correctValues) : undefined;

  const toggle = (optionValue: string, checked: boolean) => {
    const next = checked
      ? [...value, optionValue]
      : value.filter((entry) => entry !== optionValue);
    setValue(next);
  };

  const submit = () => {
    if (value.length === 0) return;
    setSubmitted(true);
    onSubmit?.({ value, correct: sameSet(value, correctValues) });
  };

  return (
    <QuizShell
      titleId={titleId}
      question={question}
      instructions={instructions}
      submitted={submitted}
      correct={correct}
      canSubmit={value.length > 0 && !disabled}
      submitLabel={submitLabel}
      onSubmit={submit}
      feedback={feedback}
      className={className}
    >
      <div role="group" aria-labelledby={titleId} className="grid gap-3">
        {options.map((option) => {
          const optionId = `${titleId}-${option.value}`;
          const isCorrectOption = correctValues.includes(option.value);
          const isChosen = value.includes(option.value);
          const showCorrect = submitted && isCorrectOption;
          const showYoursWrong = submitted && isChosen && !isCorrectOption;
          return (
            <div key={option.value} className="flex items-center gap-2">
              <Checkbox
                id={optionId}
                checked={isChosen}
                onCheckedChange={(checked) => toggle(option.value, checked === true)}
                disabled={disabled || submitted}
              />
              <Label htmlFor={optionId} className="font-normal">
                {option.label}
                {showCorrect ? <OptionMarker kind="correct" /> : null}
                {showYoursWrong ? <OptionMarker kind="yours" /> : null}
              </Label>
            </div>
          );
        })}
      </div>
    </QuizShell>
  );
}

/* ------------------------------------------------------------------ TrueFalseQuiz */

export interface TrueFalseQuizProps extends QuizVariantBaseProps {
  /** The correct judgement. Never rendered to the DOM before submission. */
  correctValue: boolean;
  value?: boolean;
  defaultValue?: boolean;
  onAnswer?: (value: boolean) => void;
  onSubmit?: (result: { value: boolean | undefined; correct: boolean }) => void;
  /** Labels for the two choices. Defaults to True / False. */
  trueLabel?: React.ReactNode;
  falseLabel?: React.ReactNode;
}

export function TrueFalseQuiz({
  question,
  correctValue,
  value: valueProp,
  defaultValue,
  onAnswer,
  onSubmit,
  feedback,
  disabled = false,
  submitLabel = "Submit",
  trueLabel = "True",
  falseLabel = "False",
  className,
}: TrueFalseQuizProps) {
  const titleId = React.useId();
  const [value, setValue] = useControllable<boolean | undefined>(
    valueProp,
    defaultValue,
    onAnswer ? (next) => next !== undefined && onAnswer(next) : undefined,
  );
  const [submitted, setSubmitted] = React.useState(false);
  const correct = submitted ? value === correctValue : undefined;

  const submit = () => {
    if (value === undefined) return;
    setSubmitted(true);
    onSubmit?.({ value, correct: value === correctValue });
  };

  const choices: { key: string; boolValue: boolean; label: React.ReactNode }[] = [
    { key: "true", boolValue: true, label: trueLabel },
    { key: "false", boolValue: false, label: falseLabel },
  ];

  return (
    <QuizShell
      titleId={titleId}
      question={question}
      submitted={submitted}
      correct={correct}
      canSubmit={value !== undefined && !disabled}
      submitLabel={submitLabel}
      onSubmit={submit}
      feedback={feedback}
      className={className}
    >
      <RadioGroup
        aria-labelledby={titleId}
        value={value === undefined ? "" : value ? "true" : "false"}
        onValueChange={(next) => setValue(next === "true")}
        disabled={disabled || submitted}
      >
        {choices.map((choice) => {
          const optionId = `${titleId}-${choice.key}`;
          const showCorrect = submitted && choice.boolValue === correctValue;
          const showYoursWrong =
            submitted && choice.boolValue === value && value !== correctValue;
          return (
            <div key={choice.key} className="flex items-center gap-2">
              <RadioGroupItem value={choice.key} id={optionId} />
              <Label htmlFor={optionId} className="font-normal">
                {choice.label}
                {showCorrect ? <OptionMarker kind="correct" /> : null}
                {showYoursWrong ? <OptionMarker kind="yours" /> : null}
              </Label>
            </div>
          );
        })}
      </RadioGroup>
    </QuizShell>
  );
}

/* ------------------------------------------------------------------ FillInTheBlankQuiz */

function normalizeAnswer(value: string, caseSensitive: boolean): string {
  const trimmed = value.trim().replace(/\s+/g, " ");
  return caseSensitive ? trimmed : trimmed.toLowerCase();
}

export interface FillInTheBlankQuizProps extends QuizVariantBaseProps {
  /** Accepted answers. Any match (after normalization) is correct. Never rendered before submit. */
  answers: string[];
  /** Compare case-sensitively. Default false. Whitespace is always trimmed/collapsed. */
  caseSensitive?: boolean;
  value?: string;
  defaultValue?: string;
  onAnswer?: (value: string) => void;
  onSubmit?: (result: { value: string; correct: boolean }) => void;
  placeholder?: string;
}

export function FillInTheBlankQuiz({
  question,
  answers,
  caseSensitive = false,
  value: valueProp,
  defaultValue = "",
  onAnswer,
  onSubmit,
  feedback,
  disabled = false,
  submitLabel = "Submit",
  placeholder,
  className,
}: FillInTheBlankQuizProps) {
  const titleId = React.useId();
  const [value, setValue] = useControllable<string>(valueProp, defaultValue, onAnswer);
  const [submitted, setSubmitted] = React.useState(false);

  const isCorrect = (candidate: string) => {
    const normalizedCandidate = normalizeAnswer(candidate, caseSensitive);
    return answers.some((answer) => normalizeAnswer(answer, caseSensitive) === normalizedCandidate);
  };
  const correct = submitted ? isCorrect(value) : undefined;

  const submit = () => {
    if (value.trim().length === 0) return;
    setSubmitted(true);
    onSubmit?.({ value, correct: isCorrect(value) });
  };

  return (
    <QuizShell
      titleId={titleId}
      question={question}
      submitted={submitted}
      correct={correct}
      canSubmit={value.trim().length > 0 && !disabled}
      submitLabel={submitLabel}
      onSubmit={submit}
      feedback={feedback}
      className={className}
      afterResult={
        // The accepted answer is revealed only after an incorrect submission -- never before.
        submitted && correct === false && answers[0] !== undefined ? (
          <p className="text-sm text-muted-foreground">
            Accepted answer: <span className="font-medium text-foreground">{answers[0]}</span>
          </p>
        ) : null
      }
    >
      <Input
        aria-labelledby={titleId}
        value={value}
        placeholder={placeholder}
        onChange={(event) => setValue(event.target.value)}
        disabled={disabled || submitted}
        aria-invalid={correct === false || undefined}
      />
    </QuizShell>
  );
}

/* ------------------------------------------------------------------ ShortAnswerQuiz */

export interface ShortAnswerQuizProps extends QuizVariantBaseProps {
  /** Model/sample answer revealed after submission for the learner to compare against. */
  modelAnswer?: React.ReactNode;
  value?: string;
  defaultValue?: string;
  onAnswer?: (value: string) => void;
  onSubmit?: (result: { value: string }) => void;
  /** Fires when the learner self-assesses after seeing the model answer (assisted verification). */
  onSelfAssess?: (correct: boolean) => void;
  placeholder?: string;
}

export function ShortAnswerQuiz({
  question,
  modelAnswer,
  value: valueProp,
  defaultValue = "",
  onAnswer,
  onSubmit,
  onSelfAssess,
  feedback,
  disabled = false,
  submitLabel = "Submit",
  placeholder,
  className,
}: ShortAnswerQuizProps) {
  const titleId = React.useId();
  const modelId = React.useId();
  const [value, setValue] = useControllable<string>(valueProp, defaultValue, onAnswer);
  const [submitted, setSubmitted] = React.useState(false);
  const [selfCorrect, setSelfCorrect] = React.useState<boolean | undefined>(undefined);

  const submit = () => {
    if (value.trim().length === 0) return;
    setSubmitted(true);
    onSubmit?.({ value });
  };

  const assess = (next: string) => {
    // Radix single-select ToggleGroup emits "" when the active item is clicked again -- ignore it.
    if (next !== "correct" && next !== "incorrect") return;
    const correct = next === "correct";
    setSelfCorrect(correct);
    onSelfAssess?.(correct);
  };

  return (
    <QuizShell
      titleId={titleId}
      question={question}
      submitted={submitted}
      // Correctness is self-assessed, not auto-graded (RF-4 "assisted verification").
      correct={selfCorrect}
      canSubmit={value.trim().length > 0 && !disabled}
      submitLabel={submitLabel}
      onSubmit={submit}
      feedback={feedback}
      className={className}
      afterResult={
        <div className="flex flex-col gap-3">
          {/* Model answer is not in the DOM until the learner submits their own attempt. */}
          {modelAnswer !== undefined ? (
            <div className="rounded-md border p-3 text-sm">
              <p id={modelId} className="mb-1 font-medium">
                Model answer
              </p>
              <div className="text-muted-foreground">{modelAnswer}</div>
            </div>
          ) : null}
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium">Did your answer match?</span>
            <ToggleGroup
              type="single"
              variant="outline"
              value={
                selfCorrect === undefined ? "" : selfCorrect ? "correct" : "incorrect"
              }
              onValueChange={assess}
              aria-label="Self-assess your answer"
            >
              <ToggleGroupItem value="correct" aria-label="I was right">
                <CheckIcon className="size-4" />
                I was right
              </ToggleGroupItem>
              <ToggleGroupItem value="incorrect" aria-label="I was wrong">
                <CrossIcon className="size-4" />
                I was wrong
              </ToggleGroupItem>
            </ToggleGroup>
          </div>
        </div>
      }
    >
      <Textarea
        aria-labelledby={titleId}
        value={value}
        placeholder={placeholder}
        onChange={(event) => setValue(event.target.value)}
        disabled={disabled || submitted}
      />
    </QuizShell>
  );
}
