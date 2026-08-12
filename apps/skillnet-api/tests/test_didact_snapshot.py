"""Integrity tests for the offline Didact catalog snapshot."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parents[1]
SNAPSHOT_PATH = ROOT / "src/personalization/didact_snapshot.json"
LOCK_PATH = ROOT / "src/personalization/didact.lock.json"
VENDOR_ROOT = ROOT.parent / "skillnet-web/vendor/didact"
PINNED_COMMIT = "06c80e8a8af4f20ad20ba345b7b6b13e1cc27e0c"
PINNED_SNAPSHOT_SHA256 = "b517ea1edba79e1e4e7c34ed6afb866c8c22488a39aef127efda6f2c1a4cf675"
PINNED_CLOSURE_SHA256 = "2f97bb5d30fe1a5ad0459a270573ff4b24b3b02293ae19e7d891be8daa8ec07b"
PINNED_SOURCE_TREE_SHA256 = "82ab1c1bb6e5e67f09c1fc0737c0b307d199fd910526ee5778da10136285a455"


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def test_didact_snapshot_is_pinned_and_hashes_match() -> None:
    snapshot_bytes = SNAPSHOT_PATH.read_bytes()
    snapshot = json.loads(snapshot_bytes)
    lock = json.loads(LOCK_PATH.read_bytes())

    assert snapshot["source"]["commit"] == PINNED_COMMIT
    assert lock["commit"] == PINNED_COMMIT
    assert lock["snapshot_sha256"] == PINNED_SNAPSHOT_SHA256
    assert hashlib.sha256(snapshot_bytes).hexdigest() == lock["snapshot_sha256"]

    content_hash = snapshot.pop("content_sha256")
    assert hashlib.sha256(_canonical_json(snapshot)).hexdigest() == content_hash


def test_didact_snapshot_is_exhaustive_and_references_are_closed() -> None:
    snapshot = json.loads(SNAPSHOT_PATH.read_bytes())

    assert snapshot["counts"] == {
        "available_types": 34,
        "collections": 6,
        "manifests": 28,
        "registry_items": 26,
    }
    assert len(snapshot["available_types"]) == 34
    assert len(snapshot["manifests"]) == 28
    assert len(snapshot["collections"]) == 6

    type_ids = [item["id"] for item in snapshot["available_types"]]
    manifest_ids = {item["id"] for item in snapshot["manifests"]}
    collection_ids = [item["id"] for item in snapshot["collections"]]
    registry_items = {item["name"] for item in snapshot["registry_items"]}

    assert len(type_ids) == len(set(type_ids))
    assert len(collection_ids) == len(set(collection_ids))
    assert all(item["manifest_id"] in manifest_ids for item in snapshot["available_types"])
    assert all(item["registry_item"] in registry_items for item in snapshot["available_types"])

    mapped_manifests = {item["manifest_id"] for item in snapshot["available_types"]}
    assert mapped_manifests == manifest_ids


def test_vendored_didact_registry_closure_is_complete_and_immutable() -> None:
    snapshot = json.loads(SNAPSHOT_PATH.read_bytes())
    closure_bytes = (VENDOR_ROOT / "registry-closure.json").read_bytes()
    closure = json.loads(closure_bytes)
    vendor_lock = json.loads((VENDOR_ROOT / "vendor.lock.json").read_bytes())

    assert closure["source"]["commit"] == PINNED_COMMIT
    assert vendor_lock["commit"] == PINNED_COMMIT
    assert hashlib.sha256(closure_bytes).hexdigest() == PINNED_CLOSURE_SHA256
    assert vendor_lock["registry_closure_sha256"] == PINNED_CLOSURE_SHA256
    assert vendor_lock["source_tree_sha256"] == PINNED_SOURCE_TREE_SHA256
    assert closure["counts"] == {
        "available_types": 34,
        "closure_items": 46,
        "files": 51,
        "root_items": 26,
    }

    roots = set(closure["root_items"])
    assert roots == {item["registry_item"] for item in snapshot["available_types"]}
    closure_names = {item["name"] for item in closure["items"]}
    assert all(
        dependency in closure_names
        for item in closure["items"]
        for dependency in item["registry_dependencies"]
    )

    locked_files = vendor_lock["files"]
    assert hashlib.sha256(_canonical_json(locked_files)).hexdigest() == PINNED_SOURCE_TREE_SHA256
    assert len(locked_files) == 51
    for file in locked_files:
        contents = (VENDOR_ROOT / "source" / file["path"]).read_bytes()
        assert hashlib.sha256(contents).hexdigest() == file["sha256"]

    assert hashlib.sha256((VENDOR_ROOT / "LICENSE").read_bytes()).hexdigest() == vendor_lock[
        "license_sha256"
    ]
    assert hashlib.sha256((VENDOR_ROOT / "README.md").read_bytes()).hexdigest() == vendor_lock[
        "notice_sha256"
    ]


def test_every_didact_loader_target_has_its_export_and_relative_imports() -> None:
    snapshot = json.loads(SNAPSHOT_PATH.read_bytes())
    closure = json.loads((VENDOR_ROOT / "registry-closure.json").read_bytes())
    vendor_lock = json.loads((VENDOR_ROOT / "vendor.lock.json").read_bytes())
    closure_by_name = {item["name"]: item for item in closure["items"]}
    locked_paths = {file["path"] for file in vendor_lock["files"]}

    for available_type in snapshot["available_types"]:
        registry_item = closure_by_name[available_type["registry_item"]]
        owning_source = "\n".join(
            (VENDOR_ROOT / "source" / file["path"]).read_text(encoding="utf-8")
            for file in registry_item["files"]
        )
        assert re.search(rf"\b{re.escape(available_type['export_name'])}\b", owning_source), (
            f"{available_type['id']} has no {available_type['export_name']} export in "
            f"registry item {registry_item['name']}"
        )

    import_pattern = re.compile(r"(?:from\s+|import\s*)[\"'](\.{1,2}/[^\"']+)[\"']")
    for file in vendor_lock["files"]:
        if not re.search(r"\.[cm]?[jt]sx?$", file["path"]):
            continue
        source = (VENDOR_ROOT / "source" / file["path"]).read_text(encoding="utf-8")
        for imported in import_pattern.findall(source):
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(file["path"]), imported))
            candidates = {
                resolved,
                re.sub(r"\.js$", ".ts", resolved),
                re.sub(r"\.js$", ".tsx", resolved),
                f"{resolved}.ts",
                f"{resolved}.tsx",
                f"{resolved}/index.ts",
                f"{resolved}/index.tsx",
            }
            assert candidates & locked_paths, f"{file['path']} -> {imported} is missing"
