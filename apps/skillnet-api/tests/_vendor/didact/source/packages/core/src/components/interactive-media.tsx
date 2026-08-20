import * as React from "react";
import { MdCheck, MdClose } from "react-icons/md";
import {
  validateInteractiveMediaDefinition,
  type EmbeddedLearningActivity,
  type InteractiveMediaDefinition,
  type InteractiveMediaRuntimeState,
} from "@didact/schema";
import { Button, Card, CardContent, CardHeader, CardTitle, Separator } from "@didact/ui";

import { cn } from "../lib/cn.js";
import { MediaPlayer } from "./media-player.js";

export interface InteractiveMediaPlayerController {
  play: () => void | Promise<void>;
  pause: () => void;
  seek: (positionMs: number) => void;
}

export interface InteractiveMediaPlayerContext {
  definition: InteractiveMediaDefinition;
  disabled: boolean;
  setController: (controller: InteractiveMediaPlayerController | null) => void;
  onTimeChange: (positionMs: number, durationMs?: number) => void;
  onPlay: () => void;
  onPause: () => void;
  onEnded: () => void;
}

export interface InteractiveMediaActivityContext {
  checkpointId: string;
  completed: boolean;
  disabled: boolean;
  complete: () => void;
  close: () => void;
}

export interface InteractiveMediaLabels {
  loading: string;
  invalid: string;
  checkpoints: string;
  transcript: string;
  openCheckpoint: (label: string) => string;
  completed: string;
  optional: string;
  required: string;
  close: string;
  markComplete: string;
  progress: (completed: number, total: number) => string;
  position: (position: string, duration?: string) => string;
}

const defaultLabels: InteractiveMediaLabels = {
  loading: "Media is still loading.",
  invalid: "This interactive media configuration is incomplete.",
  checkpoints: "Learning checkpoints",
  transcript: "Transcript",
  openCheckpoint: (label) => `Open checkpoint: ${label}`,
  completed: "Completed",
  optional: "Optional",
  required: "Required",
  close: "Close checkpoint",
  markComplete: "Mark checkpoint complete",
  progress: (completed, total) => `${completed} of ${total} required checkpoints completed`,
  position: (position, duration) => duration ? `${position} of ${duration}` : position,
};

const initialState: InteractiveMediaRuntimeState = {
  status: "idle",
  positionMs: 0,
  watchedMs: 0,
  mediaEnded: false,
  completedCheckpointIds: [],
};

function localText(value: string | Record<string, string> | undefined): string | undefined {
  if (typeof value === "string") return value;
  return value?.en ?? (value ? Object.values(value)[0] : undefined);
}

