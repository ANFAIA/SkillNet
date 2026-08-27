"""Install a read package into a database, with no LLM call and no key.

The installer is the counterpart of :mod:`read`: reading answers "is this valid", installing
answers "is this here". It lives in ``src/services`` rather than in the script that calls it
so the application can install a package too -- ``org_demo_seed`` already pre-bakes a course
for a brand-new organization the same way, and a package is that idea with the course moved
out of Python and onto disk.

Two properties do the work:

* **Identity comes from the package, not from this instance.** A package installs as the
  same course id and the same node ids everywhere, so re-installing updates rather than
  duplicates, and a screen pre-generated on one machine still matches on another.
* **Nodes are updated in place, never dropped and re-created.** Deleting a node takes its
  learner state, attempts and renders with it. A node the package no longer declares is
  archived instead, which is reversible; deleting one is not.

What the installer deliberately does not do is call a model. A course arrives with its
graph and its knowledge packs already written; screens are generated live by the runtime,
exactly as they are for a course that was created through the wizard.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.knowledge_pack.markdown import render_markdown
from src.models import (
    Course,
    CourseFolder,
    CourseNode,
    CourseNodePrerequisite,
    Organization,
    User,
    UserRole,
)
from src.models.course import ContentStatus, CourseDeliveryMode, CourseSchemaStatus
from src.models.course_node import NodeCriticality, UiFormat
from src.models.node_knowledge_pack import (
    NodeKnowledgePackRecord,
    NodeKnowledgePackStatus,
)
from src.services.course_package.format import HANDWRITTEN_GENERATOR, sha256_text
from src.services.course_package.read import CoursePackage, PackageNode
from src.services.course_schema_service import default_threshold_for


class InstallError(RuntimeError):
    """The package cannot be installed here, for a reason the caller has to resolve."""


@dataclass
class InstallResult:
    """What one install did, in the terms a caller reports to a person."""

    course_id: uuid.UUID
    title: str
    created: bool
    nodes_written: int
    nodes_archived: int
    packs_written: int

    def summary(self) -> str:
        verb = "created" if self.created else "updated"
        archived = f", {self.nodes_archived} archived" if self.nodes_archived else ""
        return (
            f"{verb} {self.title} ({self.course_id}): "
            f"{self.nodes_written} nodes{archived}, {self.packs_written} packs"
        )


async def resolve_identity(
    db: AsyncSession, org_id: uuid.UUID | None, actor_id: uuid.UUID | None
) -> tuple[uuid.UUID, uuid.UUID]:
    """Resolve (organization, acting admin), defaulting to the first org and its admin.

    The acting admin is not decoration: it is stamped as the reviewer of every node and as
    the validator of the schema, and ``validate`` is the only thing that publishes a v2
    course. The same default as ``scripts/create_course.py``, so both entry points agree.
    """
    if org_id is None:
        org = (await db.execute(select(Organization).limit(1))).scalar_one_or_none()
        if org is None:
            raise InstallError("no organization exists yet; start the application first")
        org_id = org.id
    if actor_id is None:
        admin = (
            await db.execute(
                select(User).where(User.org_id == org_id, User.role == UserRole.ADMIN).limit(1)
            )
        ).scalar_one_or_none()
        if admin is None:
            raise InstallError(f"organization {org_id} has no admin to install as")
        actor_id = admin.id
    return org_id, actor_id


async def _folder_id(
    db: AsyncSession, org_id: uuid.UUID, name: str | None
) -> uuid.UUID | None:
    """The org's folder called ``name``, created when it is not there yet."""
    if not name:
        return None
    folder = (
        await db.execute(
            select(CourseFolder).where(
                CourseFolder.org_id == org_id, CourseFolder.name == name
            )
        )
    ).scalar_one_or_none()
    if folder is None:
        folder = CourseFolder(org_id=org_id, name=name)
        db.add(folder)
        await db.flush()
    return folder.id


async def _course_row(
    db: AsyncSession, package: CoursePackage, org_id: uuid.UUID, actor_id: uuid.UUID
) -> tuple[Course, bool]:
    course = await db.get(Course, package.uuid)
    created = course is None
    if course is not None and course.org_id != org_id:
        raise InstallError(
            f"package {package.slug!r} is already installed in another organization on this "
            "instance; a package installs under one identity per instance"
        )
    if course is None:
        course = Course(id=package.uuid, org_id=org_id, created_by=actor_id)
        db.add(course)

    course.title = package.title
    course.folder_id = await _folder_id(db, org_id, package.folder)
    course.intent_density = package.intent_density
    if package.tutor_style:
        course.tutor_style = package.tutor_style
    course.status = ContentStatus.PUBLISHED
    # The two conditions ``course_delivery.resolve_delivery`` checks, and the only ones. A
    # package arrives reviewed and validated because a person wrote and signed off its
    # material before it was ever a directory.
    course.delivery_mode = CourseDeliveryMode.DYNAMIC
    course.schema_status = CourseSchemaStatus.VALIDATED
    course.schema_validated_by = actor_id
    course.schema_validated_at = datetime.now(timezone.utc)
    course.schema_version = package.schema_version
    await db.flush()
    return course, created


def _apply_node(
    node: CourseNode, source: PackageNode, position: int, actor_id: uuid.UUID
) -> None:
    node.title = source.title
    node.summary = source.summary
    node.outcome = source.outcome
    node.criticality = NodeCriticality(source.criticality)
    node.position = position
    node.default_ui_format = UiFormat(source.ui_format)
    node.mastery_threshold = default_threshold_for(source.criticality)
    node.estimated_minutes = source.estimated_minutes
    node.archived = False
    # ``assert_reviewed`` refuses to serve an unreviewed node, so a package that arrives
    # already written also arrives already signed off; the installing admin is the signer.
    node.reviewed_at = datetime.now(timezone.utc)
    node.reviewed_by = actor_id


