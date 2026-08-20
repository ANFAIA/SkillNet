import * as React from "react";
import { MdCheck, MdDeleteOutline, MdOutlineFormatQuote } from "react-icons/md";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@didact/ui";

import { cn } from "../lib/cn.js";

export type EvidenceAnnotationText = string | Record<string, string>;

export interface EvidenceSegment {
  id: string;
  text: EvidenceAnnotationText;
  /** Stable offsets in the source document, when the host has them. */
  start?: number;
  end?: number;
}

export interface EvidenceCategory {
  id: string;
  label: EvidenceAnnotationText;
}

export interface EvidenceClaim {
  id: string;
  label: EvidenceAnnotationText;
}

export interface EvidenceAnnotationDefinition {
  id: string;
  title: EvidenceAnnotationText;
  description?: EvidenceAnnotationText;
  instructions?: EvidenceAnnotationText;
  documentTitle?: EvidenceAnnotationText;
  segments: EvidenceSegment[];
  categories: EvidenceCategory[];
  claims?: EvidenceClaim[];
}

export interface EvidenceAnnotationItem {
  id: string;
  segmentId: string;
  /** Offsets are relative to the segment and remain valid across rendering changes. */
  start: number;
  end: number;
  quote: string;
  categoryId: string;
  claimId?: string;
  note?: string;
}

export interface EvidenceAnnotationState {
  annotations: EvidenceAnnotationItem[];
}

export interface EvidenceAnnotationEvaluation {
  status: "correct" | "partial" | "incorrect";
  feedback: EvidenceAnnotationText;
}

export type EvidenceAnnotationResult =
  | { status: "ungraded"; state: EvidenceAnnotationState }
  | (EvidenceAnnotationEvaluation & { state: EvidenceAnnotationState });

export interface EvidenceAnnotationLabels {
  activity: string;
  loading: string;
  empty: string;
  category: string;
  claim: string;
  noClaim: string;
  note: string;
  notePlaceholder: string;
  readerHelp: string;
  selected: string;
  selectEvidence: (text: string) => string;
  removeEvidence: (text: string) => string;
  accessibleSelection: string;
  accessibleHelp: string;
  annotations: string;
  noAnnotations: string;
  remove: string;
  submit: string;
  submitting: string;
}

const defaultLabels: EvidenceAnnotationLabels = {
  activity: "Evidence annotation",
  loading: "The document is still loading.",
  empty: "There is no document to annotate.",
  category: "Evidence type",
  claim: "Related claim",
  noClaim: "No related claim",
  note: "Reasoning note",
  notePlaceholder: "Explain why this passage matters (optional)",
  readerHelp: "Choose a category, then select a passage. Selected passages remain anchored to stable document segments.",
  selected: "Selected",
  selectEvidence: (text) => `Select evidence: ${text}`,
  removeEvidence: (text) => `Remove evidence: ${text}`,
  accessibleSelection: "Select from a list",
  accessibleHelp: "This keyboard-friendly list changes the same annotations as the document view.",
  annotations: "Your evidence",
  noAnnotations: "No evidence selected yet.",
  remove: "Remove",
  submit: "Submit evidence",
  submitting: "Checking evidence…",
};

export interface EvidenceAnnotationProps extends Omit<React.ComponentPropsWithoutRef<"section">, "children" | "title" | "onChange"> {
  definition?: EvidenceAnnotationDefinition;
  state?: EvidenceAnnotationState;
  defaultState?: EvidenceAnnotationState;
  onStateChange?: (state: EvidenceAnnotationState) => void;
  evaluate?: (state: EvidenceAnnotationState, definition: EvidenceAnnotationDefinition) => EvidenceAnnotationEvaluation | Promise<EvidenceAnnotationEvaluation>;
  onResult?: (result: EvidenceAnnotationResult) => void;
  labels?: Partial<EvidenceAnnotationLabels>;
  locale?: string;
  disabled?: boolean;
  streaming?: boolean;
}

const EMPTY_STATE: EvidenceAnnotationState = { annotations: [] };

function localText(value: EvidenceAnnotationText | undefined, locale: string): string {
  if (typeof value === "string") return value;
  if (!value) return "";
  return value[locale] ?? value[locale.split("-")[0] ?? ""] ?? value.en ?? Object.values(value)[0] ?? "";
}

