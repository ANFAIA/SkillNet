#!/usr/bin/env node
/**
 * Batch render: reads all .uidl files from generative-ui-proto/uidl/
 * that start with "skillnet_", parses them, renders HTML, writes to output/.
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync } from 'node:fs';
import { join, resolve, basename } from 'node:path';
import { parseUIDL } from './dist/parser.js';
import { renderHTML } from './dist/renderer.js';
import { exec } from 'node:child_process';

const UIDL_DIR = resolve('./..', 'generative-ui-proto', 'uidl');
const OUTPUT_DIR = resolve('.', 'output');

if (!existsSync(OUTPUT_DIR)) mkdirSync(OUTPUT_DIR, { recursive: true });

const files = readdirSync(UIDL_DIR).filter(f => f.startsWith('skillnet_') && f.endsWith('.uidl'));

console.log(`Found ${files.length} SkillNet UIDL specs in ${UIDL_DIR}\n`);

for (const file of files) {
  const specText = readFileSync(join(UIDL_DIR, file), 'utf-8');
  const parsed = parseUIDL(specText);
  const html = renderHTML(parsed);

  const outName = basename(file, '.uidl') + '.html';
  const outPath = join(OUTPUT_DIR, outName);
  writeFileSync(outPath, html, 'utf-8');

  // Also write HTML next to the UIDL file for easy access
  const protoOutPath = join(UIDL_DIR, outName);
  writeFileSync(protoOutPath, html, 'utf-8');

  const uidlTokens = Math.round(specText.length / 3.5);
  const htmlTokens = Math.round(html.length / 3.5);

  console.log(`  ${file}`);
  console.log(`    Title: ${parsed.title}`);
  console.log(`    Sections: ${parsed.sections.length}`);
  console.log(`    UIDL tokens: ~${uidlTokens} | HTML tokens: ~${htmlTokens} | Ratio: ${(uidlTokens/htmlTokens*100).toFixed(1)}%`);
  console.log(`    Output: ${outPath}`);
  console.log();
}

// Open all in browser
const htmlFiles = files.map(f => join(OUTPUT_DIR, basename(f, '.uidl') + '.html'));
for (const hp of htmlFiles) {
  exec(`start "" "${hp}"`);
}
console.log(`\nAll ${files.length} pages opened in browser.`);
