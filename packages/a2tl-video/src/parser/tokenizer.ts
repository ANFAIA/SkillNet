/**
 * VDSL Tokenizer
 *
 * Line-by-line tokenizer for VDSL source text.
 * Handles:
 *   - Indentation measurement
 *   - Quoted string extraction (double-quotes)
 *   - Numeric literals
 *   - Bare keyword tokens
 *   - Timing expressions (`0-5s`, `3.2s`, `0.5-9s`)
 *   - Comment lines (`//`)
 *   - Color detection heuristic
 */

import type { Timing } from "./types";

// ---------------------------------------------------------------------------
// Public interfaces
// ---------------------------------------------------------------------------

export interface TokenizedLine {
  /** Raw source line (before stripping). */
  raw: string;
  /** Number of leading spaces (tabs counted as 1 space). */
  indent: number;
  /** Zero-based line index in the source file. */
  lineNumber: number;
  /** True when the line is blank or only whitespace. */
  isEmpty: boolean;
  /** True when the (trimmed) line starts with `//`. */
  isComment: boolean;
  /** Ordered token array; strings are unquoted, numbers are parsed. */
  tokens: Token[];
}

export type Token = StringToken | NumberToken | KeywordToken;

export interface StringToken {
  kind: "string";
  value: string;
}

export interface NumberToken {
  kind: "number";
  value: number;
}

export interface KeywordToken {
  kind: "keyword";
  value: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Returns the number of leading spaces in a raw source line.
 * Tab characters are treated as a single space each.
 */
export function getIndent(line: string): number {
  let count = 0;
  for (const ch of line) {
    if (ch === " " || ch === "\t") count++;
    else break;
  }
  return count;
}

/**
 * Naively recognises CSS-style hex colours (#rgb / #rrggbb / #rrggbbaa)
 * and common colour keywords.  Used to decide whether a bare token
 * represents a colour value.
 */
export function isColor(token: string): boolean {
  if (/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(token)) {
    return true;
  }
  const named = new Set([
    "red",
    "green",
    "blue",
    "yellow",
    "orange",
    "purple",
    "pink",
    "white",
    "black",
    "gray",
    "grey",
    "cyan",
    "magenta",
    "teal",
    "indigo",
    "violet",
    "amber",
    "lime",
    "emerald",
    "sky",
    "rose",
    "slate",
    "zinc",
    "neutral",
    "stone",
  ]);
  return named.has(token.toLowerCase());
}

/**
 * Attempts to parse a VDSL timing expression.
 *
 * Accepted forms:
 *   `0-5s`      → { start: 0, end: 5 }
 *   `0.5-9s`    → { start: 0.5, end: 9 }
 *   `3.2s`      → { start: 3.2 }
 *   `3s`        → { start: 3 }
 *
 * Returns `null` when the token does not look like a timing expression.
 */
export function parseTiming(token: string): Timing | null {
  // Range: <start>-<end>s
  const rangeMatch = /^(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)s$/.exec(token);
  if (rangeMatch) {
    return { start: parseFloat(rangeMatch[1]), end: parseFloat(rangeMatch[2]) };
  }

  // Point: <start>s
  const pointMatch = /^(\d+(?:\.\d+)?)s$/.exec(token);
  if (pointMatch) {
    return { start: parseFloat(pointMatch[1]) };
  }

  return null;
}

/**
 * Returns true when `token` matches a VDSL timing pattern.
 */
export function isTiming(token: string): boolean {
  return parseTiming(token) !== null;
}

// ---------------------------------------------------------------------------
// Core tokenizer
// ---------------------------------------------------------------------------

/**
 * Splits a single trimmed VDSL line into an ordered list of tokens.
 *
 * Algorithm:
 *   1. Walk char-by-char.
 *   2. On `"` enter string mode; collect until the closing `"`.
 *   3. On a digit (or `-` followed by digit when we're at word boundary),
 *      check if the upcoming segment looks like a timing token (`N-Ns` / `Ns`).
 *      If so emit it as a keyword for timing parsing; otherwise emit as number.
 *   4. Otherwise collect a bare word up to the next whitespace.
 */
export function tokenizeLine(trimmed: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;

  while (i < trimmed.length) {
    // Skip whitespace
    if (trimmed[i] === " " || trimmed[i] === "\t") {
      i++;
      continue;
    }

    // Double-quoted string
    if (trimmed[i] === '"') {
      i++; // skip opening quote
      let str = "";
      while (i < trimmed.length && trimmed[i] !== '"') {
        if (trimmed[i] === "\\" && i + 1 < trimmed.length) {
          // Handle simple escape sequences
          const esc = trimmed[i + 1];
          if (esc === '"') str += '"';
          else if (esc === "\\") str += "\\";
          else if (esc === "n") str += "\n";
          else if (esc === "t") str += "\t";
          else str += trimmed[i] + esc;
          i += 2;
        } else {
          str += trimmed[i];
          i++;
        }
      }
      i++; // skip closing quote
      tokens.push({ kind: "string", value: str });
      continue;
    }

    // Collect a bare token (no whitespace, no quote)
    let word = "";
    while (i < trimmed.length && trimmed[i] !== " " && trimmed[i] !== "\t" && trimmed[i] !== '"') {
      word += trimmed[i];
      i++;
    }

    if (word === "") continue;

    // Try timing first (e.g., `0-5s`, `3.2s`)
    if (isTiming(word)) {
      tokens.push({ kind: "keyword", value: word });
      continue;
    }

    // Pure number?
    const num = Number(word);
    if (word !== "" && !isNaN(num) && word !== "-") {
      tokens.push({ kind: "number", value: num });
      continue;
    }

    // Everything else is a keyword
    tokens.push({ kind: "keyword", value: word });
  }

  return tokens;
}

// ---------------------------------------------------------------------------
// Full-document tokenizer
// ---------------------------------------------------------------------------

/**
 * Tokenizes every line in a VDSL source string and returns an array of
 * `TokenizedLine` objects, one per source line.
 */
export function tokenizeDocument(source: string): TokenizedLine[] {
  const rawLines = source.split(/\r?\n/);
  return rawLines.map((raw, lineNumber) => {
    const indent = getIndent(raw);
    const trimmed = raw.trim();
    const isEmpty = trimmed.length === 0;
    const isComment = trimmed.startsWith("//");

    return {
      raw,
      indent,
      lineNumber,
      isEmpty,
      isComment,
      tokens: isEmpty || isComment ? [] : tokenizeLine(trimmed),
    };
  });
}
