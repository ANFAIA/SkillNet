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

export interface NumericTolerance {
  /** Maximum difference in the same units as the expected value. */
  absolute?: number;
  /** Maximum proportional difference, where 0.02 means 2% of the expected value. */
  relative?: number;
  /** Whether one or every declared tolerance must pass. Defaults to `either`. */
  mode?: "either" | "both";
}

export type NumericQuestionRule =
  | { kind: "value"; value: number; tolerance?: NumericTolerance }
  | {
      kind: "range";
      min?: number;
      max?: number;
      includeMin?: boolean;
      includeMax?: boolean;
    };

export interface NumericQuestionUnit {
  /** Canonical, visible unit. */
  symbol: string;
  /** `display` keeps the unit outside the input; `required` asks the learner to type it. */
  policy: "display" | "required";
  /** Additional spellings accepted when the policy is `required`. */
  aliases?: string[];
  caseSensitive?: boolean;
}

export interface NumericQuestionNumberFormat {
  decimalSeparator?: "." | ",";
  allowExponent?: boolean;
}

export type NumericQuestionStatus = "correct" | "incorrect" | "ungraded";
export type NumericQuestionReason =
  | "matched"
  | "outside-tolerance"
  | "outside-range"
  | "invalid-number"
  | "unit-mismatch"
  | "ungraded";

export interface NumericQuestionResult {
  rawValue: string;
  value: number | null;
  status: NumericQuestionStatus;
  reason: NumericQuestionReason;
  unit?: string;
}

export interface NumericQuestionLabels {
  activity: string;
  promptPending: string;
  response: string;
  responsePlaceholder: string;
  displayUnit: (unit: string) => string;
  requiredUnit: (unit: string) => string;
  submit: string;
  correct: string;
  incorrect: string;
  ungraded: string;
  invalidNumber: string;
  unitMismatch: (unit: string) => string;
  expectedValue: (value: string) => string;
  expectedRange: (range: string) => string;
}

const defaultLabels: NumericQuestionLabels = {
  activity: "Numeric question",
  promptPending: "The question is still loading.",
  response: "Your answer",
  responsePlaceholder: "Enter a number",
  displayUnit: (unit) => `Answers are measured in ${unit}.`,
  requiredUnit: (unit) => `Include the unit ${unit}.`,
  submit: "Check answer",
  correct: "Correct",
  incorrect: "Needs revision",
  ungraded: "Response submitted",
  invalidNumber: "Enter a valid number.",
  unitMismatch: (unit) => `Use the required unit ${unit}.`,
  expectedValue: (value) => `Expected value: ${value}`,
  expectedRange: (range) => `Accepted range: ${range}`,
};

export interface NumericQuestionInputContext {
  id: string;
  value: string;
  disabled: boolean;
  describedBy?: string;
  invalid: boolean;
  placeholder: string;
  onChange: (value: string) => void;
}

export interface NumericQuestionProps
  extends Omit<
    React.ComponentPropsWithoutRef<"section">,
    "children" | "defaultValue" | "onSubmit" | "title"
  > {
  prompt?: React.ReactNode;
  description?: React.ReactNode;
  rule?: NumericQuestionRule;
  unit?: NumericQuestionUnit;
  numberFormat?: NumericQuestionNumberFormat;
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  submitted?: boolean;
  defaultSubmitted?: boolean;
  onSubmittedChange?: (submitted: boolean) => void;
  onSubmit?: (result: NumericQuestionResult) => void;
  disabled?: boolean;
  labels?: Partial<NumericQuestionLabels>;
  feedback?: Partial<Record<NumericQuestionStatus, React.ReactNode>>;
  formatValue?: (value: number) => string;
  renderInput?: (context: NumericQuestionInputContext) => React.ReactNode;
  renderFeedback?: (result: NumericQuestionResult) => React.ReactNode;
}

interface ParsedNumber {
  value: number | null;
  reason?: "invalid-number" | "unit-mismatch";
}

