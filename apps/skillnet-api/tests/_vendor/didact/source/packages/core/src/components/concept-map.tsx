import * as React from "react";
import {
  MdAdd,
  MdArrowForward,
  MdCheckCircle,
  MdDeleteOutline,
  MdLink,
  MdRestartAlt,
  MdUndo,
} from "react-icons/md";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@didact/ui";

import { cn } from "../lib/cn.js";

export type ConceptMapText = string | Record<string, string>;

export interface ConceptMapNode {
  id: string;
  label: ConceptMapText;
  /** Percent coordinates keep the model serializable and responsive. */
  position?: { x: number; y: number };
  learnerCreated?: boolean;
}

export interface ConceptMapRelation {
  id: string;
  from: string;
  to: string;
  label?: ConceptMapText;
  directed?: boolean;
}

export interface ConceptMapDefinition {
  id: string;
  title: ConceptMapText;
  description?: ConceptMapText;
  instructions?: ConceptMapText;
  nodes: ConceptMapNode[];
  initialRelations?: ConceptMapRelation[];
  allowNodeCreation?: boolean;
  allowRelationRemoval?: boolean;
  relationLabels?: ConceptMapText[];
  evaluation?: { enabled: boolean };
}

export type ConceptMapEvaluationStatus = "correct" | "incorrect" | "partial" | "ungraded";

export interface ConceptMapEvaluationResult {
  status: ConceptMapEvaluationStatus;
  feedback?: ConceptMapText;
}

export interface ConceptMapState {
  nodes: ConceptMapNode[];
  relations: ConceptMapRelation[];
  evaluation?: ConceptMapEvaluationResult;
}

export type ConceptMapEvent =
  | { type: "relation-added"; relation: ConceptMapRelation }
  | { type: "relation-removed"; relationId: string }
  | { type: "node-added"; node: ConceptMapNode }
  | { type: "node-removed"; nodeId: string }
  | { type: "submitted"; status: ConceptMapEvaluationStatus }
  | { type: "undo" }
  | { type: "reset" };

export interface ConceptMapLabels {
  activity: string;
  loading: string;
  empty: string;
  map: string;
  connectionBuilder: string;
  from: string;
  to: string;
  relationship: string;
  noRelationship: string;
  connect: string;
  connections: string;
  noConnections: string;
  remove: (label: string) => string;
  newConcept: string;
  conceptName: string;
  addConcept: string;
  removeConcept: (label: string) => string;
  undo: string;
  reset: string;
  submit: string;
  feedback: string;
  directed: string;
  undirected: string;
}

const defaultLabels: ConceptMapLabels = {
  activity: "Concept map",
  loading: "The concept map is still loading.",
  empty: "There is no concept map to display.",
  map: "Visual concept map",
  connectionBuilder: "Create a connection",
  from: "From concept",
  to: "To concept",
  relationship: "Relationship",
  noRelationship: "No label",
  connect: "Connect",
  connections: "Connections",
  noConnections: "No connections yet.",
  remove: (label) => `Remove connection ${label}`,
  newConcept: "Add a concept",
  conceptName: "Concept name",
  addConcept: "Add concept",
  removeConcept: (label) => `Remove concept ${label}`,
  undo: "Undo",
  reset: "Reset",
  submit: "Check map",
  feedback: "Feedback",
  directed: "directed",
  undirected: "undirected",
};

export interface ConceptMapProps
  extends Omit<React.ComponentPropsWithoutRef<"section">, "children" | "title" | "defaultValue"> {
  definition?: ConceptMapDefinition;
  state?: ConceptMapState;
  defaultState?: ConceptMapState;
  onStateChange?: (state: ConceptMapState, event: ConceptMapEvent) => void;
  evaluate?: (state: ConceptMapState, definition: ConceptMapDefinition) => ConceptMapEvaluationResult;
  onResult?: (result: ConceptMapEvaluationResult & { state: ConceptMapState }) => void;
  locale?: string;
  labels?: Partial<ConceptMapLabels>;
  disabled?: boolean;
  streaming?: boolean;
}

