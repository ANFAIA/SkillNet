import * as React from "react";
import { Button, Popover, PopoverContent, PopoverTrigger } from "@didact/ui";

import { cn } from "../lib/cn.js";

/** One portable glossary entry. Fields may arrive incrementally for streaming consumers (RNF-4). */
export interface GlossaryEntry {
  /** Stable identity used as the React key. Falls back to the term text. */
  id?: string;
  /** The vocabulary item shown as the popover trigger. */
  term: string;
  /** Definition revealed without navigating away from the current content (RF-5). */
  definition?: React.ReactNode;
  /** Optional example or supporting content shown after the definition. */
  example?: React.ReactNode;
  /** Optional active-recall prompt shown before the learner reveals the definition. */
  recallPrompt?: React.ReactNode;
}

export interface TermLabels {
  definition: string;
  revealDefinition: string;
  definitionPending: string;
}

const defaultLabels: TermLabels = {
  definition: "Definition",
  revealDefinition: "Reveal definition",
  definitionPending: "Definition not available yet.",
};

export interface TermProps
  extends Omit<React.ComponentPropsWithoutRef<"button">, "children" | "onChange">,
    Omit<GlossaryEntry, "id"> {
  /** Controlled popover state. */
  open?: boolean;
  /** Initial state when uncontrolled. */
  defaultOpen?: boolean;
  /** Notified whenever the popover opens or closes. */
  onOpenChange?: (open: boolean) => void;
  /** Override embedded UI copy for localization (RNF-2). */
  labels?: Partial<TermLabels>;
  /** Classes for the anchored popover surface. */
  contentClassName?: string;
}

/**
 * Inline glossary term (RF-5). Activation opens an anchored popover rather than navigating away.
 * A supplied `recallPrompt` intentionally adds a reveal step: the definition is not mounted until
 * requested, turning passive lookup into an optional active-recall moment. Radix supplies keyboard
 * operation, Escape/outside dismissal, collision avoidance and focus restoration. The content uses
 * `side="top"` by default so it cannot cover the focused trigger below it (WCAG 2.4.11).
 */
export const Term = React.forwardRef<HTMLButtonElement, TermProps>(function Term(
  {
    term,
    definition,
    example,
    recallPrompt,
    open,
    defaultOpen,
    onOpenChange,
    labels,
    className,
    contentClassName,
    ...props
  },
  ref,
) {
  const copy = { ...defaultLabels, ...labels };
  const [revealed, setRevealed] = React.useState(recallPrompt === undefined);

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen && recallPrompt !== undefined) setRevealed(false);
    onOpenChange?.(nextOpen);
  }

  return (
    <Popover open={open} defaultOpen={defaultOpen} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <button
          ref={ref}
          type="button"
          data-slot="term"
          className={cn(
            "inline rounded-sm font-medium text-foreground underline decoration-border decoration-dotted underline-offset-4 transition-colors hover:decoration-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring motion-reduce:transition-none",
            className,
          )}
          {...props}
        >
          {term}
        </button>
      </PopoverTrigger>
      <PopoverContent
        data-slot="term-content"
        side="top"
        align="start"
        aria-label={`${copy.definition}: ${term}`}
        className={cn("w-80", contentClassName)}
      >
        <div className="flex flex-col gap-3">
          <div>
            <p className="text-sm font-semibold">{term}</p>
            {recallPrompt !== undefined && !revealed ? (
              <div className="mt-1 text-sm text-muted-foreground">{recallPrompt}</div>
            ) : (
              <div className="mt-1 text-sm leading-relaxed">
                {definition ?? <span className="text-muted-foreground">{copy.definitionPending}</span>}
              </div>
            )}
          </div>

          {recallPrompt !== undefined && !revealed ? (
            <Button type="button" size="sm" onClick={() => setRevealed(true)}>
              {copy.revealDefinition}
            </Button>
          ) : example !== undefined ? (
            <div className="border-t pt-3 text-sm text-muted-foreground">{example}</div>
          ) : null}
        </div>
      </PopoverContent>
    </Popover>
  );
});

export interface GlossaryProps
  extends Omit<React.ComponentPropsWithoutRef<"ul">, "children"> {
  /** Entries may be partial while structured content streams in (RNF-4). */
  entries: GlossaryEntry[];
  /** Labels passed to every Term. */
  labels?: Partial<TermLabels>;
  /** Visible empty-state copy; pass translated text as needed. */
  emptyLabel?: React.ReactNode;
}

/** A compact, named list whose terms reveal their definitions in-place. */
export const Glossary = React.forwardRef<HTMLUListElement, GlossaryProps>(function Glossary(
  { entries, labels, emptyLabel = "No glossary terms yet.", className, ...props },
  ref,
) {
  return (
    <ul
      ref={ref}
      data-slot="glossary"
      className={cn("grid gap-3", className)}
      {...props}
    >
      {entries.length === 0 ? (
        <li className="list-none rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
          {emptyLabel}
        </li>
      ) : (
        entries.map((entry) => (
          <li key={entry.id ?? entry.term} className="flex items-baseline justify-between gap-4 border-b pb-3 last:border-b-0 last:pb-0">
            <Term {...entry} labels={labels} />
            <span aria-hidden="true" className="text-xs text-muted-foreground">
              {labels?.definition ?? defaultLabels.definition}
            </span>
          </li>
        ))
      )}
    </ul>
  );
});
