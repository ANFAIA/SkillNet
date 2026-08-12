import * as React from "react";
import { MdAddAPhoto, MdPause, MdPlayArrow, MdRestartAlt, MdSkipNext } from "react-icons/md";
import {
  createSimulationInitialState,
  type SimulationDefinition,
  type SimulationEvent,
  type SimulationResult,
  type SimulationState,
  type SimulationValues,
} from "@didact/schema";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@didact/ui";
import { cn } from "../lib/cn.js";

export interface SimulationRuntimeContext {
  definition: SimulationDefinition;
  state: SimulationState;
}

export interface SimulationActionResult {
  values?: SimulationValues;
  parameters?: SimulationValues;
}

export interface SimulationLabLabels {
  activity: string;
  loading: string;
  empty: string;
  parameters: string;
  observables: string;
  actions: string;
  play: string;
  pause: string;
  reset: string;
  step: string;
  snapshot: string;
  snapshots: string;
  restore: string;
  elapsed: string;
}

const defaultLabels: SimulationLabLabels = {
  activity: "Simulation lab", loading: "The simulation is still loading.", empty: "There is no simulation to display.",
  parameters: "Parameters", observables: "Observables", actions: "Actions", play: "Run", pause: "Pause", reset: "Reset", step: "Advance one step", snapshot: "Save snapshot", snapshots: "Snapshots", restore: "Restore", elapsed: "Elapsed",
};

export interface SimulationLabProps extends Omit<React.ComponentPropsWithoutRef<"section">, "children" | "title"> {
  definition?: SimulationDefinition;
  state?: SimulationState;
  defaultState?: SimulationState;
  advance: (context: SimulationRuntimeContext, deltaMs: number) => SimulationValues;
  performAction?: (actionId: string, context: SimulationRuntimeContext) => SimulationActionResult | void;
  renderSystem?: (context: SimulationRuntimeContext) => React.ReactNode;
  onStateChange?: (state: SimulationState, event: SimulationEvent) => void;
  onResult?: (result: SimulationResult) => void;
  locale?: string;
  labels?: Partial<SimulationLabLabels>;
  disabled?: boolean;
  streaming?: boolean;
}

function localText(value: string | Record<string, string> | undefined, locale: string): string {
  if (typeof value === "string") return value;
  if (!value) return "";
  return value[locale] ?? value[locale.split("-")[0] ?? ""] ?? value.en ?? Object.values(value)[0] ?? "";
}

function formatValue(value: string | number | boolean, precision: number | undefined, locale: string): string {
  if (typeof value === "number") return new Intl.NumberFormat(locale, { maximumFractionDigits: precision ?? 2, minimumFractionDigits: precision }).format(value);
  return typeof value === "boolean" ? (value ? "Yes" : "No") : value;
}

function formatElapsed(milliseconds: number, locale: string): string {
  const units: Array<[Intl.NumberFormatOptions["unit"], number]> = [
    ["day", 86_400_000],
    ["hour", 3_600_000],
    ["minute", 60_000],
    ["second", 1_000],
  ];
  const [unit, divisor] = units.find(([, size]) => milliseconds >= size) ?? ["second", 1_000];
  return new Intl.NumberFormat(locale, {
    style: "unit",
    unit,
    unitDisplay: "short",
    maximumFractionDigits: unit === "second" ? 1 : 2,
  }).format(milliseconds / divisor);
}

