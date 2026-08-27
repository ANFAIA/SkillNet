// GFM autolinks (remark-gfm) only recognise `http://`, `https://` and `www.`-prefixed
// text — a bare domain like "events.ticketrona.com" (exactly what source manuals write,
// with no protocol) is left as plain text. This rewrites those into explicit markdown
// links `[domain](https://domain)` before handing the string to ReactMarkdown, so the
// existing `a` renderer (already wired for `[text](url)` syntax) picks them up too.
//
// Restricted to a closed list of common TLDs rather than a generic domain regex: without
// it, ordinary prose fragments like "v3.pdf" or "paso 2.1" would false-positive as links.
const TLDS = ['com', 'es', 'org', 'net', 'io', 'app', 'dev', 'co']

// Alternation, tried left to right at each position: an existing markdown link or
// `<autolink>` matches (and is left untouched) before the bare-domain branch gets a
// chance, so an already-linked domain is never double-wrapped.
const LINK_OR_DOMAIN = new RegExp(
  `\\[[^\\]]*\\]\\([^)]*\\)|<[^\\s>]+>|(?<![\\w/@.])((?:[a-z0-9-]+\\.)+(?:${TLDS.join('|')}))(?![\\w.])`,
  'gi',
)

export function autolinkBareDomains(text: string): string {
  if (!text.includes('.')) return text
  return text.replace(LINK_OR_DOMAIN, (match, domain: string | undefined) =>
    domain ? `[${domain}](https://${domain})` : match,
  )
}
