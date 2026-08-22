// Content Collections for /docs.
//
// The files under src/content/docs/*.md are a synced copy of the public
// subset of docs/design/*.md (plus RUNNING.md for the quickstart), generated
// with scripts/copy-docs.mjs. The repo's docs/ is still the source of truth:
// after editing a doc there, re-run `node scripts/copy-docs.mjs` from this
// package and rebuild. There is no automatic sync step in the build itself.
import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

const docs = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/docs" }),
  schema: z.object({
    title: z.string(),
    order: z.number(),
    section: z.enum(["start", "core", "v2", "extensibility"]),
  }),
});

export const collections = { docs };
