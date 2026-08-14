import { readFile, readdir } from 'node:fs/promises'
import { join, relative } from 'node:path'
import process from 'node:process'

const root = new URL('../', import.meta.url)
const data = JSON.parse(await readFile(new URL('src/data/site.json', root), 'utf8'))
const errors = []

function assert(condition, message) {
  if (!condition) errors.push(message)
}

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const target = join(directory, entry.name)
    if (entry.isDirectory()) files.push(...(await walk(target)))
    else files.push(target)
  }
  return files
}

const rootPath = decodeURIComponent(root.pathname).replace(/^\/(?:([A-Za-z]:))/, '$1')
const pagesPath = join(rootPath, 'src', 'pages')
const sourcePath = join(rootPath, 'src')
const pageFiles = (await walk(pagesPath))
  .map((file) => relative(pagesPath, file).replaceAll('\\', '/'))
  .sort()
const expectedPageFiles = [
  '404.astro',
  'docs/index.astro',
  'for/companies.astro',
  'healthz.json.ts',
  'index.astro',
]

assert(
  JSON.stringify(pageFiles) === JSON.stringify(expectedPageFiles),
  `Route source set differs. Expected ${expectedPageFiles.join(', ')}, found ${pageFiles.join(', ')}`,
)

const expectedRoutes = ['/', '/for/companies/', '/docs/']
assert(
  JSON.stringify(data.routes) === JSON.stringify(expectedRoutes),
  `Public route manifest must be exactly ${expectedRoutes.join(', ')}`,
)

assert(
  JSON.stringify(data.serviceRoutes) === JSON.stringify(['/healthz.json']),
  'Static service route manifest must contain only /healthz.json',
)

assert(data.site.releaseStatus === 'provisional-noindex', 'Release must remain provisional-noindex')
assert(Array.isArray(data.docsManifest), 'docsManifest must be an array')
assert(data.docsManifest.length === 0, 'No detail document is approved for this provisional cut')
assert(data.primaryCta.kind === 'repository', 'Provisional CTA must lead to the source repository')
assert(/^https:\/\/github\.com\/ANFAIA\/SkillNet\/?$/.test(data.primaryCta.href), 'CTA URL is unexpected')

const claimIds = new Set()
for (const claim of data.claims) {
  assert(!claimIds.has(claim.id), `Duplicate claim id: ${claim.id}`)
  claimIds.add(claim.id)
  assert(claim.availability === 'available', `${claim.id} has an unsupported availability state`)
  assert(/^\d{4}-\d{2}-\d{2}$/.test(claim.reviewedAt), `${claim.id} has no valid review date`)
  assert(claim.sourceRefs.length > 0, `${claim.id} has no repository source`)
  assert(claim.limitations.length > 0, `${claim.id} has no limitations`)
}

const sourceFiles = await walk(sourcePath)
let sourceText = ''
for (const file of sourceFiles) {
  sourceText += `\n${await readFile(file, 'utf8')}`
}

for (const id of claimIds) {
  assert(sourceText.includes(`getClaim('${id}')`), `${id} is registered but never referenced by a page`)
}

for (const match of sourceText.matchAll(/getClaim\('([^']+)'\)/g)) {
  assert(claimIds.has(match[1]), `Page references unknown claim id: ${match[1]}`)
}

const prohibited = [
  ['href="#"', 'placeholder hash link'],
  ['client:', 'client-side Astro island'],
  ['<img', 'image asset'],
  ['mascot', 'mascot reference'],
  ['logo.', 'logo asset reference'],
]
for (const [needle, label] of prohibited) {
  assert(!sourceText.toLowerCase().includes(needle), `Prohibited ${label} found: ${needle}`)
}

const layout = await readFile(new URL('src/layouts/SiteLayout.astro', root), 'utf8')
assert(layout.includes('noindex, nofollow'), 'Provisional pages must remain noindex')
assert(layout.includes('class="skip-link"'), 'Skip link is missing')
assert(layout.includes('rel="canonical"'), 'Canonical link is missing')

const health = await readFile(new URL('src/pages/healthz.json.ts', root), 'utf8')
assert(health.includes("status: 'ok'"), 'Static health response must report ok')
assert(health.includes('process.env.BUILD_SHA'), 'Static health response must accept BUILD_SHA at build time')

const robots = await readFile(new URL('public/robots.txt', root), 'utf8')
assert(/Disallow:\s*\//.test(robots), 'robots.txt must block this provisional artifact')

if (errors.length > 0) {
  console.error(`Contract check failed with ${errors.length} error(s):`)
  for (const error of errors) console.error(`- ${error}`)
  process.exit(1)
}

console.log(`Contract check passed: ${data.routes.length} public routes, ${data.claims.length} bounded claims, 0 migrated docs.`)
