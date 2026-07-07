/**
 * Vault index compiler + query engine.
 *
 * Compiles all .md files in a vault into a graph-index.json,
 * then serves queries over that index.
 *
 * The existing per-file tools are the microscope.
 * This is the map.
 */

import { readFile, writeFile, stat, readdir, mkdir } from 'node:fs/promises';
import { join, relative, basename, dirname } from 'node:path';
import { parse as parseYaml } from 'yaml';

// ── Types ───────────────────────────────────────────────────────────────

export interface HeadingNode {
  title: string;
  level: number;
  line: number;
  children?: HeadingNode[];
}

export interface VaultNode {
  path: string;
  frontmatter: Record<string, unknown> | null;
  structure: HeadingNode[];
  links_out: string[];
  links_in: string[];
}

export interface GraphIndex {
  meta: {
    vault: string;
    generated_at: string;
    generator: string;
    total_nodes: number;
    total_edges: number;
  };
  nodes: Record<string, VaultNode>;
}

// ── Config ──────────────────────────────────────────────────────────────

const INDEX_SUBPATH = '10_PROYECTOS_ACTUALES/Cerebro_Digital/05_Producto/graphd';
const INDEX_FILENAME = 'graph-index.json';
const STALE_MS = 60 * 60 * 1000; // 1 hour
const IGNORE_DIRS = new Set(['node_modules', '.git', '.obsidian', 'ATTACHMENTS']);

// ── Compiler ────────────────────────────────────────────────────────────

function normalizeId(filename: string): string {
  return filename.replace(/\.md$/i, '').toLowerCase().replace(/\s+/g, '_');
}

async function walkMd(dir: string): Promise<string[]> {
  const results: string[] = [];
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return results;
  }
  for (const entry of entries) {
    if (IGNORE_DIRS.has(entry.name)) continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...(await walkMd(full)));
    } else if (entry.isFile() && entry.name.endsWith('.md')) {
      results.push(full);
    }
  }
  return results;
}

function extractFrontmatter(raw: string): [Record<string, unknown> | null, number] {
  if (!raw.startsWith('---')) return [null, 0];
  const end = raw.indexOf('\n---', 3);
  if (end === -1) return [null, 0];
  const yamlBlock = raw.slice(4, end);
  const bodyStartLine = yamlBlock.split('\n').length + 2;
  try {
    const parsed = parseYaml(yamlBlock);
    return [parsed && typeof parsed === 'object' ? parsed : null, bodyStartLine];
  } catch {
    return [null, bodyStartLine];
  }
}

