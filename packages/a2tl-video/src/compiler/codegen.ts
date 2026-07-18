/**
 * VDSL Code Generation Helpers
 *
 * Low-level utilities for generating readable JSX/TypeScript strings.
 */

// ---------------------------------------------------------------------------
// Indentation
// ---------------------------------------------------------------------------

/**
 * Indents every line of `code` by `level` × 2 spaces.
 * Empty lines are left blank (no trailing whitespace).
 */
export function indent(code: string, level: number): string {
  const pad = "  ".repeat(level);
  return code
    .split("\n")
    .map((line) => (line.trim() === "" ? "" : pad + line))
    .join("\n");
}

// ---------------------------------------------------------------------------
// String escaping
// ---------------------------------------------------------------------------

/**
 * Escapes a string value for safe use inside JSX double-quoted attribute
 * values or template literals.  Handles double-quotes, backslashes, and
 * common control characters.
 */
export function escapeString(s: string): string {
  return s
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\n/g, "\\n")
    .replace(/\r/g, "\\r")
    .replace(/\t/g, "\\t");
}

// ---------------------------------------------------------------------------
// JSX prop serialisation
// ---------------------------------------------------------------------------

type PropValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | Record<string, unknown>
  | unknown[]
  | unknown;

/**
 * Serialises a plain JavaScript value to a JSX-safe expression string.
 *
 * Rules:
 *  - `string`  → `"escaped string"` (double-quoted)
 *  - `number`  → numeric literal
 *  - `boolean` → `true` / `false`
 *  - `null` / `undefined` → `null`
 *  - `Array`   → `[item, item, …]`
 *  - `object`  → `{ key: value, … }`
 */
export function serializeValue(value: PropValue): string {
  if (value === null || value === undefined) {
    return "null";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "number") {
    return String(value);
  }
  if (typeof value === "string") {
    return `"${escapeString(value)}"`;
  }
  if (Array.isArray(value)) {
    const items = (value as PropValue[]).map(serializeValue).join(", ");
    return `[${items}]`;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => `${k}: ${serializeValue(v as PropValue)}`)
      .join(", ");
    return `{ ${entries} }`;
  }
  // Fallback — should not happen in practice
  return JSON.stringify(value);
}

/**
 * Converts a props object to a JSX attribute string.
 *
 * Example:
 *   `{ text: "Hello", timing: { start: 0, end: 3 } }`
 *   → `text="Hello" timing={{ start: 0, end: 3 }}`
 *
 * String values are rendered as `key="value"`.
 * All other values are rendered as `key={expression}`.
 * Undefined / null values are omitted.
 */
export function propsToJSX(props: Record<string, PropValue>): string {
  return Object.entries(props)
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([key, value]) => {
      if (typeof value === "string") {
        return `${key}="${escapeString(value)}"`;
      }
      return `${key}={${serializeValue(value)}}`;
    })
    .join(" ");
}

// ---------------------------------------------------------------------------
// JSX element builder
// ---------------------------------------------------------------------------

export interface JSXElementOptions {
  /** The component name, e.g. "WordReveal". */
  name: string;
  /** Props object — undefined/null values are omitted. */
  props?: Record<string, PropValue>;
  /** Inner JSX children as a pre-rendered string. If absent → self-closing. */
  children?: string;
}

/**
 * Renders a single JSX element string (self-closing or with children).
 *
 * The element is not indented here — callers should use `indent()`.
 */
export function jsxElement({ name, props = {}, children }: JSXElementOptions): string {
  const propStr = propsToJSX(props);
  const attrPart = propStr ? ` ${propStr}` : "";

  if (children === undefined || children.trim() === "") {
    return `<${name}${attrPart} />`;
  }

  return `<${name}${attrPart}>\n${children}\n</${name}>`;
}
