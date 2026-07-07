#!/usr/bin/env node
/**
 * Benchmark — test md-reader tools against real vault files.
 * Measures: token savings, response time, cache hit rate, fuzzy matcher accuracy.
 * Tests diverse edge cases: code blocks, no headings, deep nesting, binary, huge files, etc.
 */

import { readFile } from 'node:fs/promises';
import {
  parseMarkdown,
  parseMarkdownCached,
  renderTree,
  findSection,
  searchInFile,
  estimateTokens,
} from './parser.js';
import { findMdFiles, extractWikilinks, buildGraph } from './graph.js';
import { getCacheStats, clearCache } from './cache.js';
import { compileIndex, queryIndex } from './vault-index.js';

// ── Config ─────────────────────────────────────────────────────────────

interface TestFile {
  path: string;
  tag: string;  // category for reporting
  searchQuery?: string;  // per-file search query (falls back to generic)
}

const VAULT = 'C:/Users/sonde/Documents/Obsidian Vault';

const TEST_FILES: TestFile[] = [
  // ── Original 2 files ──
  {
    path: `${VAULT}/15_TRABAJO/SkillNet/07_ANFAIA/_context.md`,
    tag: 'original',
  },
  {
    path: `${VAULT}/15_TRABAJO/SkillNet/07_ANFAIA/investigacion/fronteras_semanticas/dashboard.md`,
    tag: 'original',
    searchQuery: 'ontologia',
  },

  // ── VERY LARGE file (1437 lines) ──
  {
    path: `${VAULT}/15_TRABAJO/SkillNet/07_ANFAIA/investigacion/fronteras_semanticas/profundidad/clasificacion_3_ejes.md`,
    tag: 'large',
    searchQuery: 'cross-dominio',
  },

  // ── File with NO headings (plain text, 20 lines) ──
  {
    path: `${VAULT}/50_CEREBRO/REDES/02_TECH/LINKEDIN/_analisis/yelko-veiga.md`,
    tag: 'no-headings',
    searchQuery: 'InnovaTech',
  },

  // ── File with DEEPLY NESTED headings (h1>h2>h3>h4) ──
  {
    path: `${VAULT}/15_TRABAJO/SkillNet/07_ANFAIA/investigacion/post_markdown/patron_datos_tontos_lector_inteligente.md`,
    tag: 'deep-nesting',
    searchQuery: 'DOM',
  },

  // ── File with CODE BLOCKS containing # characters (parser stress test) ──
  {
    path: `${VAULT}/10_PROYECTOS_ACTUALES/Cerebro_Digital/01_Diseno/sqlite_diseno.md`,
    tag: 'code-blocks',
    searchQuery: 'SQLite',
  },

  // ── File with CODE BLOCKS + architecture diagrams (# in ``` blocks) ──
  {
    path: `${VAULT}/10_PROYECTOS_ACTUALES/Cerebro_Digital/01_Diseno/vision_arquitectura.md`,
    tag: 'code-blocks',
    searchQuery: 'Bootloader',
  },

  // ── File with YAML frontmatter arrays (tags:\n  - item) ──
  {
    path: `${VAULT}/15_TRABAJO/SkillNet/07_ANFAIA/investigacion/ui_innovadora/engagement_retencion.md`,
    tag: 'fm-arrays',
    searchQuery: 'Duolingo',
  },

  // ── VERY SMALL file (<10 lines) ──
  {
    path: `${VAULT}/30_ENTRENAMIENTO/BOXEO/Sesiones/2025-05/2025-05-10 Entreno normal.md`,
    tag: 'tiny',
    searchQuery: 'saco',
  },

  // ── File heavy with wikilinks [[...]] ──
  {
    path: `${VAULT}/50_CEREBRO/MEDIA/00_MEDIA_Indice.md`,
    tag: 'wikilinks',
    searchQuery: 'Naruto',
  },

  // ── File with wikilinks and tables (vault root) ──
  {
    path: `${VAULT}/00_HOME.md`,
    tag: 'wikilinks',
    searchQuery: 'Cerebro',
  },

  // ── File from different vault area (Sesiones log, many ## headings) ──
  {
    path: `${VAULT}/40_VIDA/Sesiones/2026/05.md`,
    tag: 'session-log',
    searchQuery: 'Proyecto',
  },

  // ── Spec file with TypeScript code blocks and headings inside them ──
  {
    path: `${VAULT}/15_TRABAJO/SkillNet/07_ANFAIA/investigacion/post_markdown/spec_mcp_smart_reader.md`,
    tag: 'code-blocks',
    searchQuery: 'md_tree',
  },

  // ── Learning guide with mixed nesting (h2>h3) and frontmatter arrays ──
  {
    path: `${VAULT}/15_TRABAJO/SkillNet/07_ANFAIA/investigacion/learnlm/guia.md`,
    tag: 'fm-arrays',
    searchQuery: 'socratico',
  },
];

