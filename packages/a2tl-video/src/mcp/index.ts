/**
 * A2TL-Video MCP Server — WEB-FIRST.
 *
 * Exposes A2TL-Video as an MCP (Model Context Protocol) stdio server so AI
 * agents can generate the INSTANT, EMBEDDABLE HTML web player directly. There
 * is no MP4 here: the product is a single, self-contained HTML file that plays
 * in the browser (and drops into a page via `<vdsl-player>`).
 *
 * Tools:
 *   render_player(spec, theme?, output?) — parse + render a .vdsl spec to a
 *       self-contained HTML player; returns the HTML (and writes a .html file
 *       when `output` is given).
 *   list_components() — the A2TL-Video components, viz types, reveals,
 *       transitions, positions, accents, fonts and theme names supported by
 *       THIS build.
 *   list_icons() — the icon names usable in `icon "<name>"`.
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

import * as fs from "fs";
import * as path from "path";

import { parseVDSL } from "../parser/index.js";
import { renderToHTML } from "../renderer/index.js";
import { themeNames } from "../themes/index.js";
import { LUCIDE_ICONS } from "../icons/index.js";

// ---------------------------------------------------------------------------
// Vocabulary — kept faithful to THIS branch's code (not MP4 guesses):
//  - components:   parser dispatch keywords (src/parser/index.ts parseComponents)
//  - vizTypes:     renderViz switch cases (src/renderer/index.ts)
//  - reveals:      RevealStyle (src/parser asReveal)
//  - transitions:  applyTransition cases (src/renderer/index.ts)
//  - positions:    Position (src/parser asPosition)
//  - accents:      AccentStyle (src/parser asAccent)
//  - fonts:        FontStyle (src/parser asFont)
// TS types are erased at runtime, so these mirror the source enums verbatim.
// ---------------------------------------------------------------------------

const COMPONENTS: { name: string; note: string }[] = [
  { name: "text", note: '`text "…" <font> <position> <reveal> <timing>` — headline / body copy' },
  { name: "text-cycle", note: "`text-cycle <position> <font>` + indented phrases — hard-cut cycling phrases" },
  { name: "label", note: '`label "…" <position> <timing>` — small kicker / eyebrow' },
  { name: "icon", note: '`icon "<name>" <position> <timing> [color]` — inline Lucide SVG (see list_icons)' },
  { name: "triptych", note: "`triptych <timing> <reveal>` + indented items — three-up panel (builds progressively)" },
  { name: "step-sequence", note: "`step-sequence <timing>` + indented steps — numbered/iconed steps (builds progressively)" },
  { name: "comparison", note: "`comparison <timing> <animation>` + left/right lines — side-by-side cards" },
  { name: "card", note: "`card <position> <reveal> <timing>` + formula/arrow/result/subtitle/icon children (builds progressively)" },
  { name: "code", note: '`code "…" <reveal> <timing>` [shrink <n> move-top <timing>] — code block' },
  { name: "trace-log", note: "`trace-log <timing> <reveal>` + columns/entries/badge — log table (builds progressively)" },
  { name: "viz", note: "`viz <timing> <reveal>` + `type: <vizType>` and structured data — diagram escape hatch" },
  { name: "byline", note: '`byline "…" <position> <timing>` — attribution / footer line' },
];

// renderViz() switch cases in src/renderer/index.ts.
const VIZ_TYPES = [
  "node-graph",
  "flow-diagram",
  "boundary-sim",
  "workspace",
  "protocol-compare",
  "trace-log",
  "custom",
];

// RevealStyle (src/parser/index.ts asReveal).
const REVEALS = ["fade", "word-stagger", "typewriter", "slide-up", "scale-in", "none"];

// applyTransition() cases in src/renderer/index.ts ("cut" is the instant default).
const TRANSITIONS = ["cut", "crossfade", "blur-crossfade", "push-left", "push-right", "push-up", "zoom-through"];

// Position (src/parser/index.ts asPosition).
const POSITIONS = ["center", "upper-left", "upper-right", "bottom-center", "bottom-right"];

// AccentStyle (src/parser/index.ts asAccent) — used on text-cycle phrases.
const ACCENTS = ["underline", "strike", "hero", "dim", "glow"];

// FontStyle (src/parser/index.ts asFont).
const FONTS = ["display", "display-italic", "body", "mono", "hero"];

// ---------------------------------------------------------------------------
// Server construction (exported so it can be smoke-tested without stdio).
// ---------------------------------------------------------------------------

export const server = new Server(
  { name: "a2tl-video", version: "0.1.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "render_player",
      description:
        "Parse an A2TL-Video spec (.vdsl) and render it to a self-contained, embeddable HTML web player " +
        "(no MP4). Returns the HTML as text; if `output` is given, also writes the .html " +
        "file and returns its path. Embed the player anywhere via <vdsl-player>.",
      inputSchema: {
        type: "object" as const,
        properties: {
          spec: { type: "string", description: "The A2TL-Video spec text (VDSL/1 format)." },
          theme: {
            type: "string",
            description: `Optional theme override. One of: ${themeNames.join(", ")}.`,
          },
          output: {
            type: "string",
            description: "Optional path to write the .html player file (returned as a path).",
          },
        },
        required: ["spec"],
      },
    },
    {
      name: "list_components",
      description:
        "List everything the A2TL-Video vocabulary supports in this build: components, viz types, " +
        "reveals, transitions, positions, accents, fonts and theme names.",
      inputSchema: { type: "object" as const, properties: {} },
    },
    {
      name: "list_icons",
      description:
        'List the icon names available for `icon "<name>"` (and card/step-sequence icon children). ' +
        "These are the only valid icon values.",
      inputSchema: { type: "object" as const, properties: {} },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  switch (name) {
    case "render_player": {
      const spec = args?.spec as string | undefined;
      if (!spec) {
        return { isError: true, content: [{ type: "text", text: "Error: `spec` is required." }] };
      }
      try {
        const parsed = parseVDSL(spec);
        const themeName = (args?.theme as string) ?? parsed.theme ?? undefined;
        const html = renderToHTML(parsed, themeName);

        const output = args?.output as string | undefined;
        if (output) {
          const outPath = path.resolve(process.cwd(), output);
          fs.mkdirSync(path.dirname(outPath), { recursive: true });
          fs.writeFileSync(outPath, html, "utf-8");
          const scenes = parsed.scenes.length;
          const dur = parsed.scenes.reduce((s, sc) => s + sc.duration, 0);
          return {
            content: [
              {
                type: "text",
                text: `Rendered ${scenes} scene(s) (${dur}s) → ${outPath}\nOpen it in a browser to play instantly, or embed via <vdsl-player>.`,
              },
            ],
          };
        }

        return { content: [{ type: "text", text: html }] };
      } catch (e: any) {
        return { isError: true, content: [{ type: "text", text: `Parse/render error: ${e?.message ?? String(e)}` }] };
      }
    }

    case "list_components": {
      const lines: string[] = [];
      lines.push("A2TL-Video components:");
      for (const c of COMPONENTS) lines.push(`  - ${c.name}: ${c.note}`);
      lines.push("");
      lines.push(`viz types (viz block \`type:\`): ${VIZ_TYPES.join(", ")}`);
      lines.push(`reveals: ${REVEALS.join(", ")}`);
      lines.push(`transitions (scene handoff): ${TRANSITIONS.join(", ")}`);
      lines.push(`positions: ${POSITIONS.join(", ")}`);
      lines.push(`accents (text-cycle phrases): ${ACCENTS.join(", ")}`);
      lines.push(`fonts: ${FONTS.join(", ")}`);
      lines.push(`themes: ${themeNames.join(", ")}`);
      lines.push("");
      lines.push("Note: composite components (triptych, step-sequence, card, trace-log, viz) build up their parts progressively across their authored window.");
      return { content: [{ type: "text", text: lines.join("\n") }] };
    }

    case "list_icons": {
      const names = Object.keys(LUCIDE_ICONS).sort();
      const text =
        `${names.length} icon names available for \`icon "<name>"\`:\n\n` +
        names.join(", ");
      return { content: [{ type: "text", text }] };
    }

    default:
      return { isError: true, content: [{ type: "text", text: `Unknown tool: ${name}` }] };
  }
});

/** Start the A2TL-Video MCP server over stdio. Resolves once connected. */
export async function startMcpServer(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  // Log to stderr so it never corrupts the stdio JSON-RPC stream on stdout.
  console.error("A2TL-Video MCP server (web-first) running on stdio.");
}
