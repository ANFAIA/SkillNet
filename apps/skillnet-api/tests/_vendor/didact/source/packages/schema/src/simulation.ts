import type { LocalizedText, ValidationIssue, ValidationResult } from "./types";

export const SIMULATION_SCHEMA_VERSION = "1.0.0" as const;
export type SimulationValue = string | number | boolean;
export type SimulationValues = Readonly<Record<string, SimulationValue>>;

export interface SimulationParameter {
  readonly id: string;
  readonly label: LocalizedText;
  readonly kind: "number" | "boolean";
  readonly initial: number | boolean;
  readonly min?: number;
  readonly max?: number;
  readonly step?: number;
  readonly unit?: LocalizedText;
}

export interface SimulationStateVariable {
  readonly id: string;
  readonly label: LocalizedText;
  readonly kind: "number" | "boolean" | "string";
  readonly initial: SimulationValue;
  readonly unit?: LocalizedText;
  readonly precision?: number;
}

export interface SimulationActionDefinition {
  readonly id: string;
  readonly label: LocalizedText;
  readonly description?: LocalizedText;
}

export interface SimulationClock {
  readonly mode: "manual" | "continuous";
  readonly stepMs: number;
  readonly maxElapsedMs?: number;
}

export interface SimulationDefinition {
  readonly schemaVersion: typeof SIMULATION_SCHEMA_VERSION;
  readonly id: string;
  readonly title: LocalizedText;
  readonly description?: LocalizedText;
  readonly parameters: readonly SimulationParameter[];
  readonly variables: readonly SimulationStateVariable[];
  readonly actions?: readonly SimulationActionDefinition[];
  readonly clock: SimulationClock;
  readonly snapshots?: { readonly enabled: boolean; readonly max?: number };
}

export interface SimulationSnapshot {
  readonly id: string;
  readonly elapsedMs: number;
  readonly parameters: SimulationValues;
  readonly values: SimulationValues;
}

export interface SimulationState {
  readonly parameters: SimulationValues;
  readonly values: SimulationValues;
  readonly elapsedMs: number;
  readonly running: boolean;
  readonly snapshots: readonly SimulationSnapshot[];
}

export type SimulationEvent =
  | { readonly type: "started" | "paused" | "reset" }
  | { readonly type: "stepped"; readonly deltaMs: number }
  | { readonly type: "parameter-changed"; readonly parameterId: string; readonly value: SimulationValue }
  | { readonly type: "action-performed"; readonly actionId: string }
  | { readonly type: "snapshot-created"; readonly snapshotId: string }
  | { readonly type: "snapshot-restored"; readonly snapshotId: string };

export interface SimulationResult { readonly status: "ungraded"; readonly state: SimulationState }

const ID = /^[a-z0-9]+(?:[.-][a-z0-9]+)*$/;
const record = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const text = (value: unknown): boolean => typeof value === "string" ? value.trim().length > 0 : record(value) && Object.keys(value).length > 0 && Object.values(value).every((entry) => typeof entry === "string" && entry.trim().length > 0);
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const simValue = (value: unknown): value is SimulationValue => typeof value === "string" || typeof value === "boolean" || finite(value);
const add = (issues: ValidationIssue[], path: string, code: string, message: string) => issues.push({ path, code, message, severity: "error" as const });

export function createSimulationInitialState(definition: SimulationDefinition): SimulationState {
  return {
    parameters: Object.fromEntries(definition.parameters.map(({ id, initial }) => [id, initial])),
    values: Object.fromEntries(definition.variables.map(({ id, initial }) => [id, initial])),
    elapsedMs: 0,
    running: false,
    snapshots: [],
  };
}

