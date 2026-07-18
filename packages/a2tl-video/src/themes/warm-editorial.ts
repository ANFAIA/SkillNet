import type { Theme } from "../parser/types";

/**
 * Warm Editorial — an elegant warm theme with classic serif typography.
 *
 * Inspired by long-form print magazines: cream paper, rich ink, restrained
 * colour palette with warm amber and burgundy accents.
 */
export const warmEditorial: Theme = {
  name: "warm-editorial",
  colors: {
    bg: "#FAF7F2",
    bg2: "#F0EBE0",
    ink: "#1C1008",
    inkSoft: "#5C4B2A",
    inkFaint: "rgba(28,16,8,0.14)",
    grid: "rgba(28,16,8,0.06)",
    green: "#2D6A4F",
    red: "#9B2226",
    amber: "#CA6702",
    purple: "#6A4C93",
  },
  fonts: {
    display: "'Playfair Display', Georgia, serif",
    body: "'Source Serif 4', Georgia, serif",
    mono: "'Courier Prime', 'Courier New', monospace",
  },
  grid: false,
};