function localText(value: ConceptMapText | undefined, locale: string): string {
  if (typeof value === "string") return value;
  if (!value) return "";
  return value[locale] ?? value[locale.split("-")[0] ?? ""] ?? value.en ?? Object.values(value)[0] ?? "";
}

function initialState(definition: ConceptMapDefinition): ConceptMapState {
  return {
    nodes: definition.nodes.map((node) => ({ ...node, position: node.position ? { ...node.position } : undefined })),
    relations: (definition.initialRelations ?? []).map((relation) => ({ ...relation })),
  };
}

function positionedNode(node: ConceptMapNode, index: number, count: number): Required<ConceptMapNode>["position"] {
  if (node.position) return node.position;
  const angle = -Math.PI / 2 + (index * Math.PI * 2) / Math.max(count, 1);
  return { x: 50 + Math.cos(angle) * 35, y: 50 + Math.sin(angle) * 34 };
}

function relationDescription(relation: ConceptMapRelation, nodes: ConceptMapNode[], locale: string) {
  const from = localText(nodes.find(({ id }) => id === relation.from)?.label, locale);
  const to = localText(nodes.find(({ id }) => id === relation.to)?.label, locale);
  const label = localText(relation.label, locale);
  const connector = relation.directed === false ? " — " : " → ";
  return `${from}${label ? ` — ${label} ${connector}` : connector}${to}`;
}

