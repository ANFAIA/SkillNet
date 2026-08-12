#!/usr/bin/env node

/**
 * Freeze Didact's neutral catalog into SkillNet.
 *
 * Synchronization is an explicit maintainer operation against a checkout pinned
 * to DIDACT_COMMIT. Runtime and normal builds only read the generated JSON.
 */

import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, posix, relative, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const DIDACT_COMMIT = "06c80e8a8af4f20ad20ba345b7b6b13e1cc27e0c";
const DIDACT_REPOSITORY = "https://github.com/JoseEstevez520/Didact";
const EXPECTED_SNAPSHOT_SHA256 = "b517ea1edba79e1e4e7c34ed6afb866c8c22488a39aef127efda6f2c1a4cf675";
const EXPECTED_REGISTRY_CLOSURE_SHA256 = "2f97bb5d30fe1a5ad0459a270573ff4b24b3b02293ae19e7d891be8daa8ec07b";
const EXPECTED_SOURCE_TREE_SHA256 = "82ab1c1bb6e5e67f09c1fc0737c0b307d199fd910526ee5778da10136285a455";
const EXPECTED_COUNTS = Object.freeze({
  available_types: 34,
  manifests: 28,
  collections: 6,
});

const scriptDir = dirname(fileURLToPath(import.meta.url));
const apiRoot = resolve(scriptDir, "..");
const snapshotPath = resolve(apiRoot, "src/personalization/didact_snapshot.json");
const lockPath = resolve(apiRoot, "src/personalization/didact.lock.json");
const webRoot = resolve(apiRoot, "../skillnet-web");
// Exact upstream sources are provenance/build inputs, not application sources.
// Host-ready adapters live separately under skillnet-web/src and opt in explicitly.
const vendorRoot = resolve(webRoot, "vendor/didact");
const vendorSourceRoot = resolve(vendorRoot, "source");
const vendorClosurePath = resolve(vendorRoot, "registry-closure.json");
const vendorLockPath = resolve(vendorRoot, "vendor.lock.json");
const vendorLicensePath = resolve(vendorRoot, "LICENSE");
const vendorReadmePath = resolve(vendorRoot, "README.md");

const manifestRegistryItems = Object.freeze({
  "didact.flashcard": "flashcard",
  "didact.matching-exercises": "matching-exercises",
  "didact.quiz": "quiz-item",
  "didact.glossary": "glossary",
  "didact.hint-reveal": "hint-reveal",
  "didact.progress": "progress-indicators",
  "didact.mastery-badge": "mastery-badge",
  "didact.rubric": "rubric",
  "didact.timeline": "timeline",
  "didact.practice-set": "practice-set",
  "didact.retrieval-practice-session": "retrieval-practice-session",
  "didact.self-explanation-prompt": "generative-learning",
  "didact.worked-example": "generative-learning",
  "didact.completion-problem": "generative-learning",
  "didact.numeric-question": "numeric-question",
  "didact.word-bank": "word-bank",
  "didact.hotspot": "hotspot",
  "didact.interactive-media": "interactive-media",
  "didact.data-explorer": "data-explorer",
  "didact.branching-scenario": "branching-scenario",
  "didact.simulation-lab": "simulation-lab",
  "didact.code-exercise": "code-exercise",
  "didact.label-diagram": "label-diagram",
  "didact.concept-map": "concept-map",
  "didact.drawing-response": "drawing-response",
  "didact.equation-workbench": "equation-workbench",
  "didact.evidence-annotation": "evidence-annotation",
  "didact.measurement-lab": "measurement-lab",
});

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, nested]) => [key, stable(nested)]),
    );
  }
  return value;
}

