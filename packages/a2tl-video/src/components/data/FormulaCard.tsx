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

interface FormulaPart {
  text: string;
  color?: string;
  bold?: boolean;
  sub?: string;
  sup?: string;
}

interface FormulaCardProps {
  theme: Theme;
  timing: { start: number; end?: number };
  parts: FormulaPart[];
  arrow?: string;
  result?: string;
  subtitle?: string;
  width?: number;
  accent?: string;
}

export const FormulaCard: React.FC<FormulaCardProps> = ({
  theme,
  timing,
  parts,
  arrow = "→",
  result,
  subtitle,
  width = 760,
  accent,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const localFrame = frame - timing.start * fps;
  const accentColor = accent ?? theme.colors.ink;

  // Card fade in
  const cardOpacity = interpolate(localFrame, [0, 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const cardScale = spring({
    frame: localFrame,
    fps,
    config: { damping: 18, stiffness: 160 },
  });

  // Formula parts stagger
  const partOpacities = parts.map((_, i) =>
    interpolate(localFrame, [10 + i * 5, 20 + i * 5], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );

  const partSlides = parts.map((_, i) =>
    interpolate(localFrame, [10 + i * 5, 22 + i * 5], [16, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );

  // Arrow draw progress
  const arrowFrame = localFrame - parts.length * 5 - 10;
  const arrowProgress = interpolate(arrowFrame, [0, 16], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Result reveal
  const resultFrame = arrowFrame + 14;
  const resultOpacity = interpolate(resultFrame, [0, 16], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const resultScale = spring({
    frame: resultFrame,
    fps,
    config: { damping: 12, stiffness: 240 },
  });

  // Subtitle
  const subtitleOpacity = interpolate(resultFrame + 10, [0, 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Arrow SVG width in px
  const ARROW_SVG_W = 80;
  const arrowDrawX = ARROW_SVG_W * arrowProgress;

  return (
    <div
      style={{
        width,
        opacity: cardOpacity,
        transform: `scale(${cardScale})`,
        transformOrigin: "center center",
      }}
    >
      {/* Card shell */}
      <div
        style={{
          background: theme.colors.bg2,
          border: `1px solid ${accentColor}33`,
          borderRadius: 18,
          padding: "36px 40px",
          position: "relative",
          overflow: "hidden",
          boxShadow: `0 12px 48px ${theme.colors.bg}88, 0 0 0 1px ${accentColor}15`,
        }}
      >
        {/* Background gradient */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: `radial-gradient(ellipse at 30% 0%, ${accentColor}10 0%, transparent 60%)`,
            pointerEvents: "none",
          }}
        />

        {/* Top accent line */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 40,
            right: 40,
            height: 2,
            background: `linear-gradient(90deg, transparent, ${accentColor}88, transparent)`,
          }}
        />

        {/* Formula row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
            position: "relative",
          }}
        >
          {/* Parts */}
          {parts.map((part, pi) => {
            const partColor = part.color ?? theme.colors.ink;
            return (
              <div
                key={pi}
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: 2,
                  opacity: partOpacities[pi] ?? 0,
                  transform: `translateY(${partSlides[pi] ?? 16}px)`,
                }}
              >
                <span
                  style={{
                    fontFamily: theme.fonts.mono,
                    fontSize: 28,
                    fontWeight: part.bold ? 700 : 500,
                    color: partColor,
                    letterSpacing: "-0.01em",
                  }}
                >
                  {part.text}
                </span>
                {part.sub && (
                  <span
                    style={{
                      fontFamily: theme.fonts.mono,
                      fontSize: 16,
                      color: partColor,
                      opacity: 0.65,
                      verticalAlign: "sub",
                    }}
                  >
                    {part.sub}
                  </span>
                )}
                {part.sup && (
                  <span
                    style={{
                      fontFamily: theme.fonts.mono,
                      fontSize: 16,
                      color: partColor,
                      opacity: 0.65,
                      verticalAlign: "super",
                    }}
                  >
                    {part.sup}
                  </span>
                )}
              </div>
            );
          })}

          {/* Arrow — SVG draw-on */}
          {result && arrowProgress > 0.01 && (
            <svg
              width={ARROW_SVG_W * arrowProgress}
              height={36}
              viewBox={`0 0 ${ARROW_SVG_W} 36`}
              style={{ overflow: "visible", flexShrink: 0 }}
            >
              {/* Arrow shaft */}
              <line
                x1={4}
                y1={18}
                x2={Math.max(4, arrowDrawX - 12)}
                y2={18}
                stroke={accentColor}
                strokeWidth={2.5}
                strokeLinecap="round"
                opacity={0.8}
              />
              {/* Arrow head — only when mostly drawn */}
              {arrowProgress > 0.75 && (
                <path
                  d={`M ${arrowDrawX - 14} ${18 - 7} L ${arrowDrawX} 18 L ${arrowDrawX - 14} ${18 + 7}`}
                  fill="none"
                  stroke={accentColor}
                  strokeWidth={2.5}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity={interpolate(arrowProgress, [0.75, 1], [0, 0.8], {
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                  })}
                />
              )}
            </svg>
          )}

          {/* Result */}
          {result && resultOpacity > 0.01 && (
            <div
              style={{
                opacity: resultOpacity,
                transform: `scale(${resultScale})`,
                transformOrigin: "left center",
              }}
            >
              <div
                style={{
                  padding: "8px 20px",
                  borderRadius: 10,
                  background: `${accentColor}15`,
                  border: `2px solid ${accentColor}55`,
                  boxShadow: `0 0 20px ${accentColor}22`,
                }}
              >
                <span
                  style={{
                    fontFamily: theme.fonts.mono,
                    fontSize: 28,
                    fontWeight: 700,
                    color: accentColor,
                    letterSpacing: "-0.01em",
                  }}
                >
                  {result}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Divider */}
        {subtitle && resultOpacity > 0.3 && (
          <div
            style={{
              height: 1,
              background: `linear-gradient(90deg, ${accentColor}33, transparent)`,
              margin: "20px 0 14px",
              opacity: subtitleOpacity,
            }}
          />
        )}

        {/* Subtitle */}
        {subtitle && (
          <div
            style={{
              fontFamily: theme.fonts.body,
              fontSize: 13,
              color: theme.colors.inkSoft,
              lineHeight: 1.6,
              opacity: subtitleOpacity,
              maxWidth: 520,
            }}
          >
            {subtitle}
          </div>
        )}
      </div>
    </div>
  );
};
