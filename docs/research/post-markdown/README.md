# Post-Markdown: What Comes After Markdown for AI Agents

## The context

Today, Markdown is everywhere in the AI agent ecosystem. AGENTS.md, CLAUDE.md, SKILL.md, llms.txt. Every agent, every framework, every tool uses `.md` files as the default way to give context to AI. The entire industry converged on it.

That raises a question: **what comes after Markdown?**

Because sometimes it feels like we are adapting ourselves to what already exists instead of creating new things for our current needs. Markdown was designed for humans writing web content in 2004. It was never designed for AI agents that need to navigate, query, and selectively load knowledge.

## The exploration

### New formats

The starting point was [ObjectGraph](https://arxiv.org/abs/2604.27820) (.og), a paper proposing progressive disclosure built into the file format. You can load just the index, then expand nodes on demand. It treats documents as navigable structures rather than flat text.

From that came the idea: what if we had an enhanced `.md` with frontmatter that includes relations, types, and structure that a tool could consume natively for AI? Something like a file format that already carries its own index, its connections to other files, and metadata that an agent can use without parsing the full content. Think of it as bringing some of what vector databases do, but embedded directly in the file.

Three format variants were designed along this line: Markdown extended with embedded indices via HTML comments. Results: 78-86% token savings, but it requires modifying every existing file.

This path is not closed. There will probably be something after Markdown eventually. But for now, we decided to focus on optimizing how agents consume what already exists.

### The token problem with HTML

In parallel, a trend emerged: people started using HTML to visualize their ideas, because it is more expressive than Markdown. Dashboards, charts, interactive pages. But generating HTML through an AI agent is expensive. A single page costs 2,000-8,000 output tokens and takes 20-30 seconds to generate. This is the problem explored in [generative-ui](../generative-ui/), where we built UIDL as a compact alternative.

### Smarter readers

The conclusion for now: **don't change the format, change how it's consumed.** Markdown headings ARE the navigation tree. The problem isn't the file; it's that agents read it as flat text. What's needed is a consumption standard, not a new format.

This follows a universal pattern in computing: **the format stays simple, the reader gets intelligent.** HTML didn't change for the DOM to exist. PDF didn't change for AI OCR to extract tables. JPEG didn't change for face detection. Markdown doesn't need to change for agents to navigate it by section.

Out of 6 major AI agents tested (Claude Code, Cursor, Copilot, Codex, Aider, Windsurf), **none** expose Markdown headings as a navigable tree. That was the gap we decided to fill.

## The landscape: agent memory

There's a growing ecosystem of projects trying to give agents persistent memory: [Mem0](https://github.com/mem0ai/mem0), [Letta](https://github.com/letta-ai/letta) (formerly MemGPT), [Cognee](https://github.com/topoteretes/cognee), [Zep](https://github.com/getzep/zep), among others. Each builds a complex system (knowledge graphs, vector stores, summarization chains, retrieval pipelines) on top of fundamentally simple data.

The observation: **the complexity of these systems is itself a problem.** Every layer added is a layer that can fail, that needs maintenance, that couples your data to a specific tool. The historical trend in computing goes in the opposite direction, toward simplicity. Files replaced databases for config. Markdown replaced rich text for docs. JSON replaced XML for data exchange. The evolution tends toward simpler formats with smarter readers, not toward more complex infrastructure.

This doesn't mean Mem0 or Cognee are wrong. They solve real problems. But the bet here is that the long-term direction is making the consumption layer intelligent rather than building ever-larger systems around dumb readers.

## The landscape: code graphs pointed at docs

A parallel wave promises to "turn your repo — or any folder — into a knowledge graph you can query": [Graphify](https://github.com/Graphify-Labs/graphify), [Microsoft GraphRAG](https://github.com/microsoft/graphrag), code property graphs ([Joern](https://github.com/joernio/joern)), [Sourcegraph SCIP](https://sourcegraph.com/blog/announcing-scip). The pitch is general — point it at anything — and people increasingly point it at documentation.

But look at what they are built on: tree-sitter, ASTs, call graphs, import resolution. These are **code-analysis engines.** Their power comes from structure that only code has — a function *calls* another, a file *imports* another: explicit, unambiguous, machine-extractable relations. Prose has none of that. So when these tools ingest docs they cannot parse relations, they **infer** them with an LLM. Same name, different tool: on code it is deterministic, local and free; on docs it is LLM inference — paid per file, non-deterministic between runs, and it tends to flatten a whole document into a single node, losing its sections.

The observation: **a code tool pointed at documentation quietly stops being deterministic.** The "any folder" pitch hides that the docs path is a bolt-on. And it reinforces the same conclusion as above — docs already carry their own structure (headings, links, frontmatter). The win is to navigate that structure natively and deterministically, not to borrow a code-graph tool and pay an LLM to fake the structure prose lacks.

## What Was Built

An MCP server (`@anfaia/md-reader-mcp`, v1.4.1) that parses Markdown headings into a tree and serves sections on demand:

- `md_find`: query-driven front door — matches headings, tags and filenames across the vault, returns ranked sections. Deterministic (no embeddings, no LLM). Structural navigation, complement to full-text search.
- `md_tree`: heading tree with token counts (~50 tokens for a 3,000-token file)
- `md_section`: one section by name (fuzzy match)
- `md_frontmatter`: YAML frontmatter only
- `md_vault_index`: full vault graph with BFS traversal

**Workflow:** `md_find` first with what you're looking for → it returns matching sections ranked. Then `md_section` to read the one you picked. `md_tree` when you need one file's full structure, `md_vault_index` to explore links between notes.

Source: [`packages/mcp-md-reader/`](../../../packages/mcp-md-reader/)

## Key Numbers

| Metric | Value |
|--------|-------|
| Token savings with md_tree (tree only) | **93%** avg across 14 files |
| Token savings tree + 1 section | **91%** avg |
| Lazy loading prototype (PageIndex pattern) | **78.5%** avg across 9 queries |
| ObjectGraph index-only vs Markdown | **85%** savings |
| ObjectGraph full .og vs Markdown | **44% heavier** |
| Agents exposing .md headings as tree | **0 / 6** |

## The Map

```
REPRESENTATION (file format)
  Today: Plain Markdown + conventions (AGENTS.md, SKILL.md, llms.txt)
  Emerging: ObjectGraph (.og), paper only, no adoption

PROTOCOL (how agents connect)
  MCP (Anthropic), dominant
  A2A (Google), growing

MEMORY (how agents store state)
  Mem0, Letta, Cognee, Zep (all proprietary, no shared format)

CONSUMPTION (how agents READ files) <-- THE GAP WE FILLED
  0/6 agents expose heading structure
  OUR CONTRIBUTION: mcp-md-reader (v1.4.1, 5 tools)
```

## References

### Papers
- [ObjectGraph (arXiv 2604.27820)](https://arxiv.org/abs/2604.27820)
- [PageIndex / Don't Retrieve, Navigate (arXiv 2604.14572)](https://arxiv.org/pdf/2604.14572)
- [memorywire/AMP (arXiv 2606.01138)](https://arxiv.org/abs/2606.01138)

### Key Articles
- [Context Format Decision (TianPan.co)](https://tianpan.co/blog/2026-05-07-context-format-decision-agent-reasoning-json-markdown-plain-text). Same content in different formats changes LLM accuracy by up to 40%.
- [Markdown for Agents (Cloudflare)](https://blog.cloudflare.com/markdown-for-agents/). HTML-to-Markdown conversion for agents, up to 80% token reduction.
- [Documentation is your AI interface (Mintlify)](https://www.mintlify.com/blog/docs-as-ai-interface)

### Prior Art (MCP servers that partially implement the vision)
- [mcp-server-markdown](https://github.com/ofershap/mcp-server-markdown): list_headings + extract_section
- [mq: jq for Markdown](https://mqlang.org/): query language for Markdown, Rust
- [library-mcp](https://lethain.com/library-mcp/): Markdown knowledge base navigation

### Code-graph tools (built for code, often pointed at docs)
- [Graphify](https://github.com/Graphify-Labs/graphify): tree-sitter code graph; documentation goes through the model API
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag): LLM entity/relation extraction over a corpus
- [Joern](https://github.com/joernio/joern): code property graphs (data/control flow)
- [Sourcegraph SCIP](https://sourcegraph.com/blog/announcing-scip): precise, compiler-accurate code navigation
