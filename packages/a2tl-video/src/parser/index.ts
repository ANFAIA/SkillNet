/**
 * VDSL – Video Description Language
 * Main parser: converts VDSL source text → VDSLSpec JSON.
 *
 * @module parser
 */

import {
  tokenizeDocument,
  tokenizeLine,
  parseTiming,
  isColor,
  type Token,
  type TokenizedLine,
} from "./tokenizer";

import type {
  VDSLSpec,
  Scene,
  Component,
  Timing,
  FontStyle,
  Position,
  RevealStyle,
  AccentStyle,
  ComparisonAnimation,
  CardChild,
  TextCyclePhrase,
  TriptychItem,
  StepSequenceItem,
  ComparisonSide,
  TraceLogEntry,
  VizType,
  CodeModifier,
  ThemeOverride,
} from "./types";

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

class ParseError extends Error {
  constructor(message: string, lineNumber: number) {
    super(`[VDSL ParseError] Line ${lineNumber + 1}: ${message}`);
    this.name = "ParseError";
  }
}

/** Extract the string value from a token, or throw. */
function expectString(token: Token | undefined, lineNumber: number, hint = ""): string {
  if (!token || token.kind !== "string") {
    throw new ParseError(
      `Expected quoted string${hint ? ` (${hint})` : ""}, got ${token ? `${token.kind}:"${token.value}"` : "nothing"}`,
      lineNumber
    );
  }
  return token.value;
}

/** Extract a keyword value from a token, or throw. */
function expectKeyword(token: Token | undefined, lineNumber: number, hint = ""): string {
  if (!token || token.kind !== "keyword") {
    throw new ParseError(
      `Expected keyword${hint ? ` (${hint})` : ""}, got ${token ? `${token.kind}:"${token.value}"` : "nothing"}`,
      lineNumber
    );
  }
  return token.value;
}

/** Extract a number from a token, or throw. */
function expectNumber(token: Token | undefined, lineNumber: number, hint = ""): number {
  if (!token || token.kind !== "number") {
    throw new ParseError(
      `Expected number${hint ? ` (${hint})` : ""}, got ${token ? `${token.kind}:"${token.value}"` : "nothing"}`,
      lineNumber
    );
  }
  return token.value;
}

/** Return a token's string or keyword value regardless of kind. */
function tokenValue(token: Token): string {
  return String(token.value);
}

/**
 * Extracts a timing token from the token list starting at `offset`.
 * Returns [timing, nextOffset].
 */
function extractTiming(
  tokens: Token[],
  offset: number,
  lineNumber: number
): [Timing, number] {
  const tok = tokens[offset];
  if (!tok) throw new ParseError("Expected timing token", lineNumber);
  const raw = tokenValue(tok);
  const t = parseTiming(raw);
  if (!t) throw new ParseError(`Invalid timing token: "${raw}"`, lineNumber);
  return [t, offset + 1];
}

/** Cast a string to Position with a fallback. */
function asPosition(value: string): Position {
  const valid: Position[] = ["center", "upper-left", "upper-right", "bottom-center", "bottom-right"];
  if ((valid as string[]).includes(value)) return value as Position;
  return "center"; // lenient fallback
}

/** Cast a string to FontStyle with a fallback. */
function asFont(value: string): FontStyle {
  const valid: FontStyle[] = ["display", "display-italic", "body", "mono", "hero"];
  if ((valid as string[]).includes(value)) return value as FontStyle;
  return "body";
}

/** Cast a string to RevealStyle with a fallback. */
function asReveal(value: string): RevealStyle {
  const valid: RevealStyle[] = ["fade", "word-stagger", "typewriter", "slide-up", "scale-in", "none"];
  if ((valid as string[]).includes(value)) return value as RevealStyle;
  return "none";
}

/** Cast a string to AccentStyle with a fallback. */
function asAccent(value: string): AccentStyle {
  const valid: AccentStyle[] = ["underline", "strike", "hero", "dim", "glow"];
  if ((valid as string[]).includes(value)) return value as AccentStyle;
  return "underline";
}

// ---------------------------------------------------------------------------
// Cursor: walks the tokenized line array
// ---------------------------------------------------------------------------

class Cursor {
  private pos = 0;

  constructor(private readonly lines: TokenizedLine[]) {}

