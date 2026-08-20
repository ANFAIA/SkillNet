import type { LocalizedText, ValidationIssue, ValidationResult } from "./types";

export const DATA_COORDINATE_SCHEMA_VERSION = "1.0.0" as const;

export type DataCoordinateScale = "linear" | "time";
export type DataCoordinateSeriesKind = "line" | "scatter";

export interface LinearDomain {
  readonly scale: "linear";
  readonly min: number;
  readonly max: number;
}

export interface TimeDomain {
  readonly scale: "time";
  /** An ISO-8601 timestamp. */
  readonly min: string;
  /** An ISO-8601 timestamp. */
  readonly max: string;
}

export type DataCoordinateDomain = LinearDomain | TimeDomain;
export type DataCoordinateValue = number | string;

export interface DataCoordinateAxis {
  readonly label: LocalizedText;
  readonly domain: DataCoordinateDomain;
  readonly unit?: LocalizedText;
  readonly tickFormat?: "number" | "percent" | "date" | "datetime";
}

export interface DataCoordinatePointEditability {
  readonly x?: boolean;
  readonly y?: boolean;
}

export interface DataCoordinatePoint {
  readonly id: string;
  readonly x: DataCoordinateValue;
  readonly y: DataCoordinateValue;
  readonly label?: LocalizedText;
  /** Overrides the series-level selection setting for this datum. */
  readonly selectable?: boolean;
  /** Overrides the series-level editability setting for this datum. */
  readonly editable?: DataCoordinatePointEditability;
}

export interface DataCoordinatePointsSource {
  readonly kind: "points";
  readonly points: readonly DataCoordinatePoint[];
}

/**
 * A declarative mathematical function. The schema stores the expression but never
 * evaluates it; hosts choose and secure their own expression engine.
 */
export interface DataCoordinateFunctionSource {
  readonly kind: "function";
  readonly expression: string;
  readonly variable?: string;
  readonly parameters?: Readonly<Record<string, number>>;
  readonly domain?: LinearDomain;
  readonly sampleCount?: number;
}

export type DataCoordinateSeriesSource =
  | DataCoordinatePointsSource
  | DataCoordinateFunctionSource;

export interface DataCoordinateSeries {
  readonly id: string;
  readonly label: LocalizedText;
  readonly kind: DataCoordinateSeriesKind;
  readonly source: DataCoordinateSeriesSource;
  readonly selectable?: boolean;
  readonly editable?: DataCoordinatePointEditability;
}

export interface DataCoordinateTable {
  /** Signals that rows must be derived from `series`, never supplied separately. */
  readonly source: "series";
  readonly caption: LocalizedText;
  readonly includeSeriesIds?: readonly string[];
  readonly showSeriesColumn?: boolean;
}

export interface DataCoordinateInteraction {
  readonly selection?: "none" | "single";
  /** `controlled` lets a host persist zoom/pan through runtime state. */
  readonly viewport?: "fixed" | "controlled";
}

export interface DataCoordinateDefinition {
  readonly schemaVersion: typeof DATA_COORDINATE_SCHEMA_VERSION;
  readonly id: string;
  readonly title: LocalizedText;
  readonly description?: LocalizedText;
  readonly axes: {
    readonly x: DataCoordinateAxis;
    readonly y: DataCoordinateAxis;
  };
  readonly series: readonly DataCoordinateSeries[];
  readonly table: DataCoordinateTable;
  readonly interaction?: DataCoordinateInteraction;
}

export interface DataCoordinateDatumReference {
  readonly seriesId: string;
  readonly datumId: string;
}

export interface DataCoordinatePointOverride extends DataCoordinateDatumReference {
  readonly x?: DataCoordinateValue;
  readonly y?: DataCoordinateValue;
}

export interface DataCoordinateViewport {
  readonly x: DataCoordinateDomain;
  readonly y: DataCoordinateDomain;
}

/** Serializable controlled state; renderers may keep transient gesture state separately. */
export interface DataCoordinateState {
  readonly selectedDatum?: DataCoordinateDatumReference;
  readonly pointOverrides: readonly DataCoordinatePointOverride[];
  readonly viewport?: DataCoordinateViewport;
}

export type DataCoordinateEvent =
  | {
      readonly type: "selection-changed";
      readonly selectedDatum?: DataCoordinateDatumReference;
    }
  | {
      readonly type: "point-overridden";
      readonly override: DataCoordinatePointOverride;
    }
  | {
      readonly type: "viewport-changed";
      readonly viewport: DataCoordinateViewport;
    };