function annotationId(segmentId: string): string {
  return `evidence-${segmentId}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
}

export const EvidenceAnnotation = React.forwardRef<HTMLElement, EvidenceAnnotationProps>(function EvidenceAnnotation(
  { definition, state: controlledState, defaultState = EMPTY_STATE, onStateChange, evaluate, onResult, labels, locale = "en", disabled = false, streaming = false, className, ...props },
  ref,
) {
  const text = { ...defaultLabels, ...labels };
  const [internalState, setInternalState] = React.useState(defaultState);
  const [categoryId, setCategoryId] = React.useState(definition?.categories[0]?.id ?? "");
  const [claimId, setClaimId] = React.useState("");
  const [note, setNote] = React.useState("");
  const [evaluation, setEvaluation] = React.useState<EvidenceAnnotationEvaluation>();
  const [submitting, setSubmitting] = React.useState(false);
  const titleId = React.useId();
  const helpId = React.useId();
  const state = controlledState ?? internalState;

  React.useEffect(() => {
    if (definition && !definition.categories.some(({ id }) => id === categoryId)) setCategoryId(definition.categories[0]?.id ?? "");
  }, [categoryId, definition]);

  const commit = React.useCallback((next: EvidenceAnnotationState) => {
    if (controlledState === undefined) setInternalState(next);
    onStateChange?.(next);
    setEvaluation(undefined);
  }, [controlledState, onStateChange]);

  if (!definition) {
    return <section ref={ref} aria-label={text.activity} className={cn("rounded-xl border p-6 text-sm text-muted-foreground", className)} {...props}><p role={streaming ? "status" : undefined}>{streaming ? text.loading : text.empty}</p></section>;
  }

  const findAnnotation = (segmentId: string) => state.annotations.find((item) => item.segmentId === segmentId);
  const toggleSegment = (segment: EvidenceSegment) => {
    if (disabled) return;
    const existing = findAnnotation(segment.id);
    if (existing) {
      commit({ annotations: state.annotations.filter(({ id }) => id !== existing.id) });
      return;
    }
    const quote = localText(segment.text, locale);
    const next: EvidenceAnnotationItem = {
      id: annotationId(segment.id), segmentId: segment.id, start: 0, end: quote.length, quote, categoryId,
      ...(claimId ? { claimId } : {}), ...(note.trim() ? { note: note.trim() } : {}),
    };
    commit({ annotations: [...state.annotations, next] });
    setNote("");
  };
  const submit = async () => {
    if (disabled || submitting || state.annotations.length === 0) return;
    setSubmitting(true);
    try {
      if (!evaluate) { onResult?.({ status: "ungraded", state }); return; }
      const result = await evaluate(state, definition);
      setEvaluation(result); onResult?.({ ...result, state });
    } finally { setSubmitting(false); }
  };

  return (
    <section ref={ref} aria-labelledby={titleId} className={cn("w-full", className)} {...props}>
      <Card>
        <CardHeader className="gap-1">
          <CardTitle><h2 id={titleId}>{localText(definition.title, locale)}</h2></CardTitle>
          {definition.description ? <CardDescription>{localText(definition.description, locale)}</CardDescription> : null}
        </CardHeader>
        <CardContent className="space-y-5">
          {definition.instructions ? <p className="text-sm text-muted-foreground">{localText(definition.instructions, locale)}</p> : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5"><Label htmlFor={`${titleId}-category`}>{text.category}</Label><select id={`${titleId}-category`} className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={categoryId} disabled={disabled} onChange={(event) => setCategoryId(event.target.value)}>{definition.categories.map((category) => <option key={category.id} value={category.id}>{localText(category.label, locale)}</option>)}</select></div>
            {definition.claims?.length ? <div className="space-y-1.5"><Label htmlFor={`${titleId}-claim`}>{text.claim}</Label><select id={`${titleId}-claim`} className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={claimId} disabled={disabled} onChange={(event) => setClaimId(event.target.value)}><option value="">{text.noClaim}</option>{definition.claims.map((claim) => <option key={claim.id} value={claim.id}>{localText(claim.label, locale)}</option>)}</select></div> : null}
          </div>
          <div className="space-y-1.5"><Label htmlFor={`${titleId}-note`}>{text.note}</Label><Input id={`${titleId}-note`} value={note} placeholder={text.notePlaceholder} disabled={disabled} onChange={(event) => setNote(event.target.value)} /></div>

          <article aria-labelledby={`${titleId}-document`} aria-describedby={helpId} className="rounded-lg border bg-background p-5 sm:p-6">
            {definition.documentTitle ? <h3 id={`${titleId}-document`} className="mb-3 text-sm font-semibold">{localText(definition.documentTitle, locale)}</h3> : <span id={`${titleId}-document`} className="sr-only">{text.activity}</span>}
            <p id={helpId} className="mb-4 text-xs text-muted-foreground">{text.readerHelp}</p>
            <div className="text-[15px] leading-8">
              {definition.segments.map((segment) => { const value = localText(segment.text, locale); const selected = Boolean(findAnnotation(segment.id)); return <button key={segment.id} type="button" disabled={disabled} aria-pressed={selected} aria-label={selected ? text.removeEvidence(value) : text.selectEvidence(value)} onClick={() => toggleSegment(segment)} className={cn("mx-0.5 rounded px-1 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2", selected ? "bg-primary/15 underline decoration-primary decoration-2 underline-offset-4" : "hover:bg-muted")}>{value}</button>; })}
            </div>
          </article>

          <details className="rounded-lg border px-4 py-3">
            <summary className="cursor-pointer text-sm font-medium">{text.accessibleSelection}</summary>
            <p className="mt-2 text-xs text-muted-foreground">{text.accessibleHelp}</p>
            <ul className="mt-3 space-y-2">
              {definition.segments.map((segment) => { const value = localText(segment.text, locale); const checked = Boolean(findAnnotation(segment.id)); return <li key={segment.id} className="flex items-start gap-2"><input id={`${titleId}-segment-${segment.id}`} type="checkbox" className="mt-1" checked={checked} disabled={disabled} onChange={() => toggleSegment(segment)} /><Label htmlFor={`${titleId}-segment-${segment.id}`} className="font-normal leading-6">{value}</Label></li>; })}
            </ul>
          </details>

          <div aria-live="polite">
            <h3 className="text-sm font-semibold">{text.annotations}</h3>
            {state.annotations.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">{text.noAnnotations}</p> : <ul className="mt-2 divide-y rounded-lg border">{state.annotations.map((annotation) => {
              const category = definition.categories.find(({ id }) => id === annotation.categoryId);
              const claim = definition.claims?.find(({ id }) => id === annotation.claimId);
              return <li key={annotation.id} className="flex gap-3 p-3"><MdOutlineFormatQuote aria-hidden className="mt-1 shrink-0 text-muted-foreground" /><div className="min-w-0 flex-1"><p className="text-sm">{annotation.quote}</p><p className="mt-1 text-xs text-muted-foreground">{category ? localText(category.label, locale) : annotation.categoryId}{claim ? ` · ${localText(claim.label, locale)}` : ""}</p>{annotation.note ? <p className="mt-1 text-xs">{annotation.note}</p> : null}</div><Button type="button" size="icon" variant="ghost" aria-label={`${text.remove}: ${annotation.quote}`} disabled={disabled} onClick={() => commit({ annotations: state.annotations.filter(({ id }) => id !== annotation.id) })}><MdDeleteOutline aria-hidden /></Button></li>;
            })}</ul>}
          </div>

          {evaluation ? <div role="status" className="rounded-lg border p-3 text-sm"><p className="flex items-center gap-2 font-medium"><MdCheck aria-hidden />{evaluation.status}</p><p className="mt-1 text-muted-foreground">{localText(evaluation.feedback, locale)}</p></div> : null}
          <div className="flex justify-end"><Button type="button" disabled={disabled || submitting || state.annotations.length === 0} onClick={submit}>{submitting ? text.submitting : text.submit}</Button></div>
        </CardContent>
      </Card>
    </section>
  );
});

EvidenceAnnotation.displayName = "EvidenceAnnotation";