  get current(): TokenizedLine | undefined {
    return this.lines[this.pos];
  }

  peek(offset = 0): TokenizedLine | undefined {
    return this.lines[this.pos + offset];
  }

  advance(): TokenizedLine | undefined {
    return this.lines[this.pos++];
  }

  /** Skip blank lines and comments, return number skipped. */
  skipBlankAndComments(): number {
    let skipped = 0;
    while (this.current && (this.current.isEmpty || this.current.isComment)) {
      this.pos++;
      skipped++;
    }
    return skipped;
  }

  isEOF(): boolean {
    return this.pos >= this.lines.length;
  }

  /** Returns true when the next meaningful line has indent > `threshold`. */
  hasChildAt(parentIndent: number): boolean {
    let i = this.pos;
    while (i < this.lines.length) {
      const l = this.lines[i];
      if (l.isEmpty || l.isComment) { i++; continue; }
      return l.indent > parentIndent;
    }
    return false;
  }

  /**
   * Collect all non-blank, non-comment lines whose indent is greater than
   * `parentIndent`.  Stops at the first line whose indent <= parentIndent.
   */
  collectChildren(parentIndent: number): TokenizedLine[] {
    const children: TokenizedLine[] = [];
    while (!this.isEOF()) {
      const l = this.current!;
      if (l.isEmpty || l.isComment) { this.advance(); continue; }
      if (l.indent <= parentIndent) break;
      children.push(this.advance()!);
    }
    return children;
  }
}

// ---------------------------------------------------------------------------
// Component parsers
// ---------------------------------------------------------------------------

/**
 * text "content" <font> <position> <reveal> <timing>
 */
function parseText(tokens: Token[], lineNumber: number): Component {
  const content = expectString(tokens[0], lineNumber, "content");
  const font = asFont(expectKeyword(tokens[1], lineNumber, "font"));
  const position = asPosition(expectKeyword(tokens[2], lineNumber, "position"));
  const reveal = asReveal(expectKeyword(tokens[3], lineNumber, "reveal"));
  const [timing] = extractTiming(tokens, 4, lineNumber);

  return { type: "text", content, font, position, reveal, timing };
}

/**
 * text-cycle <position> <font>
 *   "phrase" <start>-<end>s [accent]
 */
function parseTextCycle(
  tokens: Token[],
  lineNumber: number,
  children: TokenizedLine[]
): Component {
  const position = asPosition(expectKeyword(tokens[0], lineNumber, "position"));
  const font = asFont(expectKeyword(tokens[1], lineNumber, "font"));

  const phrases: TextCyclePhrase[] = children.map((child) => {
    const ct = child.tokens;
    const text = expectString(ct[0], child.lineNumber, "phrase text");
    const [timing] = extractTiming(ct, 1, child.lineNumber);
    const accentTok = ct[2];
    const accent = accentTok ? asAccent(tokenValue(accentTok)) : undefined;
    return { text, timing, ...(accent !== undefined && { accent }) };
  });

  return { type: "text-cycle", position, font, phrases };
}

/**
 * label "text" <position> <timing>
 */
function parseLabel(tokens: Token[], lineNumber: number): Component {
  const text = expectString(tokens[0], lineNumber, "label text");
  const position = asPosition(expectKeyword(tokens[1], lineNumber, "position"));
  const [timing] = extractTiming(tokens, 2, lineNumber);
  return { type: "label", text, position, timing };
}

/**
 * icon "<name>" <position> <timing> [color]
 * Mirrors `label`. The icon name is a quoted string OR a bare keyword; an
 * optional trailing token overrides the colour.
 */
function parseIcon(tokens: Token[], lineNumber: number): Component {
  const nameTok = tokens[0];
  if (!nameTok) throw new ParseError("Expected icon name", lineNumber);
  const name = nameTok.kind === "string" ? nameTok.value : tokenValue(nameTok);
  const position = asPosition(expectKeyword(tokens[1], lineNumber, "position"));
  const [timing, next] = extractTiming(tokens, 2, lineNumber);
  const colorTok = tokens[next];
  const color = colorTok ? tokenValue(colorTok) : undefined;
  return { type: "icon", name, position, timing, ...(color !== undefined && { color }) };
}

