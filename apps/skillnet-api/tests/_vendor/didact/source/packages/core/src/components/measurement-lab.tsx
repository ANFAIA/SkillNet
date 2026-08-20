import * as React from "react";
import { Button, Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle, Input, Label } from "@didact/ui";

import { cn } from "../lib/cn.js";

export type MeasurementInstrumentKind = "linear" | "dial";

export interface MeasurementLabDefinition {
  id: string;
  title: string;
  description?: string;
  instructions?: string;
  /** Fixed value displayed by the instrument for reading tasks. Omit for manipulable instruments. */
  observedReading?: number;
  instrument: {
    kind: MeasurementInstrumentKind;
    min: number;
    max: number;
    step: number;
    majorStep?: number;
    unit: string;
    label?: string;
    orientation?: "horizontal" | "vertical";
  };
}

export interface MeasurementLabState {
  reading: number | null;
}

export type MeasurementLabStatus = "correct" | "incorrect" | "partial" | "ungraded";

export interface MeasurementLabEvaluation {
  status: MeasurementLabStatus;
  feedback?: React.ReactNode;
}

export interface MeasurementLabResult extends MeasurementLabEvaluation {
  definitionId: string;
  reading: number;
  unit: string;
}

export interface MeasurementLabLabels {
  activity: string;
  loading: string;
  empty: string;
  instrument: string;
  reading: string;
  setReading: string;
  submit: string;
  submitting: string;
  submitted: string;
  instrumentAt: (value: string, unit: string) => string;
  instrumentBetween: (lower: string, upper: string, unit: string) => string;
}

const defaultLabels: MeasurementLabLabels = {
  activity: "Measurement lab",
  loading: "The instrument is still loading.",
  empty: "There is no instrument to measure yet.",
  instrument: "Instrument",
  reading: "Current reading",
  setReading: "Set the measured value",
  submit: "Submit reading",
  submitting: "Checking reading",
  submitted: "Reading submitted",
  instrumentAt: (value, unit) => `Indicator at ${value} ${unit}.`,
  instrumentBetween: (lower, upper, unit) => `Indicator between ${lower} and ${upper} ${unit}.`,
};

export interface MeasurementLabProps
  extends Omit<React.ComponentPropsWithoutRef<"section">, "children" | "title" | "onSubmit"> {
  definition?: MeasurementLabDefinition;
  state?: MeasurementLabState;
  defaultState?: MeasurementLabState;
  onStateChange?: (state: MeasurementLabState) => void;
  evaluate?: (
    state: MeasurementLabState,
    definition: MeasurementLabDefinition,
  ) => MeasurementLabEvaluation | Promise<MeasurementLabEvaluation>;
  onSubmit?: (result: MeasurementLabResult) => void;
  disabled?: boolean;
  streaming?: boolean;
  locale?: string;
  labels?: Partial<MeasurementLabLabels>;
}

function validDefinition(definition: MeasurementLabDefinition): boolean {
  const { min, max, step } = definition.instrument;
  return Number.isFinite(min) && Number.isFinite(max) && max > min && Number.isFinite(step) && step > 0
    && (definition.observedReading === undefined
      || (Number.isFinite(definition.observedReading) && definition.observedReading >= min && definition.observedReading <= max));
}

function precision(step: number): number {
  const fraction = String(step).split(".")[1];
  return Math.min(fraction?.length ?? 0, 6);
}

function normalizeReading(value: number, definition: MeasurementLabDefinition): number {
  const { min, max, step } = definition.instrument;
  const snapped = min + Math.round((value - min) / step) * step;
  return Number(Math.min(max, Math.max(min, snapped)).toFixed(precision(step)));
}

function formatReading(value: number, definition: MeasurementLabDefinition, locale: string): string {
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: precision(definition.instrument.step),
    maximumFractionDigits: precision(definition.instrument.step),
  }).format(value);
}

