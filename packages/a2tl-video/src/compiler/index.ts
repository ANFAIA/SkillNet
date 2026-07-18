/**
 * VDSL Compiler
 *
 * Takes a parsed VDSLSpec (JSON AST) and generates a complete, standalone
 * Remotion `.jsx` file ready to be rendered with `npx remotion render`.
 *
 * Pipeline:
 *   VDSLSpec  →  compile()  →  JSX string
 */

import type {
  VDSLSpec,
  Scene,
  Component,
  TextComponent,
  TextCycleComponent,
  LabelComponent,
  TriptychComponent,
  StepSequenceComponent,
  ComparisonComponent,
  CardComponent,
  CodeComponent,
  TraceLogComponent,
  VizComponent,
  BylineComponent,
} from "../parser/types";
import { indent, propsToJSX, escapeString, serializeValue } from "./codegen";

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface CompileOptions {
  /**
   * Override the theme name. If omitted the theme from VDSLSpec is used.
   */
  themeName?: string;
  /**
   * Name of the exported composition component (default: "Video").
   */
  componentName?: string;
}

/**
 * Compiles a parsed VDSL spec into a complete Remotion `.jsx` file string.
 *
 * The generated file:
 *  - imports React, Remotion primitives, vdsl components and themes
 *  - resolves the theme at module level
 *  - exports a single composition component (`Video` by default)
 *  - wraps every scene in a `<Sequence>` + `<GridCanvas>` with exact timing
 */
export function compile(spec: VDSLSpec, options: CompileOptions = {}): string {
  const themeName = options.themeName ?? spec.theme ?? "cobalt-grid";
  const componentName = options.componentName ?? "Video";

  // Collect which component names we actually need to import
  const usedComponents = collectUsedComponents(spec);

  const sections: string[] = [];

  // 1. Imports
  sections.push(buildImports(usedComponents, themeName));

  // 2. Theme constant
  sections.push(`const theme = themes['${themeName}'];`);

  // 3. Main composition
  sections.push(buildComposition(spec, componentName));

  return sections.join("\n\n") + "\n";
}

// ---------------------------------------------------------------------------
// Import collection
// ---------------------------------------------------------------------------

const COMPONENT_IMPORTS: Record<string, string> = {
  WordReveal: "WordReveal",
  TypewriterText: "TypewriterText",
  FadeText: "FadeText",
  TextCycle: "TextCycle",
  Label: "Label",
  Triptych: "Triptych",
  StepSequence: "StepSequence",
  Comparison: "Comparison",
  FormulaCard: "FormulaCard",
  TraceLog: "TraceLog",
  NodeGraph: "NodeGraph",
  FlowDiagram: "FlowDiagram",
  BoundarySim: "BoundarySim",
  WorkspaceDiagram: "WorkspaceDiagram",
  ProtocolCompare: "ProtocolCompare",
  Byline: "Byline",
  GridCanvas: "GridCanvas",
};

function collectUsedComponents(spec: VDSLSpec): Set<string> {
  const used = new Set<string>(["GridCanvas"]);

  for (const scene of spec.scenes) {
    for (const comp of scene.components) {
      switch (comp.type) {
        case "text": {
          const tc = comp as TextComponent;
          if (tc.reveal === "typewriter") used.add("TypewriterText");
          else if (tc.reveal === "fade" || tc.reveal === "none") used.add("FadeText");
          else used.add("WordReveal");
          break;
        }
        case "text-cycle":
          used.add("TextCycle");
          break;
        case "label":
          used.add("Label");
          break;
        case "triptych":
          used.add("Triptych");
          break;
        case "step-sequence":
          used.add("StepSequence");
          break;
        case "comparison":
          used.add("Comparison");
          break;
        case "card":
          used.add("FormulaCard");
          break;
        case "code":
          used.add("TypewriterText");
          break;
        case "trace-log":
          used.add("TraceLog");
          break;
        case "viz": {
          const vc = comp as VizComponent;
          switch (vc.vizType) {
            case "node-graph":      used.add("NodeGraph"); break;
            case "flow-diagram":    used.add("FlowDiagram"); break;
            case "boundary-sim":    used.add("BoundarySim"); break;
            case "workspace":       used.add("WorkspaceDiagram"); break;
            case "protocol-compare":used.add("ProtocolCompare"); break;
            case "trace-log":       used.add("TraceLog"); break;
            default:                used.add("NodeGraph"); // generic fallback
          }
          break;
        }
        case "byline":
          used.add("Byline");
          break;
      }
    }
  }

  return used;
}