/**
 * triptych <timing> <reveal>
 *   … children (raw tokens preserved) …
 */
function parseTriptych(
  tokens: Token[],
  lineNumber: number,
  children: TokenizedLine[]
): Component {
  const [timing] = extractTiming(tokens, 0, lineNumber);
  const reveal = asReveal(expectKeyword(tokens[1], lineNumber, "reveal"));

  const items: TriptychItem[] = children.map((child) => ({
    tokens: child.tokens.map(tokenValue),
  }));

  return { type: "triptych", timing, reveal, items };
}

/**
 * step-sequence <timing>
 *   "1. TITLE" "description"
 */
function parseStepSequence(
  tokens: Token[],
  lineNumber: number,
  children: TokenizedLine[]
): Component {
  const [timing] = extractTiming(tokens, 0, lineNumber);

  const steps: StepSequenceItem[] = [];
  // Children are paired: label + description may be on the same line. An OPTIONAL
  // leading BARE keyword (not a quoted string) is taken as an icon name, e.g.
  //   rocket "1. Launch" "desc"
  // Existing steps start with a quoted string, so they are unaffected.
  for (const child of children) {
    const ct = child.tokens;
    if (ct.length === 0) continue;
    let idx = 0;
    let icon: string | undefined;
    if (ct[0].kind !== "string") {
      icon = tokenValue(ct[0]);
      idx = 1;
    }
    const labelTok = ct[idx];
    if (!labelTok) continue;
    const label = labelTok.kind === "string" ? labelTok.value : tokenValue(labelTok);
    const description = ct[idx + 1] && ct[idx + 1].kind === "string" ? (ct[idx + 1].value as string) : "";
    steps.push({ label, description, ...(icon !== undefined && { icon }) });
  }

  return { type: "step-sequence", timing, steps };
}

/**
 * comparison <timing> <animation>
 *   left "title" "subtitle" badge "text" <color>
 *   right "title" "subtitle" badge "text" <color>
 */
function parseComparison(
  tokens: Token[],
  lineNumber: number,
  children: TokenizedLine[]
): Component {
  const [timing] = extractTiming(tokens, 0, lineNumber);
  const animation = (tokens[1] ? tokenValue(tokens[1]) : "fade") as ComparisonAnimation;

  const sides: ComparisonSide[] = children.map((child) => {
    const ct = child.tokens;
    const side = tokenValue(ct[0]) as "left" | "right";
    const title = expectString(ct[1], child.lineNumber, "comparison title");
    const subtitle = expectString(ct[2], child.lineNumber, "comparison subtitle");

    // badge "text" <color>
    let badge: ComparisonSide["badge"] | undefined;
    const badgeIdx = ct.findIndex((t) => tokenValue(t) === "badge");
    if (badgeIdx !== -1 && ct[badgeIdx + 1]) {
      const badgeText =
        ct[badgeIdx + 1].kind === "string"
          ? ct[badgeIdx + 1].value as string
          : tokenValue(ct[badgeIdx + 1]);
      const badgeColor = ct[badgeIdx + 2]
        ? tokenValue(ct[badgeIdx + 2])
        : "gray";
      badge = { text: badgeText, color: badgeColor };
    }

    return { side, title, subtitle, ...(badge && { badge }) };
  });

  return { type: "comparison", timing, animation, sides };
}

/**
 * card <position> <reveal> <timing>
 *   formula …
 *   arrow [direction]
 *   result …
 *   subtitle …
 */
