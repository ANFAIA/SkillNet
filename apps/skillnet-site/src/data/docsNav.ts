// Shared ordering/section metadata for /docs/index.astro and DocsSidebar.
// Both read the same collection entries and group them the same way, so this
// file just names the section labels in display order.
export const SECTION_LABELS: Record<string, string> = {
  start: "Arranque",
  core: "Núcleo (v1)",
  v2: "Cursos dinámicos (v2)",
  extensibility: "Personalización y extensibilidad",
};

export const SECTION_ORDER = ["start", "core", "v2", "extensibility"] as const;