// ---------------------------------------------------------------------------
// Import block
// ---------------------------------------------------------------------------

function buildImports(used: Set<string>, _themeName: string): string {
  const vdslComponents = [...used].filter((c) => c in COMPONENT_IMPORTS).sort();

  const lines: string[] = [
    `import React from 'react';`,
    `import { Sequence, AbsoluteFill, useCurrentFrame, useVideoConfig, registerRoot, Composition } from 'remotion';`,
    `import { ${vdslComponents.join(", ")} } from 'vdsl/components';`,
    `import { themes } from 'vdsl/themes';`,
  ];

  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Composition component
// ---------------------------------------------------------------------------

function buildComposition(spec: VDSLSpec, componentName: string): string {
  const sceneBlocks = spec.scenes.map((scene, i) => buildScene(scene, i, spec));

  const body = sceneBlocks.join("\n");

  return [
    `export const ${componentName} = () => {`,
    `  return (`,
    `    <AbsoluteFill>`,
    indent(body, 3),
    `    </AbsoluteFill>`,
    `  );`,
    `};`,
  ].join("\n");
}

// ---------------------------------------------------------------------------
// Scene → <Sequence><GridCanvas>…</GridCanvas></Sequence>
// ---------------------------------------------------------------------------

function buildScene(scene: Scene, index: number, spec: VDSLSpec): string {
  // Compute cumulative start frame for this scene
  const startFrame = computeSceneStartFrame(spec, index);
  const durationFrames = Math.round(scene.duration * 30);

  // Timing object covers the full scene duration (in seconds from absolute 0)
  const sceneStartSec = startFrame / 30;
  const sceneEndSec = sceneStartSec + scene.duration;

  const componentLines = scene.components
    .map((comp) => buildComponent(comp, sceneStartSec))
    .filter(Boolean)
    .join("\n");

  const gridProps = propsToJSX({
    theme: "{theme}",
    timing: `{{ start: ${sceneStartSec}, end: ${sceneEndSec} }}`,
  });

  // We need to emit the brace-wrapped expressions literally, so build manually
  const gridCanvasOpen = `<GridCanvas theme={theme} timing={{ start: ${sceneStartSec}, end: ${sceneEndSec} }}>`;
  const gridCanvasClose = `</GridCanvas>`;

  const sceneName = scene.title ? escapeString(scene.title) : `Scene ${index + 1}`;

  const lines: string[] = [
    `{/* Scene ${index + 1}: ${sceneName} */}`,
    `<Sequence from={${startFrame}} durationInFrames={${durationFrames}}>`,
    `  ${gridCanvasOpen}`,
    indent(componentLines || "    {/* empty scene */}", 2),
    `  ${gridCanvasClose}`,
    `</Sequence>`,
  ];

  return lines.join("\n");
}

function computeSceneStartFrame(spec: VDSLSpec, index: number): number {
  let frame = 0;
  for (let i = 0; i < index; i++) {
    frame += Math.round(spec.scenes[i].duration * 30);
  }
  return frame;
}

// ---------------------------------------------------------------------------
// Component dispatch
// ---------------------------------------------------------------------------

function buildComponent(comp: Component, sceneStartSec: number): string {
  switch (comp.type) {
    case "text":        return buildText(comp as TextComponent);
    case "text-cycle":  return buildTextCycle(comp as TextCycleComponent);
    case "label":       return buildLabel(comp as LabelComponent);
    case "triptych":    return buildTriptych(comp as TriptychComponent);
    case "step-sequence": return buildStepSequence(comp as StepSequenceComponent);
    case "comparison":  return buildComparison(comp as ComparisonComponent);
    case "card":        return buildCard(comp as CardComponent);
    case "code":        return buildCode(comp as CodeComponent);
    case "trace-log":   return buildTraceLog(comp as TraceLogComponent);
    case "viz":         return buildViz(comp as VizComponent);
    case "byline":      return buildByline(comp as BylineComponent);
    default:            return `{/* unknown component type: ${(comp as Component).type} */}`;
  }
}

// ---------------------------------------------------------------------------
// Text
// ---------------------------------------------------------------------------

function buildText(comp: TextComponent): string {
  const reveal = comp.reveal ?? "word-stagger";

  if (reveal === "typewriter") {
    return [
      `<TypewriterText`,
      `  text="${escapeString(comp.content)}"`,
      `  font="${comp.font}"`,
      `  position="${comp.position}"`,
      `  timing={${serializeValue(comp.timing as unknown as Record<string, unknown>)}}`,
      `  theme={theme}`,
      `/>`,
    ].join("\n");
  }

  if (reveal === "fade" || reveal === "none") {
    return [
      `<FadeText`,
      `  text="${escapeString(comp.content)}"`,
      `  font="${comp.font}"`,
      `  position="${comp.position}"`,
      `  timing={${serializeValue(comp.timing as unknown as Record<string, unknown>)}}`,
      `  theme={theme}`,
      `/>`,
    ].join("\n");
  }

  // Default: WordReveal (covers word-stagger, slide-up, scale-in, etc.)
  return [
    `<WordReveal`,
    `  text="${escapeString(comp.content)}"`,
    `  font="${comp.font}"`,
    `  position="${comp.position}"`,
    `  reveal="${reveal}"`,
    `  timing={${serializeValue(comp.timing as unknown as Record<string, unknown>)}}`,
    `  theme={theme}`,
    `/>`,
  ].join("\n");
}

// ---------------------------------------------------------------------------
// TextCycle
// ---------------------------------------------------------------------------

function buildTextCycle(comp: TextCycleComponent): string {
  const phrasesArr = comp.phrases.map((p) => {
    const parts = [`text: "${escapeString(p.text)}"`, `timing: ${serializeValue(p.timing as unknown as Record<string, unknown>)}`];
    if (p.accent) parts.push(`accent: "${p.accent}"`);
    return `{ ${parts.join(", ")} }`;
  });

  return [
    `<TextCycle`,
    `  position="${comp.position}"`,
    `  font="${comp.font}"`,
    `  phrases={[`,
    phrasesArr.map((p) => `    ${p},`).join("\n"),
    `  ]}`,
    `  theme={theme}`,
    `/>`,
  ].join("\n");
}

// ---------------------------------------------------------------------------
// Label
// ---------------------------------------------------------------------------

function buildLabel(comp: LabelComponent): string {
  return [
    `<Label`,
    `  text="${escapeString(comp.text)}"`,
    `  position="${comp.position}"`,
    `  timing={${serializeValue(comp.timing as unknown as Record<string, unknown>)}}`,
    `  theme={theme}`,
    `/>`,
  ].join("\n");
}

// ---------------------------------------------------------------------------
// Triptych
// ---------------------------------------------------------------------------

function buildTriptych(comp: TriptychComponent): string {
  const itemsArr = comp.items.map((item) => `{ tokens: [${item.tokens.map((t) => `"${escapeString(t)}"`).join(", ")}] }`);

  return [
    `<Triptych`,
    `  timing={${serializeValue(comp.timing as unknown as Record<string, unknown>)}}`,
    `  reveal="${comp.reveal}"`,
    `  items={[`,
    itemsArr.map((i) => `    ${i},`).join("\n"),
    `  ]}`,
    `  theme={theme}`,
    `/>`,
  ].join("\n");
}

// ---------------------------------------------------------------------------
// StepSequence
// ---------------------------------------------------------------------------

function buildStepSequence(comp: StepSequenceComponent): string {
  const stepsArr = comp.steps.map(
    (s) => `{ label: "${escapeString(s.label)}", description: "${escapeString(s.description)}" }`
  );

  return [
    `<StepSequence`,
    `  timing={${serializeValue(comp.timing as unknown as Record<string, unknown>)}}`,
    `  steps={[`,
    stepsArr.map((s) => `    ${s},`).join("\n"),
    `  ]}`,
    `  theme={theme}`,
    `/>`,
  ].join("\n");
}

// ---------------------------------------------------------------------------
// Comparison
// ---------------------------------------------------------------------------

function buildComparison(comp: ComparisonComponent): string {
  const sidesArr = comp.sides.map((s) => {
    const parts = [
      `side: "${s.side}"`,
      `title: "${escapeString(s.title)}"`,
      `subtitle: "${escapeString(s.subtitle)}"`,
    ];
    if (s.badge) {
      parts.push(`badge: { text: "${escapeString(s.badge.text)}", color: "${s.badge.color}" }`);
    }
    return `{ ${parts.join(", ")} }`;
  });

  const left = comp.sides.find((s) => s.side === "left") ?? comp.sides[0];
  const right = comp.sides.find((s) => s.side === "right") ?? (comp.sides[1] ?? comp.sides[0]);

  const buildSide = (s: typeof left) => {
    const parts = [
      `title: "${escapeString(s.title)}"`,
      `subtitle: "${escapeString(s.subtitle)}"`,
    ];
    if (s.badge) {
      parts.push(`badge: { text: "${escapeString(s.badge.text)}", color: "${s.badge.color}" }`);
    }
    return `{ ${parts.join(", ")} }`;
  };

  return [
    `<Comparison`,
    `  timing={${serializeValue(comp.timing as unknown as Record<string, unknown>)}}`,
    `  animation="${comp.animation}"`,
    `  left={${buildSide(left)}}`,
    `  right={${buildSide(right)}}`,
    `  theme={theme}`,
    `/>`,
  ].join("\n");
}

// ---------------------------------------------------------------------------
// Card (FormulaCard)
// ---------------------------------------------------------------------------

function buildCard(comp: CardComponent): string {
  const childrenArr = comp.children.map((c) => {
    switch (c.type) {
      case "formula":  return `{ type: "formula", content: "${escapeString(c.content)}" }`;
      case "arrow":    return `{ type: "arrow"${c.direction ? `, direction: "${escapeString(c.direction)}"` : ""} }`;
      case "result":   return `{ type: "result", content: "${escapeString(c.content)}" }`;
      case "subtitle": return `{ type: "subtitle", content: "${escapeString(c.content)}" }`;
      default:         return `{ type: "unknown" }`;
    }
  });

  return [
    `<FormulaCard`,
    `  position="${comp.position}"`,
    `  reveal="${comp.reveal}"`,
    `  timing={${serializeValue(comp.timing as unknown as Record<string, unknown>)}}`,
    `  children={[`,
    childrenArr.map((c) => `    ${c},`).join("\n"),
    `  ]}`,
    `  theme={theme}`,
    `/>`,
  ].join("\n");
}

// ---------------------------------------------------------------------------
// Code (TypewriterText with mono font)
// ---------------------------------------------------------------------------

function buildCode(comp: CodeComponent): string {
  const lines: string[] = [
    `<TypewriterText`,
    `  text="${escapeString(comp.content)}"`,
    `  font="mono"`,
    `  position="center"`,
    `  reveal="${comp.reveal}"`,
    `  timing={${serializeValue(comp.timing as unknown as Record<string, unknown>)}}`,
    `  theme={theme}`,
  ];

  if (comp.modifier) {
    lines.push(`  shrink={${comp.modifier.shrink}}`);
    lines.push(`  moveTop={${serializeValue(comp.modifier.moveTop as unknown as Record<string, unknown>)}}`);
  }

  lines.push(`/>`);
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// TraceLog
// ---------------------------------------------------------------------------

function buildTraceLog(comp: TraceLogComponent): string {
  const entriesArr = comp.entries.map(
    (e) => `{ tokens: [${e.tokens.map((t) => `"${escapeString(String(t))}"`).join(", ")}] }`
  );

  const lines: string[] = [
    `<TraceLog`,
    `  timing={${serializeValue(comp.timing as unknown as Record<string, unknown>)}}`,
    `  reveal="${comp.reveal}"`,
  ];

  if (comp.columns && comp.columns.length > 0) {
    lines.push(`  columns={[${comp.columns.map((c) => `"${escapeString(c)}"`).join(", ")}]}`);
  }

  if (comp.badge) {
    lines.push(`  badge="${escapeString(comp.badge)}"`);
  }

  lines.push(
    `  entries={[`,
    ...entriesArr.map((e) => `    ${e},`),
    `  ]}`,
    `  theme={theme}`,
    `/>`
  );

  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Viz — dispatched by vizType
// ---------------------------------------------------------------------------

function buildViz(comp: VizComponent): string {
  const componentName = resolveVizComponent(comp.vizType);
  const propsEntries = Object.entries(comp.props)
    .filter(([, v]) => v !== undefined)
    .map(([k, v]) => `  ${k}={${serializeValue(v as never)}}`)
    .join("\n");

  const lines: string[] = [
    `<${componentName}`,
    `  timing={${serializeValue(comp.timing as unknown as Record<string, unknown>)}}`,
    `  reveal="${comp.reveal}"`,
  ];

  if (propsEntries) {
    lines.push(propsEntries);
  }

  lines.push(`  theme={theme}`);
  lines.push(`/>`);

  return lines.join("\n");
}

function resolveVizComponent(vizType?: string): string {
  switch (vizType) {
    case "node-graph":       return "NodeGraph";
    case "flow-diagram":     return "FlowDiagram";
    case "boundary-sim":     return "BoundarySim";
    case "workspace":        return "WorkspaceDiagram";
    case "protocol-compare": return "ProtocolCompare";
    case "trace-log":        return "TraceLog";
    default:                 return "NodeGraph";
  }
}

// ---------------------------------------------------------------------------
// Byline
// ---------------------------------------------------------------------------

function buildByline(comp: BylineComponent): string {
  return [
    `<Byline`,
    `  text="${escapeString(comp.text)}"`,
    `  position="${comp.position}"`,
    `  timing={${serializeValue(comp.timing as unknown as Record<string, unknown>)}}`,
    `  theme={theme}`,
    `/>`,
  ].join("\n");
}

// ---------------------------------------------------------------------------
// Remotion root (registerRoot + Composition)
// ---------------------------------------------------------------------------

function buildRoot(spec: VDSLSpec, componentName: string): string {
  const totalFrames = spec.scenes.reduce(
    (sum, scene) => sum + Math.round(scene.duration * 30),
    0
  );
  const width = spec.canvas?.width ?? 1920;
  const height = spec.canvas?.height ?? 1080;

  return [
    `const Root = () => (`,
    `  <Composition`,
    `    id="${componentName}"`,
    `    component={${componentName}}`,
    `    durationInFrames={${totalFrames}}`,
    `    fps={30}`,
    `    width={${width}}`,
    `    height={${height}}`,
    `  />`,
    `);`,
    ``,
    `registerRoot(Root);`,
  ].join("\n");
}
