"""Turn a course that already exists into a package directory.

Export is what makes the expensive half of a course reusable. Knowledge packs are minutes
of model time and real money, and until they can leave the database they live on exactly
one machine and die with it. A package freezes them, so the same course installs elsewhere
in seconds with no key and no second bill.

What travels is the material and its identity: the graph, the packs, and the ids the course
already has. Identity is pinned rather than derived here, because these nodes exist -- their
ids are in ``node_renders.cache_key`` and in every learner's state -- and a re-install that
minted fresh ones would install a different course wearing the same title.

What deliberately does not travel: enrolments, progress, render history and chats. They
belong to the instance that produced them, not to the course.
"""

from __future__ import annotations

import json
import re
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Course, CourseFolder, CourseNode, CourseNodePrerequisite
from src.models.node_knowledge_pack import (
    NodeKnowledgePackRecord,
    NodeKnowledgePackStatus,
)
from src.services.course_package.format import PACKAGE_FORMAT
from src.services.course_package.read import COURSE_FILE, PACKS_DIR

_NON_SLUG = re.compile(r"[^a-z0-9]+")


class ExportError(RuntimeError):
    """The course cannot be exported, for a reason the caller has to resolve."""


@dataclass
class ExportResult:
    path: Path
    slug: str
    nodes: int
    packs: int

    def summary(self) -> str:
        return f"wrote {self.path} ({self.nodes} nodes, {self.packs} packs)"


def slugify(value: str) -> str:
    """ASCII-fold to the lowercase-hyphen shape a node id and a file name both allow."""
    folded = unicodedata.normalize("NFKD", value)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii").lower()
    return _NON_SLUG.sub("-", ascii_only).strip("-") or "node"


def _unique(slug: str, taken: set[str]) -> str:
    """Two nodes titled alike must not become one file quietly overwriting the other."""
    candidate, suffix = slug, 2
    while candidate in taken:
        candidate, suffix = f"{slug}-{suffix}", suffix + 1
    taken.add(candidate)
    return candidate


def _source(ref: dict) -> dict:
    """One contract ``SourceRef`` back in the short shape a package writes.

    ``excerpt_hash`` is not written: it is derived from the descriptor on the way back in,
    so a package never carries a digest that could contradict the fields around it.
    """
    entry = {"ref": ref["ref_id"], "document": ref["document_id"]}
    if ref.get("heading_path"):
        entry["heading"] = list(ref["heading_path"])
    if ref.get("locator"):
        entry["locator"] = ref["locator"]
    if ref.get("source_revision"):
        entry["revision"] = ref["source_revision"]
    return entry


def _atom(atom: dict, *, selectable: bool) -> dict:
    """One contract atom in the short shape, dropping everything that is empty."""
    entry: dict = {
        "id": atom["atom_id"],
        "kind": atom["kind"],
        "text": atom["text"],
        "sources": list(atom.get("sources") or ()),
    }
    for key, target in (("evidence", "evidence"), ("source_units", "source_units")):
        if atom.get(key):
            entry[target] = list(atom[key])
    if selectable:
        for key, target in (
            ("missions", "missions"),
            ("presentations", "presentations"),
            ("tags", "tags"),
            ("prereqs", "requires"),
        ):
            if atom.get(key):
                entry[target] = list(atom[key])
    elif atom.get("critical"):
        entry["critical"] = True
    return entry


def _pack_document(payload: dict) -> dict:
    """A stored ``pack_payload`` as the package's own pack document.

    Provenance travels verbatim. Its digests are what an auditor and the runtime match
    against, so re-deriving them on the way out would make the exported pack a different
    pack from the one this course actually taught.
    """
    document: dict = {
        "sources": [_source(ref) for ref in payload.get("source_refs") or ()],
        "must_preserve": [
            _atom(atom, selectable=False) for atom in payload.get("must_preserve") or ()
        ],
    }
    if payload.get("selectable"):
        document["selectable"] = [
            _atom(atom, selectable=True) for atom in payload["selectable"]
        ]
    if payload.get("evidence_specs"):
        document["evidence"] = [
            {
                "id": item["evidence_id"],
                "description": item["description"],
                "atoms": list(item.get("atom_refs") or ()),
                **({} if item.get("required", True) else {"required": False}),
            }
            for item in payload["evidence_specs"]
        ]
    if payload.get("generable_slots"):
        document["slots"] = [
            {
                "id": item["slot_id"],
                "purpose": item["purpose"],
                "atoms": list(item.get("allowed_atom_refs") or ()),
                **({"forbidden": list(item["forbidden_claims"])} if item.get("forbidden_claims") else {}),
                **({"max_items": item["max_items"]} if item.get("max_items", 1) != 1 else {}),
            }
            for item in payload["generable_slots"]
        ]
    if payload.get("missing_data"):
        document["missing"] = [
            {
                "id": item["data_id"],
                "description": item["description"],
                "affects": list(item.get("affects") or ()),
                "blocking": item.get("blocking", False),
                "fallback": item["fallback"],
            }
            for item in payload["missing_data"]
        ]
    document["provenance"] = payload.get("provenance") or {}
    return document


