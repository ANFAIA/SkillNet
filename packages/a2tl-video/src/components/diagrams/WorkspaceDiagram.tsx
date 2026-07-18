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

interface WorkspaceZone {
  side: "left" | "right" | "center" | "top" | "bottom";
  label: string;
  tag?: string;
  color?: string;
}

interface WorkspaceDiagramProps {
  theme: Theme;
  timing: { start: number; end?: number };
  shared: string;
  zones: WorkspaceZone[];
  width?: number;
  height?: number;
}

export const WorkspaceDiagram: React.FC<WorkspaceDiagramProps> = ({
  theme,
  timing,
  shared,
  zones,
  width = 860,
  height = 440,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const localFrame = frame - timing.start * fps;

  const scopeId = `ws-${timing.start}`.replace(".", "_");

  const PAD = 24;
  const outerW = width - PAD * 2;
  const outerH = height - PAD * 2;
  const outerX = PAD;
  const outerY = PAD + 24; // room for shared label on top

  // Outer frame draw-on
  const outerProgress = interpolate(localFrame, [0, 28], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Shared label fade
  const sharedLabelOpacity = interpolate(localFrame, [20, 32], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Determine zone layout
  const leftZones = zones.filter((z) => z.side === "left");
  const rightZones = zones.filter((z) => z.side === "right");
  const centerZones = zones.filter((z) => z.side === "center");

  const ZONE_MARGIN = 20;
  const ZONE_TOP = outerY + ZONE_MARGIN + 20;
  const ZONE_HEIGHT = outerH - ZONE_MARGIN * 2 - 20;
  const ZONE_WIDTH = (outerW - ZONE_MARGIN * 3) / 2 - ZONE_MARGIN;

  // Build zone rects
  const buildZone = (zone: WorkspaceZone, index: number, allSameSide: WorkspaceZone[]) => {
    const totalOnSide = allSameSide.length;
    const slotH = (ZONE_HEIGHT - ZONE_MARGIN * (totalOnSide - 1)) / totalOnSide;
    const slotY = ZONE_TOP + index * (slotH + ZONE_MARGIN);

    let zoneX: number;
    let zoneW: number;

    if (zone.side === "left") {
      zoneX = outerX + ZONE_MARGIN;
      zoneW = ZONE_WIDTH;
    } else if (zone.side === "right") {
      zoneX = outerX + outerW - ZONE_MARGIN - ZONE_WIDTH;
      zoneW = ZONE_WIDTH;
    } else {
      zoneX = outerX + ZONE_MARGIN + ZONE_WIDTH + ZONE_MARGIN;
      zoneW = outerW - ZONE_MARGIN * 2 - ZONE_WIDTH * 2 - ZONE_MARGIN * 2;
    }

    return { x: zoneX, y: slotY, w: zoneW, h: slotH };
  };

  const allZonesWithPos = zones.map((zone, globalIdx) => {
    const sameSide = zones.filter((z) => z.side === zone.side);
    const sideIdx = sameSide.indexOf(zone);
    const pos = buildZone(zone, sideIdx, sameSide);
    return { zone, pos, globalIdx };
  });

  // Dashed center dividers
  const hasLeft = leftZones.length > 0;
  const hasRight = rightZones.length > 0;
  const dividerX = outerX + ZONE_MARGIN + ZONE_WIDTH + ZONE_MARGIN / 2;
  const dividerX2 = outerX + outerW - ZONE_MARGIN - ZONE_WIDTH - ZONE_MARGIN / 2;

  const dividerOpacity = interpolate(localFrame, [24, 36], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      style={{ overflow: "visible" }}
    >
      <defs>
        {/* Outer workspace gradient */}
        <linearGradient id={`${scopeId}-outer-grad`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor={theme.colors.ink} stopOpacity="0.05" />
          <stop offset="100%" stopColor={theme.colors.ink} stopOpacity="0.02" />
        </linearGradient>

        {/* Zone gradients */}
        {allZonesWithPos.map(({ zone, globalIdx }) => {
          const color = zone.color ?? (zone.side === "left" ? theme.colors.purple : zone.side === "right" ? theme.colors.green : theme.colors.amber);
          return (
            <linearGradient
              key={globalIdx}
              id={`${scopeId}-zone-${globalIdx}`}
              x1="0%"
              y1="0%"
              x2="100%"
              y2="100%"
            >
              <stop offset="0%" stopColor={color} stopOpacity="0.14" />
              <stop offset="100%" stopColor={color} stopOpacity="0.04" />
            </linearGradient>
          );
        })}

        {/* Glow filter */}
        <filter id={`${scopeId}-glow`} x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Outer workspace fill */}
      <rect
        x={outerX}
        y={outerY}
        width={outerW * outerProgress}
        height={outerH}
        fill={`url(#${scopeId}-outer-grad)`}
        opacity={0.8}
      />

      {/* Outer workspace border — draw on */}
      <rect
        x={outerX}
        y={outerY}
        width={outerW}
        height={outerH}
        rx={16}
        fill="none"
        stroke={theme.colors.inkSoft}
        strokeWidth={2}
        strokeDasharray={`${(outerW + outerH) * 2}`}
        strokeDashoffset={`${(outerW + outerH) * 2 * (1 - outerProgress)}`}
        opacity={0.35}
      />

      {/* Shared workspace label */}
      <text
        x={outerX + 16}
        y={outerY - 8}
        fill={theme.colors.inkSoft}
        fontSize={12}
        fontFamily={theme.fonts.mono}
        fontWeight={600}
        letterSpacing="0.1em"
        opacity={sharedLabelOpacity}
      >
        {shared.toUpperCase()}
      </text>

      {/* Dashed dividers */}
      {hasLeft && (
        <line
          x1={dividerX}
          y1={ZONE_TOP}
          x2={dividerX}
          y2={ZONE_TOP + ZONE_HEIGHT}
          stroke={theme.colors.grid}
          strokeWidth={1.5}
          strokeDasharray="6 8"
          opacity={dividerOpacity * 0.5}
        />
      )}
      {hasRight && (
        <line
          x1={dividerX2}
          y1={ZONE_TOP}
          x2={dividerX2}
          y2={ZONE_TOP + ZONE_HEIGHT}
          stroke={theme.colors.grid}
          strokeWidth={1.5}
          strokeDasharray="6 8"
          opacity={dividerOpacity * 0.5}
        />
      )}

      {/* Zone cards */}
      {allZonesWithPos.map(({ zone, pos, globalIdx }) => {
        const zoneFrame = localFrame - 20 - globalIdx * 10;
        const zoneColor = zone.color ?? (zone.side === "left" ? theme.colors.purple : zone.side === "right" ? theme.colors.green : theme.colors.amber);

        // Zones slide in from their side
        const slideX = zone.side === "left"
          ? interpolate(zoneFrame, [0, 20], [-60, 0], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            })
          : zone.side === "right"
          ? interpolate(zoneFrame, [0, 20], [60, 0], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            })
          : 0;

        const zoneOpacity = interpolate(zoneFrame, [0, 16], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        const labelOpacity = interpolate(zoneFrame, [14, 24], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        return (
          <g
            key={globalIdx}
            transform={`translate(${slideX}, 0)`}
            opacity={zoneOpacity}
          >
            {/* Zone background */}
            <rect
              x={pos.x}
              y={pos.y}
              width={pos.w}
              height={pos.h}
              rx={10}
              fill={`url(#${scopeId}-zone-${globalIdx})`}
            />
            {/* Zone border (dashed) */}
            <rect
              x={pos.x}
              y={pos.y}
              width={pos.w}
              height={pos.h}
              rx={10}
              fill="none"
              stroke={zoneColor}
              strokeWidth={1.5}
              strokeDasharray="5 4"
              opacity={0.5}
            />

            {/* Zone label */}
            <text
              x={pos.x + 16}
              y={pos.y + 22}
              fill={zoneColor}
              fontSize={13}
              fontWeight={700}
              fontFamily={theme.fonts.body}
              opacity={labelOpacity}
            >
              {zone.label}
            </text>

            {/* Zone tag badge */}
            {zone.tag && (
              <g opacity={labelOpacity}>
                <rect
                  x={pos.x + pos.w - 8}
                  y={pos.y + 8}
                  width={zone.tag.length * 7 + 16}
                  height={20}
                  rx={10}
                  fill={zoneColor}
                  opacity={0.15}
                  transform={`translate(${-(zone.tag.length * 7 + 24)}, 0)`}
                />
                <text
                  x={pos.x + pos.w - 16}
                  y={pos.y + 18}
                  textAnchor="end"
                  fill={zoneColor}
                  fontSize={10}
                  fontWeight={600}
                  fontFamily={theme.fonts.mono}
                  letterSpacing="0.06em"
                >
                  {zone.tag}
                </text>
              </g>
            )}

            {/* Decorative dots pattern */}
            {[0, 1, 2].map((di) => (
              <circle
                key={di}
                cx={pos.x + pos.w - 20 - di * 12}
                cy={pos.y + pos.h - 18}
                r={3}
                fill={zoneColor}
                opacity={0.25}
              />
            ))}
          </g>
        );
      })}
    </svg>
  );
};
