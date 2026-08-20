import type { LocalizedText, ValidationIssue, ValidationResult } from "./types";

export const INTERACTIVE_MEDIA_SCHEMA_VERSION = "1.0.0" as const;

export type SerializablePrimitive = string | number | boolean | null;
export type SerializableValue =
  | SerializablePrimitive
  | readonly SerializableValue[]
  | { readonly [key: string]: SerializableValue };

export type InteractiveMediaKind = "audio" | "video";
export type InteractiveMediaTrackKind = "captions" | "subtitles" | "descriptions";

export interface InteractiveMediaTrack {
  readonly id: string;
  readonly kind: InteractiveMediaTrackKind;
  readonly src: string;
  readonly language?: string;
  readonly label: LocalizedText;
  readonly default?: boolean;
}

export interface InteractiveMediaTranscriptCue {
  readonly id: string;
  readonly startMs: number;
  readonly endMs: number;
  readonly text: LocalizedText;
  readonly speaker?: LocalizedText;
}

export interface InteractiveMediaAsset {
  readonly kind: InteractiveMediaKind;
  readonly src: string;
  readonly mimeType?: string;
  readonly durationMs?: number;
  readonly poster?: string;
  readonly tracks?: readonly InteractiveMediaTrack[];
  readonly transcript?: readonly InteractiveMediaTranscriptCue[];
  readonly noSpeech?: boolean;
  readonly visualDescription?: LocalizedText;
  readonly visualContentIsDecorative?: boolean;
}

export interface EmbeddedLearningActivity {
  readonly id: string;
  readonly manifestId: string;
  readonly typeId?: string;
  readonly authoring: Readonly<Record<string, SerializableValue>>;
}

export interface InteractiveMediaCheckpoint {
  readonly id: string;
  readonly atMs: number;
  readonly label?: LocalizedText;
  readonly required?: boolean;
  readonly pause?: boolean;
  readonly activity: EmbeddedLearningActivity;
}

export interface InteractiveMediaCompletionPolicy {
  readonly kind: "media-ended" | "required-checkpoints" | "both";
  readonly minimumWatchRatio?: number;
}

export interface InteractiveMediaDefinition {
  readonly schemaVersion: typeof INTERACTIVE_MEDIA_SCHEMA_VERSION;
  readonly id: string;
  readonly title: LocalizedText;
  readonly learningObjective?: LocalizedText;
  readonly media: InteractiveMediaAsset;
  readonly checkpoints: readonly InteractiveMediaCheckpoint[];
  readonly completion: InteractiveMediaCompletionPolicy;
  readonly allowSeeking?: boolean;
  readonly allowPlaybackRate?: boolean;
}

export interface InteractiveMediaRuntimeState {
  readonly status: "idle" | "playing" | "paused" | "completed";
  readonly positionMs: number;
  readonly durationMs?: number;
  readonly watchedMs: number;
  readonly mediaEnded: boolean;
  readonly activeCheckpointId?: string;
  readonly completedCheckpointIds: readonly string[];
}

export interface InteractiveMediaValidationOptions {
  readonly mode?: "complete" | "streaming";
}

const IDENTIFIER = /^[a-z0-9]+(?:[.-][a-z0-9]+)*$/;

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function localizedText(value: unknown): boolean {
  if (typeof value === "string") return value.trim().length > 0;
  return record(value)
    && Object.keys(value).length > 0
    && Object.values(value).every((entry) => typeof entry === "string" && entry.trim().length > 0);
}

function add(issues: ValidationIssue[], path: string, code: string, message: string): void {
  issues.push({ path, code, message, severity: "error" });
}

function validIdentifier(value: unknown): value is string {
  return typeof value === "string" && IDENTIFIER.test(value);
}

function validSerializable(value: unknown, seen = new Set<unknown>()): boolean {
  if (value === null || typeof value === "string" || typeof value === "boolean") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value !== "object") return false;
  if (seen.has(value)) return false;
  seen.add(value);
  const valid = Array.isArray(value)
    ? value.every((entry) => validSerializable(entry, seen))
    : Object.getPrototypeOf(value) === Object.prototype
      && Object.values(value as Record<string, unknown>).every((entry) => validSerializable(entry, seen));
  seen.delete(value);
  return valid;
}

