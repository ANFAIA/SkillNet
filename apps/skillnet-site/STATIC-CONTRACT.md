# Static artifact contract

## Package boundary

- Package: `apps/skillnet-site/` in `ANFAIA/SkillNet`.
- Direct build dependencies: Astro, the official React integration, React and Framer Motion.
- Output mode: Astro `static` with directory-format trailing-slash routes.
- Expected output directory: `dist/`.
- Runtime process: none; a static server serves `dist/`.
- Runtime environment variables: none.
- Optional build input: `BUILD_SHA`; release builds must provide it so the static health record is
  attributable.
- Imports from `apps/skillnet-web`, root packages or repository docs: none.
- Client-side JavaScript: one intentional `client:load` island on the home hero. Navigation,
  marketing content, vertical pages and Docs remain static Astro HTML.

## Public route manifest

| URL | Source | Expected output |
|---|---|---|
| `/` | `src/pages/index.astro` | `dist/index.html` |
| `/for/companies/` | `src/pages/for/companies.astro` | `dist/for/companies/index.html` |
| `/docs/` | `src/pages/docs/index.astro` | `dist/docs/index.html` |
| `/healthz.json` | `src/pages/healthz.json.ts` | `dist/healthz.json` |
| unmatched | `src/pages/404.astro` | `dist/404.html` |

No `/for/educators/`, `/for/training-providers/`, `/for/individuals/`, `/product/`, `/projects/`,
`/research/` or detail `/docs/*` source exists.

## Content contract

- Functional copy must resolve to an ID in `src/data/site.json#claims`.
- Every claim has availability, repository sources, review date and explicit limitations.
- `docsManifest` is empty. A repository document does not become public through a glob.
- Adding a docs detail route requires an allowlisted source, owner, public status, review date and
  canonical path, plus a validator that proves the source exists inside approved roots.
- The repository link is a provisional CTA, not a claim that an install, hosted account or demo is
  currently available.

## Indexing and release boundary

- Canonicals point at `https://skillnet.es` so URL construction is testable.
- All pages remain `noindex, nofollow` and robots remain closed while the cut is provisional.
- No sitemap is generated in this cut. Add one only when the route allowlist and indexable status
  are approved.
- Redirects, security headers, caching, TLS and health probes belong to the later Systems handoff;
  no server contract is invented here.

## Acceptance commands

With the reviewed lockfile present:

```text
pnpm run check
BUILD_SHA=<source-revision> pnpm run build
```

Then verify the five expected output files above, confirm `dist/healthz.json` contains the supplied
SHA, inspect emitted HTML for a single deliberate client island, and
run link/accessibility checks against the built output. None of those build-output assertions was
claimed by this run.
