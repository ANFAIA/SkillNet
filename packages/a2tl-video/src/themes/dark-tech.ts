import type { Theme } from "../parser/types";

export const darkTech: Theme = {
  name: "dark-tech",
  colors: {
    bg: "#0a0a0f",
    bg2: "#141420",
    ink: "#00d4ff",
    inkSoft: "#0099cc",
    inkFaint: "rgba(0,212,255,0.15)",
    grid: "rgba(0,212,255,0.06)",
    green: "#10B981",
    red: "#EF4444",
    amber: "#F59E0B",
    purple: "#8B5CF6",
  },
  fonts: {
    display: "'Inter', system-ui, sans-serif",
    body: "'Inter', system-ui, sans-serif",
    mono: "'JetBrains Mono', monospace",
  },
  grid: true,
};