function parseCard(
  tokens: Token[],
  lineNumber: number,
  children: TokenizedLine[]
): Component {
  const position = asPosition(expectKeyword(tokens[0], lineNumber, "position"));
  const reveal = asReveal(expectKeyword(tokens[1], lineNumber, "reveal"));
  const [timing] = extractTiming(tokens, 2, lineNumber);

  const childItems: CardChild[] = children.map((child) => {
    const ct = child.tokens;
    const kw = ct[0] ? tokenValue(ct[0]) : "";
    switch (kw) {
      case "formula": {
        const content = ct[1] ? (ct[1].kind === "string" ? ct[1].value as string : tokenValue(ct[1])) : "";
        return { type: "formula", content } as CardChild;
      }
      case "arrow": {
        const direction = ct[1] ? tokenValue(ct[1]) : undefined;
        return { type: "arrow", ...(direction && { direction }) } as CardChild;
      }
      case "icon": {
        const name = ct[1] ? (ct[1].kind === "string" ? ct[1].value as string : tokenValue(ct[1])) : "";
        return { type: "icon", name } as CardChild;
      }
      case "result": {
        const content = ct[1] ? (ct[1].kind === "string" ? ct[1].value as string : tokenValue(ct[1])) : "";
        return { type: "result", content } as CardChild;
      }
      case "subtitle": {
        const content = ct[1] ? (ct[1].kind === "string" ? ct[1].value as string : tokenValue(ct[1])) : "";
        return { type: "subtitle", content } as CardChild;
      }
      default: {
        // Unrecognised child; store as subtitle
        const content = ct.map(tokenValue).join(" ");
        return { type: "subtitle", content } as CardChild;
      }
    }
  });

  return { type: "card", position, reveal, timing, children: childItems };
}

/**
 * code "content" <reveal> <timing>
 *   [shrink <factor> move-top <timing>]
 */
function parseCode(
  tokens: Token[],
  lineNumber: number,
  children: TokenizedLine[]
): Component {
  const content = expectString(tokens[0], lineNumber, "code content");
  const reveal = asReveal(expectKeyword(tokens[1], lineNumber, "reveal"));
  const [timing] = extractTiming(tokens, 2, lineNumber);

  let modifier: CodeModifier | undefined;
  for (const child of children) {
    const ct = child.tokens;
    if (ct[0] && tokenValue(ct[0]) === "shrink") {
      const shrink = ct[1] ? Number(tokenValue(ct[1])) : 1;
      // move-top <timing>
      const moveTopIdx = ct.findIndex((t) => tokenValue(t) === "move-top");
      let moveTop: Timing = { start: 0 };
      if (moveTopIdx !== -1 && ct[moveTopIdx + 1]) {
        moveTop = parseTiming(tokenValue(ct[moveTopIdx + 1])) ?? { start: 0 };
      }
      modifier = { shrink, moveTop };
    }
  }

  return { type: "code", content, reveal, timing, ...(modifier && { modifier }) };
}

/**
 * trace-log <timing> <reveal>
 *   columns …
 *   entry …
 *   badge "text"
 */
function parseTraceLog(
  tokens: Token[],
  lineNumber: number,
  children: TokenizedLine[]
): Component {
  const [timing] = extractTiming(tokens, 0, lineNumber);
  const reveal = asReveal(expectKeyword(tokens[1], lineNumber, "reveal"));

  let columns: string[] | undefined;
  const entries: TraceLogEntry[] = [];
  let badge: string | undefined;

  for (const child of children) {
    const ct = child.tokens;
    const kw = ct[0] ? tokenValue(ct[0]) : "";
    if (kw === "columns") {
      columns = ct.slice(1).map(tokenValue);
    } else if (kw === "badge") {
      badge = ct[1] ? (ct[1].kind === "string" ? ct[1].value as string : tokenValue(ct[1])) : "";
    } else {
      // Everything else is a data entry
      entries.push({ tokens: ct.map(tokenValue) });
    }
  }

  return {
    type: "trace-log",
    timing,
    reveal,
    ...(columns && { columns }),
    entries,
    ...(badge !== undefined && { badge }),
  };
}

function parseListItem(
  itemContent: string,
  childLines: TokenizedLine[],
  parentIndent: number
): unknown {
  // Check for quoted strings first
  if (itemContent.startsWith('"') || itemContent.startsWith("'")) {
    const itemTokens = tokenizeLine(itemContent);
    const quotedStrings = itemTokens.filter((t: Token) => t.kind === "string").map((t) => t.value);
    if (quotedStrings.length > 1) {
      return { tokens: quotedStrings };
    }
    if (quotedStrings.length === 1) {
      return quotedStrings[0];
    }
    return itemContent;
  }

  // Parse inline properties (key: value pairs)
  const parsedInline = parseInlineProperties(itemContent);

  // Parse children
  let parsedChildren: Record<string, unknown> = {};
  if (childLines.length > 0) {
    const childResult = parseStructuredChildren(childLines, parentIndent);
    if (typeof childResult === "object" && childResult !== null && !Array.isArray(childResult)) {
      parsedChildren = childResult as Record<string, unknown>;
    }
  }

  if (Object.keys(parsedInline).length > 0 || Object.keys(parsedChildren).length > 0) {
    return { ...parsedInline, ...parsedChildren };
  }

  return itemContent;
}