async def _ready_packs(
    db: AsyncSession, node_ids: list[uuid.UUID]
) -> dict[uuid.UUID, NodeKnowledgePackRecord]:
    """The newest ready pack of each node. A node without one is reported, not skipped."""
    rows = (
        (
            await db.execute(
                select(NodeKnowledgePackRecord)
                .where(
                    NodeKnowledgePackRecord.node_id.in_(node_ids),
                    NodeKnowledgePackRecord.status == NodeKnowledgePackStatus.READY,
                )
                .order_by(NodeKnowledgePackRecord.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    newest: dict[uuid.UUID, NodeKnowledgePackRecord] = {}
    for row in rows:
        newest.setdefault(row.node_id, row)
    return newest


async def export_course(
    db: AsyncSession,
    course_id: uuid.UUID,
    destination: str | Path,
    *,
    slug: str | None = None,
) -> ExportResult:
    """Write the course at ``course_id`` into ``destination`` as a package directory."""
    course = await db.get(Course, course_id)
    if course is None:
        raise ExportError(f"no course with id {course_id}")

    nodes = (
        (
            await db.execute(
                select(CourseNode)
                .where(CourseNode.course_id == course_id, CourseNode.archived.is_(False))
                .order_by(CourseNode.position)
            )
        )
        .scalars()
        .all()
    )
    if not nodes:
        raise ExportError(f"course {course.title!r} has no nodes to export")

    node_ids = [node.id for node in nodes]
    packs = await _ready_packs(db, node_ids)
    unprepared = [node.title for node in nodes if node.id not in packs]
    if unprepared:
        raise ExportError(
            "these nodes have no ready knowledge pack, so the package would install a "
            f"course with nothing to teach: {', '.join(unprepared)}"
        )

    edges = (
        (
            await db.execute(
                select(CourseNodePrerequisite).where(
                    CourseNodePrerequisite.node_id.in_(node_ids)
                )
            )
        )
        .scalars()
        .all()
    )

    package_slug = slug or slugify(course.title)
    root = Path(destination) / package_slug
    (root / PACKS_DIR).mkdir(parents=True, exist_ok=True)

    taken: set[str] = set()
    slugs = {node.id: _unique(slugify(node.title), taken) for node in nodes}
    requires: dict[uuid.UUID, list[str]] = {node.id: [] for node in nodes}
    for edge in edges:
        if edge.prerequisite_node_id in slugs:
            requires[edge.node_id].append(slugs[edge.prerequisite_node_id])

    folder = (
        await db.get(CourseFolder, course.folder_id) if course.folder_id else None
    )
    document: dict = {
        "format": PACKAGE_FORMAT,
        "package": package_slug,
        # Pinned, not derived: these nodes already exist, and their ids are part of the
        # render cache key and of every learner's state.
        "uuid": str(course.id),
        "title": course.title,
        "intent_density": course.intent_density,
        "tutor_style": getattr(course.tutor_style, "value", course.tutor_style),
        "nodes": [],
    }
    if folder is not None:
        document["folder"] = folder.name

    written = 0
    for node in nodes:
        payload = packs[node.id].pack_payload or {}
        objective = payload.get("objective") or {}
        entry: dict = {
            "id": slugs[node.id],
            "uuid": str(node.id),
            "title": node.title,
            "summary": node.summary,
            "criticality": getattr(node.criticality, "value", node.criticality),
            "ui_format": getattr(node.default_ui_format, "value", node.default_ui_format),
            "mission": objective.get("mission"),
            "source_functions": sorted(objective.get("source_functions") or ()),
        }
        if node.outcome:
            entry["outcome"] = node.outcome
        if node.estimated_minutes:
            entry["estimated_minutes"] = node.estimated_minutes
        if requires[node.id]:
            entry["requires"] = sorted(requires[node.id])
        document["nodes"].append(entry)

        pack_path = root / PACKS_DIR / f"{slugs[node.id]}.json"
        pack_path.write_text(
            json.dumps(_pack_document(payload), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written += 1

    (root / COURSE_FILE).write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return ExportResult(path=root, slug=package_slug, nodes=len(nodes), packs=written)