// ── Helpers ────────────────────────────────────────────────────────────

function bar(pctVal: number, width = 30): string {
  const clamped = Math.max(0, Math.min(100, pctVal));
  const filled = Math.round(clamped / 100 * width);
  return '\u2588'.repeat(filled) + '\u2591'.repeat(width - filled);
}

function pct(part: number, whole: number): string {
  if (whole === 0) return 'N/A';
  return `${Math.round((1 - part / whole) * 100)}%`;
}

function pctNum(part: number, whole: number): number {
  if (whole === 0) return 0;
  return Math.round((1 - part / whole) * 100);
}

function timeMs(fn: () => void): number {
  const start = performance.now();
  fn();
  return Math.round((performance.now() - start) * 100) / 100;
}

async function timeMsAsync(fn: () => Promise<void>): Promise<number> {
  const start = performance.now();
  await fn();
  return Math.round((performance.now() - start) * 100) / 100;
}

// ── Validation checks ─────────────────────────────────────────────────

interface Issue {
  file: string;
  severity: 'bug' | 'warning' | 'info';
  message: string;
}

function validateParsing(
  filePath: string,
  text: string,
  parsed: ReturnType<typeof parseMarkdown>,
): Issue[] {
  const issues: Issue[] = [];
  const shortName = filePath.split('/').pop()!;

  // Count expected headings (lines starting with # outside code blocks)
  let expectedHeadings = 0;
  let inCode = false;
  for (const line of text.split('\n')) {
    if (line.trimStart().startsWith('```') || line.trimStart().startsWith('~~~')) {
      inCode = !inCode;
      continue;
    }
    if (!inCode && /^#{1,6}\s+.+$/.test(line)) {
      expectedHeadings++;
    }
  }

  const actualHeadings = countHeadings(parsed.tree);
  if (actualHeadings !== expectedHeadings) {
    issues.push({
      file: shortName,
      severity: 'bug',
      message: `Heading count mismatch: expected ${expectedHeadings}, got ${actualHeadings}`,
    });
  }

  // Check frontmatter parsing
  const hasFrontmatter = text.trimStart().startsWith('---');
  if (hasFrontmatter && !parsed.frontmatter) {
    issues.push({
      file: shortName,
      severity: 'warning',
      message: 'File has --- but frontmatter was not parsed',
    });
  }

  // Check for zero-token sections (degenerate)
  const flat = flattenTree(parsed.tree);
  for (const node of flat) {
    if (node.tokenEstimate === 0 && node.children.length === 0) {
      issues.push({
        file: shortName,
        severity: 'info',
        message: `Empty section: "${node.title}" (0 tokens)`,
      });
    }
  }

  // Check if tree rendering works
  try {
    renderTree(parsed.tree);
  } catch (e: any) {
    issues.push({
      file: shortName,
      severity: 'bug',
      message: `renderTree crashed: ${e.message}`,
    });
  }

  // Check section lookup
  const firstH2 = findFirstLevel2(parsed.tree);
  if (firstH2) {
    try {
      const section = findSection(parsed, firstH2);
      if (!section) {
        issues.push({
          file: shortName,
          severity: 'warning',
          message: `findSection returned null for existing heading "${firstH2}"`,
        });
      }
    } catch (e: any) {
      issues.push({
        file: shortName,
        severity: 'bug',
        message: `findSection crashed: ${e.message}`,
      });
    }
  }

  return issues;
}

