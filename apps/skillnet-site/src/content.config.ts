// Content Collections for /docs.
//
// The files under src/content/docs/{en,es}/*.md are maintained BY HAND. They began
// as copies of the public subset of docs/design/*.md (plus RUNNING.md for the
// quickstart), but they have diverged on purpose: the markdown links here point at
// site paths a relative-link source cannot express, and several sources are in
// Spanish while their en/ counterpart is a translation. Regenerating either locale
// destroys that work, so nothing does.
//
// docs/ is still where a change starts. `node scripts/check-docs-drift.mjs` from this
// package reports which site copies are older than the doc they came from; updating
// them is a manual edit. There is no sync step in the build.
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
    section: z.enum(["start", "core", "v2", "extensibility", "research"]),
    // Optional family inside a section. Docs sharing a group are nested under
    // the one with the lowest `order`, which becomes the family's index page.
    // Lets a family hold together when the slugs do not share a prefix.
    group: z.string().optional(),
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
