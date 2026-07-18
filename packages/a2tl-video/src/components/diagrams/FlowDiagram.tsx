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

interface FlowStep {
  label: string;
  desc?: string;
  icon?: string;
  color?: string;
}

interface FlowDiagramProps {
  theme: Theme;
  timing: { start: number; end?: number };
  steps: FlowStep[];
  connectors?: "arrow" | "line" | "curve";
  stagger?: number;
  width?: number;
  height?: number;
}

const CARD_W = 160;
const CARD_H = 100;
const CONNECTOR_W = 60;
const STEP_STAGGER = 10;

export const FlowDiagram: React.FC<FlowDiagramProps> = ({
  theme,
  timing,
  steps,
  connectors = "arrow",
  stagger = STEP_STAGGER,
  width = 960,
  height = 240,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const localFrame = frame - timing.start * fps;

  const totalStepWidth = steps.length * CARD_W + (steps.length - 1) * CONNECTOR_W;
  const startX = (width - totalStepWidth) / 2;
  const centerY = height / 2;

  const scopeId = `fd-${timing.start}`.replace(".", "_");

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      style={{ overflow: "visible" }}
    >
      <defs>
        {/* Arrow marker */}
        <marker
          id={`${scopeId}-arrow`}
          viewBox="0 0 12 12"
          refX="10"
          refY="6"
          markerWidth="7"
          markerHeight="7"
          orient="auto"
        >
          <path d="M 0 1 L 10 6 L 0 11 z" fill={theme.colors.inkSoft} opacity={0.8} />
        </marker>

        {/* Per-step gradients */}
        {steps.map((step, i) => {
          const color = step.color ?? theme.colors.ink;
          return (
            <linearGradient
              key={i}
              id={`${scopeId}-step-${i}`}
              x1="0%"
              y1="0%"
              x2="100%"
              y2="100%"
            >
              <stop offset="0%" stopColor={color} stopOpacity="0.18" />
              <stop offset="100%" stopColor={color} stopOpacity="0.06" />
            </linearGradient>
          );
        })}

        {/* Drop shadow filter */}
        <filter id={`${scopeId}-shadow`} x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow
            dx="0"
            dy="4"
            stdDeviation="8"
            floodColor={theme.colors.bg}
            floodOpacity="0.5"
          />
        </filter>
      </defs>

      {steps.map((step, i) => {
        const stepFrame = localFrame - i * stagger;
        const cardX = startX + i * (CARD_W + CONNECTOR_W);
        const cardY = centerY - CARD_H / 2;

        const scale = spring({
          frame: stepFrame,
          fps,
          config: { damping: 16, stiffness: 200 },
        });

        const opacity = interpolate(stepFrame, [0, 12], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        const stepColor = step.color ?? theme.colors.ink;
        const isVisible = scale > 0.01;

        // Connector draw-on (after the step appears)
        const connectorFrame = stepFrame - 14;
        const connectorProgress = i < steps.length - 1
          ? interpolate(connectorFrame, [0, 16], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            })
          : 0;

        const connectorX1 = cardX + CARD_W;
        const connectorX2 = cardX + CARD_W + CONNECTOR_W;
        const connectorDrawX = connectorX1 + (connectorX2 - connectorX1) * connectorProgress;

        return (
          <g key={i}>
            {/* Connector to next step */}
            {i < steps.length - 1 && connectorProgress > 0 && (
              <g>
                {/* Connector glow */}
                <line
                  x1={connectorX1}
                  y1={centerY}
                  x2={connectorDrawX}
                  y2={centerY}
                  stroke={theme.colors.inkSoft}
                  strokeWidth={6}
                  opacity={0.1}
                  strokeLinecap="round"
                />
                {/* Connector line */}
                <line
                  x1={connectorX1}
                  y1={centerY}
                  x2={connectorDrawX}
                  y2={centerY}
                  stroke={theme.colors.inkSoft}
                  strokeWidth={1.5}
                  opacity={0.6}
                  strokeLinecap="round"
                  markerEnd={connectorProgress >= 0.95 ? `url(#${scopeId}-arrow)` : undefined}
                />
              </g>
            )}

            {/* Step card */}
            {isVisible && (
              <g
                transform={`translate(${cardX + CARD_W / 2}, ${centerY}) scale(${scale}) translate(${-CARD_W / 2}, ${-CARD_H / 2})`}
                opacity={opacity}
              >
                {/* Card shadow */}
                <rect
                  width={CARD_W}
                  height={CARD_H}
                  rx={12}
                  fill={theme.colors.bg2}
                  filter={`url(#${scopeId}-shadow)`}
                />
                {/* Card background */}
                <rect
                  width={CARD_W}
                  height={CARD_H}
                  rx={12}
                  fill={`url(#${scopeId}-step-${i})`}
                />
                {/* Card border */}
                <rect
                  width={CARD_W}
                  height={CARD_H}
                  rx={12}
                  fill="none"
                  stroke={stepColor}
                  strokeWidth={1.5}
                  opacity={0.4}
                />

                {/* Step number badge */}
                <circle
                  cx={24}
                  cy={24}
                  r={14}
                  fill={stepColor}
                  opacity={0.85}
                />
                <text
                  x={24}
                  y={24}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill="white"
                  fontSize={12}
                  fontWeight={700}
                  fontFamily={theme.fonts.mono}
                >
                  {step.icon ?? `${i + 1}`}
                </text>

                {/* Step label */}
                <text
                  x={CARD_W / 2}
                  y={54}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill={theme.colors.ink}
                  fontSize={13}
                  fontWeight={600}
                  fontFamily={theme.fonts.body}
                >
                  {step.label}
                </text>

                {/* Step desc */}
                {step.desc && (
                  <text
                    x={CARD_W / 2}
                    y={74}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill={theme.colors.inkSoft}
                    fontSize={10}
                    fontFamily={theme.fonts.body}
                  >
                    {step.desc}
                  </text>
                )}

                {/* Bottom accent bar */}
                <rect
                  x={24}
                  y={CARD_H - 8}
                  width={CARD_W - 48}
                  height={3}
                  rx={2}
                  fill={stepColor}
                  opacity={0.5}
                />
              </g>
            )}
          </g>
        );
      })}
    </svg>
  );
};
