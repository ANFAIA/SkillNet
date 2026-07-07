/**
 * Markdown parser — pure string parsing, no external deps.
 * Splits by headings, builds tree, extracts frontmatter.
 */

import { getCached, setCached } from './cache.js';

// ── Types ──────────────────────────────────────────────────────────────

export interface HeadingNode {
  level: number;
  title: string;
  lineStart: number;
  lineEnd: number;       // inclusive
  tokenEstimate: number; // chars / 4
  children: HeadingNode[];
}

export interface ParsedMarkdown {
  frontmatter: Record<string, string | string[]> | null;
  frontmatterRaw: string | null;
  tree: HeadingNode[];
  fullText: string;
  lines: string[];
}

export interface TreeLine {
  indent: string;
  title: string;
  tokens: number;
  level: number;
}

// ── Token estimation ───────────────────────────────────────────────────

export function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

// ── Frontmatter extraction ─────────────────────────────────────────────

function extractFrontmatter(lines: string[]): {
  frontmatter: Record<string, string | string[]> | null;
  frontmatterRaw: string | null;
  contentStartLine: number;
} {
  if (lines.length === 0 || lines[0].trim() !== '---') {
    return { frontmatter: null, frontmatterRaw: null, contentStartLine: 0 };
  }

  let endIdx = -1;
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() === '---') {
      endIdx = i;
      break;
    }
  }

  if (endIdx === -1) {
    return { frontmatter: null, frontmatterRaw: null, contentStartLine: 0 };
  }

  const fmLines = lines.slice(1, endIdx);
  const raw = fmLines.join('\n');
  const parsed: Record<string, string | string[]> = {};

  let currentKey: string | null = null;
  let currentArray: string[] | null = null;

  for (const line of fmLines) {
    // Check for a new key: value pair
    const match = line.match(/^(\w[\w_-]*):\s*(.*)$/);
    if (match) {
      // Flush previous array if any
      if (currentKey && currentArray) {
        parsed[currentKey] = currentArray;
        currentArray = null;
      }

      currentKey = match[1];
      const value = match[2].trim();

      if (value === '') {
        // Could be start of a multi-line array (key:\n  - item)
        currentArray = [];
      } else if (value.startsWith('[') && value.endsWith(']')) {
        // Inline array: tags: [a, b, c]
        parsed[currentKey] = value
          .slice(1, -1)
          .split(',')
          .map(s => s.trim())
          .filter(s => s.length > 0);
        currentKey = null;
      } else {
        parsed[currentKey] = value;
        currentKey = null;
      }
    } else if (currentKey && currentArray !== null) {
      // Check for array item:   - value
      const itemMatch = line.match(/^\s+-\s+(.+)$/);
      if (itemMatch) {
        currentArray.push(itemMatch[1].trim());
      }
    }
  }

  // Flush last array if any
  if (currentKey && currentArray) {
    parsed[currentKey] = currentArray;
  }

  return {
    frontmatter: parsed,
    frontmatterRaw: raw,
    contentStartLine: endIdx + 1,
  };
}

// ── Heading detection ──────────────────────────────────────────────────

