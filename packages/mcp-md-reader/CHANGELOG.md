# Changelog

## v1.3.0 — Focus (2026-07-07)

### Removed tools

Removed 3 tools that duplicate what native LLM tools (Grep, Read) already do better:

- `md_search` — Grep is faster and supports regex
- `md_search_vault` — Grep is faster and more flexible
- `md_graph` — `md_vault_index` with query "node" provides the same data vault-wide

### What remains (4 tools)

| Tool | Why it stays |
|------|-------------|
| `md_tree` | Unique — heading tree with token estimates, no native equivalent |
| `md_section` | Unique — reads exactly one section with fuzzy match, knows where headings end |
| `md_frontmatter` | Convenient — extracts YAML cleanly without guessing line limits |
| `md_vault_index` | Unique — full vault graph with BFS, paths, stats |

### Server instructions

Added MCP `instructions` field so LLMs know when to prefer md-reader tools over native Read/Grep.

---

## v1.2.0 — Vault Index (2026-07-07)

### New tool: `md_vault_index`

Bird's-eye map of the entire vault. Compiles all `.md` files into a graph index (`graph-index.json`) and exposes 7 query types:

| Query | Description |
|-------|-------------|
| `stats` | Node/edge totals, type distribution |
| `node` | Full info for a specific node (with fuzzy suggestion on miss) |
| `neighbors` | BFS traversal to N hops |
| `search_type` | Filter by frontmatter type/tipo |
| `most_connected` | Top N hubs |
| `isolated` | Nodes with zero connections |
| `path` | BFS shortest path between two nodes |

### Integrated compiler

The vault index compiler is now built into the MCP server. No external script dependency needed.

- Parses frontmatter with proper YAML parser (`yaml` package)
- Builds heading tree, extracts wikilinks (skipping code blocks)
- Resolves backlinks including path-based IDs for duplicate filenames
- Auto-recompiles when index is stale (>1 hour) or missing
- Added `yaml` as dependency

### Files changed
- `src/vault-index.ts` — New module: compiler + query engine
- `src/index.ts` — New `md_vault_index` tool, version bump
- `package.json` — Version 1.2.0, added `yaml` dependency
- `README.md` — Documented new tool with query reference table
- `CHANGELOG.md` — This entry

---

## v1.1.0 — Hardening Release (2026-07-07)

### 1. Parallel vault search (`md_search_vault`)
- **Before**: Sequential file reads with `for...of` loop
- **After**: Batched parallel reads with `Promise.allSettled` (batch size 50)
- **Impact**: 162 files searched in 31ms (0.2ms/file average)

### 2. Parallel graph sibling reads (`md_graph`)
- Sibling file reads now use `Promise.allSettled` instead of sequential loop
- `findMdFiles` now traverses subdirectories in parallel and skips `node_modules`

### 3. Persistent disk cache
- Cache now writes to `%TEMP%/mcp-md-reader-cache/index.json`
- Survives server restarts
- Validates entries against file mtime on load
- Auto-evicts entries older than 7 days
- Capped at 100 entries (same as memory)
- **Cache speedup**: 2.9x on 1438-line file (100 iterations)

### 4. Fuzzy matcher improvements
- **Before**: Required 4+ chars for any match; 2-3 char queries always returned 0
- **After**: 2-3 char queries match on word boundaries:
  - Prefix match: "en" matches "engagement", "da" matches "Dashboard"
  - Acronym match: "UI" matches "User Interface", "MCP" matches "Model Context Protocol"
  - CamelCase boundary: "SC" matches "SkillCard Component"
  - Short substrings like "no" still correctly rejected (won't match "conocimiento")
- **Test suite**: 14/14 fuzzy tests passing

### 5. Error handling hardened
- **Binary file detection**: Scans first 8KB for null bytes, rejects with clear message
- **File size limit**: 2MB cap prevents memory issues on huge files
- **Empty file handling**: Returns empty string, not an error
- **Permission errors**: Categorized with user-friendly messages (EACCES, EPERM, ENOENT, EISDIR, EMFILE)
- **Directory-as-file**: Detected and reported before reading
- `loadFile` now uses `fsStat` check before `readFile`

### 6. Benchmark suite v2.0
- Added timing measurements per file (parse time in ms)
- Added fuzzy matcher test suite (14 test cases)
- Added cache benchmark (cold vs warm, speedup ratio)
- Added vault-wide parallel search benchmark
- Added graph benchmark (outlinks, inlinks, timing)
- 5-phase benchmark structure: per-file, fuzzy, cache, vault search, graph

### Metrics summary

| Metric | Value |
|---|---|
| Files tested | 14 |
| Total bugs | 0 |
| Token savings (tree) | 93% |
| Token savings (tree + 1 section) | 91% |
| Fuzzy tests passed | 14/14 |
| Cache speedup | 2.9x |
| Vault search (162 files) | 31ms |
| Parse time (14 files total) | 1.9ms |

### Files changed
- `src/index.ts` — Parallel reads, error handling, version bump
- `src/cache.ts` — Disk persistence, cache stats export
- `src/parser.ts` — Fuzzy matcher word-boundary/acronym support
- `src/graph.ts` — Parallel subdirectory traversal, node_modules exclusion
- `src/benchmark.ts` — v2.0 with 5 test phases
- `package.json` — Version 1.1.0
