import type { LocalizedText, ValidationIssue, ValidationResult } from "./types";

export const ARTIFACT_EXECUTION_SCHEMA_VERSION = "1.0.0" as const;

export type ArtifactKind = "code" | "text" | "data";
export type ArtifactExecutionMode = "none" | "sandboxed";

export interface ArtifactFileDefinition {
  id: string;
  path: string;
  kind: ArtifactKind;
  content: string;
  language?: string;
  mimeType?: string;
  readOnly?: boolean;
}

export interface ArtifactWorkspaceDefinition {
  schemaVersion: typeof ARTIFACT_EXECUTION_SCHEMA_VERSION;
  id: string;
  title: LocalizedText;
  description?: LocalizedText;
  instructions?: LocalizedText;
  files: ArtifactFileDefinition[];
  entryFileId?: string;
  execution: {
    mode: ArtifactExecutionMode;
    runtime?: string;
    timeoutMs?: number;
  };
  evaluation?: { enabled: boolean; allowWithoutExecution?: boolean };
}

export interface ArtifactOutputEntry {
  channel: "stdout" | "stderr" | "result";
  text: string;
}

export interface ArtifactExecutionResponse {
  status: "succeeded" | "failed";
  output: ArtifactOutputEntry[];
  durationMs?: number;
}

export interface ArtifactEvaluationResult {
  status: "correct" | "incorrect" | "partial" | "ungraded";
  score?: number;
  feedback?: LocalizedText;
  details?: Array<{ id: string; status: "passed" | "failed" | "info"; message: LocalizedText }>;
}

export interface ArtifactWorkspaceState {
  files: Record<string, string>;
  activeFileId?: string;
  executionStatus: "idle" | "running" | "succeeded" | "failed";
  execution?: ArtifactExecutionResponse;
  evaluation?: ArtifactEvaluationResult;
  revision: number;
}

export interface ArtifactExecutionRequest {
  definitionId: string;
  entryFileId?: string;
  runtime?: string;
  files: Record<string, string>;
}

export type ArtifactWorkspaceEvent =
  | { type: "file-selected"; fileId: string }
  | { type: "file-changed"; fileId: string }
  | { type: "execution-started" }
  | { type: "execution-completed"; status: "succeeded" | "failed" }
  | { type: "evaluation-completed"; status: ArtifactEvaluationResult["status"] }
  | { type: "reset" };

export function createArtifactWorkspaceState(definition: ArtifactWorkspaceDefinition): ArtifactWorkspaceState {
  return {
    files: Object.fromEntries(definition.files.map((file) => [file.id, file.content])),
    activeFileId: definition.entryFileId ?? definition.files[0]?.id,
    executionStatus: "idle",
    revision: 0,
  };
}

function issue(path: string, code: string, message: string): ValidationIssue {
  return { path, code, message, severity: "error" };
}

export function validateArtifactWorkspaceDefinition(value: unknown, options: { mode?: "complete" | "streaming" } = {}): ValidationResult<ArtifactWorkspaceDefinition> {
  const issues: ValidationIssue[] = [];
  if (!value || typeof value !== "object" || Array.isArray(value)) return { success: false, issues: [issue("$", "type", "Expected an artifact workspace definition.")] };
  const definition = value as Partial<ArtifactWorkspaceDefinition>;
  const required = (key: keyof ArtifactWorkspaceDefinition) => {
    if (definition[key] === undefined && options.mode !== "streaming") issues.push(issue(String(key), "required", `${String(key)} is required.`));
  };
  required("schemaVersion"); required("id"); required("title"); required("files"); required("execution");
  if (definition.schemaVersion !== undefined && definition.schemaVersion !== ARTIFACT_EXECUTION_SCHEMA_VERSION) issues.push(issue("schemaVersion", "value", "Unsupported schema version."));
  if (definition.id !== undefined && (typeof definition.id !== "string" || !definition.id.trim())) issues.push(issue("id", "type", "id must be a non-empty string."));
  if (definition.files !== undefined) {
    if (!Array.isArray(definition.files)) issues.push(issue("files", "type", "files must be an array."));
    else {
      const ids = new Set<string>(); const paths = new Set<string>();
      definition.files.forEach((file, index) => {
        const path = `files.${index}`;
        if (!file || typeof file !== "object") { issues.push(issue(path, "type", "Expected a file.")); return; }
        if (!file.id || !file.path || typeof file.content !== "string") issues.push(issue(path, "required", "File id, path and string content are required."));
        if (file.id && ids.has(file.id)) issues.push(issue(`${path}.id`, "unique", "File ids must be unique."));
        if (file.path && paths.has(file.path)) issues.push(issue(`${path}.path`, "unique", "File paths must be unique."));
        if (file.id) ids.add(file.id); if (file.path) paths.add(file.path);
      });
      if (definition.entryFileId && !ids.has(definition.entryFileId)) issues.push(issue("entryFileId", "reference", "entryFileId must reference a file."));
    }
  }
  if (definition.execution) {
    if (!(["none", "sandboxed"] as unknown[]).includes(definition.execution.mode)) issues.push(issue("execution.mode", "value", "Unknown execution mode."));
    if (definition.execution.mode === "sandboxed" && !definition.execution.runtime) issues.push(issue("execution.runtime", "required", "A sandboxed workspace requires a runtime identifier."));
    if (definition.execution.timeoutMs !== undefined && (!Number.isFinite(definition.execution.timeoutMs) || definition.execution.timeoutMs <= 0)) issues.push(issue("execution.timeoutMs", "range", "timeoutMs must be positive."));
  }
  return issues.length ? { success: false, issues } : { success: true, data: value as ArtifactWorkspaceDefinition, issues };
}

export function validateArtifactWorkspaceState(value: unknown, definition: ArtifactWorkspaceDefinition): ValidationResult<ArtifactWorkspaceState> {
  const issues: ValidationIssue[] = [];
  if (!value || typeof value !== "object" || Array.isArray(value)) return { success: false, issues: [issue("$", "type", "Expected workspace state.")] };
  const state = value as Partial<ArtifactWorkspaceState>;
  if (!state.files || typeof state.files !== "object" || Array.isArray(state.files)) issues.push(issue("files", "type", "files must be a record."));
  else for (const file of definition.files) if (typeof state.files[file.id] !== "string") issues.push(issue(`files.${file.id}`, "required", "Every definition file needs string content."));
  if (state.activeFileId && !definition.files.some(({ id }) => id === state.activeFileId)) issues.push(issue("activeFileId", "reference", "Unknown active file."));
  if (!(["idle", "running", "succeeded", "failed"] as unknown[]).includes(state.executionStatus)) issues.push(issue("executionStatus", "value", "Unknown execution status."));
  if (!Number.isInteger(state.revision) || Number(state.revision) < 0) issues.push(issue("revision", "range", "revision must be a non-negative integer."));
  return issues.length ? { success: false, issues } : { success: true, data: value as ArtifactWorkspaceState, issues };
}