function flattenTree(nodes: any[]): any[] {
  const flat: any[] = [];
  for (const n of nodes) {
    flat.push(n);
    flat.push(...flattenTree(n.children || []));
  }
  return flat;
}

// ── Fuzzy matcher tests ───────────────────────────────────────────────

interface FuzzyTest {
  query: string;
  heading: string;
  shouldMatch: boolean;
  description: string;
}

const FUZZY_TESTS: FuzzyTest[] = [
  // Short queries (2-3 chars) — word boundary matching
  { query: 'UI', heading: 'User Interface', shouldMatch: true, description: '2-char acronym match (UI)' },
  { query: 'API', heading: 'REST API Reference', shouldMatch: true, description: '3-char exact word in title' },
  { query: 'no', heading: 'conocimiento', shouldMatch: false, description: '2-char substring reject' },
  { query: 'en', heading: 'engagement', shouldMatch: true, description: '2-char word-start match' },
  { query: 'MCP', heading: 'Model Context Protocol', shouldMatch: true, description: '3-char acronym' },
  { query: 'DB', heading: 'Database Design', shouldMatch: false, description: '2-char NOT a prefix or acronym' },
  { query: 'DB', heading: 'DB Schema', shouldMatch: true, description: '2-char exact word match' },
  { query: 'da', heading: 'Dashboard', shouldMatch: true, description: '2-char word-start match' },
  { query: 'fr', heading: 'frontmatter', shouldMatch: true, description: '2-char word-start match' },

  // Standard queries (4+ chars)
  { query: 'database', heading: 'Database Design', shouldMatch: true, description: '4+ char substring' },
  { query: 'sistema', heading: 'Sistema de Clasificacion', shouldMatch: true, description: 'Spanish substring' },
  { query: 'xyz123', heading: 'Normal Heading', shouldMatch: false, description: 'No match expected' },

  // Multi-word queries
  { query: 'cross dominio', heading: 'Cross-Dominio Analysis', shouldMatch: true, description: 'Multi-word overlap' },

  // CamelCase boundary detection (pass original casing to matcher)
  { query: 'SC', heading: 'SkillCard Component', shouldMatch: true, description: '2-char acronym from multi-word' },
];

function runFuzzyTests(): { passed: number; failed: number; results: string[] } {
  let passed = 0;
  let failed = 0;
  const results: string[] = [];

  for (const test of FUZZY_TESTS) {
    // Create a minimal parsed structure with just this heading
    const parsed = parseMarkdown(`# ${test.heading}\nSome content here.`);
    const section = findSection(parsed, test.query);
    const matched = section !== null;

    if (matched === test.shouldMatch) {
      passed++;
      results.push(`    [PASS] "${test.query}" -> "${test.heading}" (${test.description})`);
    } else {
      failed++;
      results.push(`    [FAIL] "${test.query}" -> "${test.heading}" — expected ${test.shouldMatch ? 'match' : 'no match'}, got ${matched ? 'match' : 'no match'} (${test.description})`);
    }
  }

  return { passed, failed, results };
}

// ── Vault-wide search benchmark ───────────────────────────────────────

async function benchmarkVaultSearch(): Promise<{
  fileCount: number;
  timeMs: number;
  matchCount: number;
}> {
  const searchDir = `${VAULT}/15_TRABAJO/SkillNet/07_ANFAIA`;
  const query = 'sistema';

  const start = performance.now();
  const mdFiles = await findMdFiles(searchDir, true);
  let matchCount = 0;

  // Parallel search (same as md_search_vault now does)
  const BATCH_SIZE = 50;
  for (let batchStart = 0; batchStart < mdFiles.length; batchStart += BATCH_SIZE) {
    const batch = mdFiles.slice(batchStart, batchStart + BATCH_SIZE);
    const settled = await Promise.allSettled(
      batch.map(async (filePath) => {
        const text = await readFile(filePath, 'utf-8');
        const parsed = parseMarkdown(text);
        return searchInFile(parsed, query).length;
      })
    );
    for (const result of settled) {
      if (result.status === 'fulfilled') {
        matchCount += result.value;
      }
    }
  }

  const elapsed = Math.round(performance.now() - start);
  return { fileCount: mdFiles.length, timeMs: elapsed, matchCount };
}

