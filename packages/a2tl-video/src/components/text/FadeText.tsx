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

interface FadeTextProps {
  theme: Theme;
  timing: { start: number; end?: number };
  text: string;
  font?: "display" | "display-italic" | "body" | "mono" | "hero";
  position?: "center" | "upper-left" | "upper-right" | "bottom-center";
  color?: string;
  fontSize?: number;
}

export const FadeText: React.FC<FadeTextProps> = ({
  theme,
  timing,
  text,
  font = "body",
  position = "center",
  color,
  fontSize = 36,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const localFrame = frame - timing.start * fps;
  const hasEnd = timing.end != null && timing.end! > timing.start;
  const duration = hasEnd ? (timing.end! - timing.start) * fps : 60;
  const fadeOutStart = Math.max(0, duration - 12);

  const opacity = hasEnd
    ? interpolate(localFrame, [0, 6, fadeOutStart, fadeOutStart + 10], [0, 1, 1, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : interpolate(localFrame, [0, 6], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });

  const fontFamily = theme.fonts[font === "hero" || font === "display" || font === "display-italic" ? "display" : "body"];

  const positionStyles: Record<string, React.CSSProperties> = {
    "center": { justifyContent: "center", alignItems: "center" },
    "upper-left": { justifyContent: "flex-start", alignItems: "flex-start", padding: "40px 60px" },
    "upper-right": { justifyContent: "flex-end", alignItems: "flex-start", padding: "40px 60px" },
    "bottom-center": { justifyContent: "center", alignItems: "flex-end", padding: "0 0 60px" },
  };

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        ...positionStyles[position] ?? positionStyles["center"],
        opacity,
      }}
    >
      <span
        style={{
          fontFamily,
          fontSize,
          fontWeight: font === "hero" || font === "display" ? 700 : 400,
          color: color ?? theme.colors.ink,
          fontStyle: font === "display-italic" ? "italic" : "normal",
          textAlign: "center",
          lineHeight: 1.3,
          maxWidth: "80%",
        }}
      >
        {text}
      </span>
    </div>
  );
};