function ticks(definition: MeasurementLabDefinition): number[] {
  const { min, max, majorStep = (max - min) / 4 } = definition.instrument;
  if (!Number.isFinite(majorStep) || majorStep <= 0) return [min, max];
  const values: number[] = [];
  for (let value = min; value <= max + majorStep / 1000 && values.length < 30; value += majorStep) {
    values.push(Number(Math.min(value, max).toFixed(precision(majorStep))));
  }
  if (values.at(-1) !== max) values.push(max);
  return [...new Set(values)];
}

function LinearInstrument({ definition, reading, locale, accessibleReading }: {
  definition: MeasurementLabDefinition;
  reading: number;
  locale: string;
  accessibleReading: string;
}) {
  const { min, max } = definition.instrument;
  const position = ((reading - min) / (max - min)) * 100;
  return (
    <svg viewBox="0 0 640 150" role="img" aria-label={accessibleReading} className="h-auto w-full">
      <line x1="50" y1="72" x2="590" y2="72" className="stroke-border" strokeWidth="4" />
      {ticks(definition).map((value) => {
        const x = 50 + ((value - min) / (max - min)) * 540;
        return <g key={value}><line x1={x} y1="58" x2={x} y2="87" className="stroke-muted-foreground" strokeWidth="2" /><text x={x} y="113" textAnchor="middle" className="fill-muted-foreground text-[13px]">{formatReading(value, definition, locale)}</text></g>;
      })}
      <line x1={50 + position * 5.4} y1="35" x2={50 + position * 5.4} y2="91" className="stroke-foreground" strokeWidth="4" />
      <circle cx={50 + position * 5.4} cy="31" r="7" className="fill-foreground" />
    </svg>
  );
}

function DialInstrument({ definition, reading, locale, accessibleReading }: {
  definition: MeasurementLabDefinition;
  reading: number;
  locale: string;
  accessibleReading: string;
}) {
  const { min, max } = definition.instrument;
  const angle = 135 + ((reading - min) / (max - min)) * 270;
  const radians = (angle * Math.PI) / 180;
  const endX = 160 + Math.cos(radians) * 88;
  const endY = 155 + Math.sin(radians) * 88;
  return (
    <svg viewBox="0 0 320 260" role="img" aria-label={accessibleReading} className="mx-auto h-auto w-full max-w-sm">
      <path d="M 65 205 A 135 135 0 1 1 255 205" fill="none" className="stroke-border" strokeWidth="5" />
      {ticks(definition).map((value) => {
        const tickAngle = (135 + ((value - min) / (max - min)) * 270) * Math.PI / 180;
        const x1 = 160 + Math.cos(tickAngle) * 119;
        const y1 = 155 + Math.sin(tickAngle) * 119;
        const x2 = 160 + Math.cos(tickAngle) * 132;
        const y2 = 155 + Math.sin(tickAngle) * 132;
        const labelX = 160 + Math.cos(tickAngle) * 104;
        const labelY = 159 + Math.sin(tickAngle) * 104;
        return <g key={value}><line x1={x1} y1={y1} x2={x2} y2={y2} className="stroke-muted-foreground" strokeWidth="2" /><text x={labelX} y={labelY} dominantBaseline="middle" textAnchor="middle" className="fill-muted-foreground text-[10px]">{formatReading(value, definition, locale)}</text></g>;
      })}
      <line x1="160" y1="155" x2={endX} y2={endY} className="stroke-foreground" strokeWidth="5" strokeLinecap="round" />
      <circle cx="160" cy="155" r="9" className="fill-foreground" />
    </svg>
  );
}