// ── Cache benchmark ──────────────────────────────────────────────────

async function benchmarkCache(): Promise<{
  coldMs: number;
  warmMs: number;
  speedup: string;
}> {
  // Use the LARGEST file for meaningful cache comparison
  const largePath = TEST_FILES.find(f => f.tag === 'large')?.path || TEST_FILES[0].path;
  const text = await readFile(largePath, 'utf-8');
  const ITERATIONS = 100;

  // Clear cache for cold test
  clearCache();

  // Cold parse (parseMarkdown without cache — pure CPU cost)
  const coldStart = performance.now();
  for (let i = 0; i < ITERATIONS; i++) {
    parseMarkdown(text);
  }
  const coldMs = Math.round((performance.now() - coldStart) * 100) / 100;

  // Warm (cached) — seed cache, then read from it
  // Note: cache hits involve stat() I/O, so this measures real-world benefit
  await parseMarkdownCached(largePath, text);
  const warmStart = performance.now();
  for (let i = 0; i < ITERATIONS; i++) {
    await parseMarkdownCached(largePath, text);
  }
  const warmMs = Math.round((performance.now() - warmStart) * 100) / 100;

  const speedup = warmMs > 0 ? `${(coldMs / warmMs).toFixed(1)}x` : 'N/A';

  return { coldMs, warmMs, speedup };
}

// ── Graph benchmark ──────────────────────────────────────────────────

async function benchmarkGraph(): Promise<{
  fileCount: number;
  outlinkCount: number;
  inlinkCount: number;
  timeMs: number;
}> {
  const testPath = `${VAULT}/00_HOME.md`;
  const start = performance.now();

  let text: string;
  try {
    text = await readFile(testPath, 'utf-8');
  } catch {
    return { fileCount: 0, outlinkCount: 0, inlinkCount: 0, timeMs: 0 };
  }

  const { dirname } = await import('node:path');
  const dir = dirname(testPath);
  const mdFiles = await findMdFiles(dir);

  const siblingTexts = new Map<string, string>();
  const settled = await Promise.allSettled(
    mdFiles.map(async (f) => ({ path: f, text: await readFile(f, 'utf-8') }))
  );
  for (const result of settled) {
    if (result.status === 'fulfilled') {
      siblingTexts.set(result.value.path, result.value.text);
    }
  }

  const graph = await buildGraph(testPath, text, siblingTexts);
  const elapsed = Math.round(performance.now() - start);

  return {
    fileCount: mdFiles.length,
    outlinkCount: graph.outlinks.length,
    inlinkCount: graph.inlinks.length,
    timeMs: elapsed,
  };
}

// ── Main ───────────────────────────────────────────────────────────────

