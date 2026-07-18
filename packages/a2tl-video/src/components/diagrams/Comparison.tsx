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

interface ComparisonSide {
  title: string;
  subtitle?: string;
  badge?: { text: string; color: string };
  color?: string;
  bullets?: string[];
}

interface ComparisonProps {
  theme: Theme;
  timing: { start: number; end?: number };
  left: ComparisonSide;
  right: ComparisonSide;
  animation?: "split-tilt" | "slide-in" | "fade";
  width?: number;
  height?: number;
}

const CARD_W = 340;
const CARD_H = 280;

const ComparisonCard: React.FC<{
  side: ComparisonSide;
  theme: Theme;
  localFrame: number;
  fps: number;
  direction: -1 | 1; // -1 = from left, 1 = from right
  animation: string;
  delay?: number;
}> = ({ side, theme, localFrame, fps, direction, animation, delay = 0 }) => {
  const adjustedFrame = localFrame - delay;
  const cardColor = side.color ?? (direction < 0 ? theme.colors.purple : theme.colors.green);

  let translateX = 0;
  let rotateY = 0;
  let scale = 1;
  let opacity = 1;

  if (animation === "split-tilt") {
    translateX = interpolate(adjustedFrame, [0, 22], [direction * 120, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    // 3D tilt settles in
    const tiltSpring = spring({
      frame: adjustedFrame,
      fps,
      config: { damping: 18, stiffness: 160 },
    });
    rotateY = interpolate(tiltSpring, [0, 1], [direction * -18, 0]);
    opacity = interpolate(adjustedFrame, [0, 14], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  } else if (animation === "slide-in") {
    translateX = interpolate(adjustedFrame, [0, 20], [direction * 200, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    opacity = interpolate(adjustedFrame, [0, 16], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  } else {
    opacity = interpolate(adjustedFrame, [0, 20], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    translateX = interpolate(adjustedFrame, [0, 20], [direction * 30, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  }

  const badgeOpacity = interpolate(adjustedFrame, [18, 28], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const bulletOpacities = (side.bullets ?? []).map((_, bi) =>
    interpolate(adjustedFrame, [22 + bi * 6, 32 + bi * 6], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );

  const subtitleOpacity = interpolate(adjustedFrame, [12, 22], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        width: CARD_W,
        height: CARD_H,
        opacity,
        transform: `translateX(${translateX}px) perspective(800px) rotateY(${rotateY}deg)`,
        transformOrigin: direction < 0 ? "right center" : "left center",
        position: "relative",
      }}
    >
      {/* Card shadow layer */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: 16,
          background: theme.colors.bg,
          transform: "translate(4px, 6px)",
          filter: "blur(12px)",
          opacity: 0.6,
        }}
      />

      {/* Card body */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: 16,
          background: theme.colors.bg2,
          border: `1.5px solid ${cardColor}44`,
          overflow: "hidden",
        }}
      >
        {/* Top color band */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: 5,
            background: `linear-gradient(90deg, ${cardColor}CC, ${cardColor}44)`,
            borderRadius: "16px 16px 0 0",
          }}
        />

        {/* Gradient fill */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: `linear-gradient(135deg, ${cardColor}12 0%, transparent 60%)`,
          }}
        />

        {/* Content */}
        <div
          style={{
            position: "relative",
            padding: "28px 24px 20px",
            height: "100%",
            boxSizing: "border-box",
            display: "flex",
            flexDirection: "column",
            gap: 0,
          }}
        >
          {/* Badge */}
          {side.badge && (
            <div
              style={{
                display: "inline-flex",
                alignSelf: "flex-start",
                padding: "4px 12px",
                borderRadius: 20,
                background: `${side.badge.color}22`,
                border: `1px solid ${side.badge.color}66`,
                marginBottom: 12,
                opacity: badgeOpacity,
              }}
            >
              <span
                style={{
                  fontFamily: theme.fonts.mono,
                  fontSize: 11,
                  fontWeight: 700,
                  color: side.badge.color,
                  letterSpacing: "0.1em",
                }}
              >
                {side.badge.text}
              </span>
            </div>
          )}

          {/* Title */}
          <div
            style={{
              fontFamily: theme.fonts.display,
              fontSize: 24,
              fontWeight: 700,
              color: theme.colors.ink,
              letterSpacing: "-0.02em",
              lineHeight: 1.2,
              marginBottom: 8,
            }}
          >
            {side.title}
          </div>

          {/* Subtitle */}
          {side.subtitle && (
            <div
              style={{
                fontFamily: theme.fonts.body,
                fontSize: 13,
                color: theme.colors.inkSoft,
                lineHeight: 1.5,
                marginBottom: 14,
                opacity: subtitleOpacity,
              }}
            >
              {side.subtitle}
            </div>
          )}

          {/* Divider */}
          <div
            style={{
              height: 1,
              background: `linear-gradient(90deg, ${cardColor}44, transparent)`,
              marginBottom: 12,
              opacity: subtitleOpacity,
            }}
          />

          {/* Bullets */}
          {(side.bullets ?? []).map((bullet, bi) => (
            <div
              key={bi}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 6,
                opacity: bulletOpacities[bi] ?? 0,
              }}
            >
              <div
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: cardColor,
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  fontFamily: theme.fonts.body,
                  fontSize: 12,
                  color: theme.colors.inkSoft,
                  lineHeight: 1.4,
                }}
              >
                {bullet}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export const Comparison: React.FC<ComparisonProps> = ({
  theme,
  timing,
  left,
  right,
  animation = "split-tilt",
  width = 860,
  height = 340,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const localFrame = frame - timing.start * fps;

  // VS divider
  const vsOpacity = interpolate(localFrame, [16, 26], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const vsScale = spring({
    frame: localFrame - 12,
    fps,
    config: { damping: 12, stiffness: 220 },
  });

  return (
    <div
      style={{
        width,
        height,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 32,
        position: "relative",
      }}
    >
      {/* Left card */}
      <ComparisonCard
        side={left}
        theme={theme}
        localFrame={localFrame}
        fps={fps}
        direction={-1}
        animation={animation}
      />

      {/* VS divider */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 12,
          opacity: vsOpacity,
          transform: `scale(${vsScale})`,
          flexShrink: 0,
        }}
      >
        <div
          style={{
            width: 1.5,
            height: 60,
            background: `linear-gradient(to bottom, transparent, ${theme.colors.inkFaint}66, transparent)`,
          }}
        />
        <div
          style={{
            fontFamily: theme.fonts.mono,
            fontSize: 12,
            fontWeight: 700,
            color: theme.colors.inkFaint,
            letterSpacing: "0.12em",
          }}
        >
          VS
        </div>
        <div
          style={{
            width: 1.5,
            height: 60,
            background: `linear-gradient(to bottom, transparent, ${theme.colors.inkFaint}66, transparent)`,
          }}
        />
      </div>

      {/* Right card */}
      <ComparisonCard
        side={right}
        theme={theme}
        localFrame={localFrame}
        fps={fps}
        direction={1}
        animation={animation}
        delay={4}
      />
    </div>
  );
};
