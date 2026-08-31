/**
 * The two catalogues have to describe the same app.
 *
 * They drifted silently, which is the only way this ever goes wrong: a feature is built
 * in Spanish, its ids are added to `es.ts`, `en.ts` is not touched, and react-intl fills
 * the hole at runtime with the raw id or the Spanish default. Nothing fails, nothing
 * warns, and the gap only shows up when somebody reads the app in English — which is
 * exactly how a reviewer ended up unable to follow the public demo.
 *
 * So the parity is asserted here rather than trusted. Failures name the missing ids and
 * the side they are missing from, because "1289 !== 1287" tells you nothing about what to
 * write.
 */
import { describe, expect, it } from 'vitest'

import { en } from './en'
import { es } from './es'
import { messages } from './index'
import { SUPPORTED_LOCALES } from './locale'

type Catalogue = Record<string, unknown>

/**
 * `{ a: { b: 'x' } }` becomes `{ 'a.b': 'x' }`.
 *
 * Both catalogues are flat today, but react-intl accepts nested objects and a future
 * split into namespaces should not quietly turn this test into a comparison of two
 * top-level key lists.
 */
function flatten(catalogue: Catalogue, prefix = ''): Record<string, string> {
  const flat: Record<string, string> = {}
  for (const [key, value] of Object.entries(catalogue)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (value !== null && typeof value === 'object') {
      Object.assign(flat, flatten(value as Catalogue, path))
    } else {
      flat[path] = String(value)
    }
  }
  return flat
}

const flatEs = flatten(es)
const flatEn = flatten(en)

/** Ids in `from` that `to` does not have, sorted so the message is stable. */
function missingFrom(from: Record<string, string>, to: Record<string, string>): string[] {
  return Object.keys(from)
    .filter((id) => !(id in to))
    .sort()
}

function report(label: string, ids: string[]): string {
  return `${ids.length} ${label}:\n  ${ids.join('\n  ')}`
}

describe('message catalogue parity', () => {
  it('has the same set of ids in es.ts and en.ts', () => {
    const missingInEn = missingFrom(flatEs, flatEn)
    const missingInEs = missingFrom(flatEn, flatEs)

    const problems = [
      ...(missingInEn.length ? [report('ids present in es.ts but missing from en.ts', missingInEn)] : []),
      ...(missingInEs.length ? [report('ids present in en.ts but missing from es.ts', missingInEs)] : []),
    ]

    expect(problems.join('\n\n')).toBe('')
  })

  it.each([
    ['es', flatEs],
    ['en', flatEn],
  ])('has no empty translation in %s', (locale, catalogue) => {
    // An empty string passes a key-set comparison and renders as nothing at all — a
    // button with no label, a heading that is a blank line. Whitespace counts as empty.
    const empty = Object.keys(catalogue)
      .filter((id) => catalogue[id].trim() === '')
      .sort()

    expect(empty, `empty values in ${locale}.ts`).toEqual([])
  })

  it('exposes exactly the supported locales', () => {
    // `messages` is what `IntlProvider` indexes by the store's locale: a locale the store
    // can hold and this map cannot answer renders an app with no copy in it.
    expect(Object.keys(messages).sort()).toEqual([...SUPPORTED_LOCALES].sort())
  })
})
