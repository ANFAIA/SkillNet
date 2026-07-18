import type { Theme } from "../parser/types";

/**
 * Clean — the neutral, universal DEFAULT theme.
 *
 * A brand-agnostic look that suits ANY topic: near-white paper, neutral
 * near-black ink, tasteful standard semantic colours, and PURE SYSTEM FONTS
 * (no external font loading) so it renders identically everywhere. No graph
 * grid — the subtle depth vignette carries all the ambience on the white stage.
 */
export const clean: Theme = {
  name: "clean",
  colors: {
    bg: "#ffffff",
    bg2: "#f4f4f5",
    ink: "#18181b",
    inkSoft: "#52525b",
    inkFaint: "rgba(24,24,27,0.14)",
    grid: "rgba(24,24,27,0.06)",
    green: "#16a34a",
    red: "#dc2626",
    amber: "#d97706",
    purple: "#7c3aed",
  },
  fonts: {
    display: 'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    body: 'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    mono: 'ui-monospace, "SF Mono", "Cascadia Code", Menlo, Consolas, monospace',
  },
  grid: false,
};
