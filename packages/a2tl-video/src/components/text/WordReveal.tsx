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

interface WordRevealProps {
  theme: Theme;
  timing: { start: number; end?: number };
  text: string;
  delay?: number;
  stagger?: number;
  font?: "display" | "body" | "mono" | "hero" | "display-italic";
  color?: string;
  fontSize?: number;
  position?: "center" | "upper-left" | "upper-right" | "bottom-center";
  reveal?: string;
}

export const WordReveal: React.FC<WordRevealProps> = ({
  theme,
  timing,
  text,
  delay = 0,
  stagger = 4,
  font = "display",
  color,
  fontSize = 48,
  position = "center",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const localFrame = frame - timing.start * fps - delay;
  const words = text.split(" ");
  const fontFamily = theme.fonts[font === "hero" || font === "display" || font === "display-italic" ? "display" : "body"];

  const textColor = color ?? theme.colors.ink;

  const hasEnd = timing.end != null && timing.end! > timing.start;
  const duration = hasEnd ? (timing.end! - timing.start) * fps : 0;
  const fadeOutStart = duration - 10;

  const containerOpacity = hasEnd
    ? interpolate(localFrame, [0, 8, fadeOutStart, fadeOutStart + 10], [0, 1, 1, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : interpolate(localFrame, [0, 8], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });

  const positionStyles: Record<string, React.CSSProperties> = {
    "center": { justifyContent: "center", alignItems: "center" },
    "upper-left": { justifyContent: "flex-start", alignItems: "flex-start", padding: "60px 60px" },
    "upper-right": { justifyContent: "flex-end", alignItems: "flex-start", padding: "60px 60px" },
    "bottom-center": { justifyContent: "center", alignItems: "flex-end", padding: "0 0 60px" },
  };

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        ...positionStyles[position] ?? positionStyles["center"],
        opacity: containerOpacity,
      }}
    >
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: `${fontSize * 0.28}px`,
          justifyContent: position === "center" ? "center" : position === "upper-right" ? "flex-end" : "flex-start",
          alignItems: "baseline",
          fontFamily,
          fontSize,
          fontWeight: font === "hero" ? 800 : 600,
          fontStyle: font === "display-italic" ? "italic" : "normal",
          lineHeight: 1.25,
          padding: `${fontSize * 0.1}px 0`,
          maxWidth: "85%",
          textAlign: position === "center" ? "center" : "left",
        }}
      >
        {words.map((word, i) => {
          const wordFrame = localFrame - i * stagger;

          const wordOpacity = interpolate(wordFrame, [0, 10], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });

          const translateY = interpolate(wordFrame, [0, 14], [fontSize * 0.4, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });

          const blur = interpolate(wordFrame, [0, 12], [4, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });

          return (
            <span
              key={i}
              style={{
                display: "inline-block",
                color: textColor,
                opacity: wordOpacity,
                transform: `translateY(${translateY}px)`,
                filter: blur > 0.1 ? `blur(${blur}px)` : undefined,
                willChange: "transform, opacity",
              }}
            >
              {word}
            </span>
          );
        })}
      </div>
    </div>
  );
};
