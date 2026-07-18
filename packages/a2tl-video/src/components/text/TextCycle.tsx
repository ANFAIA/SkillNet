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

interface CycleItem {
  text: string;
  timing: { start: number; end?: number };
  accent?: "underline" | "strike" | "hero" | "glow" | "dim";
}

interface TextCycleProps {
  theme: Theme;
  timing?: { start: number; end?: number };
  items?: CycleItem[];
  phrases?: CycleItem[];
  font?: "display" | "body" | "mono";
  fontSize?: number;
  align?: "left" | "center" | "right";
}

const UNDERLINE_DRAW_FRAMES = 18;
const STRIKE_DRAW_FRAMES = 16;

export const TextCycle: React.FC<TextCycleProps> = ({
  theme,
  timing = { start: 0 },
  items: rawItems,
  phrases,
  font = "display",
  fontSize = 56,
  align = "center",
}) => {
  const items = phrases ?? rawItems ?? [];
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const fontFamily = theme.fonts[font] ?? theme.fonts.display;

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        display: "flex",
        justifyContent: align === "center" ? "center" : align === "right" ? "flex-end" : "flex-start",
      }}
    >
      {items.map((item, i) => {
        const itemStart = item.timing.start * fps;
        const itemEnd = item.timing.end != null ? item.timing.end * fps : Infinity;
        const localFrame = frame - itemStart;

        const isVisible = frame >= itemStart && frame < itemEnd;

        const opacity = interpolate(localFrame, [0, 8, itemEnd - itemStart - 8, itemEnd - itemStart], [0, 1, 1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        if (!isVisible && opacity <= 0) return null;

        const isHero = item.accent === "hero";
        const currentFontSize = isHero ? fontSize * 1.5 : fontSize;

        const slideY = interpolate(localFrame, [0, 12], [20, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        // Underline draw-on progress
        const underlineProgress = item.accent === "underline"
          ? interpolate(localFrame, [6, 6 + UNDERLINE_DRAW_FRAMES], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            })
          : 0;

        // Strike-through draw-on progress
        const strikeProgress = item.accent === "strike"
          ? interpolate(localFrame, [6, 6 + STRIKE_DRAW_FRAMES], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            })
          : 0;

        // Glow pulse
        const glowOpacity = item.accent === "glow"
          ? interpolate(localFrame, [0, 20, 40], [0, 0.8, 0.4], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            })
          : 0;

        const dimOpacity = item.accent === "dim" ? 0.45 : 1;

        const textId = `text-cycle-${i}`;

        return (
          <div
            key={i}
            style={{
              position: "absolute",
              display: "flex",
              flexDirection: "column",
              alignItems: align === "center" ? "center" : align === "right" ? "flex-end" : "flex-start",
              opacity: opacity * dimOpacity,
              transform: `translateY(${slideY}px)`,
            }}
          >
            {/* Glow halo */}
            {item.accent === "glow" && (
              <div
                style={{
                  position: "absolute",
                  inset: "-20px -40px",
                  background: `radial-gradient(ellipse at center, ${theme.colors.ink}22 0%, transparent 70%)`,
                  opacity: glowOpacity,
                  pointerEvents: "none",
                }}
              />
            )}

            <div style={{ position: "relative", display: "inline-block" }}>
              <span
                style={{
                  fontFamily,
                  fontSize: currentFontSize,
                  fontWeight: isHero ? 800 : 600,
                  color: theme.colors.ink,
                  lineHeight: 1.2,
                  letterSpacing: isHero ? "-0.03em" : "-0.01em",
                  display: "block",
                }}
              >
                {item.text}
              </span>

              {/* Underline draw-on */}
              {item.accent === "underline" && (
                <svg
                  style={{
                    position: "absolute",
                    bottom: -6,
                    left: 0,
                    width: "100%",
                    height: 6,
                    overflow: "visible",
                  }}
                  viewBox={`0 0 100 6`}
                  preserveAspectRatio="none"
                >
                  <line
                    x1="0"
                    y1="3"
                    x2={underlineProgress * 100}
                    y2="3"
                    stroke={theme.colors.ink}
                    strokeWidth="2.5"
                    strokeLinecap="round"
                  />
                </svg>
              )}

              {/* Strike-through draw-on */}
              {item.accent === "strike" && (
                <svg
                  style={{
                    position: "absolute",
                    top: "50%",
                    left: 0,
                    width: "100%",
                    height: 6,
                    transform: "translateY(-50%)",
                    overflow: "visible",
                  }}
                  viewBox={`0 0 100 6`}
                  preserveAspectRatio="none"
                >
                  <line
                    x1="0"
                    y1="3"
                    x2={strikeProgress * 100}
                    y2="3"
                    stroke={theme.colors.red}
                    strokeWidth="3"
                    strokeLinecap="round"
                    opacity="0.85"
                  />
                </svg>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
