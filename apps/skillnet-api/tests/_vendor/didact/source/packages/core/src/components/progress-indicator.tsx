import * as React from "react";
import { Progress } from "@didact/ui";

import { cn } from "../lib/cn.js";

export type ProgressKind = "lesson" | "skill";

export interface ProgressLabels {
  lesson: string;
  skill: string;
  complete: string;
  progressPending: string;
}

const defaultLabels: ProgressLabels = {
  lesson: "Lesson",
  skill: "Skill",
  complete: "complete",
  progressPending: "Progress pending",
};

export interface ProgressEntry {
  id?: string;
  label: React.ReactNode;
  kind: ProgressKind;
  /** Current amount. Omit while the snapshot is still streaming. */
  value?: number;
  /** Total amount; defaults to 100. */
  max?: number;
  description?: React.ReactNode;
}

export interface ProgressIndicatorProps
  extends Omit<React.ComponentPropsWithoutRef<"div">, "children">,
    ProgressEntry {
  labels?: Partial<ProgressLabels>;
}

function normalize(value: number | undefined, max: number | undefined) {
  const safeMax = max !== undefined && Number.isFinite(max) && max > 0 ? max : 100;
  const safeValue = value === undefined ? undefined : Math.max(0, Math.min(safeMax, value));
  const percent = safeValue === undefined ? undefined : Math.round((safeValue / safeMax) * 100);
  return { safeMax, safeValue, percent };
}

/**
 * A static lesson/skill progress snapshot (RF-7). The percentage is always visible text, so the
 * filled bar never carries state through color alone. Missing values render an indeterminate,
 * text-labelled state for streaming consumers rather than inventing zero progress.
 */
export const ProgressIndicator = React.forwardRef<HTMLDivElement, ProgressIndicatorProps>(
  function ProgressIndicator(
    { label, kind, value, max, description, labels, className, id, ...props },
    ref,
  ) {
    const copy = { ...defaultLabels, ...labels };
    const generatedId = React.useId();
    const labelId = id ? `${id}-label` : `${generatedId}-label`;
    const kindId = `${labelId}-kind`;
    const descriptionId = description !== undefined ? `${labelId}-description` : undefined;
    const { safeMax, safeValue, percent } = normalize(value, max);

    return (
      <div
        ref={ref}
        id={id}
        data-slot="progress-indicator"
        data-kind={kind}
        className={cn("grid gap-2", className)}
        {...props}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <span id={kindId} className="sr-only">{copy[kind]}:</span>
            <span id={labelId} className="text-sm font-medium">{label}</span>
            {description !== undefined ? (
              <div id={descriptionId} className="mt-0.5 text-sm text-muted-foreground">{description}</div>
            ) : null}
          </div>
          <span className="shrink-0 text-sm tabular-nums text-muted-foreground">
            {percent === undefined ? copy.progressPending : `${percent}% ${copy.complete}`}
          </span>
        </div>
        <Progress
          value={safeValue ?? null}
          max={safeMax}
          aria-labelledby={`${kindId} ${labelId}`}
          aria-describedby={descriptionId}
          aria-valuetext={percent === undefined ? copy.progressPending : `${percent}% ${copy.complete}`}
        />
      </div>
    );
  },
);

export interface ProgressOverviewProps
  extends Omit<React.ComponentPropsWithoutRef<"ul">, "children"> {
  entries: ProgressEntry[];
  labels?: Partial<ProgressLabels>;
  emptyLabel?: React.ReactNode;
}

/** A named list of lesson and skill progress snapshots. */
export const ProgressOverview = React.forwardRef<HTMLUListElement, ProgressOverviewProps>(
  function ProgressOverview(
    { entries, labels, emptyLabel = "No progress data yet.", className, ...props },
    ref,
  ) {
    return (
      <ul ref={ref} data-slot="progress-overview" className={cn("grid gap-5", className)} {...props}>
        {entries.length === 0 ? (
          <li className="list-none rounded-lg border border-dashed p-4 text-sm text-muted-foreground">{emptyLabel}</li>
        ) : entries.map((entry, index) => (
          <li key={entry.id ?? index} className="list-none">
            <ProgressIndicator {...entry} labels={labels} />
          </li>
        ))}
      </ul>
    );
  },
);