function formatTime(milliseconds: number): string {
  const total = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function completionSatisfied(definition: InteractiveMediaDefinition, state: InteractiveMediaRuntimeState): boolean {
  const required = definition.checkpoints.filter(({ required }) => required !== false).map(({ id }) => id);
  const checkpointsComplete = required.every((id) => state.completedCheckpointIds.includes(id));
  const ratio = definition.completion.minimumWatchRatio;
  const duration = state.durationMs ?? definition.media.durationMs;
  const watchComplete = ratio === undefined || (duration !== undefined && state.watchedMs / duration >= ratio);
  const policyComplete = definition.completion.kind === "media-ended"
    ? state.mediaEnded
    : definition.completion.kind === "required-checkpoints"
      ? checkpointsComplete
      : state.mediaEnded && checkpointsComplete;
  return policyComplete && watchComplete;
}

function NativeMediaPlayer({ context }: { context: InteractiveMediaPlayerContext }) {
  const { definition, disabled, setController, onTimeChange, onPlay, onPause, onEnded } = context;
  return <MediaPlayer
    kind={definition.media.kind}
    src={definition.media.src}
    poster={definition.media.poster}
    durationMs={definition.media.durationMs}
    tracks={definition.media.tracks?.map((track) => ({ ...track, label: localText(track.label) ?? track.id }))}
    disabled={disabled}
    onControllerChange={setController}
    onTimeChange={onTimeChange}
    onPlay={onPlay}
    onPause={onPause}
    onEnded={onEnded}
  />;
}

export interface InteractiveMediaProps extends Omit<React.ComponentPropsWithoutRef<"section">, "children" | "title" | "onChange"> {
  definition?: InteractiveMediaDefinition;
  validationMode?: "complete" | "streaming";
  state?: InteractiveMediaRuntimeState;
  defaultState?: Partial<InteractiveMediaRuntimeState>;
  onStateChange?: (state: InteractiveMediaRuntimeState) => void;
  onCheckpointOpen?: (checkpointId: string) => void;
  onCheckpointComplete?: (checkpointId: string) => void;
  onComplete?: (state: InteractiveMediaRuntimeState) => void;
  renderActivity: (activity: EmbeddedLearningActivity, context: InteractiveMediaActivityContext) => React.ReactNode;
  renderPlayer?: (context: InteractiveMediaPlayerContext) => React.ReactNode;
  disabled?: boolean;
  labels?: Partial<InteractiveMediaLabels>;
}

export function InteractiveMedia({
  definition,
  validationMode = "complete",
  state: stateProp,
  defaultState,
  onStateChange,
  onCheckpointOpen,
  onCheckpointComplete,
  onComplete,
  renderActivity,
  renderPlayer,
  disabled = false,
  labels: labelOverrides,
  className,
  ...props
}: InteractiveMediaProps) {
  const labels = { ...defaultLabels, ...labelOverrides };
  const controlled = stateProp !== undefined;
  const [localState, setLocalState] = React.useState<InteractiveMediaRuntimeState>({ ...initialState, ...defaultState });
  const state = stateProp ?? localState;
  const controllerRef = React.useRef<InteractiveMediaPlayerController | null>(null);
  const encounteredRef = React.useRef(new Set<string>());
  const completionEmittedRef = React.useRef(false);
  const validation = React.useMemo(() => validateInteractiveMediaDefinition(definition, { mode: validationMode }), [definition, validationMode]);

  const commit = React.useCallback((next: InteractiveMediaRuntimeState) => {
    const completed = definition && completionSatisfied(definition, next) ? { ...next, status: "completed" as const } : next;
    if (!controlled) setLocalState(completed);
    onStateChange?.(completed);
    if (completed.status === "completed" && !completionEmittedRef.current) {
      completionEmittedRef.current = true;
      onComplete?.(completed);
    }
  }, [controlled, definition, onComplete, onStateChange]);

  if (!definition || (validationMode === "streaming" && !validation.success)) {
    return <Card className={cn("w-full max-w-5xl gap-0 overflow-hidden py-0", className)} data-slot="interactive-media" data-state="loading" {...props}>
      <CardContent className="grid min-h-40 place-items-center p-6 text-center" role="status">
        <div className="grid max-w-sm gap-3">
          <span className="mx-auto size-8 rounded-full border-2 border-muted border-t-primary motion-safe:animate-spin" aria-hidden="true" />
          <p className="text-sm text-muted-foreground">{labels.loading}</p>
        </div>
      </CardContent>
    </Card>;
  }
  if (!validation.success) {
    return <Card className={cn("w-full max-w-5xl gap-0 overflow-hidden py-0", className)} data-slot="interactive-media" data-state="invalid" {...props}>
      <CardContent className="p-5 sm:p-6" role="alert">
        <p className="font-semibold">{labels.invalid}</p>
        <ul className="mt-2 list-disc pl-5 text-sm leading-6 text-muted-foreground">{validation.issues.map((issue) => <li key={`${issue.path}:${issue.code}`}>{issue.message}</li>)}</ul>
      </CardContent>
    </Card>;
  }

  const required = definition.checkpoints.filter(({ required: isRequired }) => isRequired !== false);
  const completedRequired = required.filter(({ id }) => state.completedCheckpointIds.includes(id)).length;
  const active = definition.checkpoints.find(({ id }) => id === state.activeCheckpointId);
  const duration = state.durationMs ?? definition.media.durationMs;
  const setController = React.useCallback((controller: InteractiveMediaPlayerController | null) => { controllerRef.current = controller; }, []);
  const openCheckpoint = (checkpointId: string) => {
    if (disabled) return;
    const checkpoint = definition.checkpoints.find(({ id }) => id === checkpointId);
    if (!checkpoint) return;
    encounteredRef.current.add(checkpoint.id);
    if (checkpoint.pause !== false) controllerRef.current?.pause();
    commit({ ...state, status: "paused", activeCheckpointId: checkpoint.id });
    onCheckpointOpen?.(checkpoint.id);
  };
  const onTimeChange = (positionMs: number, durationMs?: number) => {
    const delta = state.status === "playing" && positionMs >= state.positionMs && positionMs - state.positionMs <= 2_000 ? positionMs - state.positionMs : 0;
    const next = { ...state, positionMs, durationMs: durationMs ?? state.durationMs, watchedMs: Math.min(durationMs ?? definition.media.durationMs ?? Number.POSITIVE_INFINITY, state.watchedMs + delta) };
    const crossed = definition.checkpoints.find((checkpoint) => !encounteredRef.current.has(checkpoint.id) && checkpoint.atMs <= positionMs && (checkpoint.atMs > state.positionMs || (state.positionMs === 0 && checkpoint.atMs === 0)));
    if (crossed) {
      encounteredRef.current.add(crossed.id);
      if (crossed.pause !== false) controllerRef.current?.pause();
      commit({ ...next, status: "paused", activeCheckpointId: crossed.id });
      onCheckpointOpen?.(crossed.id);
    } else commit(next);
  };
  const markComplete = (checkpointId: string) => {
    if (disabled || state.completedCheckpointIds.includes(checkpointId)) return;
    const next = { ...state, activeCheckpointId: undefined, completedCheckpointIds: [...state.completedCheckpointIds, checkpointId] };
    commit(next);
    onCheckpointComplete?.(checkpointId);
  };
  const playerContext: InteractiveMediaPlayerContext = {
    definition,
    disabled,
    setController,
    onTimeChange,
    onPlay: () => { if (!disabled) commit({ ...state, status: "playing" }); },
    onPause: () => { if (state.status !== "completed") commit({ ...state, status: "paused" }); },
    onEnded: () => commit({ ...state, positionMs: duration ?? state.positionMs, mediaEnded: true, status: "paused" }),
  };

  return <section className={cn("w-full max-w-5xl", className)} data-slot="interactive-media" data-state={state.status} aria-disabled={disabled || undefined} {...props}>
    <Card className="gap-0 overflow-hidden py-0">
      <CardHeader className="gap-2 px-5 py-5 sm:px-6">
        <CardTitle role="heading" aria-level={2} className="text-balance text-lg leading-tight sm:text-xl">{localText(definition.title)}</CardTitle>
        {definition.learningObjective ? <p className="max-w-3xl text-sm leading-6 text-muted-foreground">{localText(definition.learningObjective)}</p> : null}
      </CardHeader>

      <div className="border-y bg-background">
        {renderPlayer ? renderPlayer(playerContext) : <NativeMediaPlayer context={playerContext} />}
      </div>
      {definition.media.visualDescription ? <p className="border-b px-5 py-3 text-sm leading-6 text-muted-foreground sm:px-6">{localText(definition.media.visualDescription)}</p> : null}

      <CardContent className="grid gap-4 px-5 py-4 sm:px-6">
        {definition.checkpoints.length ? <div className="grid gap-3">
          <div>
            <h3 className="text-sm font-semibold">{labels.checkpoints}</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">{labels.progress(completedRequired, required.length)}</p>
          </div>
          <ol className="grid gap-1">
            {definition.checkpoints.map((checkpoint) => {
              const checkpointLabel = localText(checkpoint.label) ?? formatTime(checkpoint.atMs);
              const complete = state.completedCheckpointIds.includes(checkpoint.id);
              const status = complete ? labels.completed : checkpoint.required === false ? labels.optional : labels.required;
              return <li key={checkpoint.id}>
                <Button
                  type="button"
                  variant="ghost"
                  disabled={disabled}
                  aria-label={labels.openCheckpoint(checkpointLabel)}
                  onClick={() => openCheckpoint(checkpoint.id)}
                  className={cn("h-auto w-full justify-start gap-3 px-2 py-2 text-left", active?.id === checkpoint.id && "bg-accent")}
                >
                  <span className="flex w-12 shrink-0 items-center gap-1 text-xs tabular-nums text-muted-foreground">{complete ? <MdCheck className="size-3.5 text-foreground" aria-hidden="true" /> : null}{formatTime(checkpoint.atMs)}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{checkpointLabel}</span>
                    <span className="block text-xs font-normal text-muted-foreground">{status}</span>
                  </span>
                </Button>
              </li>;
            })}
          </ol>
        </div> : null}
      </CardContent>

      {active ? <div data-slot="interactive-media-checkpoint" className="border-t px-5 py-5 sm:px-6">
        <div className="mx-auto grid max-w-3xl gap-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-medium text-primary">{formatTime(active.atMs)} · {active.required === false ? labels.optional : labels.required}</p>
              <h3 className="mt-1 font-semibold">{localText(active.label) ?? labels.checkpoints}</h3>
            </div>
            <Button type="button" variant="ghost" size="icon-sm" onClick={() => commit({ ...state, activeCheckpointId: undefined })} disabled={disabled} aria-label={labels.close}><MdClose className="size-4" aria-hidden="true" /></Button>
          </div>
          <Separator />
          {renderActivity(active.activity, {
            checkpointId: active.id,
            completed: state.completedCheckpointIds.includes(active.id),
            disabled,
            complete: () => markComplete(active.id),
            close: () => commit({ ...state, activeCheckpointId: undefined }),
          })}
          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={() => markComplete(active.id)} disabled={disabled || state.completedCheckpointIds.includes(active.id)}>{labels.markComplete}</Button>
            <Button type="button" variant="outline" onClick={() => commit({ ...state, activeCheckpointId: undefined })} disabled={disabled}>{labels.close}</Button>
          </div>
        </div>
      </div> : null}

      {definition.media.transcript?.length ? <div className="border-t">
        <div className="px-5 py-4 sm:px-6"><h3 className="text-sm font-semibold">{labels.transcript}</h3></div>
        <ol className="max-h-80 overflow-y-auto border-t px-3 py-2 sm:px-4">
          {definition.media.transcript.map((cue) => {
            const cueActive = state.positionMs >= cue.startMs && state.positionMs < cue.endMs;
            return <li key={cue.id}>
              <button
                type="button"
                disabled={disabled}
                onClick={() => { controllerRef.current?.seek(cue.startMs); commit({ ...state, positionMs: cue.startMs }); }}
                className={cn("grid w-full grid-cols-[3.5rem_1fr] gap-3 rounded-md px-3 py-2.5 text-left text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50", cueActive && "bg-accent")}
              >
                <span className={cn("pt-0.5 text-xs tabular-nums", cueActive ? "text-foreground" : "text-muted-foreground")}>{formatTime(cue.startMs)}</span>
                <span className="leading-6">{cue.speaker ? <strong className="font-semibold">{localText(cue.speaker)}: </strong> : null}{localText(cue.text)}</span>
              </button>
            </li>;
          })}
        </ol>
      </div> : null}
    </Card>
  </section>;
}