function parseNumber(
  rawValue: string,
  format: NumericQuestionNumberFormat,
  unit?: NumericQuestionUnit,
): ParsedNumber {
  let candidate = rawValue.trim().normalize("NFKC").replace(/[\u2212\u2012-\u2014]/g, "-");

  if (unit?.policy === "required") {
    const aliases = [unit.symbol, ...(unit.aliases ?? [])]
      .map((alias) => alias.trim())
      .filter(Boolean)
      .sort((a, b) => b.length - a.length);
    const comparable = unit.caseSensitive ? candidate : candidate.toLocaleLowerCase();
    const matchedUnit = aliases.find((alias) => {
      const comparableAlias = unit.caseSensitive ? alias : alias.toLocaleLowerCase();
      return comparable.endsWith(comparableAlias);
    });
    if (!matchedUnit) return { value: null, reason: "unit-mismatch" };
    candidate = candidate.slice(0, -matchedUnit.length).trim();
  }

  const separator = format.decimalSeparator ?? ".";
  if (separator === ",") candidate = candidate.replace(",", ".");
  const exponent = format.allowExponent === false ? "" : "(?:[eE][+-]?\\d+)?";
  const pattern = new RegExp(`^[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)${exponent}$`);
  if (!pattern.test(candidate)) return { value: null, reason: "invalid-number" };
  const value = Number(candidate);
  return Number.isFinite(value)
    ? { value }
    : { value: null, reason: "invalid-number" };
}

function isValidRule(rule: NumericQuestionRule): boolean {
  if (rule.kind === "value") return Number.isFinite(rule.value);
  return (rule.min === undefined || Number.isFinite(rule.min))
    && (rule.max === undefined || Number.isFinite(rule.max))
    && (rule.min !== undefined || rule.max !== undefined);
}

function evaluate(
  rawValue: string,
  rule: NumericQuestionRule | undefined,
  format: NumericQuestionNumberFormat,
  unit?: NumericQuestionUnit,
): NumericQuestionResult {
  const parsed = parseNumber(rawValue, format, unit);
  const base = {
    rawValue,
    value: parsed.value,
    ...(unit ? { unit: unit.symbol } : {}),
  };
  if (!rule || !isValidRule(rule)) {
    return { ...base, status: "ungraded", reason: parsed.reason ?? "ungraded" };
  }
  if (parsed.value === null) {
    return { ...base, status: "incorrect", reason: parsed.reason ?? "invalid-number" };
  }

  if (rule.kind === "range") {
    const aboveMinimum = rule.min === undefined
      || (rule.includeMin === false ? parsed.value > rule.min : parsed.value >= rule.min);
    const belowMaximum = rule.max === undefined
      || (rule.includeMax === false ? parsed.value < rule.max : parsed.value <= rule.max);
    return aboveMinimum && belowMaximum
      ? { ...base, status: "correct", reason: "matched" }
      : { ...base, status: "incorrect", reason: "outside-range" };
  }

  const difference = Math.abs(parsed.value - rule.value);
  const tolerance = rule.tolerance;
  if (!tolerance || (tolerance.absolute === undefined && tolerance.relative === undefined)) {
    return difference === 0
      ? { ...base, status: "correct", reason: "matched" }
      : { ...base, status: "incorrect", reason: "outside-tolerance" };
  }
  const checks: boolean[] = [];
  if (tolerance.absolute !== undefined) checks.push(difference <= Math.max(0, tolerance.absolute));
  if (tolerance.relative !== undefined) {
    checks.push(difference <= Math.abs(rule.value) * Math.max(0, tolerance.relative));
  }
  const matches = tolerance.mode === "both" ? checks.every(Boolean) : checks.some(Boolean);
  return matches
    ? { ...base, status: "correct", reason: "matched" }
    : { ...base, status: "incorrect", reason: "outside-tolerance" };
}

function describeRule(
  rule: NumericQuestionRule,
  unit: NumericQuestionUnit | undefined,
  formatValue: (value: number) => string,
): { kind: "value" | "range"; text: string } {
  const suffix = unit ? ` ${unit.symbol}` : "";
  if (rule.kind === "value") {
    return { kind: "value", text: `${formatValue(rule.value)}${suffix}` };
  }
  const left = rule.min === undefined
    ? "−∞"
    : `${rule.includeMin === false ? "(" : "["}${formatValue(rule.min)}`;
  const right = rule.max === undefined
    ? "+∞"
    : `${formatValue(rule.max)}${rule.includeMax === false ? ")" : "]"}`;
  return { kind: "range", text: `${left}, ${right}${suffix}` };
}

/**
 * A quantitative response with explicit grading, tolerance and unit semantics. The grading rule
 * and accepted answer remain absent from the DOM until submission.
 */
