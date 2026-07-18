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

interface LabelProps {
  theme: Theme;
  timing: { start: number; end?: number };
  text: string;
  position?: "center" | "upper-left" | "upper-right" | "bottom-center";
  color?: string;
}

export const Label: React.FC<LabelProps> = ({
  theme,
  timing,
  text,
  position = "center",
  color,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const localFrame = frame - timing.start * fps;

  const opacity = interpolate(localFrame, [0, 4], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const positionStyles: Record<string, React.CSSProperties> = {
    "center": { justifyContent: "center", alignItems: "center" },
    "upper-left": { justifyContent: "flex-start", alignItems: "flex-start", padding: "24px 60px" },
    "upper-right": { justifyContent: "flex-end", alignItems: "flex-start", padding: "24px 60px" },
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
          fontFamily: theme.fonts.mono,
          fontSize: 14,
          fontWeight: 700,
          color: color ?? theme.colors.inkSoft,
          letterSpacing: "0.12em",
          textTransform: "uppercase" as const,
          textAlign: "center",
          background: `${theme.colors.ink}08`,
          padding: "6px 16px",
          borderRadius: 6,
          border: `1px solid ${theme.colors.grid}`,
        }}
      >
        {text}
      </span>
    </div>
  );
};
