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

interface BylineProps {
  theme: Theme;
  timing: { start: number; end?: number };
  text: string;
  position?: "center" | "upper-left" | "upper-right" | "bottom-center" | "bottom-right";
}

export const Byline: React.FC<BylineProps> = ({
  theme,
  timing,
  text,
  position = "bottom-right",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const localFrame = frame - timing.start * fps;

  const opacity = interpolate(localFrame, [0, 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const translateY = interpolate(localFrame, [0, 14], [12, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const positionStyles: Record<string, React.CSSProperties> = {
    "center": { justifyContent: "center", alignItems: "center" },
    "upper-left": { justifyContent: "flex-start", alignItems: "flex-start", padding: "40px 60px" },
    "upper-right": { justifyContent: "flex-end", alignItems: "flex-start", padding: "40px 60px" },
    "bottom-center": { justifyContent: "center", alignItems: "flex-end", padding: "0 0 40px" },
    "bottom-right": { justifyContent: "flex-end", alignItems: "flex-end", padding: "0 60px 40px" },
  };

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        ...positionStyles[position] ?? positionStyles["bottom-right"],
        opacity,
        transform: `translateY(${translateY}px)`,
      }}
    >
      <span
        style={{
          fontFamily: theme.fonts.body,
          fontSize: 14,
          fontWeight: 400,
          color: theme.colors.inkSoft,
          letterSpacing: "0.04em",
        }}
      >
        {text}
      </span>
    </div>
  );
};