/** This foundation records interaction only. A pedagogical layer may evaluate it. */
export interface DataCoordinateResult {
  readonly status: "ungraded";
  readonly state: DataCoordinateState;
  readonly events?: readonly DataCoordinateEvent[];
}

export interface DataCoordinateValidationOptions {
  readonly mode?: "complete" | "streaming";
}

const IDENTIFIER = /^[a-z0-9]+(?:[.-][a-z0-9]+)*$/;
const VARIABLE = /^[A-Za-z][A-Za-z0-9_]*$/;
const ISO_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?(?:Z|[+-]\d{2}:\d{2})$/;

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function localizedText(value: unknown): boolean {
  if (typeof value === "string") return value.trim().length > 0;
  return record(value)
    && Object.keys(value).length > 0
    && Object.values(value).every((entry) => typeof entry === "string" && entry.trim().length > 0);
}

function identifier(value: unknown): value is string {
  return typeof value === "string" && IDENTIFIER.test(value);
}

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isoTimestamp(value: unknown): value is string {
  return typeof value === "string" && ISO_TIMESTAMP.test(value) && Number.isFinite(Date.parse(value));
}

function add(issues: ValidationIssue[], path: string, code: string, message: string): void {
  issues.push({ path, code, message, severity: "error" });
}

function validateDomain(
  value: unknown,
  path: string,
  issues: ValidationIssue[],
): value is DataCoordinateDomain {
  if (!record(value)) {
    add(issues, path, "data-coordinate.domain", "Domain must be an object.");
    return false;
  }
  if (value.scale === "linear") {
    if (!finite(value.min)) add(issues, `${path}.min`, "data-coordinate.domain-min", "Linear domain min must be finite.");
    if (!finite(value.max)) add(issues, `${path}.max`, "data-coordinate.domain-max", "Linear domain max must be finite.");
    if (finite(value.min) && finite(value.max) && value.min >= value.max) add(issues, path, "data-coordinate.domain-order", "Domain min must be less than max.");
    return finite(value.min) && finite(value.max) && value.min < value.max;
  }
  if (value.scale === "time") {
    if (!isoTimestamp(value.min)) add(issues, `${path}.min`, "data-coordinate.time-min", "Time domain min must be an ISO-8601 timestamp.");
    if (!isoTimestamp(value.max)) add(issues, `${path}.max`, "data-coordinate.time-max", "Time domain max must be an ISO-8601 timestamp.");
    if (isoTimestamp(value.min) && isoTimestamp(value.max) && Date.parse(value.min) >= Date.parse(value.max)) add(issues, path, "data-coordinate.domain-order", "Domain min must be earlier than max.");
    return isoTimestamp(value.min) && isoTimestamp(value.max) && Date.parse(value.min) < Date.parse(value.max);
  }
  add(issues, `${path}.scale`, "data-coordinate.scale", "Scale must be linear or time.");
  return false;
}

function validateCoordinateValue(
  value: unknown,
  domain: DataCoordinateDomain | undefined,
  path: string,
  issues: ValidationIssue[],
): void {
  if (!domain) return;
  if (domain.scale === "linear" && !finite(value)) add(issues, path, "data-coordinate.linear-value", "A linear coordinate must be a finite number.");
  if (domain.scale === "time" && !isoTimestamp(value)) add(issues, path, "data-coordinate.time-value", "A time coordinate must be an ISO-8601 timestamp.");
}

function validateEditability(value: unknown, path: string, issues: ValidationIssue[]): void {
  if (!record(value)) {
    add(issues, path, "data-coordinate.editable", "editable must be an object.");
    return;
  }
  if (value.x !== undefined && typeof value.x !== "boolean") add(issues, `${path}.x`, "data-coordinate.editable-x", "editable.x must be boolean.");
  if (value.y !== undefined && typeof value.y !== "boolean") add(issues, `${path}.y`, "data-coordinate.editable-y", "editable.y must be boolean.");
}

