/**
 * VDSL Theme Registry
 *
 * All built-in themes are registered here and exported as the `themes` map.
 * Theme keys match the `theme:` directive in .vdsl source files.
 */

import type { Theme } from "../parser/types";
import { clean } from "./clean";
import { cobaltGrid } from "./cobalt-grid";
import { darkTech } from "./dark-tech";
import { warmEditorial } from "./warm-editorial";

export type { Theme };

export const themes: Record<string, Theme> = {
  clean,
  "cobalt-grid": cobaltGrid,
  "dark-tech": darkTech,
  "warm-editorial": warmEditorial,
};

/** Returns the theme for `name`, falling back to cobalt-grid (the default look). */
export function resolveTheme(name: string): Theme {
  return themes[name] ?? cobaltGrid;
}

/** #rgb / #rrggbb → "rgba(r,g,b,a)". Anything else is returned unchanged. */
function withAlpha(color: string, a: number): string {
  let h = String(color).trim();
  if (h[0] !== "#") return color;
  h = h.slice(1);
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  if (h.length !== 6) return color;
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

/** Merge inline header overrides onto a base theme. Deliberately small: the
 *  author sets a few key colours/fonts and everything else follows. When `ink`
 *  is overridden but its soft/faint/grid relatives are not, they are derived
 *  from `ink` by alpha so a single colour re-tunes the whole ink family. */
export function mergeTheme(base: Theme, ov?: import("../parser/types").ThemeOverride): Theme {
  if (!ov || (!ov.colors && !ov.fonts && ov.grid === undefined)) return base;
  const oc = ov.colors ?? {};
  const colors = { ...base.colors, ...oc };
  if (oc.ink) {
    if (oc.inkSoft === undefined) colors.inkSoft = withAlpha(oc.ink, 0.7);
    if (oc.inkFaint === undefined) colors.inkFaint = withAlpha(oc.ink, 0.32);
    if (oc.grid === undefined) colors.grid = withAlpha(oc.ink, 0.12);
  }
  return {
    ...base,
    colors,
    fonts: { ...base.fonts, ...(ov.fonts ?? {}) },
    grid: ov.grid !== undefined ? ov.grid : base.grid,
  };
}

/** List of all available theme names. */
export const themeNames: string[] = Object.keys(themes);
