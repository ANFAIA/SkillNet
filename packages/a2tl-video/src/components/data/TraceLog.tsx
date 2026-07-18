import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";

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

interface TraceLogEntry {
  tokens: string[];
  level?: "info" | "warn" | "error" | "success";
}

interface TraceLogProps {
  theme: Theme;
  timing: { start: number; end?: number };
  columns?: string[];
  entries: TraceLogEntry[];
  badge?: string;
  entryStagger?: number;
  width?: number;
}

const LEVEL_COLORS = {
  info: null,     // default
  warn: "amber",
  error: "red",
  success: "green",
} as const;

export const TraceLog: React.FC<TraceLogProps> = ({
  theme,
  timing,
  columns,
  entries,
  badge,
  entryStagger = 5,
  width = 880,
}) => {
  const normalizedColumns: string[] = !columns
    ? []
    : Array.isArray(columns)
    ? columns
    : String(columns).split(" ");
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const localFrame = frame - timing.start * fps;

  // Badge pulse
  const badgePulse = spring({
    frame: localFrame - 6,
    fps,
    config: { damping: 10, stiffness: 300 },
  });

  const badgeOpacity = interpolate(localFrame, [0, 10], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Container reveal
  const containerOpacity = interpolate(localFrame, [0, 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const FONT = theme.fonts.mono;
  const ROW_H = 32;
  const HEADER_H = 36;
  const PAD_H = 16;
  const PAD_V = 12;

  const getEntryColor = (entry: TraceLogEntry) => {
    if (!entry.level || entry.level === "info") return theme.colors.green;
    const key = LEVEL_COLORS[entry.level];
    if (!key) return theme.colors.green;
    return theme.colors[key];
  };

  // Calculate column widths
  const numCols = normalizedColumns.length || (entries[0]?.tokens.length ?? 1);
  const colWidth = (width - PAD_H * 2) / numCols;

  return (
    <div
      style={{
        width,
        fontFamily: FONT,
        opacity: containerOpacity,
        position: "relative",
      }}
    >
      {/* Terminal chrome */}
      <div
        style={{
          background: theme.colors.bg2,
          border: `1px solid ${theme.colors.grid}`,
          borderRadius: 12,
          overflow: "hidden",
          boxShadow: `0 8px 32px ${theme.colors.bg}88, 0 0 0 1px ${theme.colors.grid}44`,
        }}
      >
        {/* Top bar / chrome */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "10px 16px",
            borderBottom: `1px solid ${theme.colors.grid}`,
            background: `${theme.colors.bg}88`,
          }}
        >
          {/* Traffic lights */}
          {["#FF5F56", "#FFBD2E", "#27C93F"].map((c, i) => (
            <div
              key={i}
              style={{
                width: 10,
                height: 10,
                borderRadius: "50%",
                background: c,
                opacity: 0.8,
              }}
            />
          ))}
          <div style={{ flex: 1 }} />
          {/* Badge */}
          {badge && (
            <div
              style={{
                opacity: badgeOpacity,
                transform: `scale(${badgePulse})`,
              }}
            >
              <div
                style={{
                  padding: "2px 10px",
                  borderRadius: 20,
                  background: `${theme.colors.green}22`,
                  border: `1px solid ${theme.colors.green}55`,
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                {/* Pulse dot */}
                <div
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    background: theme.colors.green,
                    opacity: 0.9,
                  }}
                />
                <span
                  style={{
                    fontSize: 10,
                    color: theme.colors.green,
                    fontWeight: 700,
                    letterSpacing: "0.1em",
                  }}
                >
                  {badge}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Column headers */}
        {normalizedColumns.length > 0 && (
          <div
            style={{
              display: "flex",
              padding: `${PAD_V}px ${PAD_H}px`,
              borderBottom: `1px solid ${theme.colors.grid}44`,
              background: `${theme.colors.bg}44`,
            }}
          >
            {normalizedColumns.map((col, ci) => (
              <div
                key={ci}
                style={{
                  width: colWidth,
                  fontSize: 10,
                  color: theme.colors.inkFaint,
                  fontWeight: 700,
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                }}
              >
                {col}
              </div>
            ))}
          </div>
        )}

        {/* Log entries */}
        <div style={{ padding: `${PAD_V / 2}px 0` }}>
          {entries.map((entry, ei) => {
            const entryFrame = localFrame - ei * entryStagger;

            const slideX = interpolate(entryFrame, [0, 14], [-30, 0], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });

            const entryOpacity = interpolate(entryFrame, [0, 12], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });

            if (entryOpacity <= 0.01) return null;

            const entryColor = getEntryColor(entry);
            const isHighlighted = entry.level === "error" || entry.level === "warn";

            return (
              <div
                key={ei}
                style={{
                  display: "flex",
                  alignItems: "center",
                  padding: `0 ${PAD_H}px`,
                  height: ROW_H,
                  opacity: entryOpacity,
                  transform: `translateX(${slideX}px)`,
                  borderLeft: isHighlighted ? `2px solid ${entryColor}` : "2px solid transparent",
                  background: isHighlighted ? `${entryColor}08` : "transparent",
                }}
              >
                {/* Line number */}
                <div
                  style={{
                    width: 28,
                    fontSize: 10,
                    color: theme.colors.inkFaint,
                    opacity: 0.5,
                    textAlign: "right",
                    marginRight: 16,
                    flexShrink: 0,
                    userSelect: "none",
                  }}
                >
                  {ei + 1}
                </div>

                {/* Tokens */}
                {entry.tokens.map((token, ti) => (
                  <div
                    key={ti}
                    style={{
                      width: colWidth - (ti === 0 ? 44 / numCols : 0),
                      fontSize: 12,
                      lineHeight: `${ROW_H}px`,
                      color:
                        ti === 0
                          ? entryColor
                          : ti === entry.tokens.length - 1 && isHighlighted
                          ? entryColor
                          : theme.colors.inkSoft,
                      fontWeight: ti === 0 ? 600 : 400,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {ti === 0 && (
                      <span
                        style={{
                          marginRight: 6,
                          opacity: 0.5,
                        }}
                      >
                        {">"}
                      </span>
                    )}
                    {token}
                  </div>
                ))}
              </div>
            );
          })}
        </div>

        {/* Blinking cursor at end */}
        {localFrame >= entries.length * entryStagger && (
          <div
            style={{
              padding: `4px ${PAD_H}px 10px`,
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <span
              style={{
                fontSize: 12,
                color: theme.colors.green,
                opacity: 0.7,
              }}
            >
              {">"}
            </span>
            <div
              style={{
                width: 8,
                height: 14,
                background: theme.colors.green,
                opacity: interpolate(
                  (localFrame - entries.length * entryStagger) % 26,
                  [0, 3, 13, 16, 26],
                  [1, 1, 0, 0, 1],
                  { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
                ),
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
};
