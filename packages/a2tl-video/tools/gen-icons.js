// One-shot generator: reads a curated list of lucide-static SVGs and emits
// src/icons/lucide.ts as a Record<name, innerSvgMarkup>. Run once and commit
// the generated .ts (it is the source of truth; node_modules is not shipped).
//
//   node tools/gen-icons.js
//
// The inner markup (the <path>/<circle>/... children, without the outer <svg>)
// is stored so the renderer can wrap it in its own themable/sized <svg>.
const fs = require("fs");
const path = require("path");

const ICON_DIR = path.resolve(__dirname, "../node_modules/lucide-static/icons");
const OUT = path.resolve(__dirname, "../src/icons/lucide.ts");

// Curated explainer-oriented set (~190). Keep names as lucide's kebab-case.
const CURATED = [
  // status / marks
  "check", "check-circle", "check-check", "x", "x-circle", "circle-check", "circle-x",
  "info", "alert-triangle", "alert-circle", "alert-octagon", "help-circle", "ban", "shield-check",
  // arrows / chevrons
  "arrow-right", "arrow-left", "arrow-up", "arrow-down", "arrow-up-right", "arrow-down-right",
  "chevron-right", "chevron-left", "chevron-up", "chevron-down", "chevrons-right", "chevrons-down",
  "move-right", "corner-down-right", "redo", "undo", "refresh-cw", "refresh-ccw", "repeat", "rotate-cw",
  // people
  "user", "users", "user-plus", "user-check", "user-x", "user-cog", "contact", "smile", "frown",
  // data / infra
  "database", "server", "hard-drive", "cloud", "cloud-off", "cloud-upload", "cloud-download",
  "cpu", "memory-stick", "network", "router", "wifi", "wifi-off", "signal", "activity", "gauge",
  // security
  "lock", "unlock", "lock-keyhole", "shield", "shield-alert", "key", "key-round", "fingerprint", "scan-face",
  "eye", "eye-off", "shield-off", "user-lock",
  // dev
  "code", "code-2", "terminal", "terminal-square", "git-branch", "git-commit-horizontal",
  "git-merge", "git-pull-request", "bug", "braces", "brackets", "binary", "file-code", "webhook",
  // files / storage
  "file", "file-text", "files", "folder", "folder-open", "folder-tree", "save", "clipboard",
  "clipboard-check", "clipboard-list", "archive", "inbox", "paperclip", "book", "book-open",
  "newspaper", "notebook", "sticky-note", "scroll",
  // actions / ui
  "settings", "settings-2", "sliders-horizontal", "filter", "search", "plus", "minus", "plus-circle",
  "trash", "trash-2", "edit", "pencil", "pen-line", "copy", "clipboard-copy", "download", "upload",
  "share", "share-2", "link", "link-2", "external-link", "maximize", "minimize", "expand", "menu",
  "more-horizontal", "more-vertical", "grip", "list", "list-checks", "layout-grid", "layout-dashboard",
  // media / control
  "play", "pause", "square", "circle", "skip-forward", "skip-back", "fast-forward", "rewind",
  "volume-2", "volume-x", "mic", "camera", "video", "image", "monitor", "smartphone", "tablet", "laptop",
  // comms
  "mail", "mail-open", "send", "message-circle", "message-square", "messages-square", "bell", "bell-off",
  "phone", "phone-call", "at-sign", "megaphone", "rss",
  // time / calendar
  "calendar", "calendar-check", "calendar-clock", "clock", "clock-4", "timer", "hourglass", "history", "alarm-clock",
  // charts / money
  "bar-chart", "bar-chart-2", "bar-chart-3", "line-chart", "pie-chart", "trending-up", "trending-down",
  "area-chart", "gauge-circle", "dollar-sign", "euro", "credit-card", "wallet", "coins", "banknote",
  "receipt", "shopping-cart", "shopping-bag", "package", "package-check", "truck", "store", "tag", "percent",
  // concepts / delight
  "lightbulb", "rocket", "zap", "star", "heart", "sparkles", "flame", "trophy", "award", "target",
  "flag", "bookmark", "gift", "crown", "gem", "puzzle", "wand-2", "brain", "bot", "cpu",
  // structure
  "box", "boxes", "layers", "component", "blocks", "workflow", "share-2", "split", "milestone", "route",
  "map", "map-pin", "compass", "navigation", "globe", "globe-2", "orbit", "waypoints",
  // place / misc
  "home", "building", "building-2", "factory", "warehouse", "graduation-cap", "school", "briefcase",
  "landmark", "hospital", "flask-conical", "microscope", "atom", "dna", "leaf", "sun", "moon", "cloud-sun",
  "battery", "battery-charging", "plug", "power", "toggle-left", "toggle-right", "thumbs-up", "thumbs-down",
  "hand", "handshake", "scale", "gavel", "shield-question", "life-buoy", "anchor", "wrench", "hammer",
  "cog", "circle-dot", "loader", "loader-2", "check-square", "square-check-big",
];

