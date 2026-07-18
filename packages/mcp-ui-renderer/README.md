# A2TL-Web — compact format for AI-generated web pages

Write ~450 tokens, get a complete standalone HTML page with charts, tables, metrics, and dark theme. **4x fewer tokens than raw HTML.**

**A2TL-Web** is part of the **A2TL** family (**A**gent **t**o **T**ransformation **L**anguage) — compact formats where AI agents describe *what* to show and a renderer decides *how*. Siblings:
- **a2tl-web** (this package) — generates web pages
- **a2tl-video** — generates videos

## Why

Generative content is the next bottleneck. As AI agents move from answering questions to building interfaces — dashboards, reports, onboarding pages — they hit a wall: raw HTML is expensive to generate. Thousands of tokens go to boilerplate CSS, repeated `<div>` structures, and inline scripts the agent doesn't reason about.

A2TL-Web flips this. The agent writes a compact spec describing *what* to render, and a local renderer expands it to full standalone HTML instantly. The agent focuses on content and structure; the renderer handles presentation.

```
┌────────────┬──────────────┬───────────┐
│            │ Raw HTML     │ A2TL-Web  │
├────────────┼──────────────┼───────────┤
│ Bytes      │ 6,160        │ 1,541     │
├────────────┼──────────────┼───────────┤
│ Lines      │ 83           │ 43        │
├────────────┼──────────────┼───────────┤
│ Tokens (~) │ ~1,760       │ ~440      │
├────────────┼──────────────┼───────────┤
│ Ratio      │ 100%         │ 25%       │
└────────────┴──────────────┴───────────┘
```

This matters because generative UI is becoming a core agent capability — not a novelty. Every token saved on the write side compounds: faster generation, lower API costs, and more room in the context window for the agent to reason about what it's actually building.

- **4x fewer tokens** — same visual output, fraction of the generation cost
- **Zero dependencies** in the output — standalone HTML files with Chart.js from CDN
- **Dark theme** by default, clean modern look

## Quick start

```bash
npm install   # install dependencies
npm run build # compile TypeScript

# CLI: render an A2TL-Web file
node dist/cli.js render examples/dashboard.uidl

# MCP server: use from Claude Code or any MCP client
node dist/index.js
```

## A2TL-Web format

```
UIDL/1
theme dark
layout stack

h1 "My Dashboard"
text "Overview of key metrics" dim

metrics 3
  "Users" "1.2k" green "Up 12%"
  "Revenue" "$45k" blue "This month"
  "Errors" "3" red "Needs attention"

chart bar "Sales by Region"
  x "North" "South" "East" "West"
  y 120 85 95 110

table "Recent Activity"
  cols Name Action Date
  row "Alice" "Deployed v2.1" "2026-07-06"
  row "Bob" "Fixed auth bug" "2026-07-05"

cards 2
  card "Next Step" "Review pull request" "Pending"
  card "Alert" "SSL cert expires in 3 days" "Urgent"
```

This generates a complete HTML page with Chart.js bar chart, styled table, metric cards, and responsive layout.

## Components

| Component | Syntax | What it renders |
|-----------|--------|-----------------|
| `h1`, `h2`, `h3` | `h1 "Title"` | Headings (h1 gets gradient) |
| `text` | `text "..." dim\|highlight\|insight` | Paragraphs with optional style |
| `metrics` | `metrics N` + items | KPI cards with colored borders |
| `chart bar` | `chart bar "Title"` + x/y | Bar chart (Chart.js) |
| `chart line` | `chart line "Title"` + x/series | Line chart with fill |
| `chart pie` | `chart pie "Title"` + items | Pie/donut chart |
| `table` | `table "Title"` + cols/rows | Styled table with hover |
| `cards` | `cards N` + card items | Info cards grid |
| `list` | `list "Title"` + items | Bulleted list |
| `hr` | `hr` | Separator line |
| `code` | `code lang` + content | Code block |

## Usage modes

### CLI

```bash
# Render and open in browser
node dist/cli.js render input.uidl

# Render to specific file
node dist/cli.js render input.uidl -o my-page.html

# Render without opening
node dist/cli.js render input.uidl --no-open

# From stdin
cat spec.uidl | node dist/cli.js render -
```

### MCP server (for Claude Code, Cursor, etc.)

Add to your Claude Code settings:

```json
{
  "mcpServers": {
    "a2tl-web": {
      "command": "node",
      "args": ["path/to/dist/index.js"]
    }
  }
}
```

Then use the `render_page` tool:

```
render_page(spec: "UIDL/1\ntheme dark\nh1 \"Hello\"", format: "uidl")
```

### As a library

```typescript
import { parseUIDL } from './parser.js';
import { renderHTML } from './renderer.js';

const spec = parseUIDL(uidlString);
const html = renderHTML(spec);
```

## Real-world example

A SkillNet training dashboard for a new employee — 40 lines of A2TL-Web generates a full page:

| Metric | A2TL-Web | HTML | Savings |
|--------|----------|------|---------|
| Tokens | ~379 | ~2,855 | 87% |
| Bytes | 1,327 | 9,992 | 87% |
| Lines | 40 | 180+ | 78% |

## License

MIT