async function runBenchmark() {
  console.log('');
  console.log('\u2554' + '\u2550'.repeat(70) + '\u2557');
  console.log('\u2551      mcp-md-reader  BENCHMARK  v2.0 (hardened)                       \u2551');
  console.log('\u2551      ' + TEST_FILES.length + ' files + fuzzy tests + timing + cache + vault search        \u2551');
  console.log('\u255a' + '\u2550'.repeat(70) + '\u255d\n');

  // ═══════════════════════════════════════════════════════════════════
  // PHASE 1: Per-file parsing tests
  // ═══════════════════════════════════════════════════════════════════

  console.log('  PHASE 1: Per-file parsing and token savings\n');

  const allResults: Array<{
    file: string;
    tag: string;
    fullTokens: number;
    lines: number;
    headings: number;
    treeTokens: number;
    sectionTokens: number;
    searchTokens: number;
    searchMatches: number;
    fmTokens: number;
    hasFrontmatter: boolean;
    fmArrays: boolean;
    parseTimeMs: number;
    issues: Issue[];
  }> = [];

  const allIssues: Issue[] = [];

  for (const testFile of TEST_FILES) {
    const { path: filePath, tag, searchQuery } = testFile;
    const shortName = filePath.split('/').pop()!;

    console.log(`\u2501\u2501\u2501 [${tag}] ${shortName} \u2501\u2501\u2501`);
    console.log(`    Path: ${filePath}\n`);

    let text: string;
    try {
      text = await readFile(filePath, 'utf-8');
    } catch (e: any) {
      console.log(`    ERROR: ${e.message}\n`);
      allIssues.push({ file: shortName, severity: 'bug', message: `Could not read: ${e.message}` });
      continue;
    }

    // Timed parse
    let parsed: ReturnType<typeof parseMarkdown>;
    const parseTime = timeMs(() => { parsed = parseMarkdown(text); });
    parsed = parsed!;

    const fullTokens = estimateTokens(text);
    const headingCount = countHeadings(parsed.tree);

    // Validate
    const issues = validateParsing(filePath, text, parsed);
    allIssues.push(...issues);

    // Check if frontmatter has arrays
    let fmArrays = false;
    if (parsed.frontmatter) {
      for (const [, v] of Object.entries(parsed.frontmatter)) {
        if (Array.isArray(v)) { fmArrays = true; break; }
      }
    }

    console.log(`    Full file: ${text.length} chars, ~${fullTokens} tokens, ${parsed.lines.length} lines`);
    console.log(`    Parse time: ${parseTime}ms`);
    console.log(`    Headings found: ${headingCount}`);
    console.log(`    Frontmatter: ${parsed.frontmatter ? 'yes' : 'no'}${fmArrays ? ' (with arrays)' : ''}`);
    if (issues.length > 0) {
      for (const issue of issues) {
        const icon = issue.severity === 'bug' ? 'BUG' : issue.severity === 'warning' ? 'WARN' : 'INFO';
        console.log(`    [${icon}] ${issue.message}`);
      }
    } else {
      console.log(`    [OK] All checks passed`);
    }
    console.log();

    // ── md_tree ──
    const treeText = renderTree(parsed.tree);
    const treeTokens = estimateTokens(treeText);
    const treeSaving = pct(treeTokens, fullTokens);
    console.log(`    md_tree:`);
    console.log(`      Output: ~${treeTokens} tokens`);
    console.log(`      Saving: ${treeSaving}  ${bar(pctNum(treeTokens, fullTokens))}`);
    if (treeText.length > 0) {
      console.log(`      ---`);
      const treeLines = treeText.split('\n');
      console.log(`      ${treeLines.slice(0, 6).join('\n      ')}${treeLines.length > 6 ? '\n      ...' : ''}`);
    } else {
      console.log(`      (no tree — file has no headings)`);
    }
    console.log();

    // ── md_section (pick first ## heading) ──
    const testHeading = findFirstLevel2(parsed.tree);
    let sectionTokens = 0;
    if (testHeading) {
      const result = findSection(parsed, testHeading);
      if (result) {
        sectionTokens = estimateTokens(result.content);
        const secSaving = pct(sectionTokens, fullTokens);
        console.log(`    md_section("${testHeading}"):`);
        console.log(`      Output: ~${sectionTokens} tokens`);
        console.log(`      Saving: ${secSaving}  ${bar(pctNum(sectionTokens, fullTokens))}`);
        console.log(`      Preview: ${result.content.split('\n')[0].substring(0, 70)}...`);
        console.log();
      }
    } else {
      console.log(`    md_section: N/A (no ## heading found)\n`);
    }

    // ── md_search ──
    const query = searchQuery || 'sistema';
    const searchResults = searchInFile(parsed, query);
    const searchOutput = searchResults.map(r => r.context).join('\n\n');
    const searchTokens = estimateTokens(searchOutput || 'no matches');
    const searchSaving = pct(searchTokens, fullTokens);
    console.log(`    md_search("${query}"):`);
    console.log(`      Matches: ${searchResults.length}`);
    console.log(`      Output: ~${searchTokens} tokens`);
    console.log(`      Saving: ${searchSaving}  ${bar(pctNum(searchTokens, fullTokens))}`);
    console.log();

    // ── md_frontmatter ──
    const fmTokens = parsed.frontmatterRaw ? estimateTokens(parsed.frontmatterRaw) : 0;
    const fmSaving = fmTokens > 0 ? pct(fmTokens, fullTokens) : 'N/A';
    console.log(`    md_frontmatter:`);
    console.log(`      Output: ~${fmTokens} tokens`);
    console.log(`      Saving: ${fmSaving}  ${fmTokens > 0 ? bar(pctNum(fmTokens, fullTokens)) : ''}`);
    if (parsed.frontmatter) {
      const keys = Object.keys(parsed.frontmatter);
      const preview = keys.slice(0, 5).map(k => {
        const v = parsed.frontmatter![k];
        return `${k}: ${Array.isArray(v) ? `[${v.join(', ')}]` : v}`;
      }).join(' | ');
      console.log(`      Keys: ${preview}`);
    }
    console.log();

    allResults.push({
      file: filePath,
      tag,
      fullTokens,
      lines: parsed.lines.length,
      headings: headingCount,
      treeTokens,
      sectionTokens,
      searchTokens,
      searchMatches: searchResults.length,
      fmTokens,
      hasFrontmatter: !!parsed.frontmatter,
      fmArrays,
      parseTimeMs: parseTime,
      issues,
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // PHASE 2: Fuzzy matcher tests
  // ═══════════════════════════════════════════════════════════════════

  console.log('\n' + '\u2554' + '\u2550'.repeat(70) + '\u2557');
  console.log('\u2551  PHASE 2: Fuzzy matcher accuracy                                      \u2551');
  console.log('\u255a' + '\u2550'.repeat(70) + '\u255d\n');

  const fuzzyResults = runFuzzyTests();
  for (const line of fuzzyResults.results) {
    console.log(line);
  }
  console.log(`\n    Score: ${fuzzyResults.passed}/${fuzzyResults.passed + fuzzyResults.failed} passed`);

  // ═══════════════════════════════════════════════════════════════════
  // PHASE 3: Cache benchmark
  // ═══════════════════════════════════════════════════════════════════

  console.log('\n' + '\u2554' + '\u2550'.repeat(70) + '\u2557');
  console.log('\u2551  PHASE 3: Cache performance                                           \u2551');
  console.log('\u255a' + '\u2550'.repeat(70) + '\u255d\n');

  const cacheResult = await benchmarkCache();
  console.log(`    Cold parse (10x): ${cacheResult.coldMs}ms`);
  console.log(`    Warm/cached (10x): ${cacheResult.warmMs}ms`);
  console.log(`    Speedup: ${cacheResult.speedup}`);
  const cacheStats = getCacheStats();
  console.log(`    Memory cache entries: ${cacheStats.memoryEntries}`);
  console.log(`    Disk cache entries: ${cacheStats.diskEntries}`);

  // ═══════════════════════════════════════════════════════════════════
  // PHASE 4: Vault-wide parallel search
  // ═══════════════════════════════════════════════════════════════════

  console.log('\n' + '\u2554' + '\u2550'.repeat(70) + '\u2557');
  console.log('\u2551  PHASE 4: Vault-wide parallel search (md_search_vault)                \u2551');
  console.log('\u255a' + '\u2550'.repeat(70) + '\u255d\n');

  const vaultResult = await benchmarkVaultSearch();
  console.log(`    Directory: ${VAULT}/15_TRABAJO/SkillNet/07_ANFAIA`);
  console.log(`    Files scanned: ${vaultResult.fileCount}`);
  console.log(`    Matches found: ${vaultResult.matchCount}`);
  console.log(`    Time: ${vaultResult.timeMs}ms`);
  if (vaultResult.fileCount > 0) {
    console.log(`    Per-file avg: ${(vaultResult.timeMs / vaultResult.fileCount).toFixed(1)}ms`);
  }

  // ═══════════════════════════════════════════════════════════════════
  // PHASE 5: Graph benchmark
  // ═══════════════════════════════════════════════════════════════════

  console.log('\n' + '\u2554' + '\u2550'.repeat(70) + '\u2557');
  console.log('\u2551  PHASE 5: Graph benchmark (md_graph)                                  \u2551');
  console.log('\u255a' + '\u2550'.repeat(70) + '\u255d\n');

  const graphResult = await benchmarkGraph();
  console.log(`    File: ${VAULT}/00_HOME.md`);
  console.log(`    Sibling .md files: ${graphResult.fileCount}`);
  console.log(`    Outlinks: ${graphResult.outlinkCount}`);
  console.log(`    Inlinks: ${graphResult.inlinkCount}`);
  console.log(`    Time: ${graphResult.timeMs}ms`);

  // ═══════════════════════════════════════════════════════════════════
  // PHASE 6: Vault index benchmark (md_vault_index)
  // ═══════════════════════════════════════════════════════════════════

  console.log('\n' + '\u2554' + '\u2550'.repeat(70) + '\u2557');
  console.log('\u2551  PHASE 6: Vault index (md_vault_index)                                \u2551');
  console.log('\u255a' + '\u2550'.repeat(70) + '\u255d\n');

  // Compile time
  const compileStart = performance.now();
  const index = await compileIndex(VAULT);
  const compileMs = Math.round(performance.now() - compileStart);
  console.log(`    Compile: ${index.meta.total_nodes} nodes, ${index.meta.total_edges} edges in ${compileMs}ms`);
  console.log(`    Per-file avg: ${(compileMs / index.meta.total_nodes).toFixed(2)}ms`);

  // Query benchmarks — run each query type and measure time
  const queries: Array<{ name: string; query: string; nodeId?: string; depth?: number }> = [
    { name: 'stats', query: 'stats' },
    { name: 'node', query: 'node', nodeId: '00_home' },
    { name: 'neighbors (d=1)', query: 'neighbors', nodeId: '00_intentia_indice', depth: 1 },
    { name: 'neighbors (d=2)', query: 'neighbors', nodeId: '00_intentia_indice', depth: 2 },
    { name: 'most_connected', query: 'most_connected', depth: 10 },
    { name: 'isolated', query: 'isolated' },
    { name: 'search_type', query: 'search_type', nodeId: 'indice' },
    { name: 'path', query: 'path', nodeId: 'brainstorm>00_intentia_indice' },
  ];

  console.log('\n    Query benchmarks (avg of 50 runs):');
  console.log('    ' + '\u2500'.repeat(55));

  const queryTimings: Array<{ name: string; avgMs: number; resultSize: number }> = [];

  for (const q of queries) {
    const RUNS = 50;
    let resultSize = 0;
    const qStart = performance.now();
    for (let i = 0; i < RUNS; i++) {
      const result = await queryIndex(VAULT, q.query as any, q.nodeId, q.depth);
      if (i === 0) resultSize = result.length;
    }
    const avgMs = Math.round(((performance.now() - qStart) / RUNS) * 100) / 100;
    queryTimings.push({ name: q.name, avgMs, resultSize });
    console.log(`    ${q.name.padEnd(22)} ${String(avgMs).padStart(6)}ms  (${resultSize} chars)`);
  }

  // ═══════════════════════════════════════════════════════════════════
  // SUMMARY
  // ═══════════════════════════════════════════════════════════════════

  console.log('\n' + '\u2554' + '\u2550'.repeat(70) + '\u2557');
  console.log('\u2551                          SUMMARY                                      \u2551');
  console.log('\u255a' + '\u2550'.repeat(70) + '\u255d\n');

  // Per-file table
  console.log('  File                          | Lines | Hdgs | Full tok | Tree tok | Save | ms');
  console.log('  ' + '\u2500'.repeat(96));
  for (const r of allResults) {
    const name = r.file.split('/').pop()!.substring(0, 30).padEnd(30);
    const lines = String(r.lines).padStart(5);
    const hdgs = String(r.headings).padStart(4);
    const full = String(r.fullTokens).padStart(8);
    const tree = String(r.treeTokens).padStart(8);
    const save = pct(r.treeTokens, r.fullTokens).padStart(4);
    const ms = String(r.parseTimeMs).padStart(6);
    const status = r.issues.filter(i => i.severity === 'bug').length > 0 ? ' BUG' : ' OK';
    console.log(`  ${name} | ${lines} | ${hdgs} | ${full} | ${tree} | ${save} | ${ms}${status}`);
  }

  // Issue summary
  const bugs = allIssues.filter(i => i.severity === 'bug');
  const warnings = allIssues.filter(i => i.severity === 'warning');
  const infos = allIssues.filter(i => i.severity === 'info');

  console.log(`\n  Issues: ${bugs.length} bugs, ${warnings.length} warnings, ${infos.length} info`);
  if (bugs.length > 0) {
    console.log('\n  BUGS:');
    for (const b of bugs) console.log(`    [${b.file}] ${b.message}`);
  }
  if (warnings.length > 0) {
    console.log('\n  WARNINGS:');
    for (const w of warnings) console.log(`    [${w.file}] ${w.message}`);
  }

  // Category breakdown
  const categories = [...new Set(allResults.map(r => r.tag))];
  console.log('\n  By category:');
  for (const cat of categories) {
    const catResults = allResults.filter(r => r.tag === cat);
    const catFull = catResults.reduce((s, r) => s + r.fullTokens, 0);
    const catTree = catResults.reduce((s, r) => s + r.treeTokens, 0);
    const catBugs = catResults.reduce((s, r) => s + r.issues.filter(i => i.severity === 'bug').length, 0);
    console.log(`    ${cat.padEnd(15)} ${catResults.length} files, ${pct(catTree, catFull)} tree savings, ${catBugs} bugs`);
  }

  // Grand totals
  const totalFull = allResults.reduce((s, r) => s + r.fullTokens, 0);
  const totalTree = allResults.reduce((s, r) => s + r.treeTokens, 0);
  const totalSection = allResults.reduce((s, r) => s + r.sectionTokens, 0);
  const totalSearch = allResults.reduce((s, r) => s + r.searchTokens, 0);
  const totalParseMs = allResults.reduce((s, r) => s + r.parseTimeMs, 0);
  const filesWithFM = allResults.filter(r => r.hasFrontmatter).length;
  const filesWithArrayFM = allResults.filter(r => r.fmArrays).length;

  console.log(`\n  GRAND TOTAL:`);
  console.log(`    Files tested:        ${allResults.length}`);
  console.log(`    Total tokens (full): ~${totalFull}`);
  console.log(`    Total tokens (tree): ~${totalTree}  (${pct(totalTree, totalFull)} savings)`);
  console.log(`    Tree + 1 section:    ~${totalTree + totalSection} vs ~${totalFull} (${pct(totalTree + totalSection, totalFull)} savings)`);
  console.log(`    Total parse time:    ${totalParseMs.toFixed(1)}ms`);
  console.log(`    Frontmatter parsed:  ${filesWithFM}/${allResults.length} files (${filesWithArrayFM} with arrays)`);
  console.log(`    Fuzzy matcher:       ${fuzzyResults.passed}/${fuzzyResults.passed + fuzzyResults.failed} tests passed`);
  console.log(`    Cache speedup:       ${cacheResult.speedup}`);
  console.log(`    Vault search:        ${vaultResult.fileCount} files in ${vaultResult.timeMs}ms`);
  console.log(`    Total bugs:          ${bugs.length}`);
  console.log(`    Vault index compile: ${index.meta.total_nodes} nodes in ${compileMs}ms`);
  const avgQueryMs = queryTimings.reduce((s, q) => s + q.avgMs, 0) / queryTimings.length;
  console.log(`    Avg query time:      ${avgQueryMs.toFixed(2)}ms`);
  console.log(`\n  Verdict: md_tree first, then md_section on demand = massive token savings.\n`);
}

function countHeadings(nodes: any[]): number {
  let count = nodes.length;
  for (const n of nodes) count += countHeadings(n.children || []);
  return count;
}

function findFirstLevel2(nodes: any[]): string | null {
  for (const n of nodes) {
    if (n.level === 2) return n.title;
    const child = findFirstLevel2(n.children || []);
    if (child) return child;
  }
  return null;
}

runBenchmark().catch(console.error);
