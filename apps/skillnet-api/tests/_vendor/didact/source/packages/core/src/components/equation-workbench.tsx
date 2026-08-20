import * as React from "react";
import { MdAdd, MdArrowDownward, MdArrowUpward, MdDeleteOutline } from "react-icons/md";
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

export interface EquationStep {
  id: string;
  expression: string;
  note?: string;
}

export interface EquationWorkbenchState {
  steps: EquationStep[];
  finalAnswer: string;
}

export interface EquationWorkbenchDefinition {
  id: string;
  title: string;
  description?: string;
  instructions?: string;
  initialExpression: string;
  finalAnswerLabel?: string;
}

export interface EquationWorkbenchEvaluation {
  status: "correct" | "incorrect" | "partial";
  feedback: React.ReactNode;
}

export type EquationWorkbenchResult =
  | ({ status: "ungraded" } & EquationWorkbenchState)
  | (EquationWorkbenchEvaluation & EquationWorkbenchState);

export interface EquationRendererContext {
  expression: string;
  kind: "initial" | "step" | "answer";
}

export interface EquationWorkbenchLabels {
  activity: string;
  loading: string;
  empty: string;
  initialExpression: string;
  transformations: string;
  step: (index: number) => string;
  expression: string;
  expressionPlaceholder: string;
  note: string;
  notePlaceholder: string;
  addStep: string;
  moveUp: string;
  moveDown: string;
  removeStep: string;
  finalAnswer: string;
  finalAnswerPlaceholder: string;
  submit: string;
  submitting: string;
  ungraded: string;
}

const defaultLabels: EquationWorkbenchLabels = {
  activity: "Equation workbench",
  loading: "The equation activity is still loading.",
  empty: "There is no equation activity to display.",
  initialExpression: "Starting expression",
  transformations: "Transformation steps",
  step: (index) => `Step ${index}`,
  expression: "Expression",
  expressionPlaceholder: "Enter the next equivalent expression",
  note: "Reasoning (optional)",
  notePlaceholder: "Describe the transformation",
  addStep: "Add transformation step",
  moveUp: "Move step up",
  moveDown: "Move step down",
  removeStep: "Remove step",
  finalAnswer: "Final answer",
  finalAnswerPlaceholder: "Enter your final answer",
  submit: "Submit work",
  submitting: "Checking work…",
  ungraded: "Work submitted",
};

const EMPTY_STATE: EquationWorkbenchState = { steps: [], finalAnswer: "" };

