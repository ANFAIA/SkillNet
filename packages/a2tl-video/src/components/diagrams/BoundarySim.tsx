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

interface BoundaryCase {
  packet: string;
  label?: string;
  recipient: string;
  access: string;
  result: "pass" | "block";
}

interface BoundarySimProps {
  theme: Theme;
  timing: { start: number; end?: number };
  cases: BoundaryCase[];
  width?: number;
  height?: number;
  caseDuration?: number;
}

// A single boundary case animation — purely frame-based
const BoundaryCaseViz: React.FC<{
  caseData: BoundaryCase;
  localFrame: number;
  theme: Theme;
  fps: number;
  svgWidth: number;
  svgHeight: number;
  scopeId: string;
}> = ({ caseData, localFrame, theme, fps, svgWidth, svgHeight, scopeId }) => {
  const isPass = caseData.result === "pass";

  // Layout constants
  const packetY = svgHeight * 0.42;
  const gateX = svgWidth * 0.48;
  const recipientX = svgWidth * 0.78;

  // Packet travel phases:
  // 0..20:   packet slides in from left → just before gate
  // 20..30:  gate check (pulse/flash)
  // 30..50:  PASS → continues to recipient   /  BLOCK → bounces back
  // 50..65:  recipient pulses (PASS) or X flash (BLOCK)
  // 65..80:  result label fades in

  // Packet position
  const packetStartX = -80;
  const packetBeforeGate = gateX - 70;
  const packetAfterGate = recipientX - 40;
  const packetBounceBack = packetBeforeGate - 100;

  let packetX: number;
  let packetOpacity = 1;

  if (localFrame < 20) {
    packetX = interpolate(localFrame, [0, 20], [packetStartX, packetBeforeGate], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  } else if (localFrame < 30) {
    packetX = packetBeforeGate;
  } else if (isPass) {
    packetX = interpolate(localFrame, [30, 50], [packetBeforeGate, packetAfterGate], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    packetOpacity = interpolate(localFrame, [46, 54], [1, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  } else {
    // Block: bounce back
    packetX = interpolate(localFrame, [30, 46], [packetBeforeGate, packetBounceBack], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    packetOpacity = interpolate(localFrame, [44, 52], [1, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  }

  // Gate check flash
  const gateCheckIntensity = interpolate(localFrame, [20, 25, 30], [0, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Gate icon (checkmark / X) reveal
  const gateIconOpacity = interpolate(localFrame, [25, 32], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Recipient reveal
  const recipientScale = spring({
    frame: localFrame - 12,
    fps,
    config: { damping: 14, stiffness: 180 },
  });

  // Result label
  const resultOpacity = interpolate(localFrame, [60, 72], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Pass trail (green glow that follows packet through gate)
  const trailOpacity =
    isPass && localFrame >= 30
      ? interpolate(localFrame, [30, 38, 50], [0.7, 0.9, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : 0;

  // Block flash (red burst)
  const blockFlashOpacity =
    !isPass && localFrame >= 28
      ? interpolate(localFrame, [28, 32, 40], [0, 1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : 0;

  const passColor = theme.colors.green;
  const blockColor = theme.colors.red;
  const gateColor = isPass ? passColor : blockColor;

  // Packet pill width
  const pillW = 100;
  const pillH = 36;

  return (
    <g>
      {/* Background track */}
      <line
        x1={40}
        y1={packetY}
        x2={recipientX + 30}
        y2={packetY}
        stroke={theme.colors.grid}
        strokeWidth={1.5}
        strokeDasharray="6 6"
        opacity={0.3}
      />

      {/* PASS trail glow */}
      {isPass && (
        <rect
          x={packetBeforeGate}
          y={packetY - pillH / 2 - 6}
          width={packetX - packetBeforeGate + pillW}
          height={pillH + 12}
          rx={24}
          fill={passColor}
          opacity={trailOpacity * 0.25}
          filter={`url(#${scopeId}-glow)`}
        />
      )}

      {/* BLOCK red flash */}
      {!isPass && blockFlashOpacity > 0 && (
        <ellipse
          cx={gateX}
          cy={packetY}
          rx={60}
          ry={40}
          fill={blockColor}
          opacity={blockFlashOpacity * 0.35}
          filter={`url(#${scopeId}-glow)`}
        />
      )}

      {/* GATE — vertical bar */}
      <rect
        x={gateX - 5}
        y={svgHeight * 0.15}
        width={10}
        height={svgHeight * 0.7}
        rx={5}
        fill={gateColor}
        opacity={0.2 + gateCheckIntensity * 0.5}
        filter={gateCheckIntensity > 0.1 ? `url(#${scopeId}-glow)` : undefined}
      />
      <rect
        x={gateX - 2}
        y={svgHeight * 0.15}
        width={4}
        height={svgHeight * 0.7}
        rx={2}
        fill={gateColor}
        opacity={0.7 + gateCheckIntensity * 0.3}
      />

      {/* Gate icon */}
      <g
        transform={`translate(${gateX}, ${svgHeight * 0.15 - 24})`}
        opacity={gateIconOpacity}
      >
        <circle r={16} fill={gateColor} opacity={0.9} />
        {isPass ? (
          // Checkmark
          <polyline
            points="-6,0 -1,6 8,-6"
            fill="none"
            stroke="white"
            strokeWidth={2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ) : (
          // X
          <>
            <line x1={-6} y1={-6} x2={6} y2={6} stroke="white" strokeWidth={2.5} strokeLinecap="round" />
            <line x1={6} y1={-6} x2={-6} y2={6} stroke="white" strokeWidth={2.5} strokeLinecap="round" />
          </>
        )}
      </g>

      {/* Gate label */}
      <text
        x={gateX}
        y={svgHeight * 0.85 + 16}
        textAnchor="middle"
        fill={theme.colors.inkFaint}
        fontSize={10}
        fontFamily={theme.fonts.mono}
        opacity={0.7}
      >
        GATE
      </text>

      {/* DATA PACKET */}
      {packetOpacity > 0.01 && (
        <g transform={`translate(${packetX}, ${packetY})`} opacity={packetOpacity}>
          {/* Pill shadow */}
          <rect
            x={-pillW / 2}
            y={-pillH / 2 + 3}
            width={pillW}
            height={pillH}
            rx={pillH / 2}
            fill={theme.colors.bg}
            opacity={0.5}
          />
          {/* Pill body */}
          <rect
            x={-pillW / 2}
            y={-pillH / 2}
            width={pillW}
            height={pillH}
            rx={pillH / 2}
            fill={theme.colors.bg2}
            stroke={theme.colors.inkSoft}
            strokeWidth={1.5}
            strokeOpacity={0.6}
          />
          {/* Pill glow */}
          <rect
            x={-pillW / 2}
            y={-pillH / 2}
            width={pillW}
            height={pillH}
            rx={pillH / 2}
            fill="none"
            stroke={isPass ? passColor : theme.colors.amber}
            strokeWidth={1}
            opacity={0.4}
            filter={`url(#${scopeId}-glow)`}
          />
          {/* Packet label */}
          <text
            x={0}
            y={0}
            textAnchor="middle"
            dominantBaseline="middle"
            fill={theme.colors.ink}
            fontSize={11}
            fontWeight={600}
            fontFamily={theme.fonts.mono}
          >
            {caseData.packet}
          </text>
        </g>
      )}

      {/* RECIPIENT circle */}
      <g
        transform={`translate(${recipientX}, ${packetY}) scale(${recipientScale})`}
        opacity={Math.min(recipientScale, 1)}
      >
        <circle
          r={38}
          fill={theme.colors.bg2}
          stroke={isPass ? passColor : blockColor}
          strokeWidth={2}
          strokeOpacity={0.5}
        />
        <circle r={36} fill={isPass ? passColor : blockColor} opacity={0.08} />

        {/* Recipient name */}
        <text
          x={0}
          y={-8}
          textAnchor="middle"
          dominantBaseline="middle"
          fill={theme.colors.ink}
          fontSize={11}
          fontWeight={600}
          fontFamily={theme.fonts.body}
        >
          {caseData.recipient}
        </text>
        {/* Access tag */}
        <text
          x={0}
          y={9}
          textAnchor="middle"
          dominantBaseline="middle"
          fill={theme.colors.inkSoft}
          fontSize={9}
          fontFamily={theme.fonts.mono}
        >
          {caseData.access}
        </text>
      </g>

      {/* Result label */}
      {resultOpacity > 0 && (
        <g opacity={resultOpacity}>
          <rect
            x={gateX - 44}
            y={packetY + 52}
            width={88}
            height={26}
            rx={13}
            fill={isPass ? passColor : blockColor}
            opacity={0.9}
          />
          <text
            x={gateX}
            y={packetY + 65}
            textAnchor="middle"
            dominantBaseline="middle"
            fill="white"
            fontSize={12}
            fontWeight={700}
            fontFamily={theme.fonts.mono}
            letterSpacing="0.08em"
          >
            {isPass ? "PASS" : "BLOCK"}
          </text>
        </g>
      )}

      {/* Case label */}
      {caseData.label && (
        <text
          x={svgWidth / 2}
          y={svgHeight - 8}
          textAnchor="middle"
          fill={theme.colors.inkFaint}
          fontSize={11}
          fontFamily={theme.fonts.body}
          opacity={interpolate(localFrame, [0, 10], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          })}
        >
          {caseData.label}
        </text>
      )}
    </g>
  );
};

export const BoundarySim: React.FC<BoundarySimProps> = ({
  theme,
  timing,
  cases,
  width = 900,
  height = 320,
  caseDuration = 90,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const localFrame = frame - timing.start * fps;
  const scopeId = `bs-${timing.start}`.replace(".", "_");

  // Determine which case is active
  const caseIndex = Math.floor(localFrame / caseDuration);
  const activeCaseIndex = Math.min(caseIndex, cases.length - 1);
  const localCaseFrame = localFrame - activeCaseIndex * caseDuration;

  const activeCase = cases[activeCaseIndex];
  if (!activeCase) return null;

  // Case indicator dots
  const dotY = 18;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      style={{ overflow: "visible" }}
    >
      <defs>
        <filter id={`${scopeId}-glow`} x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="6" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id={`${scopeId}-glow-soft`} x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Case progress dots */}
      {cases.length > 1 && (
        <g transform={`translate(${width / 2 - (cases.length * 20) / 2}, ${dotY})`}>
          {cases.map((_, i) => (
            <circle
              key={i}
              cx={i * 20}
              cy={0}
              r={i === activeCaseIndex ? 5 : 3.5}
              fill={i === activeCaseIndex ? theme.colors.ink : theme.colors.inkFaint}
              opacity={i === activeCaseIndex ? 1 : 0.4}
            />
          ))}
        </g>
      )}

      {/* Active case visualization */}
      <g transform={`translate(0, 30)`}>
        <BoundaryCaseViz
          key={activeCaseIndex}
          caseData={activeCase}
          localFrame={localCaseFrame}
          theme={theme}
          fps={fps}
          svgWidth={width}
          svgHeight={height - 30}
          scopeId={scopeId}
        />
      </g>
    </svg>
  );
};
