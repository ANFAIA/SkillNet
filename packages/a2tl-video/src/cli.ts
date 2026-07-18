#!/usr/bin/env node
/**
 * A2TL-Video CLI (bin: vdsl)
 *
 * Commands:
 *   vdsl compile <input.vdsl> [-o output.jsx]
 *   vdsl render  <input.vdsl> [-o output.mp4] [--theme <name>]
 *   vdsl themes
 *   vdsl init    <name>
 */

import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import { execSync, spawnSync } from "child_process";

import { parseVDSL } from "./parser";
import { compile } from "./compiler";
import { renderToHTML } from "./renderer";
import { themes, themeNames } from "./themes";

// ---------------------------------------------------------------------------
// Arg parsing
// ---------------------------------------------------------------------------

interface ParsedArgs {
  command: string;
  positional: string[];
  flags: Record<string, string | boolean>;
}

function parseArgs(argv: string[]): ParsedArgs {
  const args = argv.slice(2); // strip node + script
  const command = args[0] ?? "help";
  const positional: string[] = [];
  const flags: Record<string, string | boolean> = {};

  let i = 1;
  while (i < args.length) {
    const arg = args[i];
    if (arg.startsWith("--")) {
      const key = arg.slice(2);
      if (i + 1 < args.length && !args[i + 1].startsWith("--")) {
        flags[key] = args[i + 1];
        i += 2;
      } else {
        flags[key] = true;
        i += 1;
      }
    } else if (arg.startsWith("-") && arg.length === 2) {
      const key = arg.slice(1);
      if (i + 1 < args.length && !args[i + 1].startsWith("-")) {
        flags[key] = args[i + 1];
        i += 2;
      } else {
        flags[key] = true;
        i += 1;
      }
    } else {
      positional.push(arg);
      i += 1;
    }
  }

  return { command, positional, flags };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function readVDSL(inputPath: string): string {
  const resolved = path.resolve(process.cwd(), inputPath);
  if (!fs.existsSync(resolved)) {
    die(`File not found: ${resolved}`);
  }
  return fs.readFileSync(resolved, "utf-8");
}

function die(msg: string): never {
  console.error(`\x1b[31merror:\x1b[0m ${msg}`);
  process.exit(1);
}

function info(msg: string): void {
  console.log(`\x1b[36m→\x1b[0m ${msg}`);
}

function ok(msg: string): void {
  console.log(`\x1b[32m✓\x1b[0m ${msg}`);
}

// ---------------------------------------------------------------------------
// Command: compile
// ---------------------------------------------------------------------------

function cmdCompile(positional: string[], flags: Record<string, string | boolean>): void {
  const inputFile = positional[0];
  if (!inputFile) die("Usage: a2tl-video compile <input.vdsl> [-o output.jsx]");

  const source = readVDSL(inputFile);
  const spec = parseVDSL(source);
  const themeName = (flags["theme"] as string) ?? spec.theme ?? "cobalt-grid";
  const jsx = compile(spec, { themeName });

  const defaultOut = path.join(
    path.dirname(path.resolve(inputFile)),
    path.basename(inputFile, path.extname(inputFile)) + ".jsx"
  );
  const outPath = (flags["o"] as string) ?? (flags["output"] as string) ?? defaultOut;

  fs.mkdirSync(path.dirname(path.resolve(outPath)), { recursive: true });
  fs.writeFileSync(path.resolve(outPath), jsx, "utf-8");
  ok(`Compiled → ${outPath}`);
}

// ---------------------------------------------------------------------------
// Render project path (shipped with vdsl)
// ---------------------------------------------------------------------------

function renderProjectDir(): string {
  // The render/ directory lives next to the vdsl package root
  return path.resolve(__dirname, "..", "render");
}

function updateRenderProject(
  spec: import("./parser/types").VDSLSpec,
  jsx: string
): void {
  const renderDir = renderProjectDir();
  // Write Video.jsx
  fs.writeFileSync(path.join(renderDir, "src", "Video.jsx"), jsx, "utf-8");

  // Update Root.jsx with correct composition metadata
  const totalFrames = spec.scenes.reduce(
    (sum, scene) => sum + Math.round(scene.duration * 30),
    0
  );
  const width = spec.canvas?.width ?? 1920;
  const height = spec.canvas?.height ?? 1080;

  const rootContent = [
    `import React from 'react';`,
    `import { Composition } from 'remotion';`,
    `import { Video } from './Video';`,
    ``,
    `export const RemotionRoot = () => (`,
    `  <Composition`,
    `    id="Video"`,
    `    component={Video}`,
    `    durationInFrames={${totalFrames}}`,
    `    fps={30}`,
    `    width={${width}}`,
    `    height={${height}}`,
    `  />`,
    `);`,
  ].join("\n");
  fs.writeFileSync(path.join(renderDir, "src", "Root.jsx"), rootContent, "utf-8");
}

// ---------------------------------------------------------------------------
// Command: render
// ---------------------------------------------------------------------------

function cmdRender(positional: string[], flags: Record<string, string | boolean>): void {
  const inputFile = positional[0];
  if (!inputFile) die("Usage: a2tl-video render <input.vdsl> [-o output.mp4] [--theme <name>]");

  const source = readVDSL(inputFile);
  const spec = parseVDSL(source);
  const themeName = (flags["theme"] as string) ?? spec.theme ?? "cobalt-grid";
  const jsx = compile(spec, { themeName });

  updateRenderProject(spec, jsx);

  const renderDir = renderProjectDir();

  // Determine output path
  const defaultMp4 = path.join(
    path.dirname(path.resolve(inputFile)),
    path.basename(inputFile, path.extname(inputFile)) + ".mp4"
  );
  const outPath = path.resolve(
    (flags["o"] as string) ?? (flags["output"] as string) ?? defaultMp4
  );

  info(`Rendering → ${outPath}`);

  const result = spawnSync(
    "npx",
    ["remotion", "render", "src/index.js", "Video", outPath],
    {
      cwd: renderDir,
      stdio: "inherit",
      shell: true,
    }
  );

  if (result.status !== 0) {
    die("Remotion render failed. Ensure dependencies are installed in render/.");
  }

  ok(`Rendered → ${outPath}`);
}

// ---------------------------------------------------------------------------
// Command: preview
// ---------------------------------------------------------------------------

function cmdPreview(positional: string[], flags: Record<string, string | boolean>): void {
  const inputFile = positional[0];
  if (!inputFile) die("Usage: a2tl-video preview <input.vdsl> [--theme <name>]");

  const source = readVDSL(inputFile);
  const spec = parseVDSL(source);
  const themeName = (flags["theme"] as string) ?? spec.theme ?? "cobalt-grid";
  const jsx = compile(spec, { themeName });

  updateRenderProject(spec, jsx);

  const renderDir = renderProjectDir();
  info("Starting Remotion Studio…");

  const result = spawnSync(
    "npx",
    ["remotion", "studio", "src/index.js"],
    {
      cwd: renderDir,
      stdio: "inherit",
      shell: true,
    }
  );

  if (result.status !== 0) {
    die("Remotion Studio failed to start.");
  }
}

// ---------------------------------------------------------------------------
// Command: themes
// ---------------------------------------------------------------------------

function cmdThemes(): void {
  console.log("\nAvailable A2TL-Video themes:\n");
  for (const name of themeNames) {
    const theme = themes[name];
    const grid = theme.grid ? "  [grid]" : "";
    console.log(`  \x1b[36m${name}\x1b[0m${grid}`);
    console.log(`    bg: ${theme.colors.bg}  ink: ${theme.colors.ink}`);
    console.log(`    display: ${theme.fonts.display}`);
    console.log();
  }
}

// ---------------------------------------------------------------------------
// Command: init
// ---------------------------------------------------------------------------

const TEMPLATE = (name: string): string => `// ${name}.vdsl — A2TL-Video spec
VDSL/1
theme cobalt-grid
canvas 1920x1080

scene "${name}" 5s cut
  text "Hello, World!" display center word-stagger 0-4s
  byline "Made with A2TL-Video" bottom-center 4-5s
`;

function cmdInit(positional: string[]): void {
  const name = positional[0];
  if (!name) die("Usage: a2tl-video init <name>");

  const filename = name.endsWith(".vdsl") ? name : `${name}.vdsl`;
  const outPath = path.resolve(process.cwd(), filename);

  if (fs.existsSync(outPath)) {
    die(`File already exists: ${outPath}`);
  }

  fs.writeFileSync(outPath, TEMPLATE(path.basename(name, ".vdsl")), "utf-8");
  ok(`Created ${filename}`);
  console.log(`\nNext steps:`);
  console.log(`  vdsl compile ${filename}`);
  console.log(`  vdsl render  ${filename}`);
  console.log(`  vdsl play   ${filename}`);
}

// ---------------------------------------------------------------------------
// Command: play (instant HTML preview)
// ---------------------------------------------------------------------------

function cmdPlay(positional: string[], flags: Record<string, string | boolean>): void {
  const inputFile = positional[0];
  if (!inputFile) die("Usage: a2tl-video play <input.vdsl> [--theme <name>]");

  const source = readVDSL(inputFile);
  const spec = parseVDSL(source);
  const themeName = (flags["theme"] as string) ?? spec.theme ?? undefined;
  const html = renderToHTML(spec, themeName);

  const outName = path.basename(inputFile, path.extname(inputFile)) + ".html";
  const outPath = path.resolve(process.cwd(), outName);
  fs.writeFileSync(outPath, html, "utf-8");
  ok(`Generated ${outPath}`);
  console.log(`  Open in browser to play instantly.`);
}

// ---------------------------------------------------------------------------
// Command: mcp (start the MCP stdio server — web-first)
// ---------------------------------------------------------------------------

function cmdMcp(): void {
  // Lazy import so the SDK only loads when the server is actually started.
  const { startMcpServer } = require("./mcp") as typeof import("./mcp");
  startMcpServer().catch((err: unknown) => {
    console.error(err);
    process.exit(1);
  });
}

// ---------------------------------------------------------------------------
// Help
// ---------------------------------------------------------------------------

function cmdHelp(): void {
  console.log(`
\x1b[1mA2TL-Video\x1b[0m — Agent to Transformation Language for Video

\x1b[1mUsage:\x1b[0m
  vdsl compile <input.vdsl> [-o output.jsx] [--theme <name>]
  vdsl render  <input.vdsl> [-o output.mp4]  [--theme <name>]
  vdsl play    <input.vdsl> [--theme <name>]
  vdsl preview <input.vdsl> [--theme <name>]
  vdsl themes
  vdsl init    <name>
  vdsl mcp

\x1b[1mExamples:\x1b[0m
  vdsl init my-explainer
  vdsl compile my-explainer.vdsl
  vdsl render  my-explainer.vdsl -o out.mp4 --theme dark-tech
  vdsl play    my-explainer.vdsl
  vdsl preview my-explainer.vdsl
  vdsl themes
`);
}

// ---------------------------------------------------------------------------
// Entry
// ---------------------------------------------------------------------------

function main(): void {
  const { command, positional, flags } = parseArgs(process.argv);

  switch (command) {
    case "compile": return cmdCompile(positional, flags);
    case "render":  return cmdRender(positional, flags);
    case "play":    return cmdPlay(positional, flags);
    case "preview": return cmdPreview(positional, flags);
    case "themes":  return cmdThemes();
    case "init":    return cmdInit(positional);
    case "mcp":     return cmdMcp();
    case "help":
    case "--help":
    case "-h":
    default:
      return cmdHelp();
  }
}

main();
