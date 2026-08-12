import type { LocalizedText, ValidationIssue, ValidationResult } from "./types";

export const DECISION_GRAPH_SCHEMA_VERSION = "1.0.0" as const;

export type DecisionValue = string | number | boolean | null;
export type DecisionVariables = Readonly<Record<string, DecisionValue>>;

export interface DecisionCondition {
  readonly variable: string;
  readonly operator: "equals" | "not-equals" | "greater-than" | "greater-or-equal" | "less-than" | "less-or-equal" | "truthy";
  readonly value?: DecisionValue;
}

export interface DecisionEffect {
  readonly variable: string;
  readonly operation: "set" | "increment" | "toggle";
  readonly value?: DecisionValue;
}

export interface DecisionChoice {
  readonly id: string;
  readonly label: LocalizedText;
  readonly targetNodeId: string;
  readonly condition?: DecisionCondition;
  readonly effects?: readonly DecisionEffect[];
  readonly consequence?: LocalizedText;
}

export interface DecisionOutcome {
  readonly status: "completed" | "failed" | "neutral";
  readonly label: LocalizedText;
  readonly feedback?: LocalizedText;
}

export interface DecisionNode {
  readonly id: string;
  readonly kind: "content" | "decision" | "outcome";
  readonly title?: LocalizedText;
  readonly body: LocalizedText;
  readonly choices?: readonly DecisionChoice[];
  readonly outcome?: DecisionOutcome;
}

export interface DecisionGraphDefinition {
  readonly schemaVersion: typeof DECISION_GRAPH_SCHEMA_VERSION;
  readonly id: string;
  readonly title: LocalizedText;
  readonly description?: LocalizedText;
  readonly startNodeId: string;
  readonly initialVariables?: DecisionVariables;
  readonly nodes: readonly DecisionNode[];
  readonly navigation?: { readonly allowBacktrack?: boolean; readonly allowRestart?: boolean };
}

export interface DecisionHistoryEntry {
  readonly fromNodeId: string;
  readonly choiceId: string;
  readonly toNodeId: string;
  readonly variablesBefore: DecisionVariables;
}

export interface DecisionGraphState {
  readonly currentNodeId: string;
  readonly variables: DecisionVariables;
  readonly history: readonly DecisionHistoryEntry[];
}

export type DecisionGraphEvent =
  | { readonly type: "choice-selected"; readonly choiceId: string; readonly fromNodeId: string; readonly toNodeId: string }
  | { readonly type: "backtracked"; readonly toNodeId: string }
  | { readonly type: "restarted"; readonly toNodeId: string }
  | { readonly type: "outcome-reached"; readonly nodeId: string; readonly outcome: DecisionOutcome["status"] };

export interface DecisionGraphResult {
  readonly status: "in-progress" | DecisionOutcome["status"];
  readonly state: DecisionGraphState;
}

const ID = /^[a-z0-9]+(?:[.-][a-z0-9]+)*$/;
const VARIABLE = /^[A-Za-z][A-Za-z0-9_.-]*$/;
const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const isText = (value: unknown): boolean => typeof value === "string" ? value.trim().length > 0 : isRecord(value) && Object.keys(value).length > 0 && Object.values(value).every((entry) => typeof entry === "string" && entry.trim().length > 0);
const isValue = (value: unknown): value is DecisionValue => value === null || ["string", "number", "boolean"].includes(typeof value) && (typeof value !== "number" || Number.isFinite(value));
const issue = (issues: ValidationIssue[], path: string, code: string, message: string) => issues.push({ path, code, message, severity: "error" as const });

function validateCondition(value: unknown, path: string, issues: ValidationIssue[], variables: Set<string>): void {
  if (!isRecord(value)) { issue(issues, path, "decision.condition", "Condition must be an object."); return; }
  if (typeof value.variable !== "string" || !VARIABLE.test(value.variable)) issue(issues, `${path}.variable`, "decision.variable", "Condition variable is invalid.");
  else if (!variables.has(value.variable)) issue(issues, `${path}.variable`, "decision.variable-reference", "Condition references an undeclared variable.");
  const operators = ["equals", "not-equals", "greater-than", "greater-or-equal", "less-than", "less-or-equal", "truthy"];
  if (!operators.includes(String(value.operator))) issue(issues, `${path}.operator`, "decision.operator", "Unknown condition operator.");
  if (value.operator !== "truthy" && !isValue(value.value)) issue(issues, `${path}.value`, "decision.condition-value", "Condition value is required and must be JSON-safe.");
}