function parseInlineProperties(content: string): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  // Walk through content manually, parsing key: value pairs
  // respecting quoted strings as atomic units
  let i = 0;
  while (i < content.length) {
    // Skip whitespace
    if (content[i] === " " || content[i] === "\t") { i++; continue; }

    // Read key (alphanumeric, underscore, hyphen)
    let key = "";
    while (i < content.length && /[a-zA-Z0-9_-]/.test(content[i])) {
      key += content[i]; i++;
    }

    // Expect colon
    if (i < content.length && content[i] === ":") {
      i++; // skip colon
    } else {
      if (key) i += key.length; // skip what we consumed
      else i++;
      continue;
    }

    // Skip whitespace after colon
    while (i < content.length && (content[i] === " " || content[i] === "\t")) i++;

    // Read value
    if (i < content.length && content[i] === '"') {
      // Quoted string
      i++; // skip opening quote
      let val = "";
      while (i < content.length && content[i] !== '"') {
        if (content[i] === "\\" && i + 1 < content.length) {
          val += content[i + 1]; i += 2;
        } else {
          val += content[i]; i++;
        }
      }
      i++; // skip closing quote
      result[key] = val;
    } else if (content[i] === "[" || content[i] === "{") {
      // Bracketed value: read until matching close
      const open = content[i];
      const close = open === "[" ? "]" : "}";
      i++;
      let val = open;
      let depth = 1;
      while (i < content.length && depth > 0) {
        if (content[i] === open) depth++;
        if (content[i] === close) depth--;
        val += content[i]; i++;
      }
      result[key] = val;
    } else {
      // Unquoted value: read until next space or end
      let val = "";
      while (i < content.length && content[i] !== " " && content[i] !== "\t") {
        val += content[i]; i++;
      }
      if (val !== "") {
        result[key] = parseInlineValue(val);
      }
    }
  }
  return result;
}

// ---------------------------------------------------------------------------
// Structured viz parser (YAML-like)
// ---------------------------------------------------------------------------

/** Parse a colon-terminated key with indented children as structured value */
function parseStructuredChildren(lines: TokenizedLine[], parentIndent: number): unknown {
  if (lines.length === 0) return "";

  // All lines at same indent level as first child
  const firstIndent = lines[0].indent;

  // Check if this is a list (first line starts with `-`)
  const firstTrimmed = lines[0].raw.trim();
  const isList = firstTrimmed.startsWith("- ");
  const isListItem = firstTrimmed.startsWith("- ");

  if (isListItem) {
    const items: unknown[] = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      const trimmed = line.raw.trim();
      if (!trimmed.startsWith("- ")) { i++; continue; }

      const itemContent = trimmed.slice(2).trim();
      const childLines: TokenizedLine[] = [];
      let j = i + 1;
      while (j < lines.length && lines[j].indent > line.indent) {
        childLines.push(lines[j]); j++;
      }

      items.push(parseListItem(itemContent, childLines, line.indent));
      i = j;
    }
    return items;
  }

  // Not a list — check for key:value pairs at this level
  const result: Record<string, unknown> = {};
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const raw = line.raw.trim();
    const colonIdx = raw.indexOf(":");

    if (colonIdx === -1) {
      // No colon — store as raw tokens
      result[`_line${line.lineNumber}`] = line.tokens.map(tokenValue);
      i++;
      continue;
    }

    const key = raw.slice(0, colonIdx).trim();
    const rest = raw.slice(colonIdx + 1).trim();

    if (rest === "") {
      // Key with children on subsequent indented lines
      const childLines: TokenizedLine[] = [];
      let j = i + 1;
      while (j < lines.length && lines[j].indent > line.indent) {
        childLines.push(lines[j]); j++;
      }
      if (childLines.length > 0) {
        result[key] = parseStructuredChildren(childLines, line.indent);
      } else {
        result[key] = "";
      }
      i = j;
    } else {
      // Check if rest contains more key:value pairs at this level
      if (rest.includes(":")) {
        const parsedAll = parseInlineProperties(raw);
        if (Object.keys(parsedAll).length > 0) {
          Object.assign(result, parsedAll);
          i++;
          continue;
        }
      }
      result[key] = parseInlineValue(rest);
      i++;
    }
  }

  // If result only has one key and it's a list, collapse
  const keys = Object.keys(result);
  if (keys.length === 0) return result;
  return result;
}