function validateAxis(value: unknown, path: string, issues: ValidationIssue[], complete: boolean): DataCoordinateDomain | undefined {
  if (!record(value)) {
    if (complete) add(issues, path, "data-coordinate.axis", "Axis is required.");
    return undefined;
  }
  if (!localizedText(value.label) && complete) add(issues, `${path}.label`, "data-coordinate.axis-label", "Axis label is required.");
  if (value.unit !== undefined && !localizedText(value.unit)) add(issues, `${path}.unit`, "data-coordinate.axis-unit", "Axis unit must be localized text.");
  if (value.tickFormat !== undefined && !["number", "percent", "date", "datetime"].includes(String(value.tickFormat))) add(issues, `${path}.tickFormat`, "data-coordinate.tick-format", "Unknown tick format.");
  const before = issues.length;
  validateDomain(value.domain, `${path}.domain`, issues);
  return issues.length === before ? value.domain as DataCoordinateDomain : undefined;
}

export function validateDataCoordinateDefinition(
  input: unknown,
  options: DataCoordinateValidationOptions = {},
): ValidationResult<DataCoordinateDefinition> {
  const issues: ValidationIssue[] = [];
  const complete = (options.mode ?? "complete") === "complete";
  if (!record(input)) {
    add(issues, "$", "data-coordinate.object", "Data-coordinate definition must be an object.");
    return { success: false, issues };
  }

  if (input.schemaVersion !== DATA_COORDINATE_SCHEMA_VERSION) add(issues, "schemaVersion", "data-coordinate.version", `schemaVersion must be ${DATA_COORDINATE_SCHEMA_VERSION}.`);
  if (!identifier(input.id)) add(issues, "id", "data-coordinate.id", "id must be a stable lowercase identifier.");
  if (!localizedText(input.title) && complete) add(issues, "title", "data-coordinate.title", "title is required.");
  if (input.description !== undefined && !localizedText(input.description)) add(issues, "description", "data-coordinate.description", "description must be localized text.");

  let xDomain: DataCoordinateDomain | undefined;
  let yDomain: DataCoordinateDomain | undefined;
  if (!record(input.axes)) {
    if (complete) add(issues, "axes", "data-coordinate.axes", "x and y axes are required.");
  } else {
    xDomain = validateAxis(input.axes.x, "axes.x", issues, complete);
    yDomain = validateAxis(input.axes.y, "axes.y", issues, complete);
  }

  const seriesIds = new Set<string>();
  if (!Array.isArray(input.series)) {
    if (complete) add(issues, "series", "data-coordinate.series", "series must be a list.");
  } else {
    if (complete && input.series.length === 0) add(issues, "series", "data-coordinate.series-empty", "At least one series is required.");
    input.series.forEach((candidate, seriesIndex) => {
      const path = `series[${seriesIndex}]`;
      if (!record(candidate)) {
        add(issues, path, "data-coordinate.series-item", "Series must be an object.");
        return;
      }
      if (!identifier(candidate.id)) add(issues, `${path}.id`, "data-coordinate.series-id", "Series id must be stable.");
      else if (seriesIds.has(candidate.id)) add(issues, `${path}.id`, "data-coordinate.series-duplicate", "Series ids must be unique.");
      else seriesIds.add(candidate.id);
      if (!localizedText(candidate.label) && complete) add(issues, `${path}.label`, "data-coordinate.series-label", "Series label is required.");
      if (candidate.kind !== "line" && candidate.kind !== "scatter") add(issues, `${path}.kind`, "data-coordinate.series-kind", "Series kind must be line or scatter.");
      if (candidate.selectable !== undefined && typeof candidate.selectable !== "boolean") add(issues, `${path}.selectable`, "data-coordinate.selectable", "selectable must be boolean.");
      if (candidate.editable !== undefined) validateEditability(candidate.editable, `${path}.editable`, issues);

      if (!record(candidate.source)) {
        if (complete) add(issues, `${path}.source`, "data-coordinate.source", "Series source is required.");
        return;
      }
      if (candidate.source.kind === "points") {
        if (!Array.isArray(candidate.source.points)) add(issues, `${path}.source.points`, "data-coordinate.points", "points must be a list.");
        else {
          if (complete && candidate.source.points.length === 0) add(issues, `${path}.source.points`, "data-coordinate.points-empty", "A point series requires at least one point.");
          const pointIds = new Set<string>();
          candidate.source.points.forEach((point, pointIndex) => {
            const pointPath = `${path}.source.points[${pointIndex}]`;
            if (!record(point)) {
              add(issues, pointPath, "data-coordinate.point", "Point must be an object.");
              return;
            }
            if (!identifier(point.id)) add(issues, `${pointPath}.id`, "data-coordinate.point-id", "Point id must be stable.");
            else if (pointIds.has(point.id)) add(issues, `${pointPath}.id`, "data-coordinate.point-duplicate", "Point ids must be unique within a series.");
            else pointIds.add(point.id);
            validateCoordinateValue(point.x, xDomain, `${pointPath}.x`, issues);
            validateCoordinateValue(point.y, yDomain, `${pointPath}.y`, issues);
            if (point.label !== undefined && !localizedText(point.label)) add(issues, `${pointPath}.label`, "data-coordinate.point-label", "Point label must be localized text.");
            if (point.selectable !== undefined && typeof point.selectable !== "boolean") add(issues, `${pointPath}.selectable`, "data-coordinate.selectable", "selectable must be boolean.");
            if (point.editable !== undefined) validateEditability(point.editable, `${pointPath}.editable`, issues);
          });
        }
      } else if (candidate.source.kind === "function") {
        if (xDomain?.scale === "time" || yDomain?.scale === "time") add(issues, `${path}.source`, "data-coordinate.function-scale", "Function series require linear x and y axes.");
        if ((typeof candidate.source.expression !== "string" || candidate.source.expression.trim().length === 0) && complete) add(issues, `${path}.source.expression`, "data-coordinate.expression", "Function expression is required.");
        if (candidate.source.variable !== undefined && (typeof candidate.source.variable !== "string" || !VARIABLE.test(candidate.source.variable))) add(issues, `${path}.source.variable`, "data-coordinate.variable", "Function variable must be a valid identifier.");
        if (candidate.source.parameters !== undefined) {
          if (!record(candidate.source.parameters) || Object.entries(candidate.source.parameters).some(([key, value]) => !VARIABLE.test(key) || !finite(value))) add(issues, `${path}.source.parameters`, "data-coordinate.parameters", "Function parameters must map identifiers to finite numbers.");
        }
        if (candidate.source.domain !== undefined) {
          const functionDomainPath = `${path}.source.domain`;
          if (!record(candidate.source.domain) || candidate.source.domain.scale !== "linear") add(issues, functionDomainPath, "data-coordinate.function-domain", "Function domain must be linear.");
          else validateDomain(candidate.source.domain, functionDomainPath, issues);
        }
        if (candidate.source.sampleCount !== undefined && (!Number.isInteger(candidate.source.sampleCount) || Number(candidate.source.sampleCount) < 2 || Number(candidate.source.sampleCount) > 10_000)) add(issues, `${path}.source.sampleCount`, "data-coordinate.sample-count", "sampleCount must be an integer between 2 and 10000.");
      } else add(issues, `${path}.source.kind`, "data-coordinate.source-kind", "Source kind must be points or function.");
    });
  }

  if (!record(input.table)) {
    if (complete) add(issues, "table", "data-coordinate.table", "An equivalent table configuration is required.");
  } else {
    if (input.table.source !== "series") add(issues, "table.source", "data-coordinate.table-source", "Table rows must derive from series.");
    if (!localizedText(input.table.caption) && complete) add(issues, "table.caption", "data-coordinate.table-caption", "Table caption is required.");
    if (input.table.showSeriesColumn !== undefined && typeof input.table.showSeriesColumn !== "boolean") add(issues, "table.showSeriesColumn", "data-coordinate.table-series-column", "showSeriesColumn must be boolean.");
    if (input.table.includeSeriesIds !== undefined) {
      if (!Array.isArray(input.table.includeSeriesIds)) add(issues, "table.includeSeriesIds", "data-coordinate.table-series", "includeSeriesIds must be a list.");
      else {
        const included = new Set<string>();
        input.table.includeSeriesIds.forEach((id, index) => {
          const path = `table.includeSeriesIds[${index}]`;
          if (!identifier(id)) add(issues, path, "data-coordinate.table-series-id", "Included series id must be stable.");
          else if (included.has(id)) add(issues, path, "data-coordinate.table-series-duplicate", "Included series ids must be unique.");
          else if (Array.isArray(input.series) && !seriesIds.has(id)) add(issues, path, "data-coordinate.table-series-missing", "Included series id does not exist.");
          included.add(String(id));
        });
      }
    }
  }

  if (input.interaction !== undefined) {
    if (!record(input.interaction)) add(issues, "interaction", "data-coordinate.interaction", "interaction must be an object.");
    else {
      if (input.interaction.selection !== undefined && !["none", "single"].includes(String(input.interaction.selection))) add(issues, "interaction.selection", "data-coordinate.selection", "selection must be none or single.");
      if (input.interaction.viewport !== undefined && !["fixed", "controlled"].includes(String(input.interaction.viewport))) add(issues, "interaction.viewport", "data-coordinate.viewport-mode", "viewport must be fixed or controlled.");
    }
  }

  return issues.length > 0
    ? { success: false, issues }
    : { success: true, data: input as unknown as DataCoordinateDefinition, issues };
}

