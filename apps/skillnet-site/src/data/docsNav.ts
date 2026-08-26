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

export interface DocEntry {
  slug: string;
  title: string;
  section: string;
  order: number;
}

export interface DocsTreeNode {
  entry: DocEntry;
  children: DocEntry[];
}

export interface DocsTreeGroup {
  section: string;
  label: string;
  nodes: DocsTreeNode[];
  /** Total link count in the group, children included — used for the collapsed hint. */
  count: number;
  /** True when this group holds the page being rendered. */
  containsCurrent: boolean;
}

/**
 * Derives the two-level document tree from the entries themselves — never from a
 * hand-written list, so adding a doc updates the navigation with no edit here.
 *
 * Level one is the `section` field of the frontmatter, in SECTION_ORDER.
 * Level two comes from the slugs: a doc whose slug is the dash-prefix of other
 * slugs in the same section is their parent (`semantic-boundaries` owns
 * `semantic-boundaries-dsac-bench`, `personalization` owns
 * `personalization-architecture`). Every doc that no other doc claims stays a
 * top-level leaf of its section. Declared `order` decides the sequence at both
 * levels.
 */
export function buildDocsTree(entries: DocEntry[], locale: "es" | "en", currentSlug?: string): DocsTreeGroup[] {
  const labels = SECTION_LABELS[locale];

  return SECTION_ORDER.map((section) => {
    const inSection = entries.filter((e) => e.section === section).sort((a, b) => a.order - b.order);

    // A doc is a parent when another doc in the section extends its slug with "-".
    const isParent = (e: DocEntry) => inSection.some((o) => o.slug.startsWith(`${e.slug}-`));
    // Pick the longest parent slug that claims this doc, so the deepest owner wins.
    const parentOf = (e: DocEntry) =>
      inSection
        .filter((o) => o.slug !== e.slug && e.slug.startsWith(`${o.slug}-`))
        .sort((a, b) => b.slug.length - a.slug.length)[0];

    const nodes: DocsTreeNode[] = [];
    for (const entry of inSection) {
      // A child of a parent is rendered inside it, not at the top level. A doc
      // that is itself a parent always stays at the top level, so a chain like
      // a -> a-b -> a-b-c never nests deeper than one visible level.
      if (!isParent(entry) && parentOf(entry)) continue;
      nodes.push({
        entry,
        children: inSection.filter((o) => !isParent(o) && parentOf(o)?.slug === entry.slug),
      });
    }

    const count = nodes.reduce((total, node) => total + 1 + node.children.length, 0);
    const containsCurrent = nodes.some(
      (node) => node.entry.slug === currentSlug || node.children.some((c) => c.slug === currentSlug),
    );

    return { section, label: labels[section], nodes, count, containsCurrent };
  }).filter((group) => group.nodes.length > 0);
}

/** A node of the file-tree sidebar, ready to cross the server/client boundary. */
export interface DocsFileTreeNode {
  /** Stable identity for the open/closed state ("section:v2", "doc:data-model"). */
  id: string;
  label: string;
  /** Absent on section nodes, which are folders with no page of their own. */
  href?: string;
  /** Slug of the doc behind this node, when it has one. */
  slug?: string;
  children: DocsFileTreeNode[];
}

export interface DocsFileTree {
  nodes: DocsFileTreeNode[];
  /** Ids that must already be open on arrival: the path down to the current page. */
  openIds: string[];
}

/**
 * Shapes `buildDocsTree` into the recursive form the sidebar island renders, and
 * works out which branches the current page needs open. The hierarchy still comes
 * from the entries alone — this only renames the levels.
 */
export function buildDocsFileTree(
  entries: DocEntry[],
  locale: "es" | "en",
  currentSlug: string | undefined,
  basePath: string,
): DocsFileTree {
  const groups = buildDocsTree(entries, locale, currentSlug);
  const openIds: string[] = [];

  const nodes = groups.map((group) => {
    const sectionId = `section:${group.section}`;
    // With no page selected (the index) the first section is the useful one.
    if (group.containsCurrent || (!currentSlug && group === groups[0])) openIds.push(sectionId);

    return {
      id: sectionId,
      label: group.label,
      children: group.nodes.map((node) => {
        const nodeId = `doc:${node.entry.slug}`;
        if (node.children.some((c) => c.slug === currentSlug)) openIds.push(nodeId);
        return {
          id: nodeId,
          label: node.entry.title,
          href: `${basePath}/${node.entry.slug}`,
          slug: node.entry.slug,
          children: node.children.map((child) => ({
            id: `doc:${child.slug}`,
            label: child.title,
            href: `${basePath}/${child.slug}`,
            slug: child.slug,
            children: [],
          })),
        };
      }),
    };
  });

  return { nodes, openIds };
}
