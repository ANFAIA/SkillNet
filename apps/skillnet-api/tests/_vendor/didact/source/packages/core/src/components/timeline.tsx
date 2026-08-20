import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "../lib/cn.js";

/**
 * Timeline / Steps (RF-8) -- a sequential process laid out as an ordered list of steps
 * (protocols, step-by-step procedures, wizards). Presentational by design: it renders a snapshot
 * of the process and each step's status, it does not own a "current step" cursor or drive
 * navigation. That matches the SkillNet adapter's static `StepSequence` precedent (`design.md` §5,
 * "FIT -- 1:1 precedent") and keeps it safe for streaming consumers (RNF-4): steps can arrive
 * incrementally and a step can carry just a title, nothing here assumes a complete, all-at-once
 * props payload.
 *
 * Semantics & accessibility:
 * - The container is a real `<ol>` (an ordered sequence IS an ordered list), so assistive tech
 *   announces position ("2 of 5") for free -- the visible step number is therefore decorative
 *   (`aria-hidden`), never the sole carrier of order. Pass `aria-label` (or `aria-labelledby`) to
 *   name the sequence, e.g. "Onboarding steps".
 * - **Status is never color-only** (RF-12 / WCAG 1.4.1). Each step's status is carried three ways
 *   at once: a distinct marker glyph (a check for complete, the number for current/upcoming), a
 *   visually-hidden text label read by screen readers, and -- for the active step -- the standard
 *   `aria-current="step"` on its `<li>`. The primary-tinted fills and connectors only ever
 *   reinforce a state that already stands on its own in text + shape.
 * - No animation, so RF-13 (`prefers-reduced-motion`) is satisfied by construction -- there is
 *   nothing here that moves.
 *
 * i18n (RNF-2): the only embedded strings are the visually-hidden status labels, exposed as a
 * `labels` prop so a consumer can translate them without forking the component. Nothing else in
 * this component hardcodes copy.
 *
 * Composition (docs/interface-norms.md): the step marker and the connector line have no equivalent
 * in `@didact/ui`'s primitive kit (they are not a button/card/badge/toggle), so they are built
 * here -- the norm allows a bespoke element when none of the primitives fit. Everything is still
 * styled through `@didact/theme`'s tokens with the same standard Tailwind utilities the primitives
 * use (`bg-primary`, `text-muted-foreground`, `border`, `bg-border`), never a hardcoded color, so
 * a consumer restyles it by overriding tokens exactly as they would any Didact component.
 */

/** Status of a single step. */
export type TimelineStepStatus = "complete" | "current" | "upcoming";

export interface TimelineStep {
  /** Stable identity for the step; also used as the React key. Falls back to the index. */
  id?: string;
  /** Short, scannable name of the step. */
  title: React.ReactNode;
  /** Optional one-line supporting text under the title. */
  description?: React.ReactNode;
  /** Optional richer body content for the step (rendered below the description). */
  content?: React.ReactNode;
  /**
   * Explicit status. When omitted, it is derived from `currentStep` (see `TimelineProps`): steps
   * before it are `complete`, the step at it is `current`, and later steps are `upcoming`.
   */
  status?: TimelineStepStatus;
  /** Override the marker glyph (defaults to a check for `complete`, else the 1-based number). */
  marker?: React.ReactNode;
}

/** Visually-hidden status labels, exposed for translation (RNF-2). */
export interface TimelineLabels {
  complete: string;
  current: string;
  upcoming: string;
}

const defaultLabels: TimelineLabels = {
  complete: "Completed",
  current: "Current step",
  upcoming: "Upcoming",
};

const timelineVariants = cva("flex list-none", {
  variants: {
    orientation: {
      vertical: "flex-col",
      horizontal: "flex-row",
    },
  },
  defaultVariants: {
    orientation: "vertical",
  },
});

export interface TimelineProps
  extends Omit<React.ComponentPropsWithoutRef<"ol">, "children">,
    VariantProps<typeof timelineVariants> {
  /** The ordered steps. May be rendered while still incomplete (RNF-4). */
  steps: TimelineStep[];
  /**
   * Zero-based index of the current step. Used to derive the status of any step that doesn't set
   * its own `status`: index < current -> complete, index === current -> current, else upcoming.
   * Omit it and set each step's `status` directly to control statuses individually.
   */
  currentStep?: number;
  /** Override the visually-hidden status labels (i18n, RNF-2). */
  labels?: Partial<TimelineLabels>;
}

function CheckIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      <path d="M3 8.5 6.5 12 13 4.5" />
    </svg>
  );
}

/** Resolve a step's status: explicit prop wins, otherwise derive from `currentStep`. */
function resolveStatus(
  step: TimelineStep,
  index: number,
  currentStep: number | undefined,
): TimelineStepStatus {
  if (step.status) return step.status;
  if (currentStep === undefined) return "upcoming";
  if (index < currentStep) return "complete";
  if (index === currentStep) return "current";
  return "upcoming";
}

const markerBase =
  "flex size-8 shrink-0 items-center justify-center rounded-full border text-sm font-medium";

const markerByStatus: Record<TimelineStepStatus, string> = {
  complete: "border-primary bg-primary text-primary-foreground",
  current: "border-2 border-primary bg-background text-primary",
  upcoming: "border-border bg-background text-muted-foreground",
};

export const Timeline = React.forwardRef<HTMLOListElement, TimelineProps>(function Timeline(
  { steps, currentStep, orientation = "vertical", labels, className, ...props },
  ref,
) {
  const resolvedLabels = { ...defaultLabels, ...labels };
  const isVertical = orientation === "vertical";

  return (
    <ol
      ref={ref}
      data-slot="timeline"
      data-orientation={orientation}
      className={cn(timelineVariants({ orientation }), className)}
      {...props}
    >
      {steps.map((step, index) => {
        const status = resolveStatus(step, index, currentStep);
        const isLast = index === steps.length - 1;
        const previousStatus =
          index > 0 ? resolveStatus(steps[index - 1]!, index - 1, currentStep) : undefined;

        const marker = (
          <span className={cn(markerBase, markerByStatus[status])} aria-hidden="true">
            {step.marker ?? (status === "complete" ? <CheckIcon className="size-4" /> : index + 1)}
          </span>
        );

        const body = (
          <>
            {/* Status carried in text for screen readers, independent of the marker's color. */}
            <span className="sr-only">{resolvedLabels[status]}: </span>
            {step.title !== undefined ? (
              <p
                className={cn(
                  "text-sm font-medium",
                  status === "upcoming" ? "text-muted-foreground" : "text-foreground",
                )}
              >
                {step.title}
              </p>
            ) : null}
            {step.description !== undefined ? (
              <p className="text-sm text-muted-foreground">{step.description}</p>
            ) : null}
            {step.content !== undefined ? (
              <div className="mt-1 text-sm text-muted-foreground">{step.content}</div>
            ) : null}
          </>
        );

        if (isVertical) {
          return (
            <li
              key={step.id ?? index}
              data-slot="timeline-item"
              data-status={status}
              aria-current={status === "current" ? "step" : undefined}
              className="flex gap-4 pb-6 last:pb-0"
            >
              {/* Marker column: marker + a connector line that grows to meet the next marker. */}
              <div className="flex flex-col items-center gap-1">
                {marker}
                {!isLast ? (
                  <span
                    aria-hidden="true"
                    className={cn(
                      "w-0.5 flex-1 rounded-full",
                      status === "complete" ? "bg-primary" : "bg-border",
                    )}
                  />
                ) : null}
              </div>
              <div className="flex flex-col gap-0.5 pt-1 pb-1">{body}</div>
            </li>
          );
        }

        return (
          <li
            key={step.id ?? index}
            data-slot="timeline-item"
            data-status={status}
            aria-current={status === "current" ? "step" : undefined}
            className="relative flex flex-1 flex-col items-center gap-2 px-2 text-center last:flex-none"
          >
            {/* Connector into this step, tinted when the previous step is already complete. */}
            {index > 0 ? (
              <span
                aria-hidden="true"
                className={cn(
                  "absolute right-1/2 top-4 h-0.5 w-full -translate-y-1/2 rounded-full",
                  previousStatus === "complete" ? "bg-primary" : "bg-border",
                )}
              />
            ) : null}
            <div className="relative z-10">{marker}</div>
            <div className="flex flex-col gap-0.5">{body}</div>
          </li>
        );
      })}
    </ol>
  );
});
