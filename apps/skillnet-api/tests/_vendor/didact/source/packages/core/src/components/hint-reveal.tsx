import * as React from "react";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@didact/ui";

import { cn } from "../lib/cn.js";

/** Localizable interface copy used by Hint and Reveal (RNF-2). */
export interface HintRevealLabels {
  title: string;
  description: string;
  nextHint: string;
  hint: (position: number, total: number) => string;
  revealSolution: string;
  hideSolution: string;
  solution: string;
  contentPending: string;
}

const defaultLabels: HintRevealLabels = {
  title: "Need a hint?",
  description: "Reveal one clue at a time before looking at the solution.",
  nextHint: "Show next hint",
  hint: (position, total) => `Hint ${position} of ${total}`,
  revealSolution: "Reveal solution",
  hideSolution: "Hide solution",
  solution: "Solution",
  contentPending: "Content is still loading.",
};

function useControllable<T>(
  controlled: T | undefined,
  defaultValue: T,
  onChange?: (value: T) => void,
): [T, (value: T) => void] {
  const isControlled = controlled !== undefined;
  const [uncontrolled, setUncontrolled] = React.useState(defaultValue);
  const value = isControlled ? controlled : uncontrolled;
  const setValue = React.useCallback(
    (next: T) => {
      if (!isControlled) setUncontrolled(next);
      onChange?.(next);
    },
    [isControlled, onChange],
  );
  return [value, setValue];
}

export interface RevealProps
  extends Omit<React.ComponentPropsWithoutRef<"div">, "children" | "onChange"> {
  /** Content is not mounted until the learner explicitly reveals it (RF-6). */
  children?: React.ReactNode;
  /** Controlled disclosure state. */
  revealed?: boolean;
  /** Initial disclosure state for uncontrolled usage. */
  defaultRevealed?: boolean;
  /** Called for both reveal and hide requests. */
  onRevealedChange?: (revealed: boolean) => void;
  /** Visible trigger copy; pass translated text as needed. */
  revealLabel?: React.ReactNode;
  /** Visible trigger copy once open; pass translated text as needed. */
  hideLabel?: React.ReactNode;
  /** Accessible label for the revealed region. */
  contentLabel?: string;
  /** Whether the learner may remove the revealed content from the DOM again. */
  hideable?: boolean;
  /** Button hierarchy may be adjusted when Reveal is composed into another view. */
  buttonVariant?: React.ComponentProps<typeof Button>["variant"];
}

/**
 * A controlled/uncontrolled disclosure whose protected content is structurally absent before the
 * learner requests it. This is deliberately conditional rendering, not CSS hiding.
 */
export const Reveal = React.forwardRef<HTMLDivElement, RevealProps>(function Reveal(
  {
    children,
    revealed: revealedProp,
    defaultRevealed = false,
    onRevealedChange,
    revealLabel = defaultLabels.revealSolution,
    hideLabel = defaultLabels.hideSolution,
    contentLabel = defaultLabels.solution,
    hideable = true,
    buttonVariant = "default",
    className,
    ...props
  },
  ref,
) {
  const [revealed, setRevealed] = useControllable(
    revealedProp,
    defaultRevealed,
    onRevealedChange,
  );
  const contentId = React.useId();
  const hasContent = children !== undefined;

  return (
    <div ref={ref} data-slot="reveal" data-state={revealed ? "open" : "closed"} className={cn("flex flex-col gap-3", className)} {...props}>
      {revealed && hasContent ? (
        <div
          id={contentId}
          role="region"
          aria-label={contentLabel}
          aria-live="polite"
          data-slot="reveal-content"
          className="rounded-md border bg-muted p-4 text-sm leading-relaxed text-foreground"
        >
          {children}
        </div>
      ) : null}
      {(!revealed || hideable) ? (
        <Button
          type="button"
          variant={revealed ? "outline" : buttonVariant}
          aria-expanded={revealed}
          aria-controls={revealed && hasContent ? contentId : undefined}
          disabled={!hasContent}
          onClick={() => setRevealed(!revealed)}
        >
          {revealed ? hideLabel : revealLabel}
        </Button>
      ) : null}
    </div>
  );
});

