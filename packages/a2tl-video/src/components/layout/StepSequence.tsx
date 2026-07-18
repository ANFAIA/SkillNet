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

interface StepSequenceItem {
  label: string;
  description: string;
}

interface StepSequenceProps {
  theme: Theme;
  timing: { start: number; end?: number };
  steps: StepSequenceItem[];
}

export const StepSequence: React.FC<StepSequenceProps> = ({
  theme,
  timing,
  steps,
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
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
        gap: 16,
        padding: "60px 80px",
      }}
    >
      {steps.map((step, i) => {
        const itemFrame = localFrame - i * 12;

        const opacity = interpolate(itemFrame, [0, 16], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        const translateX = interpolate(itemFrame, [0, 18], [-30, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        return (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 20,
              width: "70%",
              opacity,
              transform: `translateX(${translateX}px)`,
              padding: "12px 20px",
              borderRadius: 10,
              background: `${theme.colors.ink}04`,
              border: `1px solid ${theme.colors.grid}`,
            }}
          >
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 18,
                background: theme.colors.ink,
                color: theme.colors.bg,
                display: "flex",
                justifyContent: "center",
                alignItems: "center",
                fontFamily: theme.fonts.mono,
                fontSize: 14,
                fontWeight: 700,
                flexShrink: 0,
              }}
            >
              {i + 1}
            </div>
            <div style={{ flex: 1 }}>
              <div
                style={{
                  fontFamily: theme.fonts.display,
                  fontSize: 18,
                  fontWeight: 600,
                  color: theme.colors.ink,
                  marginBottom: 2,
                }}
              >
                {step.label}
              </div>
              {step.description && (
                <div
                  style={{
                    fontFamily: theme.fonts.body,
                    fontSize: 14,
                    color: theme.colors.inkSoft,
                  }}
                >
                  {step.description}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