function validateEffect(value: unknown, path: string, issues: ValidationIssue[], variables: Set<string>): void {
  if (!isRecord(value)) { issue(issues, path, "decision.effect", "Effect must be an object."); return; }
  if (typeof value.variable !== "string" || !VARIABLE.test(value.variable)) issue(issues, `${path}.variable`, "decision.variable", "Effect variable is invalid.");
  else if (!variables.has(value.variable)) issue(issues, `${path}.variable`, "decision.variable-reference", "Effect references an undeclared variable.");
  if (!["set", "increment", "toggle"].includes(String(value.operation))) issue(issues, `${path}.operation`, "decision.effect-operation", "Unknown effect operation.");
  if (value.operation === "set" && !isValue(value.value)) issue(issues, `${path}.value`, "decision.effect-value", "Set requires a JSON-safe value.");
  if (value.operation === "increment" && (typeof value.value !== "number" || !Number.isFinite(value.value))) issue(issues, `${path}.value`, "decision.effect-number", "Increment requires a finite number.");
}

export function validateDecisionGraphDefinition(input: unknown, options: { mode?: "complete" | "streaming" } = {}): ValidationResult<DecisionGraphDefinition> {
  const issues: ValidationIssue[] = [];
  const complete = options.mode !== "streaming";
  if (!isRecord(input)) return { success: false, issues: [{ path: "$", code: "decision.object", message: "Decision graph must be an object.", severity: "error" }] };
  if (input.schemaVersion !== DECISION_GRAPH_SCHEMA_VERSION) issue(issues, "schemaVersion", "decision.version", `schemaVersion must be ${DECISION_GRAPH_SCHEMA_VERSION}.`);
  if (typeof input.id !== "string" || !ID.test(input.id)) issue(issues, "id", "decision.id", "id must be stable lowercase identifier.");
  if (complete && !isText(input.title)) issue(issues, "title", "decision.title", "title is required.");
  const variables = new Set<string>();
  if (input.initialVariables !== undefined && !isRecord(input.initialVariables)) issue(issues, "initialVariables", "decision.variables", "initialVariables must be an object.");
  else if (isRecord(input.initialVariables)) for (const [name, value] of Object.entries(input.initialVariables)) {
    if (!VARIABLE.test(name)) issue(issues, `initialVariables.${name}`, "decision.variable", "Variable name is invalid."); else variables.add(name);
    if (!isValue(value)) issue(issues, `initialVariables.${name}`, "decision.variable-value", "Variable value must be JSON-safe.");
  }
  const nodes = Array.isArray(input.nodes) ? input.nodes : [];
  if (!Array.isArray(input.nodes)) issue(issues, "nodes", "decision.nodes", "nodes must be a list.");
  if (complete && nodes.length === 0) issue(issues, "nodes", "decision.nodes-empty", "At least one node is required.");
  const nodeIds = new Set<string>();
  for (const [index, raw] of nodes.entries()) {
    const path = `nodes.${index}`;
    if (!isRecord(raw)) { issue(issues, path, "decision.node", "Node must be an object."); continue; }
    if (typeof raw.id !== "string" || !ID.test(raw.id)) issue(issues, `${path}.id`, "decision.node-id", "Node id is invalid.");
    else if (nodeIds.has(raw.id)) issue(issues, `${path}.id`, "decision.node-duplicate", "Node ids must be unique."); else nodeIds.add(raw.id);
    if (!["content", "decision", "outcome"].includes(String(raw.kind))) issue(issues, `${path}.kind`, "decision.node-kind", "Unknown node kind.");
    if (complete && !isText(raw.body)) issue(issues, `${path}.body`, "decision.node-body", "Node body is required.");
    const choices = Array.isArray(raw.choices) ? raw.choices : [];
    if (raw.kind === "decision" && complete && choices.length === 0) issue(issues, `${path}.choices`, "decision.choices-empty", "Decision nodes require choices.");
    if (raw.kind !== "decision" && choices.length > 0) issue(issues, `${path}.choices`, "decision.choices-kind", "Only decision nodes may define choices.");
    const choiceIds = new Set<string>();
    for (const [choiceIndex, choice] of choices.entries()) {
      const choicePath = `${path}.choices.${choiceIndex}`;
      if (!isRecord(choice)) { issue(issues, choicePath, "decision.choice", "Choice must be an object."); continue; }
      if (typeof choice.id !== "string" || !ID.test(choice.id)) issue(issues, `${choicePath}.id`, "decision.choice-id", "Choice id is invalid.");
      else if (choiceIds.has(choice.id)) issue(issues, `${choicePath}.id`, "decision.choice-duplicate", "Choice ids must be unique within a node."); else choiceIds.add(choice.id);
      if (complete && !isText(choice.label)) issue(issues, `${choicePath}.label`, "decision.choice-label", "Choice label is required.");
      if (typeof choice.targetNodeId !== "string" || !ID.test(choice.targetNodeId)) issue(issues, `${choicePath}.targetNodeId`, "decision.target", "Choice target is invalid.");
      if (choice.condition !== undefined) validateCondition(choice.condition, `${choicePath}.condition`, issues, variables);
      if (choice.effects !== undefined && !Array.isArray(choice.effects)) issue(issues, `${choicePath}.effects`, "decision.effects", "effects must be a list.");
      else if (Array.isArray(choice.effects)) choice.effects.forEach((effect, effectIndex) => validateEffect(effect, `${choicePath}.effects.${effectIndex}`, issues, variables));
    }
    if (raw.kind === "outcome") {
      if (!isRecord(raw.outcome)) { if (complete) issue(issues, `${path}.outcome`, "decision.outcome", "Outcome nodes require an outcome."); }
      else {
        if (!["completed", "failed", "neutral"].includes(String(raw.outcome.status))) issue(issues, `${path}.outcome.status`, "decision.outcome-status", "Unknown outcome status.");
        if (complete && !isText(raw.outcome.label)) issue(issues, `${path}.outcome.label`, "decision.outcome-label", "Outcome label is required.");
      }
    }
  }
  if (complete && (typeof input.startNodeId !== "string" || !nodeIds.has(input.startNodeId))) issue(issues, "startNodeId", "decision.start-reference", "startNodeId must reference a node.");
  for (const [index, raw] of nodes.entries()) if (isRecord(raw) && Array.isArray(raw.choices)) raw.choices.forEach((choice, choiceIndex) => {
    if (isRecord(choice) && typeof choice.targetNodeId === "string" && !nodeIds.has(choice.targetNodeId)) issue(issues, `nodes.${index}.choices.${choiceIndex}.targetNodeId`, "decision.target-reference", "Choice target does not exist.");
  });
  return issues.length ? { success: false, issues } : { success: true, data: input as unknown as DecisionGraphDefinition, issues };
}