function serialize(value) {
  return `${JSON.stringify(stable(value), null, 2)}\n`;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function fail(message) {
  throw new Error(message);
}

function assertCounts(snapshot) {
  for (const [field, expected] of Object.entries(EXPECTED_COUNTS)) {
    const actual = snapshot.counts[field];
    if (actual !== expected) fail(`Didact ${field}: expected ${expected}, got ${actual}`);
  }
}

function safeSourcePath(source, path) {
  const absolute = resolve(source, path);
  const withinSource = relative(source, absolute);
  if (!withinSource || withinSource.startsWith(`..${sep}`) || withinSource === "..") {
    fail(`Registry file escapes the Didact checkout: ${path}`);
  }
  return absolute;
}

function readPinnedBlob(source, path) {
  safeSourcePath(source, path);
  try {
    return execFileSync(
      "git",
      ["-c", `safe.directory=${source.replaceAll("\\", "/")}`, "-C", source, "show", `${DIDACT_COMMIT}:${path}`],
      { encoding: "buffer", maxBuffer: 10 * 1024 * 1024 },
    );
  } catch {
    fail(`File is not committed at pinned Didact revision: ${path}`);
  }
}

function resolveRegistryClosure(rootNames, registryByName) {
  const names = new Set();
  function visit(name) {
    if (names.has(name)) return;
    if (name.includes("://")) fail(`Mutable or remote registry dependency is forbidden: ${name}`);
    const item = registryByName.get(name);
    if (!item) fail(`Registry dependency ${name} does not exist at the pinned commit`);
    names.add(name);
    for (const dependency of item.registryDependencies ?? []) visit(dependency);
  }
  for (const name of rootNames) visit(name);
  return [...names].sort();
}

function verifyVendor(snapshot) {
  if (!existsSync(vendorClosurePath) || !existsSync(vendorLockPath) || !existsSync(vendorLicensePath)) {
    fail("Didact vendor closure is missing; synchronize from the pinned checkout");
  }
  const closureText = readFileSync(vendorClosurePath, "utf8");
  const closure = JSON.parse(closureText);
  const lock = JSON.parse(readFileSync(vendorLockPath, "utf8"));
  if (closure.source.commit !== DIDACT_COMMIT || lock.commit !== DIDACT_COMMIT) {
    fail("Vendored Didact sources differ from the pinned commit");
  }
  if (lock.registry_closure_sha256 !== sha256(closureText)) fail("Registry closure hash is invalid");
  if (lock.registry_closure_sha256 !== EXPECTED_REGISTRY_CLOSURE_SHA256) {
    fail("Registry closure differs from the reviewed closure at the pinned commit");
  }
  if (lock.license_sha256 !== sha256(readFileSync(vendorLicensePath))) fail("Vendored license hash is invalid");
  if (!existsSync(vendorReadmePath) || lock.notice_sha256 !== sha256(readFileSync(vendorReadmePath))) {
    fail("Vendored provenance notice hash is invalid");
  }
  if (lock.source_tree_sha256 !== sha256(serialize(lock.files))) fail("Vendored source-tree hash is invalid");
  if (lock.source_tree_sha256 !== EXPECTED_SOURCE_TREE_SHA256) {
    fail("Vendored source tree differs from the reviewed tree at the pinned commit");
  }

  const closureNames = new Set(closure.items.map(({ name }) => name));
  const closureByName = new Map(closure.items.map((item) => [item.name, item]));
  const expectedRoots = new Set(snapshot.available_types.map(({ registry_item }) => registry_item));
  if (expectedRoots.size !== closure.root_items.length || closure.root_items.some((name) => !expectedRoots.has(name))) {
    fail("Registry closure does not cover every available Didact type");
  }
  for (const item of closure.items) {
    for (const dependency of item.registry_dependencies) {
      if (!closureNames.has(dependency)) fail(`${item.name} has unresolved dependency ${dependency}`);
    }
  }
  if (lock.files.length !== closure.counts.files) fail("Vendor file count differs from its closure");
  for (const file of lock.files) {
    const absolute = resolve(vendorSourceRoot, file.path);
    if (!existsSync(absolute)) fail(`Vendored Didact file is missing: ${file.path}`);
    if (sha256(readFileSync(absolute)) !== file.sha256) fail(`Vendored Didact file hash differs: ${file.path}`);
  }

  // A registry mapping is only useful to a loader when its owning source really
  // exports the public symbol declared by availableTypes. This caught the subtle
  // progress primitive/progress-indicators mismatch during integration.
  for (const type of snapshot.available_types) {
    const item = closureByName.get(type.registry_item);
    const source = item.files
      .map(({ path }) => readFileSync(resolve(vendorSourceRoot, path), "utf8"))
      .join("\n");
    if (!new RegExp(`\\b${type.export_name}\\b`).test(source)) {
      fail(`${type.id} registry item ${type.registry_item} does not contain export ${type.export_name}`);
    }
  }

  const lockedPaths = new Set(lock.files.map(({ path }) => path));
  const importPattern = /(?:from\s+|import\s*)["'](\.{1,2}\/[^"']+)["']/g;
  for (const file of lock.files.filter(({ path }) => /\.[cm]?[jt]sx?$/.test(path))) {
    const source = readFileSync(resolve(vendorSourceRoot, file.path), "utf8");
    for (const match of source.matchAll(importPattern)) {
      const imported = posix.resolve("/", posix.dirname(file.path), match[1]).slice(1);
      const candidates = [
        imported,
        imported.replace(/\.js$/, ".ts"),
        imported.replace(/\.js$/, ".tsx"),
        `${imported}.ts`,
        `${imported}.tsx`,
        `${imported}/index.ts`,
        `${imported}/index.tsx`,
      ];
      if (!candidates.some((candidate) => lockedPaths.has(candidate))) {
        fail(`${file.path} has unresolved relative import ${match[1]}`);
      }
    }
  }
}

function verifyFiles() {
  if (!existsSync(snapshotPath) || !existsSync(lockPath)) {
    fail("Didact snapshot or lock is missing; run this script with --source <checkout>");
  }
  const snapshotText = readFileSync(snapshotPath, "utf8");
  const snapshot = JSON.parse(snapshotText);
  const lock = JSON.parse(readFileSync(lockPath, "utf8"));
  assertCounts(snapshot);
  if (snapshot.source.commit !== DIDACT_COMMIT || lock.commit !== DIDACT_COMMIT) {
    fail("Didact source commit differs from the pinned commit");
  }
  if (snapshot.content_sha256 !== sha256(serialize({ ...snapshot, content_sha256: undefined }))) {
    fail("Didact snapshot content hash is invalid");
  }
  if (lock.snapshot_sha256 !== sha256(snapshotText)) fail("Didact lock hash is invalid");
  if (lock.snapshot_sha256 !== EXPECTED_SNAPSHOT_SHA256) {
    fail("Didact snapshot differs from the reviewed snapshot for the pinned commit");
  }
  const manifestIds = new Set(snapshot.manifests.map(({ id }) => id));
  const registryNames = new Set(snapshot.registry_items.map(({ name }) => name));
  for (const type of snapshot.available_types) {
    if (!manifestIds.has(type.manifest_id)) fail(`${type.id} references missing manifest ${type.manifest_id}`);
    if (!registryNames.has(type.registry_item)) fail(`${type.id} references missing registry item ${type.registry_item}`);
  }
  verifyVendor(snapshot);
  console.log(`Verified Didact snapshot ${lock.snapshot_sha256.slice(0, 12)} (${snapshot.available_types.length} types)`);
}

function materializeVendor(source, snapshot, registryByName) {
  const rootNames = [...new Set(snapshot.available_types.map(({ registry_item }) => registry_item))].sort();
  const closureNames = resolveRegistryClosure(rootNames, registryByName);
  const items = closureNames.map((name) => {
    const item = registryByName.get(name);
    const files = (item.files ?? []).map(({ path, type, target }) => ({ path, type, ...(target ? { target } : {}) }));
    return {
      name,
      type: item.type,
      title: item.title,
      description: item.description,
      dependencies: [...(item.dependencies ?? [])],
      registry_dependencies: [...(item.registryDependencies ?? [])],
      files,
    };
  });
  const paths = [...new Set(items.flatMap(({ files }) => files.map(({ path }) => path)))].sort();
  rmSync(vendorRoot, { recursive: true, force: true });
  mkdirSync(vendorSourceRoot, { recursive: true });
  const files = paths.map((path) => {
    const destination = resolve(vendorSourceRoot, path);
    mkdirSync(dirname(destination), { recursive: true });
    writeFileSync(destination, readPinnedBlob(source, path));
    return { path: path.replaceAll("\\", "/"), sha256: sha256(readFileSync(destination)) };
  });
  writeFileSync(vendorLicensePath, readPinnedBlob(source, "LICENSE"));
  writeFileSync(
    vendorReadmePath,
    `# Vendored Didact source\n\n` +
      `This directory is a reproducible source snapshot from ${DIDACT_REPOSITORY} at ` +
      `commit \`${DIDACT_COMMIT}\` (MIT).\n\n` +
      `Do not edit generated files manually. Run \`node scripts/sync_didact_snapshot.mjs ` +
      `--source <pinned-checkout>\` from \`apps/skillnet-api\`, then review the lock diff. ` +
      `The source is intentionally not connected to SkillNet's runtime; host adapters enable ` +
      `families deliberately. Normal builds and offline verification never contact GitHub.\n`,
  );
  const closure = {
    schema_version: 1,
    source: { repository: DIDACT_REPOSITORY, commit: DIDACT_COMMIT },
    root_items: rootNames,
    counts: { available_types: snapshot.available_types.length, root_items: rootNames.length, closure_items: items.length, files: files.length },
    items,
  };
  const closureText = serialize(closure);
  writeFileSync(vendorClosurePath, closureText);
  writeFileSync(
    vendorLockPath,
    serialize({
      schema_version: 1,
      repository: DIDACT_REPOSITORY,
      commit: DIDACT_COMMIT,
      registry_closure: "registry-closure.json",
      registry_closure_sha256: sha256(closureText),
      license: "LICENSE",
      license_sha256: sha256(readFileSync(vendorLicensePath)),
      notice: "README.md",
      notice_sha256: sha256(readFileSync(vendorReadmePath)),
      source_tree_sha256: sha256(serialize(files)),
      files,
    }),
  );
}

async function synchronize(sourceRoot) {
  const source = resolve(sourceRoot);
  const commit = execFileSync("git", ["-c", `safe.directory=${source.replaceAll("\\", "/")}`, "-C", source, "rev-parse", "HEAD"], {
    encoding: "utf8",
  }).trim();
  if (commit !== DIDACT_COMMIT) fail(`Didact checkout must be at ${DIDACT_COMMIT}; got ${commit}`);

  const catalogModule = resolve(source, "packages/catalog/dist/index.js");
  const registryFile = resolve(source, "packages/registry/registry.json");
  if (!existsSync(catalogModule)) fail("Didact catalog dist is missing; build Didact before synchronization");
  if (!existsSync(registryFile)) fail("Didact registry.json is missing");

  const catalog = await import(`${pathToFileURL(catalogModule).href}?commit=${DIDACT_COMMIT}`);
  const registry = JSON.parse(readFileSync(registryFile, "utf8"));
  const manifestIds = new Set(catalog.availableManifests.map(({ id }) => id));
  const mappedManifestIds = new Set(Object.keys(manifestRegistryItems));
  if (manifestIds.size !== mappedManifestIds.size || [...manifestIds].some((id) => !mappedManifestIds.has(id))) {
    fail("Manifest-to-registry mapping is not exhaustive for the pinned Didact catalog");
  }

  const registryByName = new Map(registry.items.map((item) => [item.name, item]));
  const availableTypes = catalog.availableTypes.map(({ id, manifestId, exportName }) => ({
    id,
    manifest_id: manifestId,
    export_name: exportName,
    registry_item: manifestRegistryItems[manifestId],
  }));
  const requiredRegistryNames = [...new Set(availableTypes.map(({ registry_item }) => registry_item))].sort();
  const registryItems = requiredRegistryNames.map((name) => {
    const item = registryByName.get(name);
    if (!item) fail(`Mapped registry item ${name} does not exist`);
    const { name: itemName, type, title, description, dependencies = [], registryDependencies = [], files = [] } = item;
    return {
      name: itemName,
      type,
      title,
      description,
      dependencies,
      registry_dependencies: registryDependencies,
      files,
    };
  });

  const base = {
    schema_version: 1,
    source: { repository: DIDACT_REPOSITORY, commit: DIDACT_COMMIT, license: "MIT" },
    counts: {
      available_types: availableTypes.length,
      manifests: catalog.availableManifests.length,
      collections: catalog.availableCollections.length,
      registry_items: registryItems.length,
    },
    available_types: availableTypes,
    manifests: catalog.availableManifests,
    collections: catalog.availableCollections,
    registry_items: registryItems,
  };
  assertCounts(base);
  const snapshot = { ...base, content_sha256: sha256(serialize({ ...base, content_sha256: undefined })) };
  const snapshotText = serialize(snapshot);
  const lock = {
    schema_version: 1,
    repository: DIDACT_REPOSITORY,
    commit: DIDACT_COMMIT,
    snapshot: "didact_snapshot.json",
    snapshot_sha256: sha256(snapshotText),
  };
  writeFileSync(snapshotPath, snapshotText);
  writeFileSync(lockPath, serialize(lock));
  materializeVendor(source, snapshot, registryByName);
  verifyFiles();
}

const args = process.argv.slice(2);
if (args.includes("--verify")) {
  verifyFiles();
} else {
  const sourceIndex = args.indexOf("--source");
  if (sourceIndex < 0 || !args[sourceIndex + 1]) {
    fail("Usage: node scripts/sync_didact_snapshot.mjs --source <Didact checkout> | --verify");
  }
  await synchronize(args[sourceIndex + 1]);
}