function stripCodeBlocks(content: string): string {
  const lines = content.split('\n');
  const result: string[] = [];
  let inCode = false;
  for (const line of lines) {
    if (/^```/.test(line.trimStart())) {
      inCode = !inCode;
      result.push('');
      continue;
    }
    result.push(inCode ? '' : line);
  }
  return result.join('\n');
}

function extractStructure(strippedContent: string, lineOffset: number): HeadingNode[] {
  const lines = strippedContent.split('\n');
  const flat: HeadingNode[] = [];
  for (let i = 0; i < lines.length; i++) {
    const match = lines[i].match(/^(#{1,6})\s+(.+)$/);
    if (match) {
      flat.push({ title: match[2].trim(), level: match[1].length, line: i + 1 + lineOffset });
    }
  }
  return buildHeadingTree(flat);
}

function buildHeadingTree(flat: HeadingNode[]): HeadingNode[] {
  const root: HeadingNode[] = [];
  const stack: { node: HeadingNode; level: number }[] = [];
  for (const h of flat) {
    const node: HeadingNode = { title: h.title, level: h.level, line: h.line };
    while (stack.length > 0 && stack[stack.length - 1].level >= h.level) stack.pop();
    if (stack.length === 0) {
      root.push(node);
    } else {
      const parent = stack[stack.length - 1].node;
      if (!parent.children) parent.children = [];
      parent.children.push(node);
    }
    stack.push({ node, level: h.level });
  }
  return root;
}

function extractLinks(strippedContent: string): string[] {
  const linkSet = new Set<string>();
  const regex = /\[\[([^\]]+)\]\]/g;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(strippedContent)) !== null) {
    let target = match[1];
    if (target.includes('|')) target = target.split('|')[0];
    if (target.includes('#')) target = target.split('#')[0];
    if (target.includes('^')) target = target.split('^')[0];
    target = target.replace(/\\/g, '').trim();
    if (target) {
      const filename = target.includes('/') ? target.split('/').pop()! : target;
      const normalized = normalizeId(filename);
      if (normalized) linkSet.add(normalized);
    }
  }
  return [...linkSet].sort();
}

export async function compileIndex(vaultRoot: string): Promise<GraphIndex> {
  const files = await walkMd(vaultRoot);

  // Detect duplicate filenames
  const nameCount = new Map<string, number>();
  for (const f of files) {
    const name = normalizeId(basename(f));
    nameCount.set(name, (nameCount.get(name) || 0) + 1);
  }

  const nodes: Record<string, VaultNode> = {};

  for (const filePath of files) {
    const raw = await readFile(filePath, 'utf-8');
    const relPath = relative(vaultRoot, filePath).replace(/\\/g, '/');
    const baseName = normalizeId(basename(filePath));

    const id = (nameCount.get(baseName) || 0) > 1
      ? normalizeId(relPath.replace(/\//g, '_'))
      : baseName;

    const [frontmatter, bodyStartLine] = extractFrontmatter(raw);
    const body = raw.split('\n').slice(bodyStartLine).join('\n');
    const stripped = stripCodeBlocks(body);
    const structure = extractStructure(stripped, bodyStartLine);
    const links_out = extractLinks(stripped);

    nodes[id] = { path: relPath, frontmatter, structure, links_out, links_in: [] };
  }

  // Resolve backlinks
  const simpleNameToId = new Map<string, string | null>();
  for (const [id, node] of Object.entries(nodes)) {
    const simpleName = normalizeId(basename(node.path));
    if (simpleNameToId.has(simpleName)) {
      simpleNameToId.set(simpleName, null); // ambiguous
    } else {
      simpleNameToId.set(simpleName, id);
    }
  }

  function resolveTarget(targetId: string): string | undefined {
    if (nodes[targetId]) return targetId;
    const mapped = simpleNameToId.get(targetId);
    if (mapped && nodes[mapped]) return mapped;
    return undefined;
  }

  for (const [sourceId, node] of Object.entries(nodes)) {
    for (const targetId of node.links_out) {
      const resolved = resolveTarget(targetId);
      if (resolved) nodes[resolved].links_in.push(sourceId);
    }
  }

  for (const node of Object.values(nodes)) node.links_in.sort();

  let totalEdges = 0;
  for (const node of Object.values(nodes)) totalEdges += node.links_out.length;

  return {
    meta: {
      vault: vaultRoot,
      generated_at: new Date().toISOString(),
      generator: 'graphd v0.1',
      total_nodes: Object.keys(nodes).length,
      total_edges: totalEdges,
    },
    nodes,
  };
}

// ── Index loader (with auto-recompile) ──────────────────────────────────

let cachedIndex: GraphIndex | null = null;
let cachedVault: string | null = null;
let cachedAt = 0;

function indexPath(vaultRoot: string): string {
  return join(vaultRoot, INDEX_SUBPATH, INDEX_FILENAME);
}

export async function getIndex(vaultRoot: string): Promise<GraphIndex> {
  // Return memory cache if fresh
  if (cachedIndex && cachedVault === vaultRoot && Date.now() - cachedAt < STALE_MS) {
    return cachedIndex;
  }

  const idxPath = indexPath(vaultRoot);
  let needsCompile = false;

  try {
    const s = await stat(idxPath);
    if (Date.now() - s.mtimeMs > STALE_MS) {
      needsCompile = true;
    }
  } catch {
    needsCompile = true;
  }

  if (needsCompile) {
    const index = await compileIndex(vaultRoot);
    const dir = dirname(idxPath);
    await mkdir(dir, { recursive: true });
    await writeFile(idxPath, JSON.stringify(index, null, 2), 'utf-8');
    cachedIndex = index;
    cachedVault = vaultRoot;
    cachedAt = Date.now();
    return index;
  }

  // Load from disk
  const raw = await readFile(idxPath, 'utf-8');
  cachedIndex = JSON.parse(raw) as GraphIndex;
  cachedVault = vaultRoot;
  cachedAt = Date.now();
  return cachedIndex;
}

// ── Query engine ────────────────────────────────────────────────────────

export type QueryType = 'stats' | 'node' | 'neighbors' | 'search_type' | 'most_connected' | 'isolated' | 'path';

export async function queryIndex(
  vaultRoot: string,
  query: QueryType,
  nodeId?: string,
  depth?: number,
): Promise<string> {
  const index = await getIndex(vaultRoot);
  const { nodes, meta } = index;

  switch (query) {
    case 'stats':
      return formatStats(meta, nodes);

    case 'node':
      return formatNode(nodes, nodeId);

    case 'neighbors':
      return formatNeighbors(nodes, nodeId, depth ?? 1);

    case 'search_type':
      return formatSearchType(nodes, nodeId);

    case 'most_connected':
      return formatMostConnected(nodes, depth ?? 10);

    case 'isolated':
      return formatIsolated(nodes);

    case 'path':
      return formatPath(nodes, nodeId);

    default:
      return `Unknown query type: "${query}". Valid: stats, node, neighbors, search_type, most_connected, isolated, path`;
  }
}

// ── Query formatters ────────────────────────────────────────────────────

function formatStats(meta: GraphIndex['meta'], nodes: Record<string, VaultNode>): string {
  // Count by frontmatter type
  const typeCounts = new Map<string, number>();
  for (const node of Object.values(nodes)) {
    const type = (node.frontmatter?.type ?? node.frontmatter?.tipo ?? 'untyped') as string;
    typeCounts.set(type, (typeCounts.get(type) || 0) + 1);
  }

  const typeLines = [...typeCounts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([t, c]) => `  ${t}: ${c}`)
    .join('\n');

  return [
    `Vault: ${meta.vault}`,
    `Generated: ${meta.generated_at}`,
    `Total nodes: ${meta.total_nodes}`,
    `Total edges: ${meta.total_edges}`,
    '',
    'Types:',
    typeLines,
  ].join('\n');
}

function formatNode(nodes: Record<string, VaultNode>, nodeId?: string): string {
  if (!nodeId) return 'Error: node_id is required for query "node"';
  const node = nodes[nodeId];
  if (!node) {
    // Fuzzy search
    const candidates = Object.keys(nodes).filter(k => k.includes(nodeId));
    if (candidates.length > 0) {
      return `Node "${nodeId}" not found. Similar: ${candidates.slice(0, 10).join(', ')}`;
    }
    return `Node "${nodeId}" not found.`;
  }
  return JSON.stringify({ [nodeId]: node }, null, 2);
}

function formatNeighbors(nodes: Record<string, VaultNode>, nodeId?: string, depth = 1): string {
  if (!nodeId) return 'Error: node_id is required for query "neighbors"';
  if (!nodes[nodeId]) return `Node "${nodeId}" not found.`;

  const visited = new Set<string>();
  const queue: { id: string; dist: number }[] = [{ id: nodeId, dist: 0 }];
  const result: Record<string, VaultNode & { distance: number }> = {};

  while (queue.length > 0) {
    const { id, dist } = queue.shift()!;
    if (visited.has(id)) continue;
    visited.add(id);

    const node = nodes[id];
    if (!node) continue;

    result[id] = { ...node, distance: dist };

    if (dist < depth) {
      for (const neighbor of [...node.links_out, ...node.links_in]) {
        if (!visited.has(neighbor) && nodes[neighbor]) {
          queue.push({ id: neighbor, dist: dist + 1 });
        }
      }
    }
  }

  const header = `Neighbors of "${nodeId}" (depth ${depth}): ${Object.keys(result).length} nodes\n`;
  return header + JSON.stringify(result, null, 2);
}

function formatSearchType(nodes: Record<string, VaultNode>, typeQuery?: string): string {
  if (!typeQuery) return 'Error: node_id (= type to search) is required for query "search_type"';

  const matches: { id: string; path: string }[] = [];
  for (const [id, node] of Object.entries(nodes)) {
    const type = (node.frontmatter?.type ?? node.frontmatter?.tipo ?? '') as string;
    if (type.toLowerCase() === typeQuery.toLowerCase()) {
      matches.push({ id, path: node.path });
    }
  }

  if (matches.length === 0) return `No nodes with type "${typeQuery}" found.`;

  const lines = matches.map(m => `  ${m.id} — ${m.path}`).join('\n');
  return `Nodes with type "${typeQuery}" (${matches.length}):\n${lines}`;
}

function formatMostConnected(nodes: Record<string, VaultNode>, n: number): string {
  const ranked = Object.entries(nodes)
    .map(([id, node]) => ({
      id,
      total: node.links_out.length + node.links_in.length,
      out: node.links_out.length,
      in: node.links_in.length,
      path: node.path,
    }))
    .sort((a, b) => b.total - a.total)
    .slice(0, n);

  const lines = ranked.map(
    (r, i) => `${String(i + 1).padStart(2)}. ${r.id.padEnd(40)} ${String(r.total).padStart(4)} (out:${String(r.out).padStart(3)}, in:${String(r.in).padStart(3)})  ${r.path}`
  );

  return `Top ${n} most connected nodes:\n${lines.join('\n')}`;
}

function formatIsolated(nodes: Record<string, VaultNode>): string {
  const isolated = Object.entries(nodes)
    .filter(([, node]) => node.links_out.length === 0 && node.links_in.length === 0)
    .map(([id, node]) => `  ${id} — ${node.path}`);

  if (isolated.length === 0) return 'No isolated nodes found.';
  return `Isolated nodes (${isolated.length}):\n${isolated.join('\n')}`;
}

function formatPath(nodes: Record<string, VaultNode>, nodeId?: string): string {
  if (!nodeId || !nodeId.includes('>')) {
    return 'Error: node_id must be "origin>destination" for query "path"';
  }

  const [origin, destination] = nodeId.split('>').map(s => s.trim());
  if (!nodes[origin]) return `Origin node "${origin}" not found.`;
  if (!nodes[destination]) return `Destination node "${destination}" not found.`;

  // BFS shortest path
  const visited = new Map<string, string | null>(); // node → parent
  const queue: string[] = [origin];
  visited.set(origin, null);

  while (queue.length > 0) {
    const current = queue.shift()!;
    if (current === destination) {
      // Reconstruct path
      const path: string[] = [];
      let cursor: string | null = destination;
      while (cursor !== null) {
        path.unshift(cursor);
        cursor = visited.get(cursor) ?? null;
      }
      return `Path (${path.length - 1} hops): ${path.join(' → ')}`;
    }

    const node = nodes[current];
    if (!node) continue;

    for (const neighbor of [...node.links_out, ...node.links_in]) {
      if (!visited.has(neighbor) && nodes[neighbor]) {
        visited.set(neighbor, current);
        queue.push(neighbor);
      }
    }
  }

  return `No path found between "${origin}" and "${destination}".`;
}
