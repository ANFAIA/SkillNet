<p align="center">
  <h1 align="center">mcp-md-reader</h1>
  <p align="center">
    <strong>MCP server for intelligent markdown reading — read only what you need</strong>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/MCP-compatible-blue?style=flat-square" alt="MCP">
    <img src="https://img.shields.io/badge/license-Apache_2.0-green?style=flat-square" alt="License">
    <img src="https://img.shields.io/badge/node-%3E%3D18-brightgreen?style=flat-square" alt="Node">
    <img src="https://img.shields.io/badge/token_savings-~90%25-orange?style=flat-square" alt="Token Savings">
    <img src="https://img.shields.io/badge/version-1.3.0-purple?style=flat-square" alt="Version">
  </p>
</p>

---

> AI agents waste context reading entire markdown files when they only need one section. This server fixes that.

## The problem

A 3,000-token markdown file might have 12 sections. The agent needs one. Without `mcp-md-reader`, it reads all 3,000 tokens. With it, it reads ~60 tokens for the tree and ~300 for the section. **~90% savings.**

## Tools

| Tool | What it does | Typical savings |
|------|-------------|-----------------|
| `md_tree` | Heading tree with estimated token counts | ~93% |
| `md_section` | One section by name (fuzzy match) | ~88-99% |
| `md_frontmatter` | YAML frontmatter only | ~99% |
| `md_vault_index` | Query the full vault graph: stats, neighbors, paths, types | — |

The intended workflow: `md_tree` first to see the structure, then `md_section` to read only what you need. `md_vault_index` for a bird's-eye view of the entire vault before drilling into individual files.

## Setup

```bash
git clone https://github.com/JoseEstevez520/mcp-md-reader.git
cd mcp-md-reader
npm install
npm run build
```

Then register with Claude Code:

```bash
claude mcp add md-reader -- node /full/path/to/mcp-md-reader/dist/index.js
```

Restart Claude Code. The 4 tools will appear as native tools in your session.

## Tech stack

<p>
  <img src="https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/Node.js-339933?style=for-the-badge&logo=node.js&logoColor=white" alt="Node.js">
  <img src="https://img.shields.io/badge/MCP_SDK-1C3C3C?style=for-the-badge" alt="MCP SDK">
</p>

| Layer | Detail |
|-------|--------|
| **Transport** | stdio (MCP protocol 2024-11-05) |
| **Parser** | Pure string parsing, zero external deps |
| **Cache** | LRU in memory + persistent disk cache (`%TEMP%/mcp-md-reader-cache/`) with mtime validation, 7-day TTL, 100 entries |
| **Matching** | Fuzzy heading match with word-boundary, prefix, acronym, and CamelCase support |
| **Vault index** | Compiled graph with BFS traversal, auto-recompile on stale (>1h) |

## How it works

The server parses markdown into a heading tree on first read, caches the result (validated by file modification time), and serves only the requested slice. The cache persists to disk and survives server restarts. No external parsing libraries — just string splitting by `#` headings with code-block awareness.

The fuzzy matcher scores heading similarity using exact match, substring match, and word overlap. Short queries (2-3 chars) match on word boundaries, prefixes, acronyms (e.g. "UI" matches "User Interface"), and CamelCase boundaries.

## Example

```
> md_tree("notes/project.md")

File: notes/project.md
Full file: ~2428 tokens
This tree: ~84 tokens
Savings: ~97%
# Project  (~7 tok)
  ## Objective  (~59 tok)
  ## Current state  (~804 tok)
  ## Decisions  (~297 tok)

> md_section("notes/project.md", "Decisions")

Section: Decisions (level 2)
Lines: 124-133
Section tokens: ~297 | Full file: ~2428 | Savings: ~88%
## Decisions
- Path B (pgvector + RLS) as baseline...
```

## Vault index

`md_vault_index` compiles all `.md` files into a graph and exposes queries over it. The index auto-recompiles when stale (>1 hour).

| Query | What it does | Parameters |
|-------|-------------|------------|
| `stats` | Total nodes, edges, types | — |
| `node` | Full info for one node | `node_id` |
| `neighbors` | Nodes within N hops | `node_id`, `depth` |
| `search_type` | All nodes of a frontmatter type | `node_id` = type |
| `most_connected` | Top N hubs | `depth` = N |
| `isolated` | Nodes with zero connections | — |
| `path` | Shortest path between two nodes | `node_id` = `"a>b"` |

```
> md_vault_index({vault_path: "/path/to/vault", query: "neighbors", node_id: "mandatos", depth: 2})

Neighbors of "mandatos" (depth 2): 8 nodes
{ "mandatos": { "distance": 0, ... }, "agentes": { "distance": 1, ... }, ... }
```

## Performance

| Metric | Value |
|--------|-------|
| Token savings (tree) | ~93% |
| Token savings (tree + 1 section) | ~91% |
| Cache speedup | 4.5x |
| Parse time (14 files) | 1.6ms |
| Vault index compile (699 nodes) | 355ms |
| Avg query time | 0.61ms |
| Fuzzy matcher | 14/14 |
| Bugs | 0 |

See [CHANGELOG.md](CHANGELOG.md) for full details.

## Origin

Originally developed at [github.com/JoseEstevez520/mcp-md-reader](https://github.com/JoseEstevez520/mcp-md-reader).

## License

Distributed under the [Apache 2.0](LICENSE) license.

---

<p align="center">
  <em>Built for <a href="https://github.com/modelcontextprotocol">MCP</a>-compatible AI agents.</em>
</p>
