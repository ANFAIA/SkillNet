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

interface NodeDef {
  id: string;
  label: string;
  x: number; // 0..1 normalized
  y: number; // 0..1 normalized
  color?: string;
  size?: number;
  shape?: "circle" | "rect";
}

interface EdgeDef {
  from: string;
  to: string;
  style?: "solid" | "dashed" | "dotted";
  animate?: boolean;
  label?: string;
  color?: string;
}

interface NodeGraphProps {
  theme: Theme;
  timing: { start: number; end?: number };
  nodes: NodeDef[];
  edges: EdgeDef[];
  annotation?: string;
  width?: number;
  height?: number;
  nodeStagger?: number;
  edgeStagger?: number;
}

export const NodeGraph: React.FC<NodeGraphProps> = ({
  theme,
  timing,
  nodes,
  edges,
  annotation,
  width = 900,
  height = 500,
  nodeStagger = 6,
  edgeStagger = 8,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const localFrame = frame - timing.start * fps;

  // Build node position map
  const nodeMap = new Map<string, { px: number; py: number; def: NodeDef }>();
  nodes.forEach((n) => {
    nodeMap.set(n.id, {
      px: n.x * width,
      py: n.y * height,
      def: n,
    });
  });

  const nodesStartFrame = 0;
  const edgesStartFrame = nodes.length * nodeStagger + 10;

  // Unique gradient IDs scoped to timing
  const scopeId = `ng-${timing.start}`.replace(".", "_");

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      style={{ overflow: "visible" }}
    >
      <defs>
        {/* Glow filter for nodes */}
        <filter id={`${scopeId}-glow`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>

        <filter id={`${scopeId}-glow-strong`} x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="8" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>

        {/* Arrow marker */}
        <marker
          id={`${scopeId}-arrow`}
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill={theme.colors.inkSoft} />
        </marker>

        {/* Per-node gradients */}
        {nodes.map((n, i) => {
          const nodeColor = n.color ?? theme.colors.ink;
          return (
            <radialGradient
              key={n.id}
              id={`${scopeId}-node-${i}`}
              cx="35%"
              cy="30%"
              r="65%"
            >
              <stop offset="0%" stopColor={nodeColor} stopOpacity="0.95" />
              <stop offset="100%" stopColor={nodeColor} stopOpacity="0.6" />
            </radialGradient>
          );
        })}
      </defs>

      {/* EDGES — drawn first (behind nodes) */}
      {edges.map((edge, ei) => {
        const fromNode = nodeMap.get(edge.from);
        const toNode = nodeMap.get(edge.to);
        if (!fromNode || !toNode) return null;

        const edgeFrame = localFrame - edgesStartFrame - ei * edgeStagger;
        const drawProgress = interpolate(edgeFrame, [0, 22], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        const labelOpacity = interpolate(edgeFrame, [20, 28], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        if (drawProgress <= 0) return null;

        const x1 = fromNode.px;
        const y1 = fromNode.py;
        const x2 = toNode.px;
        const y2 = toNode.py;

        // Control point for curve
        const midX = (x1 + x2) / 2;
        const midY = (y1 + y2) / 2 - 30;

        const pathData = `M ${x1} ${y1} Q ${midX} ${midY} ${x2} ${y2}`;

        // Total path length estimate for dashoffset animation
        const dx = x2 - x1;
        const dy = y2 - y1;
        const pathLen = Math.sqrt(dx * dx + dy * dy) * 1.1;

        const dashoffset = pathLen * (1 - drawProgress);
        const strokeDash =
          edge.style === "dashed"
            ? `8 6`
            : edge.style === "dotted"
            ? `2 6`
            : `${pathLen}`;

        const edgeColor = edge.color ?? theme.colors.inkSoft;

        return (
          <g key={`${edge.from}-${edge.to}-${ei}`}>
            {/* Glow trail */}
            <path
              d={pathData}
              fill="none"
              stroke={edgeColor}
              strokeWidth="6"
              strokeDasharray={`${pathLen}`}
              strokeDashoffset={pathLen * (1 - drawProgress * 0.8)}
              opacity={0.15}
              strokeLinecap="round"
            />
            {/* Main edge */}
            <path
              d={pathData}
              fill="none"
              stroke={edgeColor}
              strokeWidth={1.5}
              strokeDasharray={
                edge.style === "dashed"
                  ? `8 6`
                  : edge.style === "dotted"
                  ? `2 5`
                  : `${pathLen} ${pathLen}`
              }
              strokeDashoffset={
                edge.style === "dashed" || edge.style === "dotted"
                  ? 0
                  : dashoffset
              }
              strokeLinecap="round"
              markerEnd={`url(#${scopeId}-arrow)`}
              opacity={0.75}
            />
            {/* Edge label */}
            {edge.label && (
              <text
                x={midX}
                y={midY - 8}
                textAnchor="middle"
                fill={theme.colors.inkFaint}
                fontSize={11}
                fontFamily={theme.fonts.mono}
                opacity={labelOpacity}
              >
                {edge.label}
              </text>
            )}
          </g>
        );
      })}

      {/* NODES */}
      {nodes.map((node, ni) => {
        const pos = nodeMap.get(node.id);
        if (!pos) return null;

        const nodeFrame = localFrame - nodesStartFrame - ni * nodeStagger;

        const scale = spring({
          frame: nodeFrame,
          fps,
          config: { damping: 14, stiffness: 180 },
        });

        const opacity = interpolate(nodeFrame, [0, 10], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        if (scale <= 0.01) return null;

        const r = (node.size ?? 28) * scale;
        const nodeColor = node.color ?? theme.colors.ink;
        const isRect = node.shape === "rect";

        return (
          <g
            key={node.id}
            transform={`translate(${pos.px}, ${pos.py})`}
            opacity={opacity}
          >
            {/* Outer glow ring */}
            {isRect ? (
              <rect
                x={-r * 1.2}
                y={-r * 0.7}
                width={r * 2.4}
                height={r * 1.4}
                rx={8}
                fill={nodeColor}
                opacity={0.12}
                filter={`url(#${scopeId}-glow-strong)`}
              />
            ) : (
              <circle
                r={r * 1.4}
                fill={nodeColor}
                opacity={0.12}
                filter={`url(#${scopeId}-glow-strong)`}
              />
            )}

            {/* Node body */}
            {isRect ? (
              <rect
                x={-r}
                y={-r * 0.55}
                width={r * 2}
                height={r * 1.1}
                rx={6}
                fill={`url(#${scopeId}-node-${ni})`}
                stroke={nodeColor}
                strokeWidth={1.5}
                strokeOpacity={0.6}
              />
            ) : (
              <circle
                r={r}
                fill={`url(#${scopeId}-node-${ni})`}
                stroke={nodeColor}
                strokeWidth={1.5}
                strokeOpacity={0.6}
              />
            )}

            {/* Node label */}
            <text
              textAnchor="middle"
              dominantBaseline="middle"
              fill="white"
              fontSize={Math.max(10, r * 0.45)}
              fontFamily={theme.fonts.body}
              fontWeight={600}
              dy={0}
            >
              {node.label}
            </text>
          </g>
        );
      })}

      {/* Annotation */}
      {annotation && (
        <text
          x={width / 2}
          y={height - 12}
          textAnchor="middle"
          fill={theme.colors.inkFaint}
          fontSize={13}
          fontFamily={theme.fonts.body}
          opacity={interpolate(localFrame, [edgesStartFrame + 20, edgesStartFrame + 34], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          })}
        >
          {annotation}
        </text>
      )}
    </svg>
  );
};
