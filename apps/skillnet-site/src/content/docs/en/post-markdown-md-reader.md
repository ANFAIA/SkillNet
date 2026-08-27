---
title: "How md-reader works"
order: 60
section: "research"
group: "post-markdown"
---

# How md-reader Works

Technical reference for `@anfaia/md-reader-mcp` — the MCP server that gives AI agents structural awareness of Markdown files.

Source: [`packages/mcp-md-reader/`](https://github.com/ANFAIA/SkillNet/tree/main/packages/mcp-md-reader)

## Overview

mcp-md-reader is an MCP server that replaces flat file reads with structure-aware navigation. Instead of reading entire files as flat text, agents navigate heading trees, extract individual sections, and traverse vault-wide graphs — all with ~90% fewer tokens.

Five tools. Zero external parsing dependencies. Deterministic results (no LLM calls). Pure string parsing that understands headings, code blocks, frontmatter, and wikilinks.

## The Pipeline

Every tool request follows the same path:

```
.md file → Loader (size check, binary detection)
         → Parser (heading extraction, code-block aware)
         → Tree (HeadingNode[] hierarchy with token estimates)
         → Cache (LRU memory + disk persistence)
         → Tool (md_tree / md_section / md_find / md_frontmatter / md_vault_index)
```

The parser is **code-block aware**: a `#` inside a fenced code block is never mistaken for a heading. This is what makes the tree deterministic.

## md_tree

The first tool you call. Returns the heading hierarchy with token estimates per section — so the agent knows what's inside the file and how expensive each section is before reading anything.

**Input:** File path  
**Output:** Nested heading tree with token counts

Example for a ~820 token file:

```
File: project.md
Full file: ~820 tokens
This tree: ~50 tokens
Savings: ~93%

# Project Alpha  (~7 tok)
  ## Architecture  (~312 tok)
    ### Database  (~89 tok)
    ### API Layer  (~76 tok)
  ## Deployment  (~64 tok)
  ## Roadmap  (~48 tok)
```

### How the tree is built

1. Scan lines for heading pattern: `^(#{1-6})\s+(.+)$`
2. Skip lines inside fenced code blocks (``` or ~~~)
3. Build flat list of headings with level, title, lineIndex
4. Assign lineEnd: each heading's content ends at next heading start (or EOF)
5. Build hierarchy using a stack:
   - For each node: pop stack until parent found (lower level number)
   - If stack empty → root node
   - Else → attach to last stack element (parent)
   - Push node onto stack

Token estimate: `Math.ceil(content_length / 4)` per section.

## md_section

After seeing the tree, the agent requests a specific section by name. The matching is **fuzzy**: it handles abbreviations, substrings, acronyms, and multi-word queries.

**Input:** File path + heading name (fuzzy)  
**Output:** Section content with line numbers and token savings

### Fuzzy matching algorithm

The algorithm adapts based on query length:

**Short queries (2-3 chars):** Word boundary mode only.
- `db` → matches "Database" (word-start prefix)
- `API` → matches "API Layer" (exact word boundary)
- `no` → **rejected** (no word boundary match — avoids "conocimiento" false positive)

**Medium queries (4+ chars):** Substring matching.
- `deploy` → matches "Deployment" (substring, score 0.9)
- `database` → matches "Database Design" (substring, score 0.9)

**Multi-word queries:** Word overlap scoring.
- Each matching word = +0.5 base score, +0.3 per match ratio
- `road map plan` → matches "Roadmap" (score 0.65)

Match threshold: score ≥ 0.5 (0-1 scale). Returns best match only.

## md_find

The front door for large vaults. Takes a natural-language query, tokenizes it, scans headings/tags/filenames across the entire vault, and returns ranked results under a token budget.

### Processing flow

1. **Tokenize query:** Split on non-alphanumeric, lowercase, filter stopwords (≥3 chars). Spanish & English stopwords built in.
2. **Scan vault index:** Check headings, tags, filenames of all documents.
3. **Rank by coverage:** Most query tokens matched → highest rank. Relatedness: two tokens match if one contains the other OR they share a 4+ char prefix (`aislar` ↔ `aislamiento`, `config` ↔ `configuración`).
4. **Budget cap (~4k tokens):** Max 12 regions shown, ambiguity detection.

### Three response modes

- **Normal:** Matching regions ranked (≤20 docs match)
- **Ambiguous:** Document list (>20 docs match) — user refines query
- **No match:** Hub entry points (most-connected notes for exploration)

## md_vault_index

Compiles all `.md` files into a directed graph where nodes are documents and edges are wikilinks. Supports 7 query types:

| Query | Purpose |
|-------|---------|
| `stats` | Total nodes, edges, type distribution |
| `node` | Full node info (structure, links, frontmatter) |
| `neighbors` | BFS traversal N hops (in + out links) |
| `search_type` | Filter nodes by frontmatter `type` field |
| `most_connected` | Top N hubs by total degree |
| `isolated` | Nodes with zero in + out links |
| `path` | BFS shortest path between two nodes |

### Node ID resolution

- Default: filename without extension (lowercased)
- Duplicates: full path with `/` → `_` (e.g., `src_design` + `docs_design`)

### Link resolution

1. Extract wikilinks `[[target]]` with alias support
2. Build simple-name-to-ID map
3. Resolve each outlink to target ID
4. Populate backlinks (links_in) on targets

## md_frontmatter

Reads just the YAML frontmatter without the full file. Typical savings: 99%.

Supports inline arrays (`tags: [a, b, c]`) and multi-line arrays. Returns `Record<string, string | string[]>`.

## Cache architecture

Two-layer caching with mtime validation:

```
Tool Request
  ↓ check
Memory Cache (LRU)          — 100 entries, mtime-validated, ~0.1ms
  ↓ miss → fallback
Disk Cache                   — JSON index, 7-day TTL, survives restarts
  ↓ miss → fallback
Full Parse                   — Read file → extract headings → build tree (~1.6ms)
```

- **Memory:** LRU eviction by lastAccess. Key = file path. Validation = file mtime must match.
- **Disk:** Single JSON index at `$TMPDIR/mcp-md-reader-cache/`. Max 100 entries, 7-day TTL. Stores frontmatter + tree (JSON), not full text.
- **Warm cache:** ~4.5x speedup vs cold parse.

## Token savings summary

| Tool | Scenario | Savings |
|------|----------|---------|
| md_tree | Tree only (3k-token file) | ~93-98% |
| md_tree + md_section | Read 1 section | ~88-91% |
| md_frontmatter | Metadata only | ~99% |
| md_find | Search vault, read 1 section | ~85-88% |

## Performance

| Operation | Time | Scale |
|-----------|------|-------|
| Parse single file | 1.6ms | 14 files benchmarked |
| Vault index compile | 355ms | 699 nodes |
| Average query | 0.61ms | Single query |
| Fuzzy matcher | <0.1ms | Per heading |

## Tech stack

| Layer | Technology |
|-------|-----------|
| Protocol | MCP SDK (stdio transport) |
| Language | TypeScript |
| Parser | Pure string parsing (no external deps) |
| YAML | `yaml` package for frontmatter |
| Runtime | Node.js ≥18 |

Ignored directories during vault walk: `node_modules`, `.git`, `.obsidian`, `ATTACHMENTS`, `.mcp-md-reader`.  
Max file size: 2 MB. Binary detection: first 8KB scanned for null bytes.