// Dedupe while preserving order.
const names = [...new Set(CURATED)];

function innerOf(svgText) {
  // Drop license comment, grab everything between the outer <svg ...> and </svg>.
  const body = svgText.replace(/<!--[\s\S]*?-->/g, "");
  const m = body.match(/<svg\b[^>]*>([\s\S]*?)<\/svg>/i);
  if (!m) return null;
  return m[1]
    .replace(/\s*\n\s*/g, "")   // collapse newlines/indentation between tags
    .replace(/>\s+</g, "><")     // no whitespace between tags
    .trim();
}

const entries = [];
const missing = [];
for (const name of names) {
  const file = path.join(ICON_DIR, `${name}.svg`);
  if (!fs.existsSync(file)) { missing.push(name); continue; }
  const inner = innerOf(fs.readFileSync(file, "utf8"));
  if (!inner) { missing.push(name); continue; }
  entries.push([name, inner]);
}

if (missing.length) {
  console.warn(`WARNING: ${missing.length} names not found / unparsable and skipped:\n  ` + missing.join(", "));
}

const header = `/**
 * VDSL icon set — curated subset of Lucide (https://lucide.dev), ISC licensed.
 * See NOTICE for the full license text.
 *
 * GENERATED by tools/gen-icons.js — do not edit by hand; re-run the generator
 * to change the set. Values are the INNER SVG markup (paths/shapes only),
 * without the outer <svg> wrapper, on a 24x24 viewBox. The renderer wraps these
 * in its own <svg> so size and \`currentColor\` are controlled per usage.
 */

export const LUCIDE_ICONS: Record<string, string> = {
`;

const bodyTs = entries
  .map(([name, inner]) => `  ${JSON.stringify(name)}: ${JSON.stringify(inner)},`)
  .join("\n");

const footer = `
};

export const ICON_VIEWBOX = "0 0 24 24";

/**
 * Look up an icon's inner SVG markup by name, tolerant of snake_case / spaces /
 * camelCase (all normalized to lucide's kebab-case). Returns null if unknown.
 */
export function getIcon(name: string | undefined | null): string | null {
  if (!name) return null;
  const raw = String(name).trim();
  if (LUCIDE_ICONS[raw]) return LUCIDE_ICONS[raw];
  const kebab = raw
    .replace(/([a-z0-9])([A-Z])/g, "$1-$2") // camelCase -> camel-Case
    .replace(/[\\s_]+/g, "-")                 // spaces / underscores -> dash
    .toLowerCase();
  return LUCIDE_ICONS[kebab] ?? null;
}

/** True when \`name\` resolves to a known icon (kebab/snake/camel tolerant). */
export function hasIcon(name: string | undefined | null): boolean {
  return getIcon(name) !== null;
}
`;

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, header + bodyTs + footer, "utf8");
console.log(`Wrote ${entries.length} icons to ${OUT}`);