/** Parse a single inline value (string, number, boolean) */
function parseInlineValue(raw: string): unknown {
  if (raw.startsWith('"') && raw.endsWith('"') && raw.length >= 2) {
    return raw.slice(1, -1);
  }
  if (raw === "true") return true;
  if (raw === "false") return false;
  const num = Number(raw);
  if (!isNaN(num) && raw !== "") return num;
  return raw;
}

/**
 * Lift a triple-quoted `"""` fenced block out of a component's children,
 * returning its dedented RAW text plus the children that lie outside it.
 * A fence is a line whose trimmed content is exactly `"""`. Content lines are
 * dedented by the opening fence's indent so relative nesting is preserved.
 * If no (closed) block is present, returns the children unchanged.
 */
function extractTripleQuotedBlock(
  children: TokenizedLine[]
): { rawBlock?: string; remaining: TokenizedLine[] } {
  let start = -1;
  for (let i = 0; i < children.length; i++) {
    if (children[i].raw.trim() === '"""') { start = i; break; }
  }
  if (start === -1) return { remaining: children };
  let end = -1;
  for (let j = start + 1; j < children.length; j++) {
    if (children[j].raw.trim() === '"""') { end = j; break; }
  }
  if (end === -1) return { remaining: children }; // unterminated → leave as-is
  const fenceIndent = children[start].indent;
  const rawBlock = children
    .slice(start + 1, end)
    .map((l) => l.raw.slice(fenceIndent).replace(/\s+$/, ""))
    .join("\n")
    .replace(/^\n+|\n+$/g, "");
  const remaining = [...children.slice(0, start), ...children.slice(end + 1)];
  return { rawBlock, remaining };
}

/**
 * viz <timing> <reveal>
 *   type: <vizType>
 *   <key>: <value>
 *   <key>:
 *     <subkey>: <value>
 *   - item
 *   - key: value
 */
function parseViz(
  tokens: Token[],
  lineNumber: number,
  children: TokenizedLine[]
): Component {
  const [timing] = extractTiming(tokens, 0, lineNumber);
  const reveal = asReveal(expectKeyword(tokens[1], lineNumber, "reveal"));

  let vizType: VizType | undefined;
  const props: Record<string, unknown> = {};

  // Level-3 escape hatch: a triple-quoted `"""` block holds RAW author content
  // (e.g. inline SVG for `type: custom`). Its lines are not key:value/token
  // data, so we lift them out verbatim BEFORE structured parsing and stash the
  // dedented text as `props.svg`. What remains (e.g. `type: custom`) is parsed
  // normally. Without this the tokenizer shreds the SVG into junk `_lineN` keys.
  const { rawBlock, remaining } = extractTripleQuotedBlock(children);
  if (rawBlock !== undefined) props.svg = rawBlock;

  if (remaining.length > 0) {
    const structured = parseStructuredChildren(remaining, remaining[0].indent);
    if (typeof structured === "object" && structured !== null && !Array.isArray(structured)) {
      for (const [k, v] of Object.entries(structured as Record<string, unknown>)) {
        if (k === "type") {
          vizType = String(v) as VizType;
        } else {
          props[k] = v;
        }
      }
    }
  }

  return {
    type: "viz",
    timing,
    reveal,
    ...(vizType && { vizType }),
    props,
  };
}

/**
 * byline "text" <position> <timing>
 */
function parseByline(tokens: Token[], lineNumber: number): Component {
  const text = expectString(tokens[0], lineNumber, "byline text");
  const position = asPosition(expectKeyword(tokens[1], lineNumber, "position"));
  const [timing] = extractTiming(tokens, 2, lineNumber);
  return { type: "byline", text, position, timing };
}

// ---------------------------------------------------------------------------
// Scene parser
// ---------------------------------------------------------------------------

/**
 * scene "Title" <duration>s <transition>
 */
