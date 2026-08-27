"""Read a package directory into validated objects, reporting every fault at once.

Reading is deliberately separate from installing, and it touches no database and no LLM.
That is what lets ``course_package.py lint`` answer "is what I wrote valid" while the
material is still being written, instead of the answer arriving from a failed install.

Faults accumulate rather than raising on the first one. Someone authoring a course wants
the whole list -- a person fixes twelve mistakes in one pass and one mistake in twelve.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from src.knowledge_pack.contracts import NodeKnowledgePack
from src.services.course_package.format import (
    PACKAGE_FORMAT,
    PackageError,
    build_pack,
    build_source_ref,
    course_uuid,
    node_uuid,
)

#: A node slug is the file name of its pack and the ``node_id`` of its contract, so it is
#: held to the stricter of the two: lowercase, no spaces, no surprises on any filesystem.
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")

COURSE_FILE = "course.json"
PACKS_DIR = "packs"


@dataclass(frozen=True)
class PackageNode:
    """One node of the graph plus the pack that grounds it."""

    slug: str
    uuid: UUID
    title: str
    summary: str
    outcome: str | None
    criticality: str
    estimated_minutes: int | None
    ui_format: str
    requires: tuple[str, ...]
    pack: NodeKnowledgePack


@dataclass
class CoursePackage:
    """A package that was read. Valid only when ``errors`` is empty."""

    path: Path
    slug: str = ""
    uuid: UUID | None = None
    title: str = ""
    folder: str | None = None
    intent_density: int = 3
    tutor_style: str | None = None
    schema_version: int = 1
    nodes: list[PackageNode] = field(default_factory=list)
    errors: list[PackageError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _load_json(path: Path, location: str, errors: list[PackageError]) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(PackageError(location, "file not found"))
    except json.JSONDecodeError as exc:
        errors.append(PackageError(location, f"invalid JSON ({exc.msg}, line {exc.lineno})"))
    except UnicodeDecodeError:
        errors.append(PackageError(location, "must be UTF-8"))
    return None


def read_package(directory: str | Path) -> CoursePackage:
    """Read the package at ``directory``, collecting every fault into ``errors``."""
    path = Path(directory)
    package = CoursePackage(path=path)
    course = _load_json(path / COURSE_FILE, COURSE_FILE, package.errors)
    if course is None:
        return package

    declared = course.get("format")
    if declared != PACKAGE_FORMAT:
        package.errors.append(
            PackageError(COURSE_FILE, f"format must be {PACKAGE_FORMAT!r}, found {declared!r}")
        )
        return package

    package.slug = course.get("package") or path.name
    package.uuid = course_uuid(package.slug)
    package.title = course.get("title") or ""
    package.folder = course.get("folder")
    package.intent_density = int(course.get("intent_density", 3))
    package.tutor_style = course.get("tutor_style")
    if not package.title:
        package.errors.append(PackageError(COURSE_FILE, "missing required field 'title'"))

    source_refs = []
    for index, entry in enumerate(course.get("sources") or ()):
        try:
            source_refs.append(build_source_ref(entry, index, COURSE_FILE))
        except PackageError as exc:
            package.errors.append(exc)
    if not source_refs:
        package.errors.append(
            PackageError(f"{COURSE_FILE}.sources", "a pack must cite at least one source")
        )

    raw_nodes = course.get("nodes") or ()
    if not raw_nodes:
        package.errors.append(PackageError(f"{COURSE_FILE}.nodes", "a course needs a node"))

    # Prerequisites are checked against every node the course *declares*, not against the
    # nodes whose pack happened to build. A pack fault must not hide a graph fault, or
    # fixing the first one uncovers the second and lint has cost two passes to say so.
    seen: set[str] = set()
    declared_requires: list[tuple[str, tuple[str, ...]]] = []
    for index, node in enumerate(raw_nodes):
        where = f"{COURSE_FILE}.nodes[{index}]"
        if not isinstance(node, dict):
            package.errors.append(PackageError(where, "must be an object"))
            continue
        slug = node.get("id") or ""
        if not _SLUG.fullmatch(slug):
            package.errors.append(
                PackageError(f"{where}.id", f"{slug!r} must be lowercase letters, digits, hyphens")
            )
            continue
        if slug in seen:
            package.errors.append(PackageError(f"{where}.id", f"duplicate node id {slug!r}"))
            continue
        seen.add(slug)
        declared_requires.append((slug, tuple(node.get("requires") or ())))

        pack_location = f"{PACKS_DIR}/{slug}.json"
        pack_doc = _load_json(path / PACKS_DIR / f"{slug}.json", pack_location, package.errors)
        if pack_doc is None:
            continue
        identifier = node_uuid(package.slug, slug)
        try:
            pack = build_pack(
                node=node,
                node_id=str(identifier),
                pack_doc=pack_doc,
                source_refs=tuple(source_refs),
                schema_version=package.schema_version,
                location=pack_location,
            )
        except PackageError as exc:
            package.errors.append(exc)
            continue

        package.nodes.append(
            PackageNode(
                slug=slug,
                uuid=identifier,
                title=node.get("title") or "",
                summary=node.get("summary") or "",
                outcome=node.get("outcome"),
                criticality=node.get("criticality") or "recommended",
                estimated_minutes=node.get("estimated_minutes"),
                ui_format=node.get("ui_format") or "explanation",
                requires=tuple(node.get("requires") or ()),
                pack=pack,
            )
        )

    _check_prerequisites(package, declared_requires, seen)
    _check_orphan_packs(package, path, seen)
    return package


def _check_prerequisites(
    package: CoursePackage,
    declared: list[tuple[str, tuple[str, ...]]],
    known: set[str],
) -> None:
    """Every ``requires`` must name a node of this package, and none may name itself.

    Cycles are not checked here: ``CourseSchemaService`` already owns that rule for every
    path into the graph, and a second implementation would be a second answer to it.
    """
    for slug, requires in declared:
        for required in requires:
            if required == slug:
                package.errors.append(
                    PackageError(f"{COURSE_FILE}.nodes[{slug}]", "cannot require itself")
                )
            elif required not in known:
                package.errors.append(
                    PackageError(
                        f"{COURSE_FILE}.nodes[{slug}].requires", f"unknown node {required!r}"
                    )
                )


def _check_orphan_packs(package: CoursePackage, path: Path, declared: set[str]) -> None:
    """A pack file no node claims is reported, never silently ignored.

    It is nearly always a renamed node or a typo, and staying quiet about it means shipping
    a course missing the material someone believed they had written.
    """
    packs_dir = path / PACKS_DIR
    if not packs_dir.is_dir():
        return
    for pack_file in sorted(packs_dir.glob("*.json")):
        if pack_file.stem not in declared:
            package.errors.append(
                PackageError(
                    f"{PACKS_DIR}/{pack_file.name}",
                    f"no node with id {pack_file.stem!r} in {COURSE_FILE}",
                )
            )