export const ConceptMap = React.forwardRef<HTMLElement, ConceptMapProps>(function ConceptMap(
  {
    definition,
    state: controlledState,
    defaultState,
    onStateChange,
    evaluate,
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
  const fresh = React.useMemo(() => (definition ? initialState(definition) : undefined), [definition]);
  const [internalState, setInternalState] = React.useState<ConceptMapState | undefined>(defaultState);
  const state = controlledState ?? internalState ?? fresh;
  const [history, setHistory] = React.useState<ConceptMapState[]>([]);
  const [from, setFrom] = React.useState("");
  const [to, setTo] = React.useState("");
  const [relationLabel, setRelationLabel] = React.useState("");
  const [newConcept, setNewConcept] = React.useState("");
  const titleId = React.useId();

  const commit = React.useCallback((next: ConceptMapState, event: ConceptMapEvent, remember = true) => {
    if (state && remember) setHistory((entries) => [...entries.slice(-19), state]);
    if (controlledState === undefined) setInternalState(next);
    onStateChange?.(next, event);
  }, [controlledState, onStateChange, state]);

  React.useEffect(() => {
    if (!from && state?.nodes[0]) setFrom(state.nodes[0].id);
    if (!to && state?.nodes[1]) setTo(state.nodes[1].id);
  }, [from, state?.nodes, to]);

  if (!definition || !state) {
    return (
      <section ref={ref} aria-label={text.activity} className={cn("rounded-xl border p-6 text-sm text-muted-foreground", className)} {...props}>
        <p role={streaming ? "status" : undefined}>{streaming ? text.loading : text.empty}</p>
      </section>
    );
  }

  const addRelation = () => {
    if (disabled || !from || !to || from === to) return;
    const relation: ConceptMapRelation = {
      id: `relation-${Date.now()}-${state.relations.length}`,
      from,
      to,
      label: relationLabel || undefined,
      directed: true,
    };
    commit({ ...state, relations: [...state.relations, relation], evaluation: undefined }, { type: "relation-added", relation });
  };
  const removeRelation = (relationId: string) => commit(
    { ...state, relations: state.relations.filter(({ id }) => id !== relationId), evaluation: undefined },
    { type: "relation-removed", relationId },
  );
  const addNode = () => {
    const label = newConcept.trim();
    if (disabled || !label) return;
    const node: ConceptMapNode = { id: `concept-${Date.now()}-${state.nodes.length}`, label, learnerCreated: true };
    commit({ ...state, nodes: [...state.nodes, node], evaluation: undefined }, { type: "node-added", node });
    setNewConcept("");
  };
  const removeNode = (nodeId: string) => {
    const node = state.nodes.find(({ id }) => id === nodeId);
    if (!node?.learnerCreated || disabled) return;
    commit({ ...state, nodes: state.nodes.filter(({ id }) => id !== nodeId), relations: state.relations.filter(({ from, to }) => from !== nodeId && to !== nodeId), evaluation: undefined }, { type: "node-removed", nodeId });
    if (from === nodeId) setFrom("");
    if (to === nodeId) setTo("");
  };
  const undo = () => {
    const previous = history.at(-1);
    if (!previous || disabled) return;
    setHistory((entries) => entries.slice(0, -1));
    if (controlledState === undefined) setInternalState(previous);
    onStateChange?.(previous, { type: "undo" });
  };
  const reset = () => {
    if (!fresh || disabled) return;
    setHistory([]);
    if (controlledState === undefined) setInternalState(fresh);
    onStateChange?.(fresh, { type: "reset" });
  };
  const submit = () => {
    if (disabled || !definition.evaluation?.enabled) return;
    const result = evaluate?.(state, definition) ?? { status: "ungraded" as const };
    const next = { ...state, evaluation: result };
    if (controlledState === undefined) setInternalState(next);
    onStateChange?.(next, { type: "submitted", status: result.status });
    onResult?.({ ...result, state: next });
  };

  const positions = new Map(state.nodes.map((node, index) => [node.id, positionedNode(node, index, state.nodes.length)]));

  return (
    <section ref={ref} aria-labelledby={titleId} className={cn("w-full", className)} {...props}>
      <Card>
        <CardHeader className="gap-1">
          <CardTitle><h2 id={titleId}>{localText(definition.title, locale)}</h2></CardTitle>
          {definition.description ? <CardDescription>{localText(definition.description, locale)}</CardDescription> : null}
        </CardHeader>
        <CardContent className="space-y-5">
          {definition.instructions ? <p className="text-sm leading-relaxed">{localText(definition.instructions, locale)}</p> : null}

          <div className="relative min-h-72 overflow-hidden rounded-lg border bg-muted/15" role="group" aria-label={text.map}>
            <svg className="pointer-events-none absolute inset-0 size-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              {state.relations.map((relation) => {
                const start = positions.get(relation.from);
                const end = positions.get(relation.to);
                if (!start || !end) return null;
                return <line key={relation.id} x1={start.x} y1={start.y} x2={end.x} y2={end.y} vectorEffect="non-scaling-stroke" className="stroke-border" strokeWidth="2" />;
              })}
            </svg>
            {state.relations.map((relation) => {
              const start = positions.get(relation.from);
              const end = positions.get(relation.to);
              const label = localText(relation.label, locale);
              if (!start || !end || !label) return null;
              return <span key={`${relation.id}-label`} className="absolute -translate-x-1/2 -translate-y-1/2 rounded bg-background px-1.5 py-0.5 text-xs text-muted-foreground" style={{ left: `${(start.x + end.x) / 2}%`, top: `${(start.y + end.y) / 2}%` }}>{label}</span>;
            })}
            {state.nodes.map((node) => {
              const position = positions.get(node.id)!;
              const selected = from === node.id;
              return (
                <button key={node.id} type="button" disabled={disabled} aria-pressed={selected} onClick={() => setFrom(node.id)} className={cn("absolute max-w-36 -translate-x-1/2 -translate-y-1/2 rounded-md border bg-background px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", selected && "border-foreground")} style={{ left: `${position.x}%`, top: `${position.y}%` }}>
                  {localText(node.label, locale)}
                </button>
              );
            })}
          </div>

          <fieldset className="space-y-3 rounded-lg border p-4" disabled={disabled || state.nodes.length < 2}>
            <legend className="px-1 text-sm font-medium">{text.connectionBuilder}</legend>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1.5"><Label htmlFor={`${titleId}-from`}>{text.from}</Label><select id={`${titleId}-from`} className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={from} onChange={(event) => setFrom(event.target.value)}>{state.nodes.map((node) => <option key={node.id} value={node.id}>{localText(node.label, locale)}</option>)}</select></div>
              <div className="space-y-1.5"><Label htmlFor={`${titleId}-relation`}>{text.relationship}</Label>{definition.relationLabels?.length ? <select id={`${titleId}-relation`} className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={relationLabel} onChange={(event) => setRelationLabel(event.target.value)}><option value="">{text.noRelationship}</option>{definition.relationLabels.map((label) => { const value = localText(label, locale); return <option key={value} value={value}>{value}</option>; })}</select> : <Input id={`${titleId}-relation`} value={relationLabel} onChange={(event) => setRelationLabel(event.target.value)} />}</div>
              <div className="space-y-1.5"><Label htmlFor={`${titleId}-to`}>{text.to}</Label><select id={`${titleId}-to`} className="h-10 w-full rounded-md border bg-background px-3 text-sm" value={to} onChange={(event) => setTo(event.target.value)}>{state.nodes.map((node) => <option key={node.id} value={node.id}>{localText(node.label, locale)}</option>)}</select></div>
            </div>
            <Button type="button" size="sm" disabled={disabled || !from || !to || from === to} onClick={addRelation}><MdLink aria-hidden />{text.connect}</Button>
          </fieldset>

          {definition.allowNodeCreation ? <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); addNode(); }}><div className="min-w-52 flex-1 space-y-1.5"><Label htmlFor={`${titleId}-concept`}>{text.newConcept}</Label><Input id={`${titleId}-concept`} placeholder={text.conceptName} value={newConcept} disabled={disabled} onChange={(event) => setNewConcept(event.target.value)} /></div><Button type="submit" variant="outline" disabled={disabled || !newConcept.trim()}><MdAdd aria-hidden />{text.addConcept}</Button></form> : null}

          <div>
            <h3 className="mb-2 text-sm font-medium">{text.connections}</h3>
            {state.relations.length ? <ul className="space-y-2">{state.relations.map((relation) => { const description = relationDescription(relation, state.nodes, locale); return <li key={relation.id} className="flex min-h-10 items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"><span className="flex items-center gap-1.5">{description}{relation.directed === false ? null : <MdArrowForward className="sr-only" aria-label={text.directed} />}</span>{definition.allowRelationRemoval !== false ? <Button type="button" size="icon" variant="ghost" aria-label={text.remove(description)} disabled={disabled} onClick={() => removeRelation(relation.id)}><MdDeleteOutline aria-hidden /></Button> : null}</li>; })}</ul> : <p className="rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">{text.noConnections}</p>}
          </div>

          {definition.allowNodeCreation && state.nodes.some(({ learnerCreated }) => learnerCreated) ? <div className="flex flex-wrap gap-2">{state.nodes.filter(({ learnerCreated }) => learnerCreated).map((node) => { const label = localText(node.label, locale); return <Button key={node.id} type="button" size="sm" variant="ghost" disabled={disabled} aria-label={text.removeConcept(label)} onClick={() => removeNode(node.id)}><MdDeleteOutline aria-hidden />{label}</Button>; })}</div> : null}

          <div className="flex flex-wrap items-center gap-2">
            {definition.evaluation?.enabled ? <Button type="button" disabled={disabled} onClick={submit}><MdCheckCircle aria-hidden />{text.submit}</Button> : null}
            <Button type="button" variant="ghost" disabled={disabled || history.length === 0} onClick={undo}><MdUndo aria-hidden />{text.undo}</Button>
            <Button type="button" variant="ghost" disabled={disabled} onClick={reset}><MdRestartAlt aria-hidden />{text.reset}</Button>
          </div>
          {state.evaluation ? <div className="rounded-lg border px-4 py-3" data-status={state.evaluation.status} aria-live="polite"><h3 className="text-sm font-medium">{text.feedback}</h3>{state.evaluation.feedback ? <p className="mt-1 text-sm text-muted-foreground">{localText(state.evaluation.feedback, locale)}</p> : null}</div> : null}
        </CardContent>
      </Card>
    </section>
  );
});