function parseScene(cursor: Cursor): Scene {
  const line = cursor.advance()!;
  const tokens = line.tokens;

  // tokens[0] = "scene" keyword (already confirmed by caller)
  const title = expectString(tokens[1], line.lineNumber, "scene title");

  // duration may be bare `5s` or `5` followed by `s`
  let duration = 0;
  let transitionOffset = 3;
  const durTok = tokens[2];
  if (durTok) {
    const durRaw = tokenValue(durTok);
    // Could be timing-style "5s", or a plain number
    const asTiming = parseTiming(durRaw);
    if (asTiming) {
      duration = asTiming.start;
    } else if (durTok.kind === "number") {
      duration = durTok.value;
    } else {
      duration = parseFloat(durRaw) || 0;
    }
  }

  const transitionTok = tokens[transitionOffset];
  const transition = transitionTok ? tokenValue(transitionTok) : "cut";

  // Collect component lines (indent > scene indent)
  const sceneIndent = line.indent;
  const children = cursor.collectChildren(sceneIndent);

  const components: Component[] = parseComponents(children);

  return { title, duration, transition, components };
}

// ---------------------------------------------------------------------------
// Component dispatcher
// ---------------------------------------------------------------------------

function parseComponents(lines: TokenizedLine[]): Component[] {
  const components: Component[] = [];
  const cursor = new Cursor(lines);

  while (!cursor.isEOF()) {
    cursor.skipBlankAndComments();
    if (cursor.isEOF()) break;

    const line = cursor.current!;
    const tokens = line.tokens;
    if (tokens.length === 0) { cursor.advance(); continue; }

    const kw = tokenValue(tokens[0]);

    // Components that need to collect their own children
    const needsChildren = new Set([
      "text-cycle", "triptych", "step-sequence", "comparison",
      "card", "code", "trace-log", "viz",
    ]);

    if (needsChildren.has(kw)) {
      const parentIndent = line.indent;
      cursor.advance();
      const children = cursor.collectChildren(parentIndent);
      const rest = tokens.slice(1);

      switch (kw) {
        case "text-cycle":
          components.push(parseTextCycle(rest, line.lineNumber, children));
          break;
        case "triptych":
          components.push(parseTriptych(rest, line.lineNumber, children));
          break;
        case "step-sequence":
          components.push(parseStepSequence(rest, line.lineNumber, children));
          break;
        case "comparison":
          components.push(parseComparison(rest, line.lineNumber, children));
          break;
        case "card":
          components.push(parseCard(rest, line.lineNumber, children));
          break;
        case "code":
          components.push(parseCode(rest, line.lineNumber, children));
          break;
        case "trace-log":
          components.push(parseTraceLog(rest, line.lineNumber, children));
          break;
        case "viz":
          components.push(parseViz(rest, line.lineNumber, children));
          break;
      }
    } else {
      cursor.advance();
      const rest = tokens.slice(1);

      switch (kw) {
        case "text":
          components.push(parseText(rest, line.lineNumber));
          break;
        case "label":
          components.push(parseLabel(rest, line.lineNumber));
          break;
        case "icon":
          components.push(parseIcon(rest, line.lineNumber));
          break;
        case "byline":
          components.push(parseByline(rest, line.lineNumber));
          break;
        default:
          // Unknown keyword — skip silently
          break;
      }
    }
  }

  return components;
}

// ---------------------------------------------------------------------------
// Top-level document parser
// ---------------------------------------------------------------------------

/**
 * Parses a VDSL source string and returns a `VDSLSpec` object.
 *
 * @param input - Raw VDSL source text (UTF-8 string).
 * @returns Parsed `VDSLSpec` document tree.
 * @throws {ParseError} When the source violates the VDSL grammar.
 *
 * @example
 * ```ts
 * import parseVDSL from "./parser";
 *
 * const spec = parseVDSL(`
 * VDSL/1
 * theme dark
 * canvas 1920x1080
 *
 * scene "Intro" 5s fade
 *   text "Hello World" display center fade 0-5s
 * `);
 * console.log(spec.scenes[0].components[0].type); // "text"
 * ```
 */