async def _write_nodes(
    db: AsyncSession, package: CoursePackage, course: Course, actor_id: uuid.UUID
) -> tuple[int, int]:
    existing = {
        row.id: row
        for row in (
            await db.execute(select(CourseNode).where(CourseNode.course_id == course.id))
        )
        .scalars()
        .all()
    }
    written = 0
    for position, source in enumerate(package.nodes, start=1):
        node = existing.get(source.uuid)
        if node is None:
            node = CourseNode(id=source.uuid, org_id=course.org_id, course_id=course.id)
            db.add(node)
        _apply_node(node, source, position, actor_id)
        written += 1

    declared = {source.uuid for source in package.nodes}
    archived = 0
    for node_id, node in existing.items():
        if node_id not in declared and not node.archived:
            node.archived = True
            archived += 1

    await db.flush()
    await _write_prerequisites(db, package, declared)
    return written, archived


async def _write_prerequisites(
    db: AsyncSession, package: CoursePackage, declared: set[uuid.UUID]
) -> None:
    """Replace the edges of the declared nodes, leaving any other node's edges alone."""
    by_slug = {source.slug: source.uuid for source in package.nodes}
    existing = (
        (
            await db.execute(
                select(CourseNodePrerequisite).where(
                    CourseNodePrerequisite.node_id.in_(declared)
                )
            )
        )
        .scalars()
        .all()
    )
    wanted = {
        (source.uuid, by_slug[required])
        for source in package.nodes
        for required in source.requires
    }
    for row in existing:
        pair = (row.node_id, row.prerequisite_node_id)
        if pair in wanted:
            wanted.discard(pair)
        else:
            await db.delete(row)
    for node_id, prerequisite_id in wanted:
        db.add(CourseNodePrerequisite(node_id=node_id, prerequisite_node_id=prerequisite_id))
    await db.flush()


async def _write_packs(db: AsyncSession, package: CoursePackage, course: Course) -> int:
    """Write each node's knowledge pack as a ``ready`` snapshot.

    The snapshot key is ``(node_id, source_fingerprint, generator_version)``, and the
    fingerprint used here is the pack's own source bundle hash. Re-installing unchanged
    material therefore updates one row rather than accumulating a new snapshot per install,
    while genuinely changed material lands as the new snapshot it is.
    """
    written = 0
    for source in package.nodes:
        pack = source.pack
        fingerprint = pack.provenance.source_bundle_hash
        record = (
            await db.execute(
                select(NodeKnowledgePackRecord).where(
                    NodeKnowledgePackRecord.node_id == source.uuid,
                    NodeKnowledgePackRecord.source_fingerprint == fingerprint,
                    NodeKnowledgePackRecord.generator_version == HANDWRITTEN_GENERATOR,
                )
            )
        ).scalar_one_or_none()
        if record is None:
            record = NodeKnowledgePackRecord(
                org_id=course.org_id,
                course_id=course.id,
                node_id=source.uuid,
                source_fingerprint=fingerprint,
                generator_version=HANDWRITTEN_GENERATOR,
            )
            db.add(record)

        markdown = render_markdown(pack)
        # The same compact atom view a generated pack stores: an inspection index, never
        # the thing runtime selection reads. That is ``pack_payload``.
        atoms = [
            {"category": category, **atom.model_dump(mode="json")}
            for category, values in (
                ("must_preserve", pack.must_preserve),
                ("selectable", pack.selectable),
            )
            for atom in values
        ]
        record.schema_version = package.schema_version
        record.status = NodeKnowledgePackStatus.READY
        record.markdown = markdown
        record.markdown_hash = sha256_text(markdown)
        record.atoms = atoms
        record.atoms_hash = sha256_text(str(atoms))
        record.pack_payload = pack.canonical_payload()
        record.pack_hash = pack.canonical_hash
        record.provenance = pack.provenance.model_dump(mode="json")
        record.error_message = None
        written += 1

    # Any older snapshot of these nodes is superseded by what was just written.
    for source in package.nodes:
        stale = (
            (
                await db.execute(
                    select(NodeKnowledgePackRecord).where(
                        NodeKnowledgePackRecord.node_id == source.uuid,
                        NodeKnowledgePackRecord.source_fingerprint
                        != source.pack.provenance.source_bundle_hash,
                        NodeKnowledgePackRecord.status != NodeKnowledgePackStatus.STALE,
                    )
                )
            )
            .scalars()
            .all()
        )
        for record in stale:
            record.status = NodeKnowledgePackStatus.STALE

    await db.flush()
    return written


async def install_package(
    db: AsyncSession,
    package: CoursePackage,
    *,
    org_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
) -> InstallResult:
    """Install ``package`` into ``org_id``, creating or updating it in place.

    The caller commits. Nothing here calls a model, reads a key or reaches the network.
    """
    if not package.ok:
        raise InstallError(
            f"package has {len(package.errors)} unresolved problem(s); run lint first"
        )
    org_id, actor_id = await resolve_identity(db, org_id, actor_id)
    course, created = await _course_row(db, package, org_id, actor_id)
    written, archived = await _write_nodes(db, package, course, actor_id)
    packs = await _write_packs(db, package, course)
    return InstallResult(
        course_id=course.id,
        title=course.title,
        created=created,
        nodes_written=written,
        nodes_archived=archived,
        packs_written=packs,
    )