export const NumericQuestion = React.forwardRef<HTMLElement, NumericQuestionProps>(
  function NumericQuestion(
    {
      prompt,
      description,
      rule,
      unit,
      numberFormat = {},
      value: valueProp,
      defaultValue = "",
      onValueChange,
      submitted: submittedProp,
      defaultSubmitted = false,
      onSubmittedChange,
      onSubmit,
      disabled = false,
      labels,
      feedback,
      formatValue = String,
      renderInput,
      renderFeedback,
      className,
      "aria-label": ariaLabel,
      "aria-labelledby": ariaLabelledby,
      ...props
    },
    ref,
  ) {
    const copy = { ...defaultLabels, ...labels };
    const titleId = React.useId();
    const inputId = React.useId();
    const helpId = React.useId();
    const resultId = React.useId();
    const [value, setValue] = useControllable(valueProp, defaultValue, onValueChange);
    const [submitted, setSubmitted] = useControllable(
      submittedProp,
      defaultSubmitted,
      onSubmittedChange,
    );
    const result = submitted ? evaluate(value, rule, numberFormat, unit) : undefined;
    const canSubmit = value.trim().length > 0 && !disabled && !submitted;
    const invalid = result?.reason === "invalid-number" || result?.reason === "unit-mismatch";
    const describedBy = [unit ? helpId : undefined, result ? resultId : undefined]
      .filter(Boolean)
      .join(" ") || undefined;

    const submit = (event: React.FormEvent) => {
      event.preventDefault();
      if (!canSubmit) return;
      const nextResult = evaluate(value, rule, numberFormat, unit);
      setSubmitted(true);
      onSubmit?.(nextResult);
    };

    const inputContext: NumericQuestionInputContext = {
      id: inputId,
      value,
      disabled: disabled || submitted,
      describedBy,
      invalid,
      placeholder: copy.responsePlaceholder,
      onChange: setValue,
    };

    return (
      <section
        ref={ref}
        data-slot="numeric-question"
        data-status={result?.status}
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
          <form onSubmit={submit} className="flex flex-col gap-6">
            <CardContent className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor={inputId}>{copy.response}</Label>
                <div className="flex items-center gap-3">
                  <div className="min-w-0 flex-1">
                    {renderInput ? renderInput(inputContext) : (
                      <Input
                        id={inputId}
                        type="text"
                        inputMode="decimal"
                        autoComplete="off"
                        value={value}
                        placeholder={copy.responsePlaceholder}
                        disabled={disabled || submitted}
                        aria-describedby={describedBy}
                        aria-invalid={invalid || undefined}
                        onChange={(event) => setValue(event.target.value)}
                      />
                    )}
                  </div>
                  {unit?.policy === "display" ? (
                    <span className="shrink-0 text-sm font-medium text-foreground" aria-hidden="true">
                      {unit.symbol}
                    </span>
                  ) : null}
                </div>
                {unit ? (
                  <p
                    id={helpId}
                    className={unit.policy === "display" ? "sr-only" : "text-sm text-muted-foreground"}
                  >
                    {unit.policy === "display"
                      ? copy.displayUnit(unit.symbol)
                      : copy.requiredUnit(unit.symbol)}
                  </p>
                ) : null}
              </div>

              {result ? (
                <div id={resultId} role="status" aria-live="polite" className="rounded-md border bg-muted p-4 text-sm">
                  <p className="font-medium text-foreground">
                    {result.status === "correct"
                      ? copy.correct
                      : result.status === "incorrect"
                        ? copy.incorrect
                        : copy.ungraded}
                  </p>
                  {result.reason === "invalid-number" ? (
                    <p className="mt-1 text-muted-foreground">{copy.invalidNumber}</p>
                  ) : null}
                  {result.reason === "unit-mismatch" && unit ? (
                    <p className="mt-1 text-muted-foreground">{copy.unitMismatch(unit.symbol)}</p>
                  ) : null}
                  {result.status === "incorrect" && result.value !== null && rule && isValidRule(rule) ? (() => {
                    const expectation = describeRule(rule, unit, formatValue);
                    return (
                      <p className="mt-1 text-muted-foreground">
                        {expectation.kind === "value"
                          ? copy.expectedValue(expectation.text)
                          : copy.expectedRange(expectation.text)}
                      </p>
                    );
                  })() : null}
                  {feedback?.[result.status] !== undefined ? (
                    <div className="mt-2 text-muted-foreground">{feedback[result.status]}</div>
                  ) : null}
                  {renderFeedback ? (
                    <div className="mt-2 text-muted-foreground">{renderFeedback(result)}</div>
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
