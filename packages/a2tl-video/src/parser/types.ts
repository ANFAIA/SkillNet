/**
 * VDSL – Video Description Language
 * Type definitions for the parsed AST.
 */

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------

export interface Theme {
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

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

/** A half-open or closed timing window in seconds. */
export interface Timing {
  start: number;
  end?: number;
}

export type FontStyle = "display" | "display-italic" | "body" | "mono" | "hero";

export type Position =
  | "center"
  | "upper-left"
  | "upper-right"
  | "bottom-center"
  | "bottom-right";

export type RevealStyle =
  | "fade"
  | "word-stagger"
  | "typewriter"
  | "slide-up"
  | "scale-in"
  | "none";

export type AccentStyle = "underline" | "strike" | "hero" | "dim" | "glow";

export type Transition =
  | "cut"
  | "fade"
  | "slide"
  | "zoom"
  | "dissolve"
  | string;

export type ComparisonAnimation = "split-tilt" | "slide-in" | "fade" | string;

export type VizType =
  | "node-graph"
  | "flow-diagram"
  | "boundary-sim"
  | "workspace"
  | "protocol-compare"
  | "custom"
  | string;

// ---------------------------------------------------------------------------
// Components (discriminated union on `type`)
// ---------------------------------------------------------------------------

/** `text "…" <font> <position> <reveal> <timing>` */
export interface TextComponent {
  type: "text";
  content: string;
  font: FontStyle;
  position: Position;
  reveal: RevealStyle;
  timing: Timing;
}

/** A single phrase inside a `text-cycle` block. */
export interface TextCyclePhrase {
  text: string;
  timing: Timing;
  accent?: AccentStyle;
}

/** `text-cycle <position> <font>` with indented phrases */
export interface TextCycleComponent {
  type: "text-cycle";
  position: Position;
  font: FontStyle;
  phrases: TextCyclePhrase[];
}

/** `label "…" <position> <timing>` */
export interface LabelComponent {
  type: "label";
  text: string;
  position: Position;
  timing: Timing;
}

/** `icon "<name>" <position> <timing> [color]` — renders an inline SVG icon. */
export interface IconComponent {
  type: "icon";
  name: string;
  position: Position;
  timing: Timing;
  /** Optional trailing colour token (named palette / theme / raw css colour). */
  color?: string;
}

/** A single item inside a `triptych` block. */
export interface TriptychItem {
  /** Raw token list for the item line; structure varies by usage. */
  tokens: string[];
}

/** `triptych <timing> <reveal>` with indented items */
export interface TriptychComponent {
  type: "triptych";
  timing: Timing;
  reveal: RevealStyle;
  items: TriptychItem[];
}

/** A single step in a `step-sequence`. */
export interface StepSequenceItem {
  /** e.g. "1. TITLE" */
  label: string;
  description: string;
  /** Optional leading bare icon token (e.g. `rocket "Launch" "desc"`); when it
   *  resolves to a known icon the badge shows that icon instead of the number. */
  icon?: string;
}

/** `step-sequence <timing>` with indented steps */
export interface StepSequenceComponent {
  type: "step-sequence";
  timing: Timing;
  steps: StepSequenceItem[];
}

/** One side of a `comparison` block. */
export interface ComparisonSide {
  side: "left" | "right";
  title: string;
  subtitle: string;
  badge?: { text: string; color: string };
}

/** `comparison <timing> <animation>` */
export interface ComparisonComponent {
  type: "comparison";
  timing: Timing;
  animation: ComparisonAnimation;
  sides: ComparisonSide[];
}

/** A child element inside a `card` block. */
export type CardChild =
  | { type: "formula"; content: string }
  | { type: "arrow"; direction?: string }
  | { type: "result"; content: string }
  | { type: "subtitle"; content: string }
  | { type: "icon"; name: string };

/** `card <position> <reveal> <timing>` */
export interface CardComponent {
  type: "card";
  position: Position;
  reveal: RevealStyle;
  timing: Timing;
  children: CardChild[];
}

/** Optional shrink/move modifier for a `code` block. */
export interface CodeModifier {
  shrink: number;
  moveTop: Timing;
}

/** `code "…" <reveal> <timing>` */
export interface CodeComponent {
  type: "code";
  content: string;
  reveal: RevealStyle;
  timing: Timing;
  modifier?: CodeModifier;
}

/** A log entry inside a `trace-log` block. */
export interface TraceLogEntry {
  /** Raw tokens for the entry; varies by schema. */
  tokens: string[];
}

/** `trace-log <timing> <reveal>` */
export interface TraceLogComponent {
  type: "trace-log";
  timing: Timing;
  reveal: RevealStyle;
  columns?: string[];
  entries: TraceLogEntry[];
  badge?: string;
}

/**
 * `viz <timing> <reveal>` — Level-3 escape hatch.
 * Children are key-value pairs whose structure depends on the viz type.
 */
export interface VizComponent {
  type: "viz";
  timing: Timing;
  reveal: RevealStyle;
  vizType?: VizType;
  /** Arbitrary structured properties parsed from indented children. */
  props: Record<string, unknown>;
}

/** `byline "…" <position> <timing>` */
export interface BylineComponent {
  type: "byline";
  text: string;
  position: Position;
  timing: Timing;
}

export type Component =
  | TextComponent
  | TextCycleComponent
  | LabelComponent
  | IconComponent
  | TriptychComponent
  | StepSequenceComponent
  | ComparisonComponent
  | CardComponent
  | CodeComponent
  | TraceLogComponent
  | VizComponent
  | BylineComponent;

// ---------------------------------------------------------------------------
// Top-level document
// ---------------------------------------------------------------------------

export interface Scene {
  title: string;
  duration: number;
  transition: Transition;
  components: Component[];
}

/** Optional inline theme tweaks from the header (`palette` / `font` lines).
 *  Kept deliberately small: override a base theme's key colours/fonts without a
 *  separate theme file, so a couple of header lines re-skin the whole video. */
export interface ThemeOverride {
  colors?: Partial<Theme["colors"]>;
  fonts?: Partial<Theme["fonts"]>;
  grid?: boolean;
}

export interface VDSLSpec {
  version: number;
  theme: string;
  canvas: { width: number; height: number };
  scenes: Scene[];
  /** Inline overrides applied on top of the resolved base theme. */
  themeOverride?: ThemeOverride;
}