export interface HintProps
  extends Omit<React.ComponentPropsWithoutRef<"div">, "children" | "title"> {
  /** Hints in pedagogical order. Undefined entries are safely ignored while content streams. */
  hints?: Array<React.ReactNode | undefined>;
  /** Protected answer; remains absent from the DOM until explicitly requested. */
  solution?: React.ReactNode;
  /** Optional explanation or strategy, shown only with the solution. */
  feedback?: React.ReactNode;
  /** Controlled number of visible hints. */
  revealedHintCount?: number;
  /** Initial number of visible hints for uncontrolled usage. */
  defaultRevealedHintCount?: number;
  /** Notifies whenever the learner asks for another hint. */
  onRevealedHintCountChange?: (count: number) => void;
  /** Controlled solution state. */
  solutionRevealed?: boolean;
  /** Initial solution state for uncontrolled usage. */
  defaultSolutionRevealed?: boolean;
  /** Notifies whenever the learner reveals or hides the solution. */
  onSolutionRevealedChange?: (revealed: boolean) => void;
  /** Optional title override. */
  heading?: React.ReactNode;
  /** Optional supporting copy override. */
  description?: React.ReactNode;
  /** Framework-agnostic localization extension point. */
  labels?: Partial<HintRevealLabels>;
}

/** Progressive hints followed by an optional, hideable solution (RF-6). */
export const Hint = React.forwardRef<HTMLDivElement, HintProps>(function Hint(
  {
    hints = [],
    solution,
    feedback,
    revealedHintCount: revealedHintCountProp,
    defaultRevealedHintCount = 0,
    onRevealedHintCountChange,
    solutionRevealed: solutionRevealedProp,
    defaultSolutionRevealed = false,
    onSolutionRevealedChange,
    heading,
    description,
    labels,
    className,
    ...props
  },
  ref,
) {
  const copy = { ...defaultLabels, ...labels };
  const availableHints = hints.filter((hint) => hint !== undefined);
  const [requestedHintCount, setRequestedHintCount] = useControllable(
    revealedHintCountProp,
    defaultRevealedHintCount,
    onRevealedHintCountChange,
  );
  const [solutionRevealed, setSolutionRevealed] = useControllable(
    solutionRevealedProp,
    defaultSolutionRevealed,
    onSolutionRevealedChange,
  );
  const visibleHintCount = Math.max(0, Math.min(requestedHintCount, availableHints.length));
  const canRevealHint = visibleHintCount < availableHints.length;
  const hasVisibleContent =
    visibleHintCount > 0 ||
    (solutionRevealed && solution !== undefined) ||
    (availableHints.length === 0 && solution === undefined);
  const titleId = React.useId();
  const hintsId = React.useId();

  return (
    <Card ref={ref} data-slot="hint" role="region" className={cn("w-full max-w-md", className)} aria-labelledby={titleId} {...props}>
      <CardHeader>
        <CardTitle id={titleId}>{heading ?? copy.title}</CardTitle>
        <CardDescription>{description ?? copy.description}</CardDescription>
      </CardHeader>
      {hasVisibleContent ? <CardContent className="flex flex-col gap-4">
        {visibleHintCount > 0 ? (
          <ol id={hintsId} aria-live="polite" className="flex list-none flex-col gap-3">
            {availableHints.slice(0, visibleHintCount).map((hint, index) => (
              <li key={index} className="rounded-md border bg-muted p-3 text-sm leading-relaxed">
                <p className="mb-1 text-xs font-medium text-muted-foreground">
                  {copy.hint(index + 1, availableHints.length)}
                </p>
                <div>{hint}</div>
              </li>
            ))}
          </ol>
        ) : null}

        {solutionRevealed && solution !== undefined ? (
          <div
            role="region"
            aria-label={copy.solution}
            aria-live="polite"
            data-slot="hint-solution"
            className="rounded-md border bg-muted p-4 text-sm leading-relaxed"
          >
            {solution}
            {feedback !== undefined ? (
              <div className="mt-3 border-t pt-3 text-muted-foreground">{feedback}</div>
            ) : null}
          </div>
        ) : null}

        {availableHints.length === 0 && solution === undefined ? (
          <p className="text-sm text-muted-foreground">{copy.contentPending}</p>
        ) : null}
      </CardContent> : null}
      {(canRevealHint || solution !== undefined) ? (
        <CardFooter className="flex flex-wrap gap-2">
          {canRevealHint ? (
            <Button
              type="button"
              aria-expanded={visibleHintCount > 0}
              aria-controls={visibleHintCount > 0 ? hintsId : undefined}
              onClick={() => setRequestedHintCount(visibleHintCount + 1)}
            >
              {copy.nextHint}
            </Button>
          ) : null}
          {solution !== undefined ? (
            <Button
              type="button"
              variant={canRevealHint || solutionRevealed ? "outline" : "default"}
              aria-expanded={solutionRevealed}
              onClick={() => setSolutionRevealed(!solutionRevealed)}
            >
              {solutionRevealed ? copy.hideSolution : copy.revealSolution}
            </Button>
          ) : null}
        </CardFooter>
      ) : null}
    </Card>
  );
});

/** Descriptive alias for consumers who prefer the full component name. */
export const HintReveal = Hint;