function makeStep(): EquationStep {
  return {
    id: `equation-step-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    expression: "",
    note: "",
  };
}

export interface EquationWorkbenchProps
  extends Omit<React.ComponentPropsWithoutRef<"section">, "children" | "title" | "onChange"> {
  definition?: EquationWorkbenchDefinition;
  state?: EquationWorkbenchState;
  defaultState?: EquationWorkbenchState;
  onStateChange?: (state: EquationWorkbenchState) => void;
  evaluate?: (
    state: EquationWorkbenchState,
    definition: EquationWorkbenchDefinition,
  ) => EquationWorkbenchEvaluation | Promise<EquationWorkbenchEvaluation>;
  onResult?: (result: EquationWorkbenchResult) => void;
  renderEquation?: (context: EquationRendererContext) => React.ReactNode;
  labels?: Partial<EquationWorkbenchLabels>;
  disabled?: boolean;
  streaming?: boolean;
}

export const EquationWorkbench = React.forwardRef<HTMLElement, EquationWorkbenchProps>(
  function EquationWorkbench(
    {
      definition,
      state: controlledState,
      defaultState = EMPTY_STATE,
      onStateChange,
      evaluate,
      onResult,
      renderEquation,
      labels,
      disabled = false,
      streaming = false,
      className,
      ...props
    },
    ref,
  ) {
    const text = { ...defaultLabels, ...labels };
    const [internalState, setInternalState] = React.useState(defaultState);
    const [evaluation, setEvaluation] = React.useState<EquationWorkbenchEvaluation>();
    const [submittedUngraded, setSubmittedUngraded] = React.useState(false);
    const [submitting, setSubmitting] = React.useState(false);
    const titleId = React.useId();
    const instructionsId = React.useId();
    const state = controlledState ?? internalState;

    const commit = React.useCallback(
      (next: EquationWorkbenchState) => {
        if (controlledState === undefined) setInternalState(next);
        onStateChange?.(next);
        setEvaluation(undefined);
        setSubmittedUngraded(false);
      },
      [controlledState, onStateChange],
    );

    if (!definition) {
      return (
        <section
          ref={ref}
          aria-label={text.activity}
          className={cn("rounded-xl border p-6 text-sm text-muted-foreground", className)}
          {...props}
        >
          <p role={streaming ? "status" : undefined}>{streaming ? text.loading : text.empty}</p>
        </section>
      );
    }

    const updateStep = (id: string, patch: Partial<Pick<EquationStep, "expression" | "note">>) => {
      commit({
        ...state,
        steps: state.steps.map((step) => (step.id === id ? { ...step, ...patch } : step)),
      });
    };
    const moveStep = (index: number, offset: -1 | 1) => {
      const destination = index + offset;
      if (destination < 0 || destination >= state.steps.length) return;
      const steps = [...state.steps];
      const [step] = steps.splice(index, 1);
      if (!step) return;
      steps.splice(destination, 0, step);
      commit({ ...state, steps });
    };
    const renderMath = (expression: string, kind: EquationRendererContext["kind"]) =>
      renderEquation ? (
        renderEquation({ expression, kind })
      ) : (
        <code className="break-words font-mono text-sm" dir="ltr">{expression}</code>
      );
    const submit = async () => {
      if (disabled || submitting || (!state.finalAnswer.trim() && state.steps.every(({ expression }) => !expression.trim()))) return;
      setSubmitting(true);
      const snapshot = {
        steps: state.steps.map((step) => ({ ...step })),
        finalAnswer: state.finalAnswer,
      };
      try {
        if (!evaluate) {
          setSubmittedUngraded(true);
          onResult?.({ status: "ungraded", ...snapshot });
          return;
        }
        const result = await evaluate(snapshot, definition);
        setEvaluation(result);
        onResult?.({ ...snapshot, ...result });
      } finally {
        setSubmitting(false);
      }
    };

    return (
      <section ref={ref} aria-labelledby={titleId} className={cn("w-full", className)} {...props}>
        <Card>
          <CardHeader className="gap-1">
            <CardTitle><h2 id={titleId}>{definition.title}</h2></CardTitle>
            {definition.description ? <CardDescription>{definition.description}</CardDescription> : null}
          </CardHeader>
          <CardContent className="space-y-6">
            {definition.instructions ? (
              <p id={instructionsId} className="text-sm text-muted-foreground">{definition.instructions}</p>
            ) : null}

            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{text.initialExpression}</p>
              <div className="rounded-lg border bg-muted/20 px-4 py-3" aria-label={text.initialExpression}>
                {renderMath(definition.initialExpression, "initial")}
              </div>
            </div>

            <fieldset className="space-y-3" disabled={disabled} aria-describedby={definition.instructions ? instructionsId : undefined}>
              <legend className="mb-2 text-sm font-medium">{text.transformations}</legend>
              {state.steps.map((step, index) => {
                const expressionId = `${titleId}-expression-${step.id}`;
                const noteId = `${titleId}-note-${step.id}`;
                return (
                  <div key={step.id} className="rounded-lg border p-4">
                    <div className="mb-3 flex items-center justify-between gap-2">
                      <span className="text-sm font-medium">{text.step(index + 1)}</span>
                      <div className="flex items-center gap-1">
                        <Button type="button" size="icon" variant="ghost" aria-label={`${text.moveUp}: ${text.step(index + 1)}`} disabled={disabled || index === 0} onClick={() => moveStep(index, -1)}><MdArrowUpward aria-hidden /></Button>
                        <Button type="button" size="icon" variant="ghost" aria-label={`${text.moveDown}: ${text.step(index + 1)}`} disabled={disabled || index === state.steps.length - 1} onClick={() => moveStep(index, 1)}><MdArrowDownward aria-hidden /></Button>
                        <Button type="button" size="icon" variant="ghost" aria-label={`${text.removeStep}: ${text.step(index + 1)}`} disabled={disabled} onClick={() => commit({ ...state, steps: state.steps.filter(({ id }) => id !== step.id) })}><MdDeleteOutline aria-hidden /></Button>
                      </div>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="space-y-1.5">
                        <Label htmlFor={expressionId}>{text.expression}</Label>
                        <Input id={expressionId} value={step.expression} placeholder={text.expressionPlaceholder} onChange={(event) => updateStep(step.id, { expression: event.target.value })} />
                      </div>
                      <div className="space-y-1.5">
                        <Label htmlFor={noteId}>{text.note}</Label>
                        <Input id={noteId} value={step.note ?? ""} placeholder={text.notePlaceholder} onChange={(event) => updateStep(step.id, { note: event.target.value })} />
                      </div>
                    </div>
                    {renderEquation && step.expression.trim() ? <div className="mt-3 border-l-2 border-primary/30 pl-3 text-foreground">{renderMath(step.expression, "step")}</div> : null}
                  </div>
                );
              })}
              <Button type="button" variant="outline" disabled={disabled} onClick={() => commit({ ...state, steps: [...state.steps, makeStep()] })}><MdAdd aria-hidden className="mr-1.5" />{text.addStep}</Button>
            </fieldset>

            <div className="space-y-1.5">
              <Label htmlFor={`${titleId}-answer`}>{definition.finalAnswerLabel ?? text.finalAnswer}</Label>
              <Input id={`${titleId}-answer`} value={state.finalAnswer} placeholder={text.finalAnswerPlaceholder} disabled={disabled} onChange={(event) => commit({ ...state, finalAnswer: event.target.value })} />
              {state.finalAnswer.trim() ? <div className="pt-1 text-foreground">{renderMath(state.finalAnswer, "answer")}</div> : null}
            </div>

            {evaluation ? (
              <div role="status" className={cn("rounded-lg border px-4 py-3 text-sm", evaluation.status === "correct" && "border-emerald-500/40 bg-emerald-500/5", evaluation.status === "partial" && "border-amber-500/40 bg-amber-500/5", evaluation.status === "incorrect" && "border-destructive/40 bg-destructive/5")}>
                {evaluation.feedback}
              </div>
            ) : submittedUngraded ? <p role="status" className="text-sm text-muted-foreground">{text.ungraded}</p> : null}
          </CardContent>
          <CardFooter>
            <Button type="button" disabled={disabled || submitting || (!state.finalAnswer.trim() && state.steps.every(({ expression }) => !expression.trim()))} onClick={submit}>{submitting ? text.submitting : text.submit}</Button>
          </CardFooter>
        </Card>
      </section>
    );
  },
);
