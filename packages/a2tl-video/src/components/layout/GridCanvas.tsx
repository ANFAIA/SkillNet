import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";

interface Theme {
  name: string;
  colors: {
    bg: string;
    bg2: string;
    ink: string;
    inkSoft: string;
    inkFaint: string;
    grid: string;
    green: string;
    red: string;
    amber: string;
    purple: string;
  };
  fonts: {
    display: string;
    body: string;
    mono: string;
  };
  grid: boolean;
}

interface GridCanvasProps {
  theme: Theme;
  timing: { start: number; end?: number };
  children?: React.ReactNode;
  cellSize?: number;
  hairlineOpacity?: number;
  vignette?: boolean;
}

export const GridCanvas: React.FC<GridCanvasProps> = ({
  theme,
  timing,
  children,
  cellSize = 48,
  hairlineOpacity = 0.18,
  vignette = false,
}) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();

  const localFrame = frame - timing.start * fps;

  const fadeIn = interpolate(localFrame, [0, 6], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const cols = Math.ceil(width / cellSize) + 1;
  const rows = Math.ceil(height / cellSize) + 1;

  // Subtle grid drift — purely deterministic, no random
  const drift = interpolate(localFrame, [0, 600], [0, cellSize * 0.5], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const gridId = `grid-pattern-${timing.start}`;
  const vignetteId = `vignette-${timing.start}`;
  const glowId = `center-glow-${timing.start}`;

  return (
    <div
      style={{
        width,
        height,
        position: "relative",
        overflow: "hidden",
        background: theme.colors.bg,
      }}
    >
      {/* SVG Grid Layer */}
      {theme.grid && (
        <svg
          width={width}
          height={height}
          style={{
            position: "absolute",
            inset: 0,
            opacity: fadeIn,
          }}
        >
          <defs>
            <pattern
              id={gridId}
              width={cellSize}
              height={cellSize}
              patternUnits="userSpaceOnUse"
              x={(-drift) % cellSize}
              y={(-drift * 0.5) % cellSize}
            >
              {/* Cell border lines */}
              <line
                x1={cellSize}
                y1="0"
                x2={cellSize}
                y2={cellSize}
                stroke={theme.colors.grid}
                strokeWidth="0.5"
                opacity={hairlineOpacity}
              />
              <line
                x1="0"
                y1={cellSize}
                x2={cellSize}
                y2={cellSize}
                stroke={theme.colors.grid}
                strokeWidth="0.5"
                opacity={hairlineOpacity}
              />
              {/* Dot at intersection */}
              <circle
                cx={cellSize}
                cy={cellSize}
                r="1"
                fill={theme.colors.grid}
                opacity={hairlineOpacity * 1.4}
              />
            </pattern>

            {/* Accent hairlines every 4 cells */}
            <pattern
              id={`${gridId}-major`}
              width={cellSize * 4}
              height={cellSize * 4}
              patternUnits="userSpaceOnUse"
              x={(-drift) % (cellSize * 4)}
              y={(-drift * 0.5) % (cellSize * 4)}
            >
              <line
                x1={cellSize * 4}
                y1="0"
                x2={cellSize * 4}
                y2={cellSize * 4}
                stroke={theme.colors.grid}
                strokeWidth="1"
                opacity={hairlineOpacity * 0.6}
              />
              <line
                x1="0"
                y1={cellSize * 4}
                x2={cellSize * 4}
                y2={cellSize * 4}
                stroke={theme.colors.grid}
                strokeWidth="1"
                opacity={hairlineOpacity * 0.6}
              />
            </pattern>

            {/* Radial center glow */}
            <radialGradient id={glowId} cx="50%" cy="50%" r="60%">
              <stop
                offset="0%"
                stopColor={theme.colors.ink}
                stopOpacity="0.04"
              />
              <stop offset="100%" stopColor={theme.colors.bg} stopOpacity="0" />
            </radialGradient>

            {/* Vignette gradient */}
            <radialGradient id={vignetteId} cx="50%" cy="50%" r="70%">
              <stop offset="40%" stopColor="transparent" stopOpacity="0" />
              <stop
                offset="100%"
                stopColor={theme.colors.bg}
                stopOpacity="0.65"
              />
            </radialGradient>
          </defs>

          {/* Minor grid */}
          <rect width={width} height={height} fill={`url(#${gridId})`} />
          {/* Major grid */}
          <rect
            width={width}
            height={height}
            fill={`url(#${gridId}-major)`}
          />
          {/* Center glow */}
          <rect width={width} height={height} fill={`url(#${glowId})`} />
          {/* Vignette */}
          {vignette && (
            <rect
              width={width}
              height={height}
              fill={`url(#${vignetteId})`}
            />
          )}
        </svg>
      )}

      {/* Children on top */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          opacity: fadeIn,
        }}
      >
        {children}
      </div>
    </div>
  );
};