const HEADING_RE = /^(#{1,6})\s+(.+)$/;

interface RawHeading {
  level: number;
  title: string;
  lineIndex: number; // 0-based index into lines array
}

function findHeadings(lines: string[], startLine: number): RawHeading[] {
  const headings: RawHeading[] = [];
  let inCodeBlock = false;

  for (let i = startLine; i < lines.length; i++) {
    // Track fenced code blocks (``` or ~~~)
    if (lines[i].trimStart().startsWith('```') || lines[i].trimStart().startsWith('~~~')) {
      inCodeBlock = !inCodeBlock;
      continue;
    }

    // Skip lines inside code blocks
    if (inCodeBlock) continue;

    const m = lines[i].match(HEADING_RE);
    if (m) {
      headings.push({
        level: m[1].length,
        title: m[2].trim(),
        lineIndex: i,
      });
    }
  }
  return headings;
}

// ── Build tree ─────────────────────────────────────────────────────────

function sliceContent(lines: string[], from: number, to: number): string {
  return lines.slice(from, to + 1).join('\n');
}

function buildTree(headings: RawHeading[], lines: string[]): HeadingNode[] {
  if (headings.length === 0) return [];

  // Assign lineEnd: each heading's content ends where the next heading starts (or EOF)
  const nodes: HeadingNode[] = headings.map((h, i) => {
    const lineEnd = i < headings.length - 1
      ? headings[i + 1].lineIndex - 1
      : lines.length - 1;
    const content = sliceContent(lines, h.lineIndex, lineEnd);
    return {
      level: h.level,
      title: h.title,
      lineStart: h.lineIndex,
      lineEnd,
      tokenEstimate: estimateTokens(content),
      children: [],
    };
  });

  // Build hierarchy using a stack
  const root: HeadingNode[] = [];
  const stack: HeadingNode[] = [];

  for (const node of nodes) {
    // Pop stack until we find a parent (lower level number)
    while (stack.length > 0 && stack[stack.length - 1].level >= node.level) {
      stack.pop();
    }

    if (stack.length === 0) {
      root.push(node);
    } else {
      stack[stack.length - 1].children.push(node);
    }
    stack.push(node);
  }

  return root;
}

// ── Main parse function ────────────────────────────────────────────────

export function parseMarkdown(text: string): ParsedMarkdown {
  const lines = text.split('\n');
  const { frontmatter, frontmatterRaw, contentStartLine } = extractFrontmatter(lines);
  const headings = findHeadings(lines, contentStartLine);
  const tree = buildTree(headings, lines);

  return {
    frontmatter,
    frontmatterRaw,
    tree,
    fullText: text,
    lines,
  };
}

// ── Tree rendering (compact text) ──────────────────────────────────────

export function renderTree(nodes: HeadingNode[], prefix = ''): string {
  const lines: string[] = [];
  for (const node of nodes) {
    const indent = '  '.repeat(node.level - 1);
    lines.push(`${indent}${'#'.repeat(node.level)} ${node.title}  (~${node.tokenEstimate} tok)`);
    if (node.children.length > 0) {
      lines.push(renderTree(node.children, prefix));
    }
  }
  return lines.join('\n');
}

// ── Section extraction ─────────────────────────────────────────────────

function flattenTree(nodes: HeadingNode[]): HeadingNode[] {
  const flat: HeadingNode[] = [];
  for (const n of nodes) {
    flat.push(n);
    flat.push(...flattenTree(n.children));
  }
  return flat;
}

/**
 * Check if a short query (2-3 chars, already lowercased) matches a word boundary
 * in the target (ORIGINAL casing preserved for camelCase/acronym detection).
 * "ui" matches "User Interface" (acronym), "da" matches "Dashboard" (prefix).
 * "sc" matches "SkillCard" (camelCase acronym).
 */
function matchesWordBoundary(q: string, target: string): boolean {
  // Split target into words on spaces, hyphens, underscores, camelCase boundaries
  const words = target.split(/[\s_\-/]+|(?<=[a-z])(?=[A-Z])/);

  // Direct word-start match: "da" matches "Dashboard"
  for (const w of words) {
    if (w.toLowerCase().startsWith(q)) return true;
  }

  // Acronym match: "ui" matches "User Interface" (initials U+I = "ui")
  if (q.length >= 2 && q.length <= 5) {
    const initials = words
      .filter(w => w.length > 0)
      .map(w => w[0].toLowerCase())
      .join('');
    if (initials.includes(q)) return true;
  }

  return false;
}

/**
 * Fuzzy match: case-insensitive substring match, acronym match, word overlap.
 * Returns similarity 0..1
 */
function fuzzyScore(query: string, target: string): number {
  const q = query.toLowerCase().trim();
  const t = target.toLowerCase().trim();

  // Exact match
  if (q === t) return 1.0;

  // Short queries (2-3 chars): only match on word boundaries to avoid false positives
  if (q.length >= 2 && q.length < 4) {
    // Pass ORIGINAL target for camelCase/acronym detection, plus lowercased for prefix
    if (matchesWordBoundary(q, target.trim())) return 0.85;
    // Also allow exact word match within target words
    const tWords = t.split(/\s+/);
    if (tWords.some(w => w === q)) return 0.9;
    return 0; // Short queries MUST match boundaries — no substring matching
  }

  // Substring match — for queries >= 4 chars (avoids "no" matching "conocimiento")
  if (q.length >= 4 && t.includes(q)) return 0.9;
  if (q.length >= 4 && q.includes(t)) return 0.8;

  // Word overlap (ignore words < 3 chars unless they're the only word)
  const qWords = q.split(/\s+/).filter(w => w.length >= 3);
  const tWords = t.split(/\s+/).filter(w => w.length >= 3);

  // If no valid words remain after filtering, no match
  if (qWords.length === 0) return 0;

  const matches = qWords.filter(w => tWords.some(tw => tw.includes(w) || w.includes(tw)));
  if (matches.length > 0) {
    return 0.5 + (0.3 * matches.length / Math.max(qWords.length, tWords.length));
  }

  return 0;
}

export function findSection(parsed: ParsedMarkdown, heading: string): {
  node: HeadingNode;
  content: string;
} | null {
  const allNodes = flattenTree(parsed.tree);
  let best: HeadingNode | null = null;
  let bestScore = 0;

  for (const node of allNodes) {
    const score = fuzzyScore(heading, node.title);
    if (score > bestScore) {
      bestScore = score;
      best = node;
    }
  }

  if (!best || bestScore < 0.5) return null;

  const content = parsed.lines.slice(best.lineStart, best.lineEnd + 1).join('\n');
  return { node: best, content };
}

// ── Text search ────────────────────────────────────────────────────────

export interface SearchResult {
  heading: string;
  level: number;
  lineNumber: number; // 1-based
  matchLine: string;
  context: string;    // 2 lines before + match + 2 lines after
}

export function searchInFile(parsed: ParsedMarkdown, query: string): SearchResult[] {
  const q = query.toLowerCase();
  const results: SearchResult[] = [];
  const allNodes = flattenTree(parsed.tree);

  for (let i = 0; i < parsed.lines.length; i++) {
    if (parsed.lines[i].toLowerCase().includes(q)) {
      // Find which heading this line belongs to
      let ownerHeading = '(before first heading)';
      let ownerLevel = 0;
      for (const node of allNodes) {
        if (i >= node.lineStart && i <= node.lineEnd) {
          ownerHeading = node.title;
          ownerLevel = node.level;
        }
      }

      const start = Math.max(0, i - 2);
      const end = Math.min(parsed.lines.length - 1, i + 2);
      const context = parsed.lines.slice(start, end + 1).join('\n');

      results.push({
        heading: ownerHeading,
        level: ownerLevel,
        lineNumber: i + 1,
        matchLine: parsed.lines[i],
        context,
      });
    }
  }

  return results;
}

// ── Cached parse ──────────────────────────────────────────────────────

export async function parseMarkdownCached(path: string, text: string): Promise<ParsedMarkdown> {
  const cached = await getCached(path);
  if (cached) return cached;

  const parsed = parseMarkdown(text);
  await setCached(path, parsed);
  return parsed;
}