export function validateSimulationDefinition(input: unknown, options: { mode?: "complete" | "streaming" } = {}): ValidationResult<SimulationDefinition> {
  const issues: ValidationIssue[] = [];
  const complete = options.mode !== "streaming";
  if (!record(input)) return { success: false, issues: [{ path: "$", code: "simulation.object", message: "Simulation must be an object.", severity: "error" }] };
  if (input.schemaVersion !== SIMULATION_SCHEMA_VERSION) add(issues, "schemaVersion", "simulation.version", `schemaVersion must be ${SIMULATION_SCHEMA_VERSION}.`);
  if (typeof input.id !== "string" || !ID.test(input.id)) add(issues, "id", "simulation.id", "id must be stable lowercase identifier.");
  if (complete && !text(input.title)) add(issues, "title", "simulation.title", "title is required.");
  const parameters = Array.isArray(input.parameters) ? input.parameters : [];
  const variables = Array.isArray(input.variables) ? input.variables : [];
  if (!Array.isArray(input.parameters)) add(issues, "parameters", "simulation.parameters", "parameters must be a list.");
  if (!Array.isArray(input.variables)) add(issues, "variables", "simulation.variables", "variables must be a list.");
  if (complete && variables.length === 0) add(issues, "variables", "simulation.variables-empty", "At least one state variable is required.");
  const ids = new Set<string>();
  const validateId = (raw: unknown, path: string) => {
    if (!record(raw)) { add(issues, path, "simulation.field", "Entry must be an object."); return false; }
    if (typeof raw.id !== "string" || !ID.test(raw.id)) add(issues, `${path}.id`, "simulation.field-id", "id is invalid.");
    else if (ids.has(raw.id)) add(issues, `${path}.id`, "simulation.field-duplicate", "Parameter, variable and action ids must be unique."); else ids.add(raw.id);
    if (complete && !text(raw.label)) add(issues, `${path}.label`, "simulation.field-label", "label is required.");
    return true;
  };
  parameters.forEach((raw, index) => {
    const path = `parameters.${index}`; if (!validateId(raw, path) || !record(raw)) return;
    if (raw.kind !== "number" && raw.kind !== "boolean") add(issues, `${path}.kind`, "simulation.parameter-kind", "Parameter kind must be number or boolean.");
    if ((raw.kind === "number" && !finite(raw.initial)) || (raw.kind === "boolean" && typeof raw.initial !== "boolean")) add(issues, `${path}.initial`, "simulation.parameter-initial", "Initial value must match parameter kind.");
    if (raw.kind === "number") {
      if (raw.min !== undefined && !finite(raw.min)) add(issues, `${path}.min`, "simulation.parameter-bound", "min must be finite.");
      if (raw.max !== undefined && !finite(raw.max)) add(issues, `${path}.max`, "simulation.parameter-bound", "max must be finite.");
      if (finite(raw.min) && finite(raw.max) && raw.min >= raw.max) add(issues, path, "simulation.parameter-order", "min must be less than max.");
      if (raw.step !== undefined && (!finite(raw.step) || raw.step <= 0)) add(issues, `${path}.step`, "simulation.parameter-step", "step must be positive.");
    }
  });
  variables.forEach((raw, index) => {
    const path = `variables.${index}`; if (!validateId(raw, path) || !record(raw)) return;
    if (!["number", "boolean", "string"].includes(String(raw.kind))) add(issues, `${path}.kind`, "simulation.variable-kind", "Unknown variable kind.");
    if (!simValue(raw.initial) || typeof raw.initial !== raw.kind) add(issues, `${path}.initial`, "simulation.variable-initial", "Initial value must match variable kind.");
    if (raw.precision !== undefined && (!Number.isInteger(raw.precision) || Number(raw.precision) < 0 || Number(raw.precision) > 10)) add(issues, `${path}.precision`, "simulation.precision", "precision must be an integer from 0 to 10.");
  });
  const actions = Array.isArray(input.actions) ? input.actions : [];
  if (input.actions !== undefined && !Array.isArray(input.actions)) add(issues, "actions", "simulation.actions", "actions must be a list.");
  actions.forEach((raw, index) => validateId(raw, `actions.${index}`));
  if (!record(input.clock)) add(issues, "clock", "simulation.clock", "clock is required.");
  else {
    if (input.clock.mode !== "manual" && input.clock.mode !== "continuous") add(issues, "clock.mode", "simulation.clock-mode", "Clock mode must be manual or continuous.");
    if (!finite(input.clock.stepMs) || input.clock.stepMs <= 0) add(issues, "clock.stepMs", "simulation.clock-step", "stepMs must be positive.");
    if (input.clock.maxElapsedMs !== undefined && (!finite(input.clock.maxElapsedMs) || input.clock.maxElapsedMs <= 0)) add(issues, "clock.maxElapsedMs", "simulation.clock-max", "maxElapsedMs must be positive.");
  }
  if (input.snapshots !== undefined && (!record(input.snapshots) || typeof input.snapshots.enabled !== "boolean")) add(issues, "snapshots", "simulation.snapshots", "snapshots must declare enabled.");
  return issues.length ? { success: false, issues } : { success: true, data: input as unknown as SimulationDefinition, issues };
}

export function validateSimulationState(input: unknown, definition: SimulationDefinition): ValidationResult<SimulationState> {
  const issues: ValidationIssue[] = [];
  if (!record(input)) return { success: false, issues: [{ path: "$", code: "simulation.state", message: "State must be an object.", severity: "error" }] };
  if (!record(input.parameters)) add(issues, "parameters", "simulation.state-parameters", "parameters must be an object.");
  if (!record(input.values)) add(issues, "values", "simulation.state-values", "values must be an object.");
  if (!finite(input.elapsedMs) || input.elapsedMs < 0) add(issues, "elapsedMs", "simulation.state-time", "elapsedMs must be zero or greater.");
  if (typeof input.running !== "boolean") add(issues, "running", "simulation.state-running", "running must be boolean.");
  if (!Array.isArray(input.snapshots)) add(issues, "snapshots", "simulation.state-snapshots", "snapshots must be a list.");
  for (const parameter of definition.parameters) if (!record(input.parameters) || !simValue(input.parameters[parameter.id])) add(issues, `parameters.${parameter.id}`, "simulation.state-parameter", "Parameter is missing or invalid.");
  for (const variable of definition.variables) if (!record(input.values) || !simValue(input.values[variable.id]) || typeof input.values[variable.id] !== variable.kind) add(issues, `values.${variable.id}`, "simulation.state-variable", "Variable is missing or has the wrong kind.");
  return issues.length ? { success: false, issues } : { success: true, data: input as unknown as SimulationState, issues };
}