export function evaluateDecisionCondition(condition: DecisionCondition | undefined, variables: DecisionVariables): boolean {
  if (!condition) return true;
  const actual = variables[condition.variable];
  switch (condition.operator) {
    case "equals": return actual === condition.value;
    case "not-equals": return actual !== condition.value;
    case "greater-than": return typeof actual === "number" && typeof condition.value === "number" && actual > condition.value;
    case "greater-or-equal": return typeof actual === "number" && typeof condition.value === "number" && actual >= condition.value;
    case "less-than": return typeof actual === "number" && typeof condition.value === "number" && actual < condition.value;
    case "less-or-equal": return typeof actual === "number" && typeof condition.value === "number" && actual <= condition.value;
    case "truthy": return Boolean(actual);
  }
}

export function applyDecisionEffects(variables: DecisionVariables, effects: readonly DecisionEffect[] = []): DecisionVariables {
  const next: Record<string, DecisionValue> = { ...variables };
  for (const effect of effects) {
    if (effect.operation === "set") next[effect.variable] = effect.value ?? null;
    if (effect.operation === "increment") next[effect.variable] = (typeof next[effect.variable] === "number" ? next[effect.variable] as number : 0) + (effect.value as number);
    if (effect.operation === "toggle") next[effect.variable] = !Boolean(next[effect.variable]);
  }
  return next;
}