export function validateInteractiveMediaDefinition(
  input: unknown,
  options: InteractiveMediaValidationOptions = {},
): ValidationResult<InteractiveMediaDefinition> {
  const issues: ValidationIssue[] = [];
  const complete = (options.mode ?? "complete") === "complete";
  if (!record(input)) {
    add(issues, "$", "interactive-media.object", "Interactive media must be an object.");
    return { success: false, issues };
  }

  if (input.schemaVersion !== INTERACTIVE_MEDIA_SCHEMA_VERSION) add(issues, "schemaVersion", "interactive-media.version", `schemaVersion must be ${INTERACTIVE_MEDIA_SCHEMA_VERSION}.`);
  if (!validIdentifier(input.id)) add(issues, "id", "interactive-media.id", "id must be a stable lowercase identifier.");
  if (!localizedText(input.title) && complete) add(issues, "title", "interactive-media.title", "title is required.");
  if (input.learningObjective !== undefined && !localizedText(input.learningObjective)) add(issues, "learningObjective", "interactive-media.learning-objective", "learningObjective must be localized text.");

  const media = input.media;
  if (!record(media)) add(issues, "media", "interactive-media.media", "media is required.");
  else {
    if (media.kind !== "audio" && media.kind !== "video") add(issues, "media.kind", "interactive-media.media-kind", "media.kind must be audio or video.");
    if ((typeof media.src !== "string" || media.src.trim().length === 0) && complete) add(issues, "media.src", "interactive-media.media-src", "media.src is required.");
    if (media.durationMs !== undefined && (typeof media.durationMs !== "number" || !Number.isFinite(media.durationMs) || media.durationMs <= 0)) add(issues, "media.durationMs", "interactive-media.duration", "durationMs must be a positive finite number.");

    const tracks = Array.isArray(media.tracks) ? media.tracks : [];
    const trackIds = new Set<string>();
    for (const [index, track] of tracks.entries()) {
      const path = `media.tracks[${index}]`;
      if (!record(track)) { add(issues, path, "interactive-media.track", "Track must be an object."); continue; }
      if (!validIdentifier(track.id)) add(issues, `${path}.id`, "interactive-media.track-id", "Track id must be stable.");
      else if (trackIds.has(track.id)) add(issues, `${path}.id`, "interactive-media.track-duplicate", "Track ids must be unique.");
      else trackIds.add(track.id);
      if (!["captions", "subtitles", "descriptions"].includes(String(track.kind))) add(issues, `${path}.kind`, "interactive-media.track-kind", "Unknown track kind.");
      if (typeof track.src !== "string" || track.src.trim().length === 0) add(issues, `${path}.src`, "interactive-media.track-src", "Track src is required.");
      if (!localizedText(track.label)) add(issues, `${path}.label`, "interactive-media.track-label", "Track label is required.");
      if ((track.kind === "captions" || track.kind === "subtitles") && (typeof track.language !== "string" || track.language.trim().length === 0)) add(issues, `${path}.language`, "interactive-media.track-language", "Caption and subtitle tracks require a language.");
    }

    const transcript = Array.isArray(media.transcript) ? media.transcript : [];
    const cueIds = new Set<string>();
    let previousStart = -1;
    for (const [index, cue] of transcript.entries()) {
      const path = `media.transcript[${index}]`;
      if (!record(cue)) { add(issues, path, "interactive-media.cue", "Transcript cue must be an object."); continue; }
      if (!validIdentifier(cue.id)) add(issues, `${path}.id`, "interactive-media.cue-id", "Cue id must be stable.");
      else if (cueIds.has(cue.id)) add(issues, `${path}.id`, "interactive-media.cue-duplicate", "Cue ids must be unique.");
      else cueIds.add(cue.id);
      if (typeof cue.startMs !== "number" || !Number.isFinite(cue.startMs) || cue.startMs < 0) add(issues, `${path}.startMs`, "interactive-media.cue-start", "startMs must be zero or greater.");
      if (typeof cue.endMs !== "number" || !Number.isFinite(cue.endMs) || cue.endMs <= Number(cue.startMs)) add(issues, `${path}.endMs`, "interactive-media.cue-end", "endMs must be greater than startMs.");
      if (typeof cue.startMs === "number" && cue.startMs < previousStart) add(issues, path, "interactive-media.cue-order", "Transcript cues must be ordered by startMs.");
      previousStart = typeof cue.startMs === "number" ? cue.startMs : previousStart;
      if (typeof media.durationMs === "number" && typeof cue.endMs === "number" && cue.endMs > media.durationMs) add(issues, `${path}.endMs`, "interactive-media.cue-bounds", "Transcript cue exceeds media duration.");
      if (!localizedText(cue.text)) add(issues, `${path}.text`, "interactive-media.cue-text", "Transcript cue text is required.");
    }

    if (complete && media.kind === "audio" && transcript.length === 0) add(issues, "media.transcript", "interactive-media.audio-transcript", "Prerecorded audio requires a transcript.");
    if (complete && media.kind === "video" && media.noSpeech !== true && !tracks.some((track) => record(track) && track.kind === "captions")) add(issues, "media.tracks", "interactive-media.video-captions", "Video with speech requires a captions track.");
    if (complete && media.kind === "video" && media.visualContentIsDecorative !== true && !localizedText(media.visualDescription) && !tracks.some((track) => record(track) && track.kind === "descriptions")) add(issues, "media.visualDescription", "interactive-media.video-description", "Meaningful video requires a visual description or descriptions track.");
  }

  const checkpoints = input.checkpoints;
  if (!Array.isArray(checkpoints)) add(issues, "checkpoints", "interactive-media.checkpoints", "checkpoints must be a list.");
  else {
    if (complete && checkpoints.length === 0) add(issues, "checkpoints", "interactive-media.checkpoints-empty", "Interactive media requires at least one checkpoint.");
    const ids = new Set<string>();
    let previousAt = -1;
    for (const [index, checkpoint] of checkpoints.entries()) {
      const path = `checkpoints[${index}]`;
      if (!record(checkpoint)) { add(issues, path, "interactive-media.checkpoint", "Checkpoint must be an object."); continue; }
      if (!validIdentifier(checkpoint.id)) add(issues, `${path}.id`, "interactive-media.checkpoint-id", "Checkpoint id must be stable.");
      else if (ids.has(checkpoint.id)) add(issues, `${path}.id`, "interactive-media.checkpoint-duplicate", "Checkpoint ids must be unique.");
      else ids.add(checkpoint.id);
      if (typeof checkpoint.atMs !== "number" || !Number.isFinite(checkpoint.atMs) || checkpoint.atMs < 0) add(issues, `${path}.atMs`, "interactive-media.checkpoint-time", "atMs must be zero or greater.");
      if (typeof checkpoint.atMs === "number" && checkpoint.atMs < previousAt) add(issues, path, "interactive-media.checkpoint-order", "Checkpoints must be ordered by atMs.");
      previousAt = typeof checkpoint.atMs === "number" ? checkpoint.atMs : previousAt;
      if (record(media) && typeof media.durationMs === "number" && typeof checkpoint.atMs === "number" && checkpoint.atMs > media.durationMs) add(issues, `${path}.atMs`, "interactive-media.checkpoint-bounds", "Checkpoint exceeds media duration.");
      if (!record(checkpoint.activity)) add(issues, `${path}.activity`, "interactive-media.activity", "Checkpoint activity is required.");
      else {
        if (!validIdentifier(checkpoint.activity.id)) add(issues, `${path}.activity.id`, "interactive-media.activity-id", "Activity id must be stable.");
        if (!validIdentifier(checkpoint.activity.manifestId)) add(issues, `${path}.activity.manifestId`, "interactive-media.manifest-id", "manifestId must be stable.");
        if (checkpoint.activity.typeId !== undefined && !validIdentifier(checkpoint.activity.typeId)) add(issues, `${path}.activity.typeId`, "interactive-media.type-id", "typeId must be stable.");
        if (!record(checkpoint.activity.authoring) || !validSerializable(checkpoint.activity.authoring)) add(issues, `${path}.activity.authoring`, "interactive-media.authoring", "Child authoring data must be a JSON-safe object.");
      }
    }
  }

  if (!record(input.completion)) add(issues, "completion", "interactive-media.completion", "completion policy is required.");
  else {
    if (!["media-ended", "required-checkpoints", "both"].includes(String(input.completion.kind))) add(issues, "completion.kind", "interactive-media.completion-kind", "Unknown completion policy.");
    if (input.completion.minimumWatchRatio !== undefined && (typeof input.completion.minimumWatchRatio !== "number" || input.completion.minimumWatchRatio < 0 || input.completion.minimumWatchRatio > 1)) add(issues, "completion.minimumWatchRatio", "interactive-media.watch-ratio", "minimumWatchRatio must be between 0 and 1.");
  }

  return issues.length > 0
    ? { success: false, issues }
    : { success: true, data: input as unknown as InteractiveMediaDefinition, issues };
}
