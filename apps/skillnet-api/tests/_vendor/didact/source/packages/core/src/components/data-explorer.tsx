import * as React from "react";
import type {
  DataCoordinateDefinition,
  DataCoordinateDomain,
  DataCoordinateEvent,
  DataCoordinateFunctionSource,
  DataCoordinatePoint,
  DataCoordinatePointEditability,
  DataCoordinateResult,
  DataCoordinateSeries,
  DataCoordinateState,
  DataCoordinateValue,
} from "@didact/schema";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@didact/ui";

import { cn } from "../lib/cn.js";

const EMPTY_STATE: DataCoordinateState = { pointOverrides: [] };
const WIDTH = 640;
const HEIGHT = 360;
const PADDING = { top: 20, right: 48, bottom: 58, left: 74 };

export interface DataExplorerLabels {
  activity: string;
  loading: string;
  empty: string;
  chart: string;
  table: string;
  chartDescription: (title: string) => string;
  selected: string;
  series: string;
  editX: (axis: string) => string;
  editY: (axis: string) => string;
  point: (series: string, x: string, y: string) => string;
  keyboardHelp: string;
}

const defaultLabels: DataExplorerLabels = {
  activity: "Data explorer",
  loading: "The data is still loading.",
  empty: "There is no data to display yet.",
  chart: "Chart",
  table: "Data table",
  chartDescription: (title) => `Interactive chart for ${title}`,
  selected: "Selected",
  series: "Series",
  editX: (axis) => `Edit ${axis}`,
  editY: (axis) => `Edit ${axis}`,
  point: (series, x, y) => `${series}: ${x}, ${y}`,
  keyboardHelp: "Select a point with Enter. Use arrow keys to change editable values.",
};

export interface DataExplorerProps
  extends Omit<React.ComponentPropsWithoutRef<"section">, "children" | "title" | "defaultValue"> {
  /** A serializable definition. Omit it while a streamed definition is not ready. */
  definition?: DataCoordinateDefinition;
  state?: DataCoordinateState;
  defaultState?: DataCoordinateState;
  onStateChange?: (state: DataCoordinateState, event: DataCoordinateEvent) => void;
  onResult?: (result: DataCoordinateResult) => void;
  /** Host-owned, safe expression evaluation. The component intentionally never calls eval. */
  evaluateFunction?: (
    source: DataCoordinateFunctionSource,
    x: number,
    series: DataCoordinateSeries,
  ) => number | null;
  locale?: string;
  disabled?: boolean;
  /** Shows the streaming message instead of treating a missing definition as final emptiness. */
  streaming?: boolean;
  labels?: Partial<DataExplorerLabels>;
  initialView?: "chart" | "table";
}

interface ResolvedPoint {
  point: DataCoordinatePoint;
  series: DataCoordinateSeries;
  x: DataCoordinateValue;
  y: DataCoordinateValue;
  generated: boolean;
}

function localText(value: string | Record<string, string> | undefined, locale: string): string {
  if (typeof value === "string") return value;
  if (!value) return "";
  return value[locale] ?? value[locale.split("-")[0] ?? ""] ?? value.en ?? Object.values(value)[0] ?? "";
}

function numeric(value: DataCoordinateValue): number {
  return typeof value === "number" ? value : Date.parse(value);
}

function serialize(value: number, domain: DataCoordinateDomain): DataCoordinateValue {
  return domain.scale === "time" ? new Date(value).toISOString() : value;
}

function domainNumbers(domain: DataCoordinateDomain): [number, number] {
  return [numeric(domain.min), numeric(domain.max)];
}

function pointEditability(point: DataCoordinatePoint, series: DataCoordinateSeries): DataCoordinatePointEditability {
  return point.editable ?? series.editable ?? {};
}

function isSelectable(point: DataCoordinatePoint, series: DataCoordinateSeries): boolean {
  return point.selectable ?? series.selectable ?? false;
}

function formatValue(value: DataCoordinateValue, domain: DataCoordinateDomain, locale: string): string {
  if (domain.scale === "time") {
    const date = new Date(String(value));
    return Number.isNaN(date.valueOf()) ? String(value) : new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(date);
  }
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 3 }).format(Number(value));
}

