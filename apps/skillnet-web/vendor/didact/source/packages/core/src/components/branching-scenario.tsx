import * as React from "react";
import {
  applyDecisionEffects,
  evaluateDecisionCondition,
  type DecisionChoice,
  type DecisionGraphDefinition,
  type DecisionGraphEvent,
  type DecisionGraphResult,
  type DecisionGraphState,
} from "@didact/schema";
import { Button, Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@didact/ui";

import { cn } from "../lib/cn.js";

export interface BranchingScenarioLabels {
  activity: string;
  loading: string;
  empty: string;
  choices: string;
  back: string;
  restart: string;
  step: (value: number) => string;
  unavailable: string;
  outcome: string;
}

const defaultLabels: BranchingScenarioLabels = {
  activity: "Branching scenario",
  loading: "The scenario is still loading.",
  empty: "There is no scenario to display.",
  choices: "Choose what to do next",
  back: "Back",
  restart: "Restart",
  step: (value) => `Step ${value}`,
  unavailable: "This option is not available yet",
  outcome: "Outcome",
};

export interface BranchingScenarioProps extends Omit<React.ComponentPropsWithoutRef<"section">, "children" | "title"> {
  definition?: DecisionGraphDefinition;
  state?: DecisionGraphState;
  defaultState?: DecisionGraphState;
  onStateChange?: (state: DecisionGraphState, event: DecisionGraphEvent) => void;
  onEvent?: (event: DecisionGraphEvent) => void;
  onResult?: (result: DecisionGraphResult) => void;
  locale?: string;
  labels?: Partial<BranchingScenarioLabels>;
  disabled?: boolean;
  streaming?: boolean;
}

function localText(value: string | Record<string, string> | undefined, locale: string): string {
  if (typeof value === "string") return value;
  if (!value) return "";
  return value[locale] ?? value[locale.split("-")[0] ?? ""] ?? value.en ?? Object.values(value)[0] ?? "";
}

function initialState(definition: DecisionGraphDefinition): DecisionGraphState {
  return { currentNodeId: definition.startNodeId, variables: { ...definition.initialVariables }, history: [] };
}

function findChoice(definition: DecisionGraphDefinition, nodeId: string, choiceId: string): DecisionChoice | undefined {
  return definition.nodes.find(({ id }) => id === nodeId)?.choices?.find(({ id }) => id === choiceId);
}

export const BranchingScenario = React.forwardRef<HTMLElement, BranchingScenarioProps>(function BranchingScenario(
  {
    definition,
    state: controlledState,
    defaultState,
    onStateChange,
    onEvent,
    onResult,
    locale = "en",
    labels,
    disabled = false,
    streaming = false,
    className,
    ...props
  },
  ref,
) {
  const text = { ...defaultLabels, ...labels };
  const [internalState, setInternalState] = React.useState<DecisionGraphState | undefined>(defaultState);
  const fallbackState = definition ? initialState(definition) : undefined;
  const state = controlledState ?? internalState ?? fallbackState;
  const titleId = React.useId();

  if (!definition || !state) {
    return (
      <section ref={ref} aria-label={text.activity} className={cn("rounded-xl border p-6 text-sm text-muted-foreground", className)} {...props}>
        <p role={streaming ? "status" : undefined}>{streaming ? text.loading : text.empty}</p>
      </section>
    );
  }

  const node = definition.nodes.find(({ id }) => id === state.currentNodeId);
  if (!node) {
    return <section ref={ref} aria-label={text.activity} className={cn("rounded-xl border p-6 text-sm text-destructive", className)} {...props}>{text.empty}</section>;
  }

  const previous = state.history.at(-1);
  const previousChoice = previous ? findChoice(definition, previous.fromNodeId, previous.choiceId) : undefined;
  const outcomeStatus = node.kind === "outcome" && node.outcome ? node.outcome.status : "in-progress";

  const commit = (next: DecisionGraphState, event: DecisionGraphEvent) => {
    if (controlledState === undefined) setInternalState(next);
    onStateChange?.(next, event);
    onEvent?.(event);
    const nextNode = definition.nodes.find(({ id }) => id === next.currentNodeId);
    const status = nextNode?.kind === "outcome" && nextNode.outcome ? nextNode.outcome.status : "in-progress";
    onResult?.({ status, state: next });
    if (nextNode?.kind === "outcome" && nextNode.outcome) onEvent?.({ type: "outcome-reached", nodeId: nextNode.id, outcome: nextNode.outcome.status });
  };

  const choose = (choice: DecisionChoice) => {
    if (disabled || !evaluateDecisionCondition(choice.condition, state.variables)) return;
    const next: DecisionGraphState = {
      currentNodeId: choice.targetNodeId,
      variables: applyDecisionEffects(state.variables, choice.effects),
      history: [...state.history, { fromNodeId: node.id, choiceId: choice.id, toNodeId: choice.targetNodeId, variablesBefore: state.variables }],
    };
    commit(next, { type: "choice-selected", choiceId: choice.id, fromNodeId: node.id, toNodeId: choice.targetNodeId });
  };

  const back = () => {
    const entry = state.history.at(-1);
    if (!entry || disabled || !definition.navigation?.allowBacktrack) return;
    const next = { currentNodeId: entry.fromNodeId, variables: entry.variablesBefore, history: state.history.slice(0, -1) };
    commit(next, { type: "backtracked", toNodeId: entry.fromNodeId });
  };

  const restart = () => {
    if (disabled || !definition.navigation?.allowRestart) return;
    const next = initialState(definition);
    commit(next, { type: "restarted", toNodeId: definition.startNodeId });
  };

  return (
    <section ref={ref} aria-labelledby={titleId} className={cn("w-full", className)} {...props}>
      <Card>
        <CardHeader className="gap-1">
          <p className="text-xs text-muted-foreground">{text.step(state.history.length + 1)}</p>
          <CardTitle><h2 id={titleId}>{localText(definition.title, locale)}</h2></CardTitle>
          {definition.description ? <CardDescription>{localText(definition.description, locale)}</CardDescription> : null}
        </CardHeader>
        <CardContent className="space-y-5">
          {previousChoice?.consequence ? (
            <div className="border-l-2 border-primary pl-3 text-sm" role="status">
              {localText(previousChoice.consequence, locale)}
            </div>
          ) : null}

          <div className="space-y-2">
            {node.title ? <h3 className="font-medium">{localText(node.title, locale)}</h3> : null}
            <p className="leading-relaxed">{localText(node.body, locale)}</p>
          </div>

          {node.kind === "decision" && node.choices?.length ? (
            <fieldset className="space-y-2" disabled={disabled}>
              <legend className="mb-2 text-sm font-medium">{text.choices}</legend>
              {node.choices.map((choice) => {
                const available = evaluateDecisionCondition(choice.condition, state.variables);
                return (
                  <Button key={choice.id} type="button" variant="outline" className="h-auto w-full justify-start whitespace-normal py-3 text-left" disabled={disabled || !available} title={!available ? text.unavailable : undefined} onClick={() => choose(choice)}>
                    {localText(choice.label, locale)}
                  </Button>
                );
              })}
            </fieldset>
          ) : null}

          {node.kind === "outcome" && node.outcome ? (
            <div className="space-y-2 border-t pt-4" aria-label={text.outcome}>
              <p className="font-medium">{localText(node.outcome.label, locale)}</p>
              {node.outcome.feedback ? <p className="text-sm leading-relaxed text-muted-foreground">{localText(node.outcome.feedback, locale)}</p> : null}
              <span className="sr-only">{outcomeStatus}</span>
            </div>
          ) : null}
        </CardContent>
        {state.history.length > 0 && (definition.navigation?.allowBacktrack || definition.navigation?.allowRestart) ? (
          <CardFooter className="justify-between gap-2 border-t pt-4">
            <Button type="button" variant="ghost" disabled={disabled || !definition.navigation.allowBacktrack || state.history.length === 0} onClick={back}>{text.back}</Button>
            {definition.navigation.allowRestart ? <Button type="button" variant="ghost" disabled={disabled || state.history.length === 0} onClick={restart}>{text.restart}</Button> : null}
          </CardFooter>
        ) : null}
      </Card>
    </section>
  );
});