function validateReference(
  value: unknown,
  path: string,
  issues: ValidationIssue[],
  requireOverride: boolean,
): void {
  if (!record(value)) {
    add(issues, path, "data-coordinate.reference", "Datum reference must be an object.");
    return;
  }
  if (!identifier(value.seriesId)) add(issues, `${path}.seriesId`, "data-coordinate.reference-series", "seriesId must be stable.");
  if (!identifier(value.datumId)) add(issues, `${path}.datumId`, "data-coordinate.reference-datum", "datumId must be stable.");
  if (value.x !== undefined && !(finite(value.x) || isoTimestamp(value.x))) add(issues, `${path}.x`, "data-coordinate.override-x", "Override x must be a finite number or ISO timestamp.");
  if (value.y !== undefined && !(finite(value.y) || isoTimestamp(value.y))) add(issues, `${path}.y`, "data-coordinate.override-y", "Override y must be a finite number or ISO timestamp.");
  if (requireOverride && value.x === undefined && value.y === undefined) add(issues, path, "data-coordinate.override-empty", "Point override must change x or y.");
}

function validateViewport(value: unknown, path: string, issues: ValidationIssue[]): void {
  if (!record(value)) {
    add(issues, path, "data-coordinate.viewport", "Viewport must be an object.");
    return;
  }
  validateDomain(value.x, `${path}.x`, issues);
  validateDomain(value.y, `${path}.y`, issues);
}