function useControllableState(
  controlled: DataCoordinateState | undefined,
  defaultState: DataCoordinateState,
  onChange?: DataExplorerProps["onStateChange"],
  onResult?: DataExplorerProps["onResult"],
) {
  const [internal, setInternal] = React.useState(defaultState);
  const state = controlled ?? internal;
  const commit = React.useCallback((next: DataCoordinateState, event: DataCoordinateEvent) => {
    if (controlled === undefined) setInternal(next);
    onChange?.(next, event);
    onResult?.({ status: "ungraded", state: next, events: [event] });
  }, [controlled, onChange, onResult]);
  return [state, commit] as const;
}

function resolvePoints(
  definition: DataCoordinateDefinition,
  state: DataCoordinateState,
  evaluateFunction: DataExplorerProps["evaluateFunction"],
): ResolvedPoint[] {
  const overrides = new Map(state.pointOverrides.map((entry) => [`${entry.seriesId}\u0000${entry.datumId}`, entry]));
  return definition.series.flatMap((series) => {
    if (series.source.kind === "points") {
      return series.source.points.map((point) => {
        const override = overrides.get(`${series.id}\u0000${point.id}`);
        return { point, series, x: override?.x ?? point.x, y: override?.y ?? point.y, generated: false };
      });
    }
    if (!evaluateFunction) return [];
    const source = series.source;
    const domain = source.domain ?? (definition.axes.x.domain.scale === "linear" ? definition.axes.x.domain : undefined);
    if (!domain) return [];
    const count = Math.max(2, source.sampleCount ?? 41);
    return Array.from({ length: count }, (_, index): ResolvedPoint | null => {
      const x = domain.min + ((domain.max - domain.min) * index) / (count - 1);
      const y = evaluateFunction(source, x, series);
      if (y === null || !Number.isFinite(y)) return null;
      return { point: { id: `sample-${index}`, x, y }, series, x, y, generated: true };
    }).filter((entry): entry is ResolvedPoint => entry !== null);
  });
}

function ticks(domain: DataCoordinateDomain): number[] {
  const [min, max] = domainNumbers(domain);
  return Array.from({ length: 5 }, (_, index) => min + ((max - min) * index) / 4);
}

