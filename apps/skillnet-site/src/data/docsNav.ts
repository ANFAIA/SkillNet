// Shared ordering/section metadata for /docs/index.astro and DocsSidebar.
// Both read the same collection entries and group them the same way, so this
// file just names the section labels in display order, per locale.
export const SECTION_LABELS: Record<"es" | "en", Record<string, string>> = {
  es: {
    start: "Arranque",
    core: "Núcleo (v1)",
    v2: "Cursos dinámicos (v2)",
    extensibility: "Personalización y extensibilidad",
    research: "Investigación",
  },
  en: {
    start: "Getting started",
    core: "Core (v1)",
    v2: "Dynamic courses (v2)",
    extensibility: "Personalization and extensibility",
    research: "Research",
  },
};

export const SECTION_ORDER = ["start", "core", "v2", "extensibility", "research"] as const;
