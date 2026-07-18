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

interface TriptychItem {
  tokens: string[];
}

interface TriptychProps {
  theme: Theme;
  timing: { start: number; end?: number };
  items: TriptychItem[];
  reveal?: "fade" | "stagger" | "none";
}

export const Triptych: React.FC<TriptychProps> = ({
  theme,
  timing,
  items,
  reveal = "stagger",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const localFrame = frame - timing.start * fps;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        gap: 24,
        padding: "0 60px",
      }}
    >
      {items.map((item, i) => {
        const staggerDelay = reveal === "stagger" ? i * 8 : 0;
        const itemFrame = localFrame - staggerDelay;

        const opacity = interpolate(itemFrame, [0, 14], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        const translateY = interpolate(itemFrame, [0, 16], [30, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        const text = item.tokens.join(" ");

        return (
          <div
            key={i}
            style={{
              flex: 1,
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              opacity,
              transform: `translateY(${translateY}px)`,
              fontFamily: theme.fonts.display,
              fontSize: 24,
              fontWeight: 600,
              color: theme.colors.ink,
              textAlign: "center",
              lineHeight: 1.3,
              background: `${theme.colors.ink}06`,
              borderRadius: 12,
              padding: "24px 16px",
              minHeight: 120,
              border: `1px solid ${theme.colors.grid}`,
            }}
          >
            {text}
          </div>
        );
      })}
    </div>
  );
};
