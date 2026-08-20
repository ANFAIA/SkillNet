import * as React from "react";
import { MdCheck, MdCheckCircle, MdClose, MdInfoOutline, MdPlayArrow, MdRefresh } from "react-icons/md";
import {
  createArtifactWorkspaceState,
  type ArtifactEvaluationResult,
  type ArtifactExecutionRequest,
  type ArtifactExecutionResponse,
  type ArtifactWorkspaceDefinition,
  type ArtifactWorkspaceEvent,
  type ArtifactWorkspaceState,
} from "@didact/schema";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Textarea } from "@didact/ui";
import { cn } from "../lib/cn.js";

export interface CodeExerciseLabels {
  activity: string; loading: string; empty: string; files: string; editor: string; run: string; running: string;
  evaluate: string; evaluating: string; reset: string; output: string; noOutput: string; feedback: string;
}

const defaultLabels: CodeExerciseLabels = {
  activity: "Code exercise", loading: "The exercise is still loading.", empty: "There is no exercise to display.",
  files: "Files", editor: "Editor", run: "Run", running: "Running", evaluate: "Check work", evaluating: "Checking", reset: "Reset", output: "Output", noOutput: "Run the code to see its output.", feedback: "Feedback",
};

export interface CodeExerciseProps extends Omit<React.ComponentPropsWithoutRef<"section">, "children" | "title"> {
  definition?: ArtifactWorkspaceDefinition;
  state?: ArtifactWorkspaceState;
  defaultState?: ArtifactWorkspaceState;
  execute?: (request: ArtifactExecutionRequest) => Promise<ArtifactExecutionResponse> | ArtifactExecutionResponse;
  evaluate?: (request: ArtifactExecutionRequest, execution?: ArtifactExecutionResponse) => Promise<ArtifactEvaluationResult> | ArtifactEvaluationResult;
  onStateChange?: (state: ArtifactWorkspaceState, event: ArtifactWorkspaceEvent) => void;
  locale?: string;
  labels?: Partial<CodeExerciseLabels>;
  disabled?: boolean;
  streaming?: boolean;
}

function localText(value: string | Record<string, string> | undefined, locale: string): string {
  if (typeof value === "string") return value;
  if (!value) return "";
  return value[locale] ?? value[locale.split("-")[0] ?? ""] ?? value.en ?? Object.values(value)[0] ?? "";
}

