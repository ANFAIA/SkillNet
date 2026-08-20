import * as React from "react";
import {
  MdCheck,
  MdDeleteOutline,
  MdGesture,
  MdLocationOn,
  MdShowChart,
  MdUndo,
} from "react-icons/md";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@didact/ui";
import { cn } from "../lib/cn.js";

export type DrawingTool = "freehand" | "line" | "marker";

export interface DrawingPoint {
  /** Horizontal position normalized from 0 to 1. */
  x: number;
  /** Vertical position normalized from 0 to 1. */
  y: number;
}

export interface DrawingStroke {
  id: string;
  tool: DrawingTool;
  points: DrawingPoint[];
}

export interface DrawingResponseState {
  strokes: DrawingStroke[];
}

export interface DrawingResponseDefinition {
  id: string;
  title: string;
  description?: string;
  instructions?: string;
  background?: { src: string; alt: string };
  tools?: DrawingTool[];
}

export interface DrawingEvaluation {
  status: "correct" | "partial" | "incorrect";
  feedback: string;
}

export type DrawingResponseResult =
  | { status: "ungraded"; strokes: DrawingStroke[] }
  | ({ strokes: DrawingStroke[] } & DrawingEvaluation);

export interface DrawingResponseLabels {
  activity: string;
  loading: string;
  empty: string;
  freehand: string;
  line: string;
  marker: string;
  undo: string;
  clear: string;
  submit: string;
  submitting: string;
  responseDetails: string;
  noStrokes: string;
  stroke: string;
  tool: string;
  points: string;
  remove: string;
  coordinates: string;
  coordinateHelp: string;
  x: string;
  y: string;
  addMarker: string;
  canvasHelp: string;
}

const defaultLabels: DrawingResponseLabels = {
  activity: "Drawing response",
  loading: "The drawing activity is still loading.",
  empty: "There is no drawing activity to display.",
  freehand: "Draw",
  line: "Line",
  marker: "Marker",
  undo: "Undo",
  clear: "Clear",
  submit: "Submit response",
  submitting: "Checking response…",
  responseDetails: "Response details",
  noStrokes: "No marks yet.",
  stroke: "Mark",
  tool: "Tool",
  points: "Coordinates",
  remove: "Remove",
  coordinates: "Add by coordinates",
  coordinateHelp: "Enter percentages from 0 to 100. This is an accessible alternative to drawing with a pointer.",
  x: "Horizontal position",
  y: "Vertical position",
  addMarker: "Add marker",
  canvasHelp: "Draw with a pointer. With the canvas focused, use the arrow keys to position the cursor and Space to add a marker.",
};

export interface DrawingResponseProps extends Omit<React.ComponentPropsWithoutRef<"section">, "children" | "title" | "onChange"> {
  definition?: DrawingResponseDefinition;
  state?: DrawingResponseState;
  defaultState?: DrawingResponseState;
  onStateChange?: (state: DrawingResponseState) => void;
  evaluate?: (strokes: DrawingStroke[]) => DrawingEvaluation | Promise<DrawingEvaluation>;
  onResult?: (result: DrawingResponseResult) => void;
  labels?: Partial<DrawingResponseLabels>;
  disabled?: boolean;
  streaming?: boolean;
}

const EMPTY_STATE: DrawingResponseState = { strokes: [] };
const ICONS = { freehand: MdGesture, line: MdShowChart, marker: MdLocationOn };
const VIEWBOX_WIDTH = 1000;
const VIEWBOX_HEIGHT = 600;

