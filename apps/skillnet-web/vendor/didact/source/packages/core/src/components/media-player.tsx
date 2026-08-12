import * as React from "react";
import { MdForward10, MdPause, MdPlayArrow } from "react-icons/md";
import { Button } from "@didact/ui";

import { cn } from "../lib/cn.js";

export interface MediaPlayerTrack {
  id: string;
  kind: "captions" | "subtitles" | "descriptions";
  src: string;
  language?: string;
  label: string;
  default?: boolean;
}

export interface MediaPlayerController {
  play: () => void | Promise<void>;
  pause: () => void;
  seek: (positionMs: number) => void;
}

export interface MediaPlayerLabels {
  play: string;
  pause: string;
  seek: string;
  forwardTen: string;
}

const defaultLabels: MediaPlayerLabels = {
  play: "Play",
  pause: "Pause",
  seek: "Media position",
  forwardTen: "Advance 10 seconds",
};

export interface MediaPlayerProps extends Omit<React.ComponentPropsWithoutRef<"div">, "children" | "onTimeUpdate"> {
  kind: "audio" | "video";
  src: string;
  poster?: string;
  tracks?: readonly MediaPlayerTrack[];
  durationMs?: number;
  disabled?: boolean;
  labels?: Partial<MediaPlayerLabels>;
  onTimeChange?: (positionMs: number, durationMs?: number) => void;
  onPlay?: () => void;
  onPause?: () => void;
  onEnded?: () => void;
  onControllerChange?: (controller: MediaPlayerController | null) => void;
}

function formatTime(milliseconds: number) {
  const total = Math.max(0, Math.floor(milliseconds / 1_000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export function MediaPlayer({
  kind,
  src,
  poster,
  tracks,
  durationMs: durationFallback,
  disabled = false,
  labels: labelOverrides,
  onTimeChange,
  onPlay,
  onPause,
  onEnded,
  onControllerChange,
  className,
  ...props
}: MediaPlayerProps) {
  const labels = { ...defaultLabels, ...labelOverrides };
  const mediaRef = React.useRef<HTMLMediaElement | null>(null);
  const [playing, setPlaying] = React.useState(false);
  const [positionMs, setPositionMs] = React.useState(0);
  const [durationMs, setDurationMs] = React.useState(durationFallback ?? 0);

  const seek = React.useCallback((nextPositionMs: number) => {
    const duration = durationMs || durationFallback || nextPositionMs;
    const next = Math.max(0, Math.min(duration, nextPositionMs));
    if (mediaRef.current) mediaRef.current.currentTime = next / 1_000;
    setPositionMs(next);
    onTimeChange?.(next, duration || undefined);
  }, [durationFallback, durationMs, onTimeChange]);

  const play = React.useCallback(async () => {
    if (disabled) return;
    await mediaRef.current?.play();
  }, [disabled]);
  const pause = React.useCallback(() => mediaRef.current?.pause(), []);

  React.useEffect(() => {
    onControllerChange?.({ play, pause, seek });
    return () => onControllerChange?.(null);
  }, [onControllerChange, pause, play, seek]);

  const updateFromElement = (element: HTMLMediaElement) => {
    const nextDuration = Number.isFinite(element.duration) ? element.duration * 1_000 : durationFallback;
    if (nextDuration) setDurationMs(nextDuration);
    const nextPosition = element.currentTime * 1_000;
    setPositionMs(nextPosition);
    onTimeChange?.(nextPosition, nextDuration);
  };

  const mediaProps = {
    ref: (node: HTMLMediaElement | null) => { mediaRef.current = node; },
    src,
    preload: "metadata" as const,
    tabIndex: -1,
    onLoadedMetadata: (event: React.SyntheticEvent<HTMLMediaElement>) => updateFromElement(event.currentTarget),
    onTimeUpdate: (event: React.SyntheticEvent<HTMLMediaElement>) => updateFromElement(event.currentTarget),
    onPlay: () => { setPlaying(true); onPlay?.(); },
    onPause: () => { setPlaying(false); onPause?.(); },
    onEnded: () => { setPlaying(false); onEnded?.(); },
  };
  const trackNodes = tracks?.map((track) => <track key={track.id} kind={track.kind} src={track.src} srcLang={track.language} label={track.label} default={track.default} />);
  const controls = <div className={cn("flex items-center gap-2 px-3 py-3 sm:gap-3 sm:px-4", kind === "video" && "absolute inset-x-0 bottom-0 text-background")}>
    <Button type="button" variant="ghost" size="icon-sm" disabled={disabled} onClick={() => { if (playing) pause(); else void play(); }} aria-label={playing ? labels.pause : labels.play} title={playing ? labels.pause : labels.play} className={cn("shrink-0 hover:bg-transparent", kind === "video" && "text-background hover:text-background")}>
      {playing ? <MdPause className="size-5" aria-hidden="true" /> : <MdPlayArrow className="size-5" aria-hidden="true" />}
    </Button>
    <label className="flex min-w-0 flex-1 items-center gap-2">
      <span className={cn("shrink-0 text-xs tabular-nums text-muted-foreground", kind === "video" && "text-background")}>{formatTime(positionMs)}</span>
      <input aria-label={labels.seek} type="range" min={0} max={durationMs || durationFallback || 0} step={1_000} value={positionMs} disabled={disabled || !(durationMs || durationFallback)} onChange={(event) => seek(Number(event.currentTarget.value))} className={cn("min-w-0 flex-1 accent-foreground", kind === "video" && "accent-background")} />
      <span className={cn("shrink-0 text-xs tabular-nums text-muted-foreground", kind === "video" && "text-background")}>{formatTime(durationMs || durationFallback || 0)}</span>
    </label>
    <Button type="button" variant="ghost" size="icon-sm" disabled={disabled} onClick={() => seek(positionMs + 10_000)} aria-label={labels.forwardTen} title={labels.forwardTen} className={cn("shrink-0 hover:bg-transparent", kind === "video" && "text-background hover:text-background")}><MdForward10 className="size-5" aria-hidden="true" /></Button>
  </div>;

  return <div data-slot="media-player" data-kind={kind} className={cn("bg-background", kind === "video" && "relative overflow-hidden bg-foreground", className)} {...props}>
    {kind === "video" ? <video {...mediaProps} poster={poster} className="aspect-video w-full object-contain">{trackNodes}</video> : <audio {...mediaProps}>{trackNodes}</audio>}
    {controls}
  </div>;
}
