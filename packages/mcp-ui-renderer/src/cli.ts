#!/usr/bin/env node
/**
 * uidl CLI — render UIDL specs to standalone HTML pages.
 *
 * Usage:
 *   npx uidl render input.uidl                  → output/input.html + open
 *   npx uidl render input.uidl -o my-page.html  → my-page.html
 *   npx uidl render input.uidl --no-open        → don't open browser
 *   cat spec.uidl | npx uidl render -            → stdin
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { resolve, basename, dirname, join } from 'node:path';
import { exec } from 'node:child_process';
import { parseUIDL } from './parser.js';
import { renderHTML } from './renderer.js';

function openInBrowser(filePath: string): void {
  const cmd = process.platform === 'win32' ? `start "" "${filePath}"`
            : process.platform === 'darwin' ? `open "${filePath}"`
            : `xdg-open "${filePath}"`;
  exec(cmd);
}

function printUsage(): void {
  console.log(`
uidl — render UIDL specs to standalone HTML pages

Usage:
  uidl render <file.uidl>              Render and open in browser
  uidl render <file.uidl> -o out.html  Render to specific file
  uidl render <file.uidl> --no-open    Render without opening
  uidl render -                        Read from stdin

Options:
  -o, --output <file>    Output file path
  --no-open              Don't open in browser
  -h, --help             Show this help

Example UIDL spec:
  UIDL/1
  theme dark
  h1 "My Dashboard"
  metrics 2
    "Users" "1.2k" green
    "Revenue" "$45k" blue
  chart bar "Sales"
    x "Q1" "Q2" "Q3"
    y 120 85 95
`);
}

const args = process.argv.slice(2);

if (args.length === 0 || args.includes('-h') || args.includes('--help')) {
  printUsage();
  process.exit(0);
}

if (args[0] !== 'render') {
  console.error(`Unknown command: ${args[0]}. Use "uidl render <file>".`);
  process.exit(1);
}

// Parse args
const inputFile = args[1];
if (!inputFile) { console.error('Missing input file. Use "uidl render <file.uidl>".'); process.exit(1); }

let outputFile: string | null = null;
let shouldOpen = true;

for (let i = 2; i < args.length; i++) {
  if (args[i] === '-o' || args[i] === '--output') { outputFile = args[++i]; }
  else if (args[i] === '--no-open') { shouldOpen = false; }
}

// Read input
let uidlContent: string;
if (inputFile === '-') {
  uidlContent = readFileSync(0, 'utf-8');
} else {
  const resolved = resolve(inputFile);
  if (!existsSync(resolved)) { console.error(`File not found: ${resolved}`); process.exit(1); }
  uidlContent = readFileSync(resolved, 'utf-8');
}

// Parse and render
try {
  const spec = parseUIDL(uidlContent);
  const html = renderHTML(spec);

  // Determine output path
  if (!outputFile) {
    const outDir = resolve('output');
    if (!existsSync(outDir)) mkdirSync(outDir, { recursive: true });
    const name = inputFile === '-' ? 'stdin' : basename(inputFile, '.uidl');
    outputFile = join(outDir, `${name}.html`);
  }

  writeFileSync(outputFile, html, 'utf-8');

  const uidlTokens = Math.round(uidlContent.length / 3.5);
  const htmlTokens = Math.round(html.length / 3.5);

  console.log(`  Input:   ${uidlContent.length} bytes (~${uidlTokens} tokens)`);
  console.log(`  Output:  ${html.length} bytes (~${htmlTokens} tokens)`);
  console.log(`  Savings: ${((1 - uidlTokens / htmlTokens) * 100).toFixed(0)}%`);
  console.log(`  File:    ${resolve(outputFile)}`);

  if (shouldOpen) openInBrowser(resolve(outputFile));

} catch (e: any) {
  console.error(`Error: ${e.message}`);
  process.exit(1);
}
