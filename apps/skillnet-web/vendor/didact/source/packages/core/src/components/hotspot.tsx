import * as React from "react";
import { Button, Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle, Input, Label } from "@didact/ui";

import { cn } from "../lib/cn.js";

export interface HotspotPoint { x: number; y: number }

export interface HotspotRegion {
  id: string;
  label: string;
  description?: React.ReactNode;
  /** Normalized coordinates in the inclusive 0..1 range. */
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface HotspotValue {
  regionIds: readonly string[];
  points: readonly HotspotPoint[];
}

export type HotspotResult = "correct" | "incorrect" | "partial" | "ungraded";

export type HotspotGrading =
  | { kind: "regions"; correctRegionIds: readonly string[] }
  | { kind: "points"; targets: readonly HotspotPoint[]; tolerance?: number };

export interface HotspotSubmitPayload {
  value: HotspotValue;
  result: HotspotResult;
}

export interface HotspotLabels {
  selectRegion: string;
  removeRegion: string;
  selected: string;
  regionList: string;
  pointInstructions: string;
  xCoordinate: string;
  yCoordinate: string;
  addPoint: string;
  selectedPoints: string;
  removePoint: (index: number) => string;
  submit: string;
  result: Record<HotspotResult, string>;
  mediaPending: string;
  regionsPending: string;
}

const defaultLabels: HotspotLabels = {
  selectRegion: "Select",
  removeRegion: "Remove",
  selected: "Selected",
  regionList: "Text alternative: available regions",
  pointInstructions: "Select a point on the diagram, or enter its horizontal and vertical percentages.",
  xCoordinate: "Horizontal position (%)",
  yCoordinate: "Vertical position (%)",
  addPoint: "Add point",
  selectedPoints: "Selected points",
  removePoint: (index) => `Remove point ${index}`,
  submit: "Submit selection",
  result: { correct: "Correct", incorrect: "Not quite", partial: "Partially correct", ungraded: "Response submitted" },
  mediaPending: "Diagram is still loading.",
  regionsPending: "Regions are still loading.",
};

export interface HotspotProps extends Omit<React.ComponentPropsWithoutRef<"div">, "onChange" | "onSubmit" | "title" | "defaultValue"> {
  title?: React.ReactNode;
  instructions?: React.ReactNode;
  media?: React.ReactNode;
  alt: string;
  longDescription?: React.ReactNode;
  interaction?: "regions" | "points";
  selection?: "single" | "multiple";
  regions?: readonly HotspotRegion[];
  grading?: HotspotGrading;
  value?: HotspotValue;
  defaultValue?: HotspotValue;
  onValueChange?: (value: HotspotValue) => void;
  onSubmit?: (payload: HotspotSubmitPayload) => void;
  feedback?: React.ReactNode | ((result: HotspotResult) => React.ReactNode);
  disabled?: boolean;
  labels?: Partial<Omit<HotspotLabels, "result">> & { result?: Partial<HotspotLabels["result"]> };
}

const emptyValue: HotspotValue = { regionIds: [], points: [] };
const clamp = (value: number) => Math.max(0, Math.min(1, value));

function grade(value: HotspotValue, grading: HotspotGrading | undefined): HotspotResult {
  if (!grading) return "ungraded";
  if (grading.kind === "regions") {
    const selected = new Set(value.regionIds);
    const correct = new Set(grading.correctRegionIds);
    const matches = [...selected].filter((id) => correct.has(id)).length;
    if (selected.size === correct.size && matches === correct.size) return "correct";
    return matches > 0 ? "partial" : "incorrect";
  }
  const tolerance = grading.tolerance ?? 0.05;
  const matchedTargets = new Set<number>();
  for (const point of value.points) {
    const targetIndex = grading.targets.findIndex((target, index) =>
      !matchedTargets.has(index) && Math.hypot(point.x - target.x, point.y - target.y) <= tolerance,
    );
    if (targetIndex >= 0) matchedTargets.add(targetIndex);
  }
  if (value.points.length === grading.targets.length && matchedTargets.size === grading.targets.length) return "correct";
  return matchedTargets.size > 0 ? "partial" : "incorrect";
}

/** Responsive spatial selection with an equivalent non-spatial keyboard/screen-reader path. */
export const Hotspot = React.forwardRef<HTMLDivElement, HotspotProps>(function Hotspot({
  title,
  instructions,
  media,
  alt,
  longDescription,
  interaction = "regions",
  selection = "single",
  regions,
  grading,
  value: valueProp,
  defaultValue = emptyValue,
  onValueChange,
  onSubmit,
  feedback,
  disabled = false,
  labels: labelsProp,
  className,
  ...props
}, ref) {
  const descriptionId = React.useId();
  const xId = React.useId();
  const yId = React.useId();
  const labels: HotspotLabels = {
    ...defaultLabels,
    ...labelsProp,
    result: { ...defaultLabels.result, ...labelsProp?.result },
  };
  const controlled = valueProp !== undefined;
  const [localValue, setLocalValue] = React.useState(defaultValue);
  const [submitted, setSubmitted] = React.useState(false);
  const [result, setResult] = React.useState<HotspotResult>();
  const [draftX, setDraftX] = React.useState("50");
  const [draftY, setDraftY] = React.useState("50");
  const value = controlled ? valueProp : localValue;
  const locked = disabled || submitted;

  const changeValue = (next: HotspotValue) => {
    if (locked) return;
    if (!controlled) setLocalValue(next);
    onValueChange?.(next);
  };

  const toggleRegion = (id: string) => {
    const selected = value.regionIds.includes(id);
    const regionIds = selection === "single"
      ? (selected ? [] : [id])
      : (selected ? value.regionIds.filter((entry) => entry !== id) : [...value.regionIds, id]);
    changeValue({ ...value, regionIds });
  };

  const addPoint = (point: HotspotPoint) => {
    const normalized = { x: clamp(point.x), y: clamp(point.y) };
    changeValue({ ...value, points: selection === "single" ? [normalized] : [...value.points, normalized] });
  };

  const handleDiagramClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (interaction !== "points" || locked) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    addPoint({ x: (event.clientX - rect.left) / rect.width, y: (event.clientY - rect.top) / rect.height });
  };

  const submit = () => {
    if (locked) return;
    const nextResult = grade(value, grading);
    setResult(nextResult);
    setSubmitted(true);
    onSubmit?.({ value, result: nextResult });
  };

  const hasSelection = interaction === "regions" ? value.regionIds.length > 0 : value.points.length > 0;
  const resolvedFeedback = result && (typeof feedback === "function" ? feedback(result) : feedback);

  return <Card ref={ref} className={cn("w-full max-w-2xl", className)} data-slot="hotspot" data-state={submitted ? "submitted" : "answering"} aria-disabled={disabled || undefined} {...props}>
    {(title || instructions) ? <CardHeader>{title ? <CardTitle>{title}</CardTitle> : null}{instructions ? <CardDescription>{instructions}</CardDescription> : null}</CardHeader> : null}
    <CardContent className="flex flex-col gap-5">
      <div>
        <div className="relative min-h-48 w-full overflow-hidden rounded-md border bg-muted/30" onClick={handleDiagramClick}>
          <div role="img" aria-label={alt} aria-describedby={longDescription ? descriptionId : undefined}>
            {media ?? <div className="flex min-h-48 items-center justify-center p-6 text-sm text-muted-foreground">{labels.mediaPending}</div>}
          </div>
          {interaction === "regions" ? regions?.map((region) => <button key={region.id} type="button" disabled={locked} aria-label={`${value.regionIds.includes(region.id) ? labels.removeRegion : labels.selectRegion}: ${region.label}`} aria-pressed={value.regionIds.includes(region.id)} onClick={(event) => { event.stopPropagation(); toggleRegion(region.id); }} className={cn("absolute border-2 border-foreground/60 bg-background/20 outline-none hover:bg-primary/20 focus-visible:ring-2 focus-visible:ring-ring", value.regionIds.includes(region.id) && "border-primary bg-primary/25")} style={{ left: `${clamp(region.x) * 100}%`, top: `${clamp(region.y) * 100}%`, width: `${clamp(region.width) * 100}%`, height: `${clamp(region.height) * 100}%` }} />) : value.points.map((point, index) => <span key={`${index}-${point.x}-${point.y}`} aria-hidden="true" className="pointer-events-none absolute size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-primary shadow" style={{ left: `${clamp(point.x) * 100}%`, top: `${clamp(point.y) * 100}%` }} />)}
        </div>
        {longDescription ? <div id={descriptionId} className="mt-2 text-sm text-muted-foreground">{longDescription}</div> : null}
      </div>

      {interaction === "regions" ? <fieldset disabled={locked} className="grid gap-2"><legend className="text-sm font-semibold">{labels.regionList}</legend>{regions === undefined ? <p className="text-sm text-muted-foreground">{labels.regionsPending}</p> : regions.map((region) => { const selected = value.regionIds.includes(region.id); return <div key={region.id} className="flex items-center justify-between gap-3 rounded-md border p-3"><div><p className="text-sm font-medium">{region.label}</p>{region.description ? <div className="text-sm text-muted-foreground">{region.description}</div> : null}</div><Button type="button" variant="outline" aria-pressed={selected} onClick={() => toggleRegion(region.id)}>{selected ? `${labels.selected} · ${labels.removeRegion}` : labels.selectRegion}</Button></div>; })}</fieldset> : <div className="grid gap-3"><p className="text-sm text-muted-foreground">{labels.pointInstructions}</p><div className="grid grid-cols-[1fr_1fr_auto] items-end gap-2"><div className="grid gap-1"><Label htmlFor={xId}>{labels.xCoordinate}</Label><Input id={xId} type="number" min={0} max={100} value={draftX} disabled={locked} onChange={(event) => setDraftX(event.target.value)} /></div><div className="grid gap-1"><Label htmlFor={yId}>{labels.yCoordinate}</Label><Input id={yId} type="number" min={0} max={100} value={draftY} disabled={locked} onChange={(event) => setDraftY(event.target.value)} /></div><Button type="button" variant="outline" disabled={locked || !Number.isFinite(Number(draftX)) || !Number.isFinite(Number(draftY))} onClick={() => addPoint({ x: Number(draftX) / 100, y: Number(draftY) / 100 })}>{labels.addPoint}</Button></div>{value.points.length > 0 ? <div><p className="mb-2 text-sm font-semibold">{labels.selectedPoints}</p><ul className="grid gap-2">{value.points.map((point, index) => <li key={`${index}-${point.x}-${point.y}`} className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"><span>{Math.round(point.x * 100)}%, {Math.round(point.y * 100)}%</span><Button type="button" variant="outline" disabled={locked} aria-label={labels.removePoint(index + 1)} onClick={() => changeValue({ ...value, points: value.points.filter((_, pointIndex) => pointIndex !== index) })}>{labels.removeRegion}</Button></li>)}</ul></div> : null}</div>}

      {submitted && result ? <div role="status" aria-live="polite" data-result={result} className="rounded-md border bg-muted/40 p-3 text-sm font-semibold">{labels.result[result]}</div> : null}
      {submitted && resolvedFeedback ? <div className="rounded-md bg-muted p-3 text-sm text-muted-foreground">{resolvedFeedback}</div> : null}
    </CardContent>
    <CardFooter><Button type="button" disabled={locked || !hasSelection} onClick={submit}>{labels.submit}</Button></CardFooter>
  </Card>;
});