export const DataExplorer = React.forwardRef<HTMLElement, DataExplorerProps>(function DataExplorer(
  {
    definition,
    state: controlledState,
    defaultState = EMPTY_STATE,
    onStateChange,
    onResult,
    evaluateFunction,
    locale = "en",
    disabled = false,
    streaming = false,
    labels,
    initialView = "chart",
    className,
    ...props
  },
  ref,
) {
  const text = { ...defaultLabels, ...labels };
  const [state, commit] = useControllableState(controlledState, defaultState, onStateChange, onResult);
  const [view, setView] = React.useState<"chart" | "table">(initialView);
  const drag = React.useRef<ResolvedPoint | null>(null);
  const chartId = React.useId();

  if (!definition) {
    return (
      <section ref={ref} className={cn("rounded-xl border p-6 text-sm text-muted-foreground", className)} aria-label={text.activity} {...props}>
        <p role={streaming ? "status" : undefined}>{streaming ? text.loading : text.empty}</p>
      </section>
    );
  }

  const title = localText(definition.title, locale);
  const description = localText(definition.description, locale);
  const xLabel = localText(definition.axes.x.label, locale);
  const yLabel = localText(definition.axes.y.label, locale);
  const xUnit = localText(definition.axes.x.unit, locale);
  const yUnit = localText(definition.axes.y.unit, locale);
  const xDisplayLabel = xUnit ? `${xLabel} (${xUnit})` : xLabel;
  const yDisplayLabel = yUnit ? `${yLabel} (${yUnit})` : yLabel;
  const xDomain = state.viewport?.x ?? definition.axes.x.domain;
  const yDomain = state.viewport?.y ?? definition.axes.y.domain;
  const points = resolvePoints(definition, state, evaluateFunction);
  const included = definition.table.includeSeriesIds ? new Set(definition.table.includeSeriesIds) : undefined;
  const tablePoints = points.filter(({ series }) => !included || included.has(series.id));
  const [xMin, xMax] = domainNumbers(xDomain);
  const [yMin, yMax] = domainNumbers(yDomain);
  const plotWidth = WIDTH - PADDING.left - PADDING.right;
  const plotHeight = HEIGHT - PADDING.top - PADDING.bottom;
  const sx = (value: DataCoordinateValue) => PADDING.left + ((numeric(value) - xMin) / (xMax - xMin)) * plotWidth;
  const sy = (value: DataCoordinateValue) => PADDING.top + (1 - (numeric(value) - yMin) / (yMax - yMin)) * plotHeight;

  const updateSelection = (datum: ResolvedPoint) => {
    if (disabled || definition.interaction?.selection === "none" || !isSelectable(datum.point, datum.series)) return;
    const selectedDatum = { seriesId: datum.series.id, datumId: datum.point.id };
    const next = { ...state, selectedDatum };
    commit(next, { type: "selection-changed", selectedDatum });
  };

  const updatePoint = (datum: ResolvedPoint, axis: "x" | "y", value: DataCoordinateValue) => {
    if (disabled || datum.generated || !pointEditability(datum.point, datum.series)[axis]) return;
    const existing = state.pointOverrides.find((item) => item.seriesId === datum.series.id && item.datumId === datum.point.id);
    const override = { ...existing, seriesId: datum.series.id, datumId: datum.point.id, [axis]: value };
    const pointOverrides = [...state.pointOverrides.filter((item) => item.seriesId !== datum.series.id || item.datumId !== datum.point.id), override];
    const next = { ...state, pointOverrides };
    commit(next, { type: "point-overridden", override });
  };

  const onPointKeyDown = (event: React.KeyboardEvent<SVGCircleElement>, datum: ResolvedPoint) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      updateSelection(datum);
      return;
    }
    const editability = pointEditability(datum.point, datum.series);
    const xStep = (xMax - xMin) / 100;
    const yStep = (yMax - yMin) / 100;
    if ((event.key === "ArrowLeft" || event.key === "ArrowRight") && editability.x) {
      event.preventDefault();
      updatePoint(datum, "x", serialize(Math.min(xMax, Math.max(xMin, numeric(datum.x) + (event.key === "ArrowRight" ? xStep : -xStep))), xDomain));
    }
    if ((event.key === "ArrowUp" || event.key === "ArrowDown") && editability.y) {
      event.preventDefault();
      updatePoint(datum, "y", serialize(Math.min(yMax, Math.max(yMin, numeric(datum.y) + (event.key === "ArrowUp" ? yStep : -yStep))), yDomain));
    }
  };

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const datum = drag.current;
    if (!datum || disabled) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const xPixel = ((event.clientX - rect.left) / rect.width) * WIDTH;
    const yPixel = ((event.clientY - rect.top) / rect.height) * HEIGHT;
    const editable = pointEditability(datum.point, datum.series);
    if (editable.x) updatePoint(datum, "x", serialize(Math.min(xMax, Math.max(xMin, xMin + ((xPixel - PADDING.left) / plotWidth) * (xMax - xMin))), xDomain));
    if (editable.y) updatePoint(datum, "y", serialize(Math.min(yMax, Math.max(yMin, yMax - ((yPixel - PADDING.top) / plotHeight) * (yMax - yMin))), yDomain));
  };

  return (
    <section ref={ref} aria-labelledby={`${chartId}-title`} className={cn("w-full", className)} {...props}>
      <Card>
        <CardHeader className="gap-1">
          <CardTitle><h2 id={`${chartId}-title`}>{title}</h2></CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-1 border-b" role="tablist" aria-label={text.activity}>
            {(["chart", "table"] as const).map((option) => (
              <Button
                key={option}
                type="button"
                role="tab"
                id={`${chartId}-${option}-tab`}
                variant="ghost"
                aria-selected={view === option}
                aria-controls={`${chartId}-${option}`}
                onClick={() => setView(option)}
                className="rounded-b-none"
              >
                {option === "chart" ? text.chart : text.table}
              </Button>
            ))}
          </div>

          {points.length === 0 ? <p className="py-8 text-center text-sm text-muted-foreground" role={streaming ? "status" : undefined}>{streaming ? text.loading : text.empty}</p> : null}

          <div id={`${chartId}-chart`} role="tabpanel" hidden={view !== "chart"} aria-labelledby={`${chartId}-chart-tab`}>
            {points.length ? (
              <>
                <svg
                  viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
                  className="block h-auto w-full text-foreground"
                  role="group"
                  aria-label={text.chartDescription(title)}
                  onPointerMove={onPointerMove}
                  onPointerUp={() => { drag.current = null; }}
                  onPointerCancel={() => { drag.current = null; }}
                >
                  {ticks(xDomain).map((tick) => <line key={`x-${tick}`} x1={sx(tick)} x2={sx(tick)} y1={PADDING.top} y2={HEIGHT - PADDING.bottom} className="stroke-border" />)}
                  {ticks(yDomain).map((tick) => <line key={`y-${tick}`} x1={PADDING.left} x2={WIDTH - PADDING.right} y1={sy(tick)} y2={sy(tick)} className="stroke-border" />)}
                  <line x1={PADDING.left} x2={WIDTH - PADDING.right} y1={HEIGHT - PADDING.bottom} y2={HEIGHT - PADDING.bottom} className="stroke-foreground" strokeWidth="1.5" />
                  <line x1={PADDING.left} x2={PADDING.left} y1={PADDING.top} y2={HEIGHT - PADDING.bottom} className="stroke-foreground" strokeWidth="1.5" />
                  {ticks(xDomain).map((tick) => <text key={`xt-${tick}`} x={sx(tick)} y={HEIGHT - 30} textAnchor="middle" className="fill-muted-foreground text-[11px]">{formatValue(serialize(tick, xDomain), xDomain, locale)}</text>)}
                  {ticks(yDomain).map((tick) => <text key={`yt-${tick}`} x={PADDING.left - 10} y={sy(tick) + 4} textAnchor="end" className="fill-muted-foreground text-[11px]">{formatValue(serialize(tick, yDomain), yDomain, locale)}</text>)}
                  <text x={PADDING.left + plotWidth / 2} y={HEIGHT - 4} textAnchor="middle" className="fill-foreground text-xs font-medium">{xDisplayLabel}</text>
                  <text transform={`translate(14 ${PADDING.top + plotHeight / 2}) rotate(-90)`} textAnchor="middle" className="fill-foreground text-xs font-medium">{yDisplayLabel}</text>
                  {definition.series.map((series, seriesIndex) => {
                    const seriesPoints = points.filter((datum) => datum.series.id === series.id);
                    const path = seriesPoints.map((datum, index) => `${index ? "L" : "M"}${sx(datum.x)},${sy(datum.y)}`).join(" ");
                    return (
                      <g key={series.id} data-series={series.id} className={seriesIndex % 2 ? "text-muted-foreground" : "text-primary"}>
                        {series.kind === "line" && path ? <path d={path} fill="none" stroke="currentColor" strokeWidth="2.5" strokeDasharray={seriesIndex % 2 ? "7 5" : undefined} vectorEffect="non-scaling-stroke" /> : null}
                        {seriesPoints.map((datum) => {
                          const selected = state.selectedDatum?.seriesId === series.id && state.selectedDatum.datumId === datum.point.id;
                          const interactive = isSelectable(datum.point, series) || Object.values(pointEditability(datum.point, series)).some(Boolean);
                          if (datum.generated && series.kind === "line" && !interactive) return null;
                          return (
                            <circle
                              key={datum.point.id}
                              cx={sx(datum.x)} cy={sy(datum.y)} r={selected ? 7 : 5}
                              fill={selected ? "currentColor" : "var(--background)"}
                              stroke="currentColor" strokeWidth={selected ? 3 : 2}
                              role={interactive ? "button" : undefined}
                              tabIndex={!disabled && interactive ? 0 : undefined}
                              aria-label={text.point(localText(series.label, locale), formatValue(datum.x, xDomain, locale), formatValue(datum.y, yDomain, locale))}
                              aria-pressed={isSelectable(datum.point, series) ? selected : undefined}
                              aria-disabled={disabled || undefined}
                              onClick={() => updateSelection(datum)}
                              onKeyDown={(event) => onPointKeyDown(event, datum)}
                              onPointerDown={(event) => {
                                if (!disabled && !datum.generated && Object.values(pointEditability(datum.point, series)).some(Boolean)) {
                                  drag.current = datum;
                                  event.currentTarget.setPointerCapture(event.pointerId);
                                }
                              }}
                              className={interactive && !disabled ? "cursor-pointer outline-none focus:stroke-foreground" : undefined}
                            />
                          );
                        })}
                      </g>
                    );
                  })}
                </svg>
                <p className="sr-only">{text.keyboardHelp}</p>
              </>
            ) : null}
          </div>

          <div id={`${chartId}-table`} role="tabpanel" hidden={view !== "table"} aria-labelledby={`${chartId}-table-tab`}>
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full border-collapse text-sm">
                <caption className="px-4 py-3 text-left font-medium">{localText(definition.table.caption, locale)}</caption>
                <thead className="border-y bg-muted/50 text-left">
                  <tr>
                    {definition.table.showSeriesColumn ? <th scope="col" className="px-4 py-2">{text.series}</th> : null}
                    <th scope="col" className="px-4 py-2">{xLabel}</th>
                    <th scope="col" className="px-4 py-2">{yLabel}</th>
                    <th scope="col" className="px-4 py-2">{text.selected}</th>
                  </tr>
                </thead>
                <tbody>
                  {tablePoints.map((datum) => {
                    const selected = state.selectedDatum?.seriesId === datum.series.id && state.selectedDatum.datumId === datum.point.id;
                    const editability = pointEditability(datum.point, datum.series);
                    const key = `${datum.series.id}-${datum.point.id}`;
                    return (
                      <tr key={key} className="border-b last:border-0" data-selected={selected || undefined}>
                        {definition.table.showSeriesColumn ? <th scope="row" className="px-4 py-2 text-left font-medium">{localText(datum.series.label, locale)}</th> : null}
                        {(["x", "y"] as const).map((axis) => {
                          const value = datum[axis];
                          const domain = axis === "x" ? xDomain : yDomain;
                          const axisLabel = axis === "x" ? xLabel : yLabel;
                          return (
                            <td key={axis} className="px-4 py-2">
                              {editability[axis] && !datum.generated ? (
                                <div className="min-w-28">
                                  <Label className="sr-only" htmlFor={`${chartId}-${key}-${axis}`}>{axis === "x" ? text.editX(axisLabel) : text.editY(axisLabel)}</Label>
                                  <Input
                                    id={`${chartId}-${key}-${axis}`}
                                    type={domain.scale === "linear" ? "number" : "text"}
                                    step="any"
                                    value={String(value)}
                                    disabled={disabled}
                                    onChange={(event) => {
                                      const next = domain.scale === "linear" ? Number(event.target.value) : event.target.value;
                                      if (domain.scale === "time" || Number.isFinite(next)) updatePoint(datum, axis, next);
                                    }}
                                  />
                                </div>
                              ) : formatValue(value, domain, locale)}
                            </td>
                          );
                        })}
                        <td className="px-4 py-2">
                          {isSelectable(datum.point, datum.series) ? (
                            <Button type="button" size="sm" variant={selected ? "secondary" : "outline"} disabled={disabled} aria-pressed={selected} onClick={() => updateSelection(datum)}>
                              {selected ? text.selected : text.point(localText(datum.series.label, locale), formatValue(datum.x, xDomain, locale), formatValue(datum.y, yDomain, locale))}
                            </Button>
                          ) : <span aria-hidden="true">—</span>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </CardContent>
      </Card>
    </section>
  );
});