function clamp(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function coordinateLabel(point: DrawingPoint): string {
  return `${Math.round(point.x * 100)}%, ${Math.round(point.y * 100)}%`;
}

function makeId(): string {
  return `mark-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

export const DrawingResponse = React.forwardRef<HTMLElement, DrawingResponseProps>(function DrawingResponse(
  { definition, state: controlledState, defaultState = EMPTY_STATE, onStateChange, evaluate, onResult, labels, disabled = false, streaming = false, className, ...props },
  ref,
) {
  const text = { ...defaultLabels, ...labels };
  const [internalState, setInternalState] = React.useState(defaultState);
  const [tool, setTool] = React.useState<DrawingTool>(definition?.tools?.[0] ?? "freehand");
  const [draft, setDraft] = React.useState<DrawingStroke>();
  const [keyboardPoint, setKeyboardPoint] = React.useState<DrawingPoint>({ x: 0.5, y: 0.5 });
  const [coordinateX, setCoordinateX] = React.useState(50);
  const [coordinateY, setCoordinateY] = React.useState(50);
  const [evaluation, setEvaluation] = React.useState<DrawingEvaluation>();
  const [submitting, setSubmitting] = React.useState(false);
  const titleId = React.useId();
  const instructionsId = React.useId();
  const coordinateHelpId = React.useId();
  const state = controlledState ?? internalState;
  const availableTools = definition?.tools?.length ? definition.tools : (["freehand", "line", "marker"] as DrawingTool[]);

  React.useEffect(() => {
    if (!availableTools.includes(tool)) setTool(availableTools[0] ?? "freehand");
  }, [availableTools, tool]);

  const commit = React.useCallback((strokes: DrawingStroke[]) => {
    const next = { strokes };
    if (controlledState === undefined) setInternalState(next);
    onStateChange?.(next);
    setEvaluation(undefined);
  }, [controlledState, onStateChange]);

  if (!definition) {
    return <section ref={ref} aria-label={text.activity} className={cn("rounded-xl border p-6 text-sm text-muted-foreground", className)} {...props}><p role={streaming ? "status" : undefined}>{streaming ? text.loading : text.empty}</p></section>;
  }

  const pointFromEvent = (event: React.PointerEvent<SVGSVGElement>): DrawingPoint => {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: clamp((event.clientX - rect.left) / Math.max(rect.width, 1)), y: clamp((event.clientY - rect.top) / Math.max(rect.height, 1)) };
  };
  const startStroke = (event: React.PointerEvent<SVGSVGElement>) => {
    if (disabled || event.button !== 0) return;
    const point = pointFromEvent(event);
    if (tool === "marker") commit([...state.strokes, { id: makeId(), tool, points: [point] }]);
    else {
      event.currentTarget.setPointerCapture?.(event.pointerId);
      setDraft({ id: makeId(), tool, points: [point] });
    }
  };
  const moveStroke = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!draft || !event.currentTarget.hasPointerCapture?.(event.pointerId)) return;
    const point = pointFromEvent(event);
    setDraft({ ...draft, points: draft.tool === "line" ? [draft.points[0]!, point] : [...draft.points, point] });
  };
  const finishStroke = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!draft) return;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    const point = pointFromEvent(event);
    const finished = draft.tool === "line" ? { ...draft, points: [draft.points[0]!, point] } : { ...draft, points: [...draft.points, point] };
    commit([...state.strokes, finished]);
    setDraft(undefined);
  };
  const addMarker = (point: DrawingPoint) => commit([...state.strokes, { id: makeId(), tool: "marker", points: [{ x: clamp(point.x), y: clamp(point.y) }] }]);
  const onCanvasKeyDown = (event: React.KeyboardEvent<SVGSVGElement>) => {
    const delta = event.shiftKey ? 0.05 : 0.01;
    const movement: Partial<Record<string, DrawingPoint>> = {
      ArrowLeft: { x: -delta, y: 0 }, ArrowRight: { x: delta, y: 0 }, ArrowUp: { x: 0, y: -delta }, ArrowDown: { x: 0, y: delta },
    };
    if (movement[event.key]) {
      event.preventDefault(); const change = movement[event.key]!;
      setKeyboardPoint((current) => ({ x: clamp(current.x + change.x), y: clamp(current.y + change.y) }));
    } else if (event.key === " " || event.key === "Enter") {
      event.preventDefault(); if (!disabled) addMarker(keyboardPoint);
    }
  };
  const submit = async () => {
    if (disabled || submitting || state.strokes.length === 0) return;
    setSubmitting(true);
    try {
      if (!evaluate) { onResult?.({ status: "ungraded", strokes: state.strokes }); return; }
      const result = await evaluate(state.strokes); setEvaluation(result); onResult?.({ ...result, strokes: state.strokes });
    } finally { setSubmitting(false); }
  };
  const allStrokes = draft ? [...state.strokes, draft] : state.strokes;

  return (
    <section ref={ref} aria-labelledby={titleId} className={cn("w-full", className)} {...props}>
      <Card>
        <CardHeader className="gap-1">
          <CardTitle><h2 id={titleId}>{definition.title}</h2></CardTitle>
          {definition.description ? <CardDescription>{definition.description}</CardDescription> : null}
        </CardHeader>
        <CardContent className="space-y-5">
          {definition.instructions ? <p id={instructionsId} className="text-sm text-muted-foreground">{definition.instructions}</p> : <span id={instructionsId} className="sr-only">{text.canvasHelp}</span>}

          <div className="flex flex-wrap items-center gap-1 border-b pb-3" role="toolbar" aria-label={text.activity}>
            {availableTools.map((item) => { const Icon = ICONS[item]; return <Button key={item} type="button" size="sm" variant={tool === item ? "secondary" : "ghost"} aria-pressed={tool === item} disabled={disabled} onClick={() => setTool(item)}><Icon aria-hidden className="mr-1.5" />{text[item]}</Button>; })}
            <span className="mx-1 h-5 w-px bg-border" aria-hidden />
            <Button type="button" size="icon" variant="ghost" aria-label={text.undo} title={text.undo} disabled={disabled || state.strokes.length === 0} onClick={() => commit(state.strokes.slice(0, -1))}><MdUndo aria-hidden /></Button>
            <Button type="button" size="icon" variant="ghost" aria-label={text.clear} title={text.clear} disabled={disabled || state.strokes.length === 0} onClick={() => commit([])}><MdDeleteOutline aria-hidden /></Button>
          </div>

          <div className="overflow-hidden rounded-lg border bg-muted/20">
            <svg
              viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`}
              preserveAspectRatio="xMidYMid meet"
              className={cn("block aspect-[5/3] w-full touch-none outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2", disabled && "cursor-not-allowed opacity-60")}
              role="img" aria-label={definition.background?.alt ?? text.activity} aria-describedby={instructionsId}
              tabIndex={disabled ? -1 : 0}
              onKeyDown={onCanvasKeyDown}
              onPointerDown={startStroke} onPointerMove={moveStroke} onPointerUp={finishStroke} onPointerCancel={() => setDraft(undefined)}
            >
              {definition.background ? <image href={definition.background.src} x="0" y="0" width={VIEWBOX_WIDTH} height={VIEWBOX_HEIGHT} preserveAspectRatio="xMidYMid slice" /> : <rect width={VIEWBOX_WIDTH} height={VIEWBOX_HEIGHT} fill="hsl(var(--muted))" opacity="0.25" />}
              {allStrokes.map((stroke) => {
                const points = stroke.points.map((point) => `${point.x * VIEWBOX_WIDTH},${point.y * VIEWBOX_HEIGHT}`).join(" ");
                if (stroke.tool === "marker") { const point = stroke.points[0]!; return <g key={stroke.id} transform={`translate(${point.x * VIEWBOX_WIDTH} ${point.y * VIEWBOX_HEIGHT})`}><circle r="18" fill="hsl(var(--background))" stroke="hsl(var(--primary))" strokeWidth="8"/><circle r="4" fill="hsl(var(--primary))" /></g>; }
                return <polyline key={stroke.id} points={points} fill="none" stroke="hsl(var(--primary))" strokeWidth={stroke.tool === "line" ? 8 : 10} strokeLinecap="round" strokeLinejoin="round" />;
              })}
              <g aria-hidden opacity="0.7" transform={`translate(${keyboardPoint.x * VIEWBOX_WIDTH} ${keyboardPoint.y * VIEWBOX_HEIGHT})`}><path d="M-12 0H12M0-12V12" stroke="hsl(var(--foreground))" strokeWidth="3" /></g>
            </svg>
          </div>
          <p className="text-xs text-muted-foreground">{text.canvasHelp}</p>

          <details className="rounded-lg border px-4 py-3">
            <summary className="cursor-pointer text-sm font-medium">{text.coordinates}</summary>
            <p id={coordinateHelpId} className="mt-2 text-xs text-muted-foreground">{text.coordinateHelp}</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
              <div className="space-y-1.5"><Label htmlFor={`${titleId}-x`}>{text.x} (%)</Label><Input id={`${titleId}-x`} type="number" min="0" max="100" value={coordinateX} disabled={disabled} aria-describedby={coordinateHelpId} onChange={(event) => setCoordinateX(Number(event.target.value))} /></div>
              <div className="space-y-1.5"><Label htmlFor={`${titleId}-y`}>{text.y} (%)</Label><Input id={`${titleId}-y`} type="number" min="0" max="100" value={coordinateY} disabled={disabled} aria-describedby={coordinateHelpId} onChange={(event) => setCoordinateY(Number(event.target.value))} /></div>
              <Button type="button" variant="outline" disabled={disabled || !Number.isFinite(coordinateX) || !Number.isFinite(coordinateY)} onClick={() => addMarker({ x: coordinateX / 100, y: coordinateY / 100 })}><MdLocationOn aria-hidden className="mr-1.5" />{text.addMarker}</Button>
            </div>
          </details>

          <div>
            <h3 className="mb-2 text-sm font-medium">{text.responseDetails}</h3>
            {state.strokes.length === 0 ? <p className="text-sm text-muted-foreground">{text.noStrokes}</p> : <ol className="divide-y rounded-lg border">{state.strokes.map((stroke, index) => <li key={stroke.id} className="flex items-center gap-3 px-3 py-2 text-sm"><span className="min-w-0 flex-1"><span className="font-medium">{text.stroke} {index + 1}</span><span className="ml-2 text-muted-foreground">{text[stroke.tool]} · {stroke.points.length === 1 ? coordinateLabel(stroke.points[0]!) : `${coordinateLabel(stroke.points[0]!)} → ${coordinateLabel(stroke.points.at(-1)!)}`}</span></span><Button type="button" size="icon" variant="ghost" aria-label={`${text.remove} ${text.stroke} ${index + 1}`} disabled={disabled} onClick={() => commit(state.strokes.filter(({ id }) => id !== stroke.id))}><MdDeleteOutline aria-hidden /></Button></li>)}</ol>}
          </div>

          {evaluation ? <div role="status" className="rounded-lg border px-4 py-3 text-sm"><p className="font-medium capitalize">{evaluation.status}</p><p className="mt-1 text-muted-foreground">{evaluation.feedback}</p></div> : null}
          <div className="flex justify-end"><Button type="button" disabled={disabled || submitting || state.strokes.length === 0} onClick={submit}><MdCheck aria-hidden className="mr-1.5" />{submitting ? text.submitting : text.submit}</Button></div>
        </CardContent>
      </Card>
    </section>
  );
});
