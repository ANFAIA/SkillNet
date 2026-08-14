# SkillNet public site — provisional Astro cut

This self-contained Astro package implements the first deliberately small public surface:

- `/` — product home;
- `/for/companies/` — the only published audience vertical in this cut;
- `/docs/` — documentation migration index, with no detail document exposed;
- `404.html` — explicit not-found page.
- `/healthz.json` — static health metadata, prerendered with an optional build SHA.

The visual system extends the product's neutral surfaces, blue/green palette, compact radii and
motion language. It uses no current logo, mascot, screenshot or provisional brand asset. One
deliberate React island uses Framer Motion for the hero and product-model preview; the rest remains
static Astro HTML. The copy is English-first and intentionally provisional.

## Local development and checks

From `apps/skillnet-site`:

```text
pnpm install --ignore-workspace --ignore-scripts
node scripts/check-contract.mjs
pnpm build
```

The check has no third-party dependency. It validates the exact route sources, claim registry,
documentation allowlist state, provisional indexing boundary, canonical shell and absence of hash
links, images and Astro client directives.

The production image is built from this package's Dockerfile:

```text
docker build --build-arg BUILD_SHA=<source-revision> -t skillnet-site .
```

`package.json` pins Astro and pnpm; `pnpm-lock.yaml` freezes the transitive graph. The build-time
`BUILD_SHA` is written into `/healthz.json`. Release acceptance rejects `not-provided`.

## Safety state

Every page emits `noindex, nofollow`, and `public/robots.txt` disallows crawling. These protections
must remain until Product approves the claims, Brand approves the copy, the source-repository CTA is
replaced or accepted, Astro builds successfully, and the release owner approves publication.

See `STATIC-CONTRACT.md` for the route, content and release boundary.
