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

interface TypewriterTextProps {
  theme: Theme;
  timing: { start: number; end?: number };
  text: string;
  delay?: number;
  speed?: number; // frames per character
  font?: "display" | "body" | "mono";
  color?: string;
  fontSize?: number;
  cursorChar?: string;
}

export const TypewriterText: React.FC<TypewriterTextProps> = ({
  theme,
  timing,
  text,
  delay = 0,
  speed = 2,
  font = "mono",
  color,
  fontSize = 32,
  cursorChar = "█",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const localFrame = frame - timing.start * fps - delay;
  const fontFamily = theme.fonts[font] ?? theme.fonts.mono;
  const textColor = color ?? theme.colors.ink;

  // How many characters to show
  const charsToShow = Math.floor(Math.max(0, localFrame) / speed);
  const visibleText = text.slice(0, charsToShow);
  const isDone = charsToShow >= text.length;

  // Cursor blink: 12-frame period after typing is done
  const blinkFrame = isDone ? localFrame - charsToShow * speed : localFrame % 24;
  const cursorOpacity = isDone
    ? interpolate(blinkFrame % 28, [0, 4, 14, 18, 28], [1, 1, 0, 0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 1;

  // Fade in the whole block
  const fadeIn = interpolate(localFrame, [0, 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Split text into lines for multiline support
  const lines = visibleText.split("\n");

  return (
    <div
      style={{
        opacity: fadeIn,
        fontFamily,
        fontSize,
        color: textColor,
        lineHeight: 1.6,
        letterSpacing: "0.01em",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
      }}
    >
      {lines.map((line, lineIndex) => (
        <div key={lineIndex} style={{ display: "flex", alignItems: "center" }}>
          <span>{line}</span>
          {/* Cursor only on last line */}
          {lineIndex === lines.length - 1 && (
            <span
              style={{
                display: "inline-block",
                color: theme.colors.ink,
                opacity: cursorOpacity,
                marginLeft: 2,
                fontSize: fontSize * 0.85,
                lineHeight: 1,
              }}
            >
              {cursorChar}
            </span>
          )}
        </div>
      ))}
    </div>
  );
};
