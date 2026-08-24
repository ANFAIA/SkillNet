// Content Collections for /docs.
//
// The files under src/content/docs/en/*.md are a synced literal copy of the
// public subset of docs/design/*.md (plus RUNNING.md for the quickstart),
// generated with scripts/copy-docs.mjs. The repo's docs/ is still the source
// of truth: after editing a doc there, re-run `node scripts/copy-docs.mjs`
// from this package, which refreshes en/ and prints which es/ files are now
// stale so they can be translated by hand. There is no automatic sync step
// in the build itself.
//
// src/content/docs/es/*.md holds the hand-translated Spanish prose for the
// same slugs (code blocks, filenames and commands stay untranslated). Both
// locales live in one collection so index.astro / [slug].astro can share the
// same loading/sorting logic; the locale is the first path segment of each
// entry's id (e.g. "es/quickstart" or "en/quickstart"), which the glob
// loader derives automatically from the folder structure.
import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

const docs = defineCollection({
  loader: glob({ pattern: "*/*.md", base: "./src/content/docs" }),
  schema: z.object({
    title: z.string(),
    order: z.number(),
    section: z.enum(["start", "core", "v2", "extensibility"]),
  }),
});

export const collections = { docs };

// Helpers for splitting a collection entry's id ("es/quickstart") into its
// locale and slug parts. Kept here so pages/layouts don't duplicate the
// parsing logic.
export function splitDocId(id: string): { locale: "es" | "en"; slug: string } {
  const [locale, ...rest] = id.split("/");
  return { locale: locale as "es" | "en", slug: rest.join("/") };
}