export const CodeExercise = React.forwardRef<HTMLElement, CodeExerciseProps>(function CodeExercise(
  { definition, state: controlledState, defaultState, execute, evaluate, onStateChange, locale = "en", labels, disabled = false, streaming = false, className, ...props }, ref,
) {
  const text = { ...defaultLabels, ...labels };
  const initial = React.useMemo(() => definition ? createArtifactWorkspaceState(definition) : undefined, [definition]);
  const [internalState, setInternalState] = React.useState<ArtifactWorkspaceState | undefined>(defaultState);
  const [evaluating, setEvaluating] = React.useState(false);
  const state = controlledState ?? internalState ?? initial;
  const titleId = React.useId();

  const commit = React.useCallback((next: ArtifactWorkspaceState, event: ArtifactWorkspaceEvent) => {
    if (controlledState === undefined) setInternalState(next);
    onStateChange?.(next, event);
  }, [controlledState, onStateChange]);

  if (!definition || !state) return <section ref={ref} aria-label={text.activity} className={cn("rounded-xl border p-6 text-sm text-muted-foreground", className)} {...props}><p role={streaming ? "status" : undefined}>{streaming ? text.loading : text.empty}</p></section>;

  const active = definition.files.find(({ id }) => id === state.activeFileId) ?? definition.files[0];
  const request = (): ArtifactExecutionRequest => ({ definitionId: definition.id, entryFileId: definition.entryFileId, runtime: definition.execution.runtime, files: state.files });
  const selectFile = (fileId: string) => commit({ ...state, activeFileId: fileId }, { type: "file-selected", fileId });
  const changeFile = (fileId: string, content: string) => commit({ ...state, files: { ...state.files, [fileId]: content }, executionStatus: "idle", execution: undefined, evaluation: undefined, revision: state.revision + 1 }, { type: "file-changed", fileId });
  const run = async () => {
    if (!execute || disabled || state.executionStatus === "running") return;
    const runningState: ArtifactWorkspaceState = { ...state, executionStatus: "running", execution: undefined, evaluation: undefined };
    commit(runningState, { type: "execution-started" });
    try {
      const result = await execute(request());
      commit({ ...runningState, executionStatus: result.status, execution: result }, { type: "execution-completed", status: result.status });
    } catch (error) {
      const result: ArtifactExecutionResponse = { status: "failed", output: [{ channel: "stderr", text: error instanceof Error ? error.message : String(error) }] };
      commit({ ...runningState, executionStatus: "failed", execution: result }, { type: "execution-completed", status: "failed" });
    }
  };
  const check = async () => {
    if (!evaluate || disabled || evaluating) return;
    setEvaluating(true);
    try {
      const result = await evaluate(request(), state.execution);
      commit({ ...state, evaluation: result }, { type: "evaluation-completed", status: result.status });
    } finally { setEvaluating(false); }
  };
  const reset = () => commit(createArtifactWorkspaceState(definition), { type: "reset" });
  const canEvaluate = Boolean(evaluate && definition.evaluation?.enabled && (definition.evaluation.allowWithoutExecution || state.executionStatus === "succeeded"));

  return (
    <section ref={ref} aria-labelledby={titleId} className={cn("w-full", className)} {...props}>
      <Card>
        <CardHeader className="gap-1"><CardTitle><h2 id={titleId}>{localText(definition.title, locale)}</h2></CardTitle>{definition.description ? <CardDescription>{localText(definition.description, locale)}</CardDescription> : null}</CardHeader>
        <CardContent className="space-y-5">
          {definition.instructions ? <p className="text-sm leading-relaxed">{localText(definition.instructions, locale)}</p> : null}
          <div className="overflow-hidden rounded-lg border">
            <div className="flex items-center gap-1 overflow-x-auto border-b bg-muted/30 p-1" role="tablist" aria-label={text.files}>
              {definition.files.map((file) => <button key={file.id} type="button" role="tab" aria-selected={file.id === active?.id} className={cn("whitespace-nowrap rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", file.id === active?.id && "bg-background text-foreground shadow-sm")} onClick={() => selectFile(file.id)}>{file.path}</button>)}
            </div>
            {active ? <div role="tabpanel" className="bg-background"><Textarea aria-label={`${text.editor}: ${active.path}`} value={state.files[active.id] ?? ""} readOnly={active.readOnly} disabled={disabled} spellCheck={active.kind !== "code"} className="min-h-64 resize-y rounded-none border-0 bg-transparent p-4 font-mono text-sm leading-6 shadow-none focus-visible:ring-0" onChange={(event) => changeFile(active.id, event.target.value)} /></div> : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {definition.execution.mode === "sandboxed" ? <Button type="button" disabled={disabled || !execute || state.executionStatus === "running"} onClick={run}><MdPlayArrow aria-hidden />{state.executionStatus === "running" ? text.running : text.run}</Button> : null}
            {definition.evaluation?.enabled ? <Button type="button" variant="outline" disabled={disabled || !canEvaluate || evaluating} onClick={check}><MdCheckCircle aria-hidden />{evaluating ? text.evaluating : text.evaluate}</Button> : null}
            <Button type="button" variant="ghost" disabled={disabled || state.revision === 0 && state.executionStatus === "idle"} onClick={reset}><MdRefresh aria-hidden />{text.reset}</Button>
          </div>
          <div aria-live="polite"><h3 className="mb-2 text-sm font-medium">{text.output}</h3>{state.execution ? <div className="max-h-48 overflow-auto rounded-lg bg-foreground p-4 font-mono text-sm text-background">{state.execution.output.length ? state.execution.output.map((entry, index) => <div key={`${entry.channel}-${index}`} data-channel={entry.channel} className={cn("whitespace-pre-wrap", entry.channel === "stderr" && "opacity-75")}>{entry.text}</div>) : <span className="opacity-70">—</span>}</div> : <p className="rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">{text.noOutput}</p>}</div>
          {state.evaluation ? <div className="rounded-lg border px-4 py-3" data-status={state.evaluation.status}><h3 className="text-sm font-medium">{text.feedback}</h3>{state.evaluation.feedback ? <p className="mt-1 text-sm text-muted-foreground">{localText(state.evaluation.feedback, locale)}</p> : null}{state.evaluation.details?.length ? <ul className="mt-3 space-y-1 text-sm">{state.evaluation.details.map((detail) => <li key={detail.id} className="flex items-start gap-2">{detail.status === "passed" ? <MdCheck className="mt-0.5 shrink-0" aria-hidden /> : detail.status === "failed" ? <MdClose className="mt-0.5 shrink-0" aria-hidden /> : <MdInfoOutline className="mt-0.5 shrink-0" aria-hidden />}<span>{localText(detail.message, locale)}</span></li>)}</ul> : null}</div> : null}
        </CardContent>
      </Card>
    </section>
  );
});
