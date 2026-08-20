import * as React from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  RadioGroup,
  RadioGroupItem,
} from "@didact/ui";

import { cn } from "../lib/cn.js";

/** A performance level that the learner can choose for one criterion. */
export interface RubricLevel {
  /** Stable value reported in the rubric selection. */
  id: string;
  /** Short level name. May arrive after the id when data is streaming. */
  label?: React.ReactNode;
  /** Optional description of what performance at this level looks like. */
  description?: React.ReactNode;
}

/** One independently self-assessed criterion. */
export interface RubricCriterion {
  /** Stable identity used as the key in `value` and `onValueChange`. */
  id: string;
  /** Criterion name. May be omitted while structured content is streaming. */
  label?: React.ReactNode;
  /** Optional explanation or evidence prompt. */
  description?: React.ReactNode;
  /** Levels available for this criterion. An empty/partial list is valid. */
  levels?: RubricLevel[];
  /** Disables this criterion without hiding it. */
  disabled?: boolean;
}

/** Map from criterion id to the learner-selected level id. */
export type RubricValue = Record<string, string>;

/** All embedded UI copy is replaceable for localization (RNF-2). */
export interface RubricLabels {
  rubric: string;
  criterion: (index: number) => string;
  level: (index: number) => string;
  progress: (assessed: number, total: number) => string;
  noCriteria: string;
  levelsPending: string;
}

const defaultLabels: RubricLabels = {
  rubric: "Self-assessment rubric",
  criterion: (index) => `Criterion ${index}`,
  level: (index) => `Level ${index}`,
  progress: (assessed, total) => `${assessed} of ${total} criteria assessed`,
  noCriteria: "No criteria yet.",
  levelsPending: "Levels are not available yet.",
};

export interface RubricProps
  extends Omit<
    React.ComponentPropsWithoutRef<"section">,
    "children" | "defaultValue" | "title"
  > {
  /** Rubric criteria. Empty and partially populated arrays render safely (RNF-4). */
  criteria?: RubricCriterion[];
  /** Optional visible title. An accessible fallback is still supplied when omitted. */
  title?: React.ReactNode;
  /** Optional supporting instructions. */
  description?: React.ReactNode;
  /** Controlled selection map. The component never derives a grade from it. */
  value?: RubricValue;
  /** Initial selections in uncontrolled usage. */
  defaultValue?: RubricValue;
  /** Called with the complete selection map after a learner changes one criterion. */
  onValueChange?: (value: RubricValue) => void;
  /** Disables every level control while preserving the rubric content. */
  disabled?: boolean;
  /** Replace any embedded copy, including functional fallbacks (i18n). */
  labels?: Partial<RubricLabels>;
}

/**
 * A criterion-by-criterion self-assessment rubric (RF-10).
 *
 * Each criterion is a labelled radio group, so arrow-key behavior and selected-state semantics
 * come from `@didact/ui`. Choosing a level only records the learner's own judgement: this
 * component deliberately exposes no score, answer key, weighting, pass/fail result, or automatic
 * grading path. Visible selection text, native `aria-checked`, and the textual progress summary
 * ensure state never depends on color alone. Styling uses theme-backed utilities exclusively.
 */
export const Rubric = React.forwardRef<HTMLElement, RubricProps>(function Rubric(
  {
    criteria = [],
    title,
    description,
    value: valueProp,
    defaultValue = {},
    onValueChange,
    disabled = false,
    labels,
    className,
    "aria-label": ariaLabel,
    "aria-labelledby": ariaLabelledby,
    ...props
  },
  ref,
) {
  const generatedTitleId = React.useId();
  const [internalValue, setInternalValue] = React.useState<RubricValue>(defaultValue);
  const isControlled = valueProp !== undefined;
  const value = valueProp ?? internalValue;
  const copy = { ...defaultLabels, ...labels };
  const assessed = criteria.reduce(
    (count, criterion) => count + (value[criterion.id] !== undefined ? 1 : 0),
    0,
  );

  const choose = (criterionId: string, levelId: string) => {
    const next = { ...value, [criterionId]: levelId };
    if (!isControlled) setInternalValue(next);
    onValueChange?.(next);
  };

  const accessibleTitle =
    ariaLabelledby ?? (title !== undefined ? generatedTitleId : undefined);

  return (
    <section
      ref={ref}
      data-slot="rubric"
      aria-label={ariaLabel ?? (accessibleTitle === undefined ? copy.rubric : undefined)}
      aria-labelledby={accessibleTitle}
      className={cn("w-full", className)}
      {...props}
    >
      <Card>
        {title !== undefined || description !== undefined ? (
          <CardHeader>
            {title !== undefined ? <CardTitle id={generatedTitleId}>{title}</CardTitle> : null}
            {description !== undefined ? (
              <CardDescription>{description}</CardDescription>
            ) : null}
          </CardHeader>
        ) : null}
        <CardContent className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground" aria-live="polite">
            {copy.progress(assessed, criteria.length)}
          </p>

          {criteria.length === 0 ? (
            <p className="rounded-md border p-4 text-sm text-muted-foreground">
              {copy.noCriteria}
            </p>
          ) : (
            <div className="flex flex-col gap-4">
              {criteria.map((criterion, criterionIndex) => {
                const criterionLabel =
                  criterion.label ?? copy.criterion(criterionIndex + 1);
                const criterionId = `${generatedTitleId}-criterion-${criterionIndex}`;
                const levels = criterion.levels ?? [];

                return (
                  <fieldset
                    key={criterion.id}
                    data-slot="rubric-criterion"
                    data-assessed={value[criterion.id] !== undefined ? "true" : "false"}
                    disabled={disabled || criterion.disabled}
                    className="min-w-0 rounded-md border p-4 disabled:opacity-50"
                  >
                    <legend id={criterionId} className="px-1 text-sm font-medium text-foreground">
                      {criterionLabel}
                    </legend>
                    {criterion.description !== undefined ? (
                      <div className="mb-3 text-sm text-muted-foreground">
                        {criterion.description}
                      </div>
                    ) : null}

                    {levels.length === 0 ? (
                      <p className="text-sm text-muted-foreground">{copy.levelsPending}</p>
                    ) : (
                      <RadioGroup
                        value={value[criterion.id] ?? ""}
                        onValueChange={(levelId) => choose(criterion.id, levelId)}
                        disabled={disabled || criterion.disabled}
                        aria-labelledby={criterionId}
                        className="gap-2"
                      >
                        {levels.map((level, levelIndex) => {
                          const levelId = `${criterionId}-level-${levelIndex}`;
                          return (
                            <label
                              key={level.id}
                              htmlFor={levelId}
                              className="flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm has-[[data-disabled]]:cursor-not-allowed"
                            >
                              <RadioGroupItem id={levelId} value={level.id} className="mt-0.5" />
                              <span className="flex min-w-0 flex-col gap-0.5">
                                <span className="font-medium text-foreground">
                                  {level.label ?? copy.level(levelIndex + 1)}
                                </span>
                                {level.description !== undefined ? (
                                  <span className="text-muted-foreground">{level.description}</span>
                                ) : null}
                              </span>
                            </label>
                          );
                        })}
                      </RadioGroup>
                    )}
                  </fieldset>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
});