function parseVDSL(input: string): VDSLSpec {
  const allLines = tokenizeDocument(input);
  const cursor = new Cursor(allLines);

  // -------------------------------------------------------------------------
  // 1. Version line (required, must be first non-blank, non-comment line)
  // -------------------------------------------------------------------------
  cursor.skipBlankAndComments();
  const versionLine = cursor.current;
  if (!versionLine || versionLine.tokens.length === 0) {
    throw new ParseError("VDSL document is empty", 0);
  }

  const versionToken = versionLine.tokens[0];
  const versionRaw = tokenValue(versionToken);
  if (!versionRaw.startsWith("VDSL/")) {
    throw new ParseError(
      `Expected "VDSL/<version>" as the first declaration, got "${versionRaw}"`,
      versionLine.lineNumber
    );
  }
  const versionNum = parseFloat(versionRaw.slice(5));
  if (isNaN(versionNum)) {
    throw new ParseError(
      `Cannot parse version number from "${versionRaw}"`,
      versionLine.lineNumber
    );
  }
  cursor.advance();

  // -------------------------------------------------------------------------
  // 2. Global directives: theme, canvas
  // -------------------------------------------------------------------------
  let theme = "";
  let canvas: VDSLSpec["canvas"] = { width: 1920, height: 1080 };
  const scenes: Scene[] = [];
  let themeOverride: ThemeOverride | undefined;

  // Allowed inline-override keys (kept small on purpose — VDSL's edge is brevity).
  const PALETTE_KEYS = ["bg", "bg2", "ink", "inkSoft", "inkFaint", "grid", "green", "red", "amber", "purple"];
  const FONT_KEYS = ["display", "body", "mono"];

  while (!cursor.isEOF()) {
    cursor.skipBlankAndComments();
    if (cursor.isEOF()) break;

    const line = cursor.current!;
    if (line.tokens.length === 0) { cursor.advance(); continue; }

    const kw = tokenValue(line.tokens[0]);

    if (kw === "theme") {
      theme = line.tokens[1] ? tokenValue(line.tokens[1]) : "";
      cursor.advance();
      continue;
    }

    if (kw === "canvas") {
      // Accepts `1920x1080` as a single token or `1920 x 1080`
      const rawCanvas = line.tokens[1] ? tokenValue(line.tokens[1]) : "";
      const match = /^(\d+)[xX×](\d+)$/.exec(rawCanvas);
      if (match) {
        canvas = { width: parseInt(match[1], 10), height: parseInt(match[2], 10) };
      } else {
        // Try `1920 x 1080` (three tokens after `canvas`)
        const w = line.tokens[1] ? Number(tokenValue(line.tokens[1])) : NaN;
        const h = line.tokens[3] ? Number(tokenValue(line.tokens[3])) : NaN;
        if (!isNaN(w) && !isNaN(h)) {
          canvas = { width: w, height: h };
        }
      }
      cursor.advance();
      continue;
    }

    if (kw === "palette") {
      const rest = line.raw.trim().replace(/^palette\s*/, "");
      const props = parseInlineProperties(rest);
      const colors: Record<string, string> = {};
      for (const k of PALETTE_KEYS) if (props[k] !== undefined) colors[k] = String(props[k]);
      if (Object.keys(colors).length) {
        themeOverride = themeOverride || {};
        themeOverride.colors = { ...(themeOverride.colors || {}), ...colors } as any;
      }
      cursor.advance();
      continue;
    }

    if (kw === "font") {
      const rest = line.raw.trim().replace(/^font\s*/, "");
      const props = parseInlineProperties(rest);
      const fonts: Record<string, string> = {};
      for (const k of FONT_KEYS) if (props[k] !== undefined) fonts[k] = String(props[k]);
      if (Object.keys(fonts).length) {
        themeOverride = themeOverride || {};
        themeOverride.fonts = { ...(themeOverride.fonts || {}), ...fonts } as any;
      }
      cursor.advance();
      continue;
    }

    if (kw === "scene") {
      // Hand off to scene parser (which calls cursor.advance() internally)
      scenes.push(parseScene(cursor));
      continue;
    }

    // Unknown global directive — skip
    cursor.advance();
  }

  return { version: versionNum, theme, canvas, scenes, ...(themeOverride && { themeOverride }) };
}

export default parseVDSL;
export { parseVDSL, ParseError };