export const SimulationLab = React.forwardRef<HTMLElement, SimulationLabProps>(function SimulationLab(
  { definition, state: controlledState, defaultState, advance, performAction, renderSystem, onStateChange, onResult, locale = "en", labels, disabled = false, streaming = false, className, ...props }, ref,
) {
  const text = { ...defaultLabels, ...labels };
  const [internalState, setInternalState] = React.useState<SimulationState | undefined>(defaultState);
  const initial = React.useMemo(() => definition ? createSimulationInitialState(definition) : undefined, [definition]);
  const state = controlledState ?? internalState ?? initial;
  const titleId = React.useId();

  const commit = React.useCallback((next: SimulationState, event: SimulationEvent) => {
    if (controlledState === undefined) setInternalState(next);
    onStateChange?.(next, event);
    onResult?.({ status: "ungraded", state: next });
  }, [controlledState, onResult, onStateChange]);

  const step = React.useCallback((deltaMs?: number) => {
    if (!definition || !state || disabled) return;
    const delta = deltaMs ?? definition.clock.stepMs;
    const limit = definition.clock.maxElapsedMs;
    const actualDelta = limit === undefined ? delta : Math.max(0, Math.min(delta, limit - state.elapsedMs));
    if (actualDelta <= 0) {
      if (state.running) commit({ ...state, running: false }, { type: "paused" });
      return;
    }
    const values = advance({ definition, state }, actualDelta);
    const elapsedMs = state.elapsedMs + actualDelta;
    const running = state.running && (limit === undefined || elapsedMs < limit);
    commit({ ...state, values, elapsedMs, running }, { type: "stepped", deltaMs: actualDelta });
  }, [advance, commit, definition, disabled, state]);

  React.useEffect(() => {
    if (!definition || !state?.running || disabled) return;
    const interval = window.setInterval(() => step(definition.clock.stepMs), Math.max(16, definition.clock.stepMs));
    return () => window.clearInterval(interval);
  }, [definition, disabled, state?.running, state?.elapsedMs, step]);

  if (!definition || !state) return <section ref={ref} aria-label={text.activity} className={cn("rounded-xl border p-6 text-sm text-muted-foreground", className)} {...props}><p role={streaming ? "status" : undefined}>{streaming ? text.loading : text.empty}</p></section>;

  const setRunning = (running: boolean) => commit({ ...state, running }, { type: running ? "started" : "paused" });
  const reset = () => commit(createSimulationInitialState(definition), { type: "reset" });
  const changeParameter = (parameterId: string, value: number | boolean) => commit({ ...state, parameters: { ...state.parameters, [parameterId]: value }, running: false }, { type: "parameter-changed", parameterId, value });
  const action = (actionId: string) => {
    if (disabled) return;
    const result = performAction?.(actionId, { definition, state });
    commit({ ...state, values: result?.values ?? state.values, parameters: result?.parameters ?? state.parameters }, { type: "action-performed", actionId });
  };
  const snapshot = () => {
    const id = `snapshot-${state.snapshots.length + 1}`;
    const nextSnapshot = { id, elapsedMs: state.elapsedMs, parameters: state.parameters, values: state.values };
    const max = definition.snapshots?.max ?? 5;
    commit({ ...state, snapshots: [...state.snapshots, nextSnapshot].slice(-max) }, { type: "snapshot-created", snapshotId: id });
  };
  const restore = (snapshotId: string) => {
    const saved = state.snapshots.find(({ id }) => id === snapshotId); if (!saved) return;
    commit({ ...state, parameters: saved.parameters, values: saved.values, elapsedMs: saved.elapsedMs, running: false }, { type: "snapshot-restored", snapshotId });
  };

  return (
    <section ref={ref} aria-labelledby={titleId} className={cn("w-full", className)} {...props}>
      <Card>
        <CardHeader className="gap-1">
          <CardTitle><h2 id={titleId}>{localText(definition.title, locale)}</h2></CardTitle>
          {definition.description ? <CardDescription>{localText(definition.description, locale)}</CardDescription> : null}
        </CardHeader>
        <CardContent className="space-y-6">
          {renderSystem ? <div className="overflow-hidden rounded-lg border" aria-label={text.activity}>{renderSystem({ definition, state })}</div> : null}

          <div className="flex items-center gap-1 border-b pb-3">
            {definition.clock.mode === "continuous" ? <Button type="button" variant="ghost" size="icon" disabled={disabled} aria-label={state.running ? text.pause : text.play} title={state.running ? text.pause : text.play} onClick={() => setRunning(!state.running)}>{state.running ? <MdPause aria-hidden /> : <MdPlayArrow aria-hidden />}</Button> : null}
            <Button type="button" variant="ghost" size="icon" disabled={disabled || state.running} aria-label={text.step} title={text.step} onClick={() => step()}><MdSkipNext aria-hidden /></Button>
            <Button type="button" variant="ghost" size="icon" disabled={disabled || (state.elapsedMs === 0 && state.snapshots.length === 0)} aria-label={text.reset} title={text.reset} onClick={reset}><MdRestartAlt aria-hidden /></Button>
            {definition.snapshots?.enabled ? <Button type="button" variant="ghost" size="icon" disabled={disabled} aria-label={text.snapshot} title={text.snapshot} onClick={snapshot}><MdAddAPhoto aria-hidden /></Button> : null}
            <span className="ml-auto text-sm tabular-nums text-muted-foreground">{text.elapsed}: {formatElapsed(state.elapsedMs, locale)}</span>
          </div>

          {definition.parameters.length ? <fieldset className="grid gap-4 sm:grid-cols-2"><legend className="mb-3 text-sm font-medium">{text.parameters}</legend>{definition.parameters.map((parameter) => {
            const value = state.parameters[parameter.id]; const unit = localText(parameter.unit, locale);
            return <div key={parameter.id} className="space-y-2"><Label htmlFor={`${titleId}-${parameter.id}`}>{localText(parameter.label, locale)}{unit ? ` (${unit})` : ""}</Label>{parameter.kind === "boolean" ? <input id={`${titleId}-${parameter.id}`} type="checkbox" checked={Boolean(value)} disabled={disabled} onChange={(event) => changeParameter(parameter.id, event.target.checked)} /> : <Input id={`${titleId}-${parameter.id}`} type="number" value={Number(value)} min={parameter.min} max={parameter.max} step={parameter.step ?? "any"} disabled={disabled} onChange={(event) => { const next = Number(event.target.value); if (Number.isFinite(next)) changeParameter(parameter.id, next); }} />}</div>;
          })}</fieldset> : null}

          <div><h3 className="mb-3 text-sm font-medium">{text.observables}</h3><dl className="grid gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-2">{definition.variables.map((variable) => <div key={variable.id} className="flex items-baseline justify-between gap-4 bg-card px-4 py-3"><dt className="text-sm text-muted-foreground">{localText(variable.label, locale)}</dt><dd className="font-medium tabular-nums">{formatValue(state.values[variable.id] ?? variable.initial, variable.precision, locale)}{variable.unit ? ` ${localText(variable.unit, locale)}` : ""}</dd></div>)}</dl></div>

          {definition.actions?.length ? <div><h3 className="mb-3 text-sm font-medium">{text.actions}</h3><div className="flex flex-wrap gap-2">{definition.actions.map((item) => <Button key={item.id} type="button" variant="outline" disabled={disabled} onClick={() => action(item.id)}>{localText(item.label, locale)}</Button>)}</div></div> : null}

          {state.snapshots.length ? <div><h3 className="mb-3 text-sm font-medium">{text.snapshots}</h3><ul className="space-y-2">{state.snapshots.map((item) => <li key={item.id} className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"><span>{formatElapsed(item.elapsedMs, locale)}</span><Button type="button" size="sm" variant="ghost" disabled={disabled} onClick={() => restore(item.id)}>{text.restore}</Button></li>)}</ul></div> : null}
        </CardContent>
      </Card>
    </section>
  );
});
