// The golden UISpec fixtures under `src/test/fixtures/ui-specs/` are copies of
// B1's canonical set in `apps/skillnet-api/tests/fixtures/ui-specs/` (§12.3).
// B1 owns the contract; this check makes drift a failed `pnpm test` instead of a
// frontend that agrees only with itself.
//
// Check-only on purpose. A silent auto-copy would hide the very thing worth
// seeing: that the render contract moved. Run with `--fix` to accept the
// backend's version.

import { readFileSync, readdirSync, existsSync, copyFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const here = fileURLToPath(new URL('.', import.meta.url))
const canonical = join(here, '..', '..', 'skillnet-api', 'tests', 'fixtures', 'ui-specs')
const local = join(here, '..', 'src', 'test', 'fixtures', 'ui-specs')

// A frontend-only checkout has no backend to compare against.
if (!existsSync(canonical)) process.exit(0)

const fix = process.argv.includes('--fix')
const names = readdirSync(canonical).filter((name) => name.endsWith('.json'))
const problems = []

for (const name of names) {
  const target = join(local, name)
  const expected = readFileSync(join(canonical, name))
  if (existsSync(target) && expected.equals(readFileSync(target))) continue
  if (fix) {
    copyFileSync(join(canonical, name), target)
    continue
  }
  problems.push(name)
}

if (problems.length > 0) {
  console.error(
    `\nUI spec fixtures drifted from B1 (${problems.join(', ')}).\n` +
      'The backend copy is canonical. Run:\n' +
      '  pnpm exec node scripts/check-ui-spec-fixtures.mjs --fix\n' +
      'and update the renderer/tests to whatever the new contract says.\n',
  )
  process.exit(1)
}
