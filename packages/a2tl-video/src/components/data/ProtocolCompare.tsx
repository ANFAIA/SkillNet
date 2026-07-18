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

interface ProtocolChecks {
  auth?: boolean | string;
  data?: boolean | string;
  [key: string]: boolean | string | undefined;
}

interface Protocol {
  name: string;
  checks: ProtocolChecks;
  highlight?: boolean;
}

interface ProtocolCompareProps {
  theme: Theme;
  timing: { start: number; end?: number };
  protocols: Protocol[];
  checkKeys?: string[];
  stagger?: number;
  width?: number;
}

const CheckBadge: React.FC<{
  value: boolean | string | undefined;
  theme: Theme;
  localFrame: number;
  delay: number;
}> = ({ value, theme, localFrame, delay }) => {
  const adjustedFrame = localFrame - delay;

  const badgeScale = spring({
    frame: adjustedFrame,
    fps: 30,
    config: { damping: 12, stiffness: 260 },
  });

  const badgeOpacity = interpolate(adjustedFrame, [0, 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (badgeScale <= 0.01) return <div style={{ width: 80 }} />;

  const isTrue = value === true || value === "true" || value === "yes" || value === "✓";
  const isFalse = value === false || value === "false" || value === "no" || value === "✗";
  const isCustom = !isTrue && !isFalse && value != null;

  const badgeColor = isTrue ? theme.colors.green : isFalse ? theme.colors.red : theme.colors.amber;
  const badgeText = isTrue ? "✓" : isFalse ? "✗" : String(value ?? "–");

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        width: 80,
        opacity: badgeOpacity,
        transform: `scale(${badgeScale})`,
      }}
    >
      <div
        style={{
          padding: isCustom ? "3px 10px" : "4px 14px",
          borderRadius: 20,
          background: `${badgeColor}18`,
          border: `1.5px solid ${badgeColor}55`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minWidth: isCustom ? 60 : 36,
        }}
      >
        <span
          style={{
            fontFamily: isCustom ? theme.fonts.mono : theme.fonts.body,
            fontSize: isCustom ? 10 : 14,
            fontWeight: 700,
            color: badgeColor,
            letterSpacing: isCustom ? "0.06em" : 0,
          }}
        >
          {badgeText}
        </span>
      </div>
    </div>
  );
};

export const ProtocolCompare: React.FC<ProtocolCompareProps> = ({
  theme,
  timing,
  protocols,
  checkKeys,
  stagger = 8,
  width = 880,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const localFrame = frame - timing.start * fps;

  // Determine check keys from first protocol if not provided
  const keys = checkKeys ?? Object.keys(protocols[0]?.checks ?? {});

  const COL_W = Math.min(100, (width - 220) / keys.length);
  const TABLE_W = 220 + keys.length * COL_W;

  // Container reveal
  const containerOpacity = interpolate(localFrame, [0, 10], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Header reveal
  const headerOpacity = interpolate(localFrame, [4, 16], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        width,
        fontFamily: theme.fonts.body,
        opacity: containerOpacity,
      }}
    >
      {/* Card shell */}
      <div
        style={{
          background: theme.colors.bg2,
          border: `1px solid ${theme.colors.grid}`,
          borderRadius: 14,
          overflow: "hidden",
          boxShadow: `0 8px 40px ${theme.colors.bg}66`,
        }}
      >
        {/* Header row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            padding: "14px 24px",
            borderBottom: `1px solid ${theme.colors.grid}`,
            background: `${theme.colors.bg}66`,
            opacity: headerOpacity,
          }}
        >
          {/* Protocol name column header */}
          <div
            style={{
              width: 220,
              fontSize: 10,
              color: theme.colors.inkFaint,
              fontWeight: 700,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
            }}
          >
            Protocol
          </div>

          {/* Check key headers */}
          {keys.map((key, ki) => (
            <div
              key={ki}
              style={{
                width: COL_W,
                textAlign: "center",
                fontSize: 10,
                color: theme.colors.inkFaint,
                fontWeight: 700,
                letterSpacing: "0.1em",
                textTransform: "uppercase",
              }}
            >
              {key}
            </div>
          ))}
        </div>

        {/* Protocol rows */}
        {protocols.map((proto, pi) => {
          const rowFrame = localFrame - pi * stagger - 8;

          const rowSlideX = interpolate(rowFrame, [0, 16], [-24, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });

          const rowOpacity = interpolate(rowFrame, [0, 14], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });

          const isHighlighted = proto.highlight === true;

          return (
            <div
              key={pi}
              style={{
                display: "flex",
                alignItems: "center",
                padding: "12px 24px",
                borderBottom:
                  pi < protocols.length - 1
                    ? `1px solid ${theme.colors.grid}33`
                    : "none",
                background: isHighlighted
                  ? `${theme.colors.ink}08`
                  : "transparent",
                opacity: rowOpacity,
                transform: `translateX(${rowSlideX}px)`,
                position: "relative",
              }}
            >
              {/* Highlight left bar */}
              {isHighlighted && (
                <div
                  style={{
                    position: "absolute",
                    left: 0,
                    top: 0,
                    bottom: 0,
                    width: 3,
                    background: theme.colors.ink,
                    borderRadius: "0 2px 2px 0",
                    opacity: 0.7,
                  }}
                />
              )}

              {/* Protocol name */}
              <div style={{ width: 220 }}>
                <div
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  <span
                    style={{
                      fontFamily: theme.fonts.mono,
                      fontSize: 14,
                      fontWeight: isHighlighted ? 700 : 500,
                      color: isHighlighted ? theme.colors.ink : theme.colors.inkSoft,
                    }}
                  >
                    {proto.name}
                  </span>
                  {isHighlighted && (
                    <span
                      style={{
                        padding: "1px 7px",
                        borderRadius: 10,
                        background: `${theme.colors.ink}22`,
                        fontSize: 9,
                        fontFamily: theme.fonts.mono,
                        color: theme.colors.inkSoft,
                        letterSpacing: "0.08em",
                      }}
                    >
                      PREFERRED
                    </span>
                  )}
                </div>
              </div>

              {/* Check badges */}
              {keys.map((key, ki) => (
                <CheckBadge
                  key={ki}
                  value={proto.checks[key]}
                  theme={theme}
                  localFrame={rowFrame}
                  delay={ki * 3 + 8}
                />
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
};
