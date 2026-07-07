#!/usr/bin/env node
/**
 * mcp-ui-renderer — MCP server for rendering UIDL specs as HTML pages.
 *
 * Tools:
 *   render_page(spec, format?, filename?) — UIDL/JSON → standalone HTML, opens in browser
 *   list_examples()                       — list available example specs
 */

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { writeFile, readFile, readdir } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { existsSync, mkdirSync } from 'node:fs';
import { exec } from 'node:child_process';
import { parseUIDL, type UIDLSpec } from './parser.js';
import { renderHTML } from './renderer.js';

// ── Config ────────────────────────────────────────────────────────────

const OUTPUT_DIR = resolve(join(import.meta.dirname, '..', 'output'));
const EXAMPLES_DIR = resolve(join(import.meta.dirname, '..', '..', 'generative-ui-proto', 'uidl'));

if (!existsSync(OUTPUT_DIR)) mkdirSync(OUTPUT_DIR, { recursive: true });

// ── Helpers ───────────────────────────────────────────────────────────

function openInBrowser(filePath: string): void {
  const cmd = process.platform === 'win32' ? `start "" "${filePath}"`
            : process.platform === 'darwin' ? `open "${filePath}"`
            : `xdg-open "${filePath}"`;
  exec(cmd, (err) => {
    if (err) console.error(`No se pudo abrir el navegador: ${err.message}`);
  });
}

function parseSpec(input: string, format: string): UIDLSpec {
  if (format === 'json') {
    const raw = JSON.parse(input);
    // Adapt UIMin JSON format → UIDLSpec
    return {
      version: 1,
      theme: raw.page?.theme || raw.theme || 'light',
      layout: raw.page?.layout || raw.layout || 'stack',
      title: raw.page?.title || raw.title || '',
      sections: raw.sections || [],
    };
  }
  return parseUIDL(input);
}

// ── Server ────────────────────────────────────────────────────────────

const server = new McpServer({
  name: 'mcp-ui-renderer',
  version: '1.0.0',
});

// ── Tool: render_page ─────────────────────────────────────────────────

server.tool(
  'render_page',
  `Render a UIDL spec as a standalone HTML page and open it in the browser.

Input: a UIDL spec string (compact text format) or JSON spec.
Output: path to the generated HTML file.

UIDL format example:
  UIDL/1
  theme dark
  h1 "My Dashboard"
  metrics 3
    "Users" "1.2k" green
    "Revenue" "$45k" blue
  chart bar "Sales by region"
    x "North" "South" "East"
    y 120 85 95
  table "Details"
    cols Name Score Grade
    row Alice 95 A
    row Bob 82 B

Supported components: h1, h2, h3, text, hr, metrics, chart (bar/line/pie/radar/scatter), table, cards, list, code, collapse.`,
  {
    spec: z.string().describe('UIDL or JSON spec string'),
    format: z.enum(['uidl', 'json']).default('uidl').describe('Input format: "uidl" (default) or "json"'),
    filename: z.string().optional().describe('Output filename (without .html). Defaults to timestamp.'),
    open: z.boolean().default(true).describe('Open in browser after generating'),
  },
  async ({ spec: specInput, format, filename, open: openBrowser }) => {
    try {
      const parsed = parseSpec(specInput, format);
      const html = renderHTML(parsed);

      const name = filename || `page_${Date.now()}`;
      const outPath = join(OUTPUT_DIR, `${name}.html`);
      await writeFile(outPath, html, 'utf-8');

      if (openBrowser) openInBrowser(outPath);

      const uidlTokens = Math.round(specInput.length / 3.5);
      const htmlTokens = Math.round(html.length / 3.5);

      return {
        content: [{
          type: 'text' as const,
          text: [
            `Pagina generada: ${outPath}`,
            `Titulo: ${parsed.title}`,
            `Theme: ${parsed.theme}`,
            `Secciones: ${parsed.sections.length}`,
            `Tokens spec: ~${uidlTokens} | Tokens HTML: ~${htmlTokens} | Ratio: ${(uidlTokens/htmlTokens*100).toFixed(0)}%`,
            openBrowser ? 'Abierta en el navegador.' : '',
          ].filter(Boolean).join('\n'),
        }],
      };
    } catch (e: any) {
      return { content: [{ type: 'text' as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

// ── Tool: list_examples ───────────────────────────────────────────────

server.tool(
  'list_examples',
  'List available UIDL example specs that can be used as reference or rendered.',
  {},
  async () => {
    try {
      const files = await readdir(EXAMPLES_DIR);
      const uidlFiles = files.filter(f => f.endsWith('.uidl'));
      const results: string[] = [];

      for (const f of uidlFiles) {
        const content = await readFile(join(EXAMPLES_DIR, f), 'utf-8');
        const lines = content.split('\n').length;
        const chars = content.length;
        results.push(`${f} (${lines} lineas, ${chars} chars)`);
      }

      return {
        content: [{
          type: 'text' as const,
          text: results.length > 0
            ? `Ejemplos disponibles:\n${results.map(r => `  - ${r}`).join('\n')}\n\nDirectorio: ${EXAMPLES_DIR}`
            : 'No hay ejemplos disponibles.',
        }],
      };
    } catch (e: any) {
      return { content: [{ type: 'text' as const, text: `Error: ${e.message}` }], isError: true };
    }
  }
);

// ── Start ─────────────────────────────────────────────────────────────

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch(console.error);
