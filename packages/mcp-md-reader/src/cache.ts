import { stat, readFile, writeFile, mkdir } from 'node:fs/promises';
import { join, dirname } from 'node:path';
import { tmpdir } from 'node:os';
import { ParsedMarkdown } from './parser.js';

// ── In-memory LRU cache ──────────────────────────────────────────────

interface CacheEntry {
  parsed: ParsedMarkdown;
  mtimeMs: number;
  lastAccess: number;
}

const MAX_ENTRIES = 100;
const cache = new Map<string, CacheEntry>();

function evictIfNeeded(): void {
  if (cache.size < MAX_ENTRIES) return;

  let oldest: string | null = null;
  let oldestAccess = Infinity;

  for (const [key, entry] of cache) {
    if (entry.lastAccess < oldestAccess) {
      oldestAccess = entry.lastAccess;
      oldest = key;
    }
  }

  if (oldest) cache.delete(oldest);
}

export async function getCached(path: string): Promise<ParsedMarkdown | null> {
  // Try in-memory first
  const entry = cache.get(path);
  if (entry) {
    try {
      const s = await stat(path);
      if (s.mtimeMs !== entry.mtimeMs) {
        cache.delete(path);
        return null;
      }
      entry.lastAccess = Date.now();
      return entry.parsed;
    } catch {
      cache.delete(path);
      return null;
    }
  }

  // Try disk cache
  const diskEntry = await getDiskCache(path);
  if (diskEntry) {
    // Promote to memory
    evictIfNeeded();
    cache.set(path, diskEntry);
    return diskEntry.parsed;
  }

  return null;
}

export async function setCached(path: string, parsed: ParsedMarkdown): Promise<void> {
  try {
    const s = await stat(path);
    evictIfNeeded();
    const entry: CacheEntry = {
      parsed,
      mtimeMs: s.mtimeMs,
      lastAccess: Date.now(),
    };
    cache.set(path, entry);

    // Write to disk asynchronously (fire-and-forget)
    setDiskCache(path, entry).catch(() => {});
  } catch {
    // file not statable, skip caching
  }
}

export function clearCache(): void {
  cache.clear();
}

// ── Disk persistence ─────────────────────────────────────────────────
// Simple JSON index file that maps file paths to {mtimeMs, treeOnly}.
// We only persist the heading tree (not full text) to keep the file small.

const CACHE_DIR = join(tmpdir(), 'mcp-md-reader-cache');
const CACHE_INDEX_PATH = join(CACHE_DIR, 'index.json');

interface DiskCacheRecord {
  mtimeMs: number;
  lastAccess: number;
  // Serialized tree + frontmatter (not fullText/lines — those are rebuilt from file)
  frontmatter: Record<string, string | string[]> | null;
  frontmatterRaw: string | null;
  treeJson: string;  // JSON-serialized HeadingNode[]
}

interface DiskCacheIndex {
  version: number;
  entries: Record<string, DiskCacheRecord>;
}

let diskIndexLoaded = false;
let diskIndex: DiskCacheIndex = { version: 1, entries: {} };

async function ensureCacheDir(): Promise<void> {
  try {
    await mkdir(CACHE_DIR, { recursive: true });
  } catch {
    // already exists or can't create
  }
}

async function loadDiskIndex(): Promise<void> {
  if (diskIndexLoaded) return;
  diskIndexLoaded = true;

  try {
    await ensureCacheDir();
    const raw = await readFile(CACHE_INDEX_PATH, 'utf-8');
    const parsed = JSON.parse(raw);
    if (parsed && parsed.version === 1 && parsed.entries) {
      diskIndex = parsed;

      // Evict stale entries (older than 7 days)
      const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
      let evicted = false;
      for (const [key, entry] of Object.entries(diskIndex.entries)) {
        if (entry.lastAccess < cutoff) {
          delete diskIndex.entries[key];
          evicted = true;
        }
      }
      if (evicted) {
        saveDiskIndex().catch(() => {});
      }
    }
  } catch {
    diskIndex = { version: 1, entries: {} };
  }
}

async function saveDiskIndex(): Promise<void> {
  try {
    await ensureCacheDir();
    // Limit disk entries to MAX_ENTRIES
    const keys = Object.keys(diskIndex.entries);
    if (keys.length > MAX_ENTRIES) {
      const sorted = keys.sort((a, b) =>
        diskIndex.entries[a].lastAccess - diskIndex.entries[b].lastAccess
      );
      for (let i = 0; i < sorted.length - MAX_ENTRIES; i++) {
        delete diskIndex.entries[sorted[i]];
      }
    }
    await writeFile(CACHE_INDEX_PATH, JSON.stringify(diskIndex), 'utf-8');
  } catch {
    // disk write failed, not critical
  }
}

async function getDiskCache(path: string): Promise<CacheEntry | null> {
  await loadDiskIndex();
  const record = diskIndex.entries[path];
  if (!record) return null;

  try {
    const s = await stat(path);
    if (s.mtimeMs !== record.mtimeMs) {
      delete diskIndex.entries[path];
      return null;
    }

    // Rebuild ParsedMarkdown from disk record + re-read file
    const text = await readFile(path, 'utf-8');
    const lines = text.split('\n');
    const tree = JSON.parse(record.treeJson);

    return {
      parsed: {
        frontmatter: record.frontmatter,
        frontmatterRaw: record.frontmatterRaw,
        tree,
        fullText: text,
        lines,
      },
      mtimeMs: record.mtimeMs,
      lastAccess: Date.now(),
    };
  } catch {
    delete diskIndex.entries[path];
    return null;
  }
}

async function setDiskCache(path: string, entry: CacheEntry): Promise<void> {
  await loadDiskIndex();
  diskIndex.entries[path] = {
    mtimeMs: entry.mtimeMs,
    lastAccess: entry.lastAccess,
    frontmatter: entry.parsed.frontmatter,
    frontmatterRaw: entry.parsed.frontmatterRaw,
    treeJson: JSON.stringify(entry.parsed.tree),
  };
  await saveDiskIndex();
}

// ── Cache stats (for benchmarks) ─────────────────────────────────────

export function getCacheStats(): { memoryEntries: number; diskEntries: number } {
  return {
    memoryEntries: cache.size,
    diskEntries: Object.keys(diskIndex.entries).length,
  };
}