export function validateDataCoordinateState(input: unknown): ValidationResult<DataCoordinateState> {
  const issues: ValidationIssue[] = [];
  if (!record(input)) {
    add(issues, "$", "data-coordinate.state", "State must be an object.");
    return { success: false, issues };
  }
  if (input.selectedDatum !== undefined) validateReference(input.selectedDatum, "selectedDatum", issues, false);
  if (!Array.isArray(input.pointOverrides)) add(issues, "pointOverrides", "data-coordinate.overrides", "pointOverrides must be a list.");
  else {
    const keys = new Set<string>();
    input.pointOverrides.forEach((override, index) => {
      const path = `pointOverrides[${index}]`;
      validateReference(override, path, issues, true);
      if (record(override) && typeof override.seriesId === "string" && typeof override.datumId === "string") {
        const key = `${override.seriesId}\u0000${override.datumId}`;
        if (keys.has(key)) add(issues, path, "data-coordinate.override-duplicate", "A datum may have only one override.");
        keys.add(key);
      }
    });
  }
  if (input.viewport !== undefined) validateViewport(input.viewport, "viewport", issues);
  return issues.length > 0
    ? { success: false, issues }
    : { success: true, data: input as unknown as DataCoordinateState, issues };
}

export function validateDataCoordinateResult(input: unknown): ValidationResult<DataCoordinateResult> {
  const issues: ValidationIssue[] = [];
  if (!record(input)) {
    add(issues, "$", "data-coordinate.result", "Result must be an object.");
    return { success: false, issues };
  }
  if (input.status !== "ungraded") add(issues, "status", "data-coordinate.result-status", "Foundation results must remain ungraded.");
  const stateResult = validateDataCoordinateState(input.state);
  stateResult.issues.forEach((issue) => issues.push({ ...issue, path: `state.${issue.path}` }));
  if (input.events !== undefined) {
    if (!Array.isArray(input.events)) add(issues, "events", "data-coordinate.events", "events must be a list.");
    else input.events.forEach((event, index) => {
      const path = `events[${index}]`;
      if (!record(event)) {
        add(issues, path, "data-coordinate.event", "Event must be an object.");
        return;
      }
      if (event.type === "selection-changed") {
        if (event.selectedDatum !== undefined) validateReference(event.selectedDatum, `${path}.selectedDatum`, issues, false);
      } else if (event.type === "point-overridden") validateReference(event.override, `${path}.override`, issues, true);
      else if (event.type === "viewport-changed") validateViewport(event.viewport, `${path}.viewport`, issues);
      else add(issues, `${path}.type`, "data-coordinate.event-type", "Unknown event type.");
    });
  }
  return issues.length > 0
    ? { success: false, issues }
    : { success: true, data: input as unknown as DataCoordinateResult, issues };
}