export function MeasurementLab({
  definition,
  state,
  defaultState = { reading: null },
  onStateChange,
  evaluate,
  onSubmit,
  disabled = false,
  streaming = false,
  locale = "en",
  labels: labelsOverride,
  className,
  ...props
}: MeasurementLabProps) {
  const labels = { ...defaultLabels, ...labelsOverride };
  const [internalState, setInternalState] = React.useState(defaultState);
  const currentState = state ?? internalState;
  const [result, setResult] = React.useState<MeasurementLabResult | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const inputId = React.useId();

  if (!definition || !validDefinition(definition)) {
    return <section aria-label={labels.activity} className={cn("w-full", className)} {...props}><Card><CardContent className="py-8 text-sm text-muted-foreground">{streaming ? labels.loading : labels.empty}</CardContent></Card></section>;
  }

  const { instrument } = definition;
  const displayReading = currentState.reading ?? normalizeReading((instrument.min + instrument.max) / 2, definition);
  const instrumentReading = definition.observedReading ?? displayReading;
  const majorTicks = ticks(definition);
  const exactTick = majorTicks.find((value) => Math.abs(value - instrumentReading) < instrument.step / 1000);
  const lowerTick = [...majorTicks].reverse().find((value) => value < instrumentReading) ?? instrument.min;
  const upperTick = majorTicks.find((value) => value > instrumentReading) ?? instrument.max;
  const accessibleReading = exactTick !== undefined
    ? labels.instrumentAt(formatReading(exactTick, definition, locale), instrument.unit)
    : labels.instrumentBetween(formatReading(lowerTick, definition, locale), formatReading(upperTick, definition, locale), instrument.unit);
  const commit = (reading: number) => {
    const next = { reading: normalizeReading(reading, definition) };
    if (state === undefined) setInternalState(next);
    onStateChange?.(next);
    setResult(null);
  };
  const submit = async () => {
    if (currentState.reading === null || submitting || disabled) return;
    setSubmitting(true);
    try {
      const evaluation = evaluate
        ? await evaluate(currentState, definition)
        : { status: "ungraded" as const };
      const next: MeasurementLabResult = {
        definitionId: definition.id,
        reading: currentState.reading,
        unit: instrument.unit,
        ...evaluation,
      };
      setResult(next);
      onSubmit?.(next);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section aria-label={labels.activity} className={cn("w-full", className)} {...props}>
      <Card>
        <CardHeader>
          <CardTitle>{definition.title}</CardTitle>
          {definition.description ? <CardDescription>{definition.description}</CardDescription> : null}
        </CardHeader>
        <CardContent className="space-y-6">
          {definition.instructions ? <p className="text-sm text-muted-foreground">{definition.instructions}</p> : null}
          <figure aria-label={instrument.label ?? labels.instrument} className="rounded-md border p-4">
            {instrument.kind === "dial"
              ? <DialInstrument definition={definition} reading={instrumentReading} locale={locale} accessibleReading={accessibleReading} />
              : <LinearInstrument definition={definition} reading={instrumentReading} locale={locale} accessibleReading={accessibleReading} />}
          </figure>
          <div className="space-y-3">
            <Label htmlFor={inputId}>{labels.setReading}</Label>
            <input id={inputId} type="range" min={instrument.min} max={instrument.max} step={instrument.step} value={displayReading} disabled={disabled} onChange={(event) => commit(event.currentTarget.valueAsNumber)} className="w-full accent-foreground" />
            <div className="flex items-end gap-3">
              <div className="flex-1 space-y-2">
                <Label htmlFor={`${inputId}-number`}>{labels.reading}</Label>
                <Input id={`${inputId}-number`} type="number" min={instrument.min} max={instrument.max} step={instrument.step} value={currentState.reading ?? ""} placeholder={formatReading(displayReading, definition, locale)} disabled={disabled} onChange={(event) => { if (event.currentTarget.value !== "") commit(event.currentTarget.valueAsNumber); }} />
              </div>
              <span className="pb-2 text-sm text-muted-foreground">{instrument.unit}</span>
            </div>
          </div>
          {result ? <div role="status" className="rounded-md border px-4 py-3 text-sm"><p className="font-medium">{labels.submitted}</p>{result.feedback ? <div className="mt-1 text-muted-foreground">{result.feedback}</div> : null}</div> : null}
        </CardContent>
        <CardFooter>
          <Button type="button" onClick={() => void submit()} disabled={disabled || submitting || currentState.reading === null}>{submitting ? labels.submitting : labels.submit}</Button>
        </CardFooter>
      </Card>
    </section>
  );
}
