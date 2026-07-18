/**
 * <A2TLVideoPlayer> — React component to embed an A2TL-Video.
 *
 * Accepts either raw .vdsl text (`spec`) or a pre-parsed JSON AST (`json`).
 * Renders the A2TL-Video inside a style-isolated <iframe> using `srcdoc`,
 * identical to the approach used by the `<vdsl-player>` web component in
 * `embed/vdsl-player.js`.
 *
 * VDSLPlayer is kept as an alias export for backwards compatibility.
 *
 * @example
 * ```tsx
 * import { A2TLVideoPlayer } from 'a2tl-video/react';
 *
 * <A2TLVideoPlayer spec={vdslSource} autoplay />
 * <A2TLVideoPlayer json={parsedSpec} theme="dark-tech" />
 * ```
 */

import {
  useRef,
  useEffect,
  useImperativeHandle,
  forwardRef,
  useMemo,
  useState,
  useCallback,
  type CSSProperties,
} from "react";

import type { VDSLSpec } from "../parser/types";
import { parseVDSL } from "../parser";
import { renderToHTML } from "../renderer";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Methods exposed via ref on the <VDSLPlayer> component. */
export interface VDSLPlayerHandle {
  /** Start playback. */
  play(): void;
  /** Pause playback. */
  pause(): void;
  /** Seek to a specific frame number. */
  seek(frame: number): void;
  /** Seek to a time in seconds. */
  seekTime(seconds: number): void;
}

export interface VDSLPlayerProps {
  /** Raw VDSL source text. Mutually exclusive with `json`. */
  spec?: string;
  /** Pre-parsed VDSLSpec JSON. Mutually exclusive with `spec`. */
  json?: VDSLSpec;
  /** Theme name override (e.g. "dark-tech", "clean"). */
  theme?: string;
  /** If true, begins playback automatically once the iframe loads. */
  autoplay?: boolean;
  /** CSS class name applied to the outer wrapper div. */
  className?: string;
  /** Inline styles applied to the outer wrapper div. */
  style?: CSSProperties;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Access the `window.vdslPlayer` API inside the iframe, if ready. */
function getPlayerAPI(
  iframe: HTMLIFrameElement | null
): {
  play(): void;
  pause(): void;
  seek(frame: number): void;
  seekTime(sec: number): void;
} | null {
  if (!iframe) return null;
  try {
    const win = iframe.contentWindow as
      | (Window & { vdslPlayer?: any; __vdslReady?: boolean })
      | null;
    if (win && win.__vdslReady && win.vdslPlayer) {
      return win.vdslPlayer;
    }
  } catch {
    // cross-origin — should never happen with srcdoc, but be safe
  }
  return null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const A2TLVideoPlayer = forwardRef<VDSLPlayerHandle, VDSLPlayerProps>(
  function A2TLVideoPlayer({ spec, json, theme, autoplay, className, style }, ref) {
    const iframeRef = useRef<HTMLIFrameElement>(null);
    const [iframeReady, setIframeReady] = useState(false);

    // --- Build the full player HTML -----------------------------------------

    const html = useMemo(() => {
      let parsed: VDSLSpec;
      if (json) {
        parsed = json;
      } else if (spec) {
        parsed = parseVDSL(spec);
      } else {
        return "";
      }
      return renderToHTML(parsed, theme);
    }, [spec, json, theme]);

    // --- Iframe load handling -----------------------------------------------

    const onLoad = useCallback(() => {
      // The renderer sets `window.__vdslReady = true` synchronously at the end
      // of its <script>, but the iframe "load" event fires *after* scripts run,
      // so the API should be available immediately. We still do a brief poll in
      // case of timing edge cases.
      const tryReady = (attempts: number) => {
        const api = getPlayerAPI(iframeRef.current);
        if (api) {
          setIframeReady(true);
          if (autoplay) api.play();
        } else if (attempts > 0) {
          setTimeout(() => tryReady(attempts - 1), 50);
        }
      };
      tryReady(20);
    }, [autoplay]);

    // Re-attach load listener when html changes
    useEffect(() => {
      setIframeReady(false);
    }, [html]);

    // --- Imperative handle --------------------------------------------------

    useImperativeHandle(
      ref,
      () => ({
        play() {
          getPlayerAPI(iframeRef.current)?.play();
        },
        pause() {
          getPlayerAPI(iframeRef.current)?.pause();
        },
        seek(frame: number) {
          getPlayerAPI(iframeRef.current)?.seek(frame);
        },
        seekTime(seconds: number) {
          getPlayerAPI(iframeRef.current)?.seekTime(seconds);
        },
      }),
      [iframeReady]
    );

    // --- Render -------------------------------------------------------------

    if (!html) return null;

    return (
      <div
        className={className}
        style={{
          position: "relative",
          width: "100%",
          aspectRatio: "16 / 9",
          overflow: "hidden",
          borderRadius: 12,
          background: "#111",
          ...style,
        }}
      >
        <iframe
          ref={iframeRef}
          srcDoc={html}
          onLoad={onLoad}
          allow="autoplay"
          scrolling="no"
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            border: "none",
            display: "block",
          }}
        />
      </div>
    );
  }
);

/** @deprecated Use A2TLVideoPlayer instead. Kept for backwards compatibility. */
export const VDSLPlayer = A2TLVideoPlayer;
