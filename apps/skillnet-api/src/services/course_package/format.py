"""On-disk course package: a directory that installs as a course, with no LLM call.

A package is the *authoring* format and the *export* format at once, and it is a thin
serialization of contracts that already exist -- :class:`NodeKnowledgePack` for the packs,
and the same node fields ``PUT /courses/{id}/schema`` already accepts for the graph. There
is deliberately **no second definition** of what a pack is: a package written by hand is
validated by exactly the code that validates a generated one, so nothing can be authored
here that the pipeline would refuse, and the two cannot drift apart later.

Layout::

    <slug>/
        course.json          course metadata, shared source pointers, the node graph
        packs/<node>.json    the atoms of one node, named after the node's slug

The on-disk shape trades the contract's long field names for short ones and fills in
everything mechanical -- hashes, provenance, the objective, the required-fact cross links --
so that writing a package by hand stays about the teaching material and never about
reproducing a digest by hand. :func:`build_pack` is the only place that knows both shapes.

The Markdown dossier is **not** part of the package: ``knowledge_pack.markdown`` projects it
deterministically from the contract, so storing it here would be a second copy free to
disagree with the atoms it claims to describe.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from pydantic import ValidationError

from src.knowledge_pack.contracts import (
    EvidenceSpec,
    GenerableSlot,
    MissingData,
    MissingDataArea,
    MustPreserveAtom,
    MustPreserveKind,
    NodeKnowledgePack,
    PackProvenance,
    PackStatus,
    SelectableAtom,
    SelectableKind,
    SourceRef,
)
from src.personalization.plan import (
    CognitiveMission,
    LearningObjective,
    Presentation,
    SourceFunction,
)

#: Version of the on-disk layout. Bump when a package written today would no longer read.
PACKAGE_FORMAT = "course-package/1"

#: ``provenance.generator`` of a package a person wrote, as opposed to one the pack
#: generator produced. It travels into the database, so a hand-authored pack stays
#: recognisable months later without consulting anything outside the row.
HANDWRITTEN_GENERATOR = "handwritten/1"

#: Namespace for the identifiers a package derives. Fixed forever: changing it would make
#: every installed package a different course on the next install.
PACKAGE_NAMESPACE = uuid.UUID("3f2b6a10-5c47-4e8d-9a71-0d2e8c6b4f15")


def course_uuid(package_slug: str) -> uuid.UUID:
    """The course id a package always installs as."""
    return uuid.uuid5(PACKAGE_NAMESPACE, f"course:{package_slug}")


def node_uuid(package_slug: str, node_slug: str) -> uuid.UUID:
    """The node id a package always installs as, on every machine.

    Derived rather than authored for two reasons. Nobody should hand-write a UUID into a
    JSON file, and ``node_renders.cache_key`` is keyed partly on ``node_id`` -- so a package
    that produced fresh ids on each install would invalidate every pre-generated screen the
    moment it moved between machines.

    It also has to be a UUID rather than the readable slug: generated packs carry
    ``node_id=str(node.id)``, and a hand-written pack that carried something else would be a
    second convention for the same field.
    """
    return uuid.uuid5(PACKAGE_NAMESPACE, f"node:{package_slug}:{node_slug}")


class PackageError(ValueError):
    """One authoring mistake, addressed by where it is rather than by what raised it.

    ``location`` is the path a person can act on -- ``packs/venta.json ->
    must_preserve[2].kind`` -- because the whole point of ``lint`` is to answer "what do I
    change" without having to read this module.
    """

    def __init__(self, location: str, message: str) -> None:
        super().__init__(f"{location}: {message}")
        self.location = location
        self.message = message


def contract_message(exc: ValueError) -> str:
    """The human half of a contract rejection.

    Pydantic renders a validation error as a header, a dump of the offending input and a
    documentation URL. None of that helps someone editing a JSON file, and all of it buries
    the one sentence that does, so a package fault reports the sentence.
    """
    if not isinstance(exc, ValidationError):
        return str(exc)
    return "; ".join(
        error["msg"].removeprefix("Value error, ") for error in exc.errors()
    ) or str(exc)


def sha256_text(value: str) -> str:
    """Lowercase SHA-256 of ``value``, the digest shape every contract hash expects."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_digest(value: Any) -> str:
    """Digest of a JSON value with object keys sorted, so it is stable across rewrites."""
    return sha256_text(json.dumps(value, sort_keys=True, ensure_ascii=False))


def _field(entry: Any, key: str, location: str) -> Any:
    if not isinstance(entry, dict):
        raise PackageError(location, "must be an object")
    if key not in entry:
        raise PackageError(location, f"missing required field {key!r}")
    return entry[key]


def _refs(entry: dict, key: str) -> tuple[str, ...]:
    """Optional list-of-strings field, where absent and empty mean the same thing."""
    return tuple(entry.get(key) or ())


def _enum(raw: Any, enum_cls: Any, location: str, key: str) -> Any:
    """Coerce to ``enum_cls`` and, when that fails, say what the valid values are.

    Listing them is the difference between a message someone can act on and one that sends
    them into this repository to find out.
    """
    try:
        return enum_cls(raw)
    except ValueError:
        allowed = ", ".join(member.value for member in enum_cls)
        raise PackageError(f"{location}.{key}", f"{raw!r} is not one of: {allowed}") from None


def build_source_ref(entry: dict, index: int, location: str) -> SourceRef:
    """One shared source pointer from ``course.json`` as a contract ``SourceRef``.

    ``excerpt_hash`` identifies the *pointer*, not a copied excerpt: a package cites
    material it deliberately does not carry, and the contract still requires a digest so
    that a changed citation invalidates what was built from it. Hashing the canonical
    descriptor gives exactly that property while keeping the author clear of writing
    digests by hand.
    """
    where = f"{location}.sources[{index}]"
    ref_id = _field(entry, "ref", where)
    document = _field(entry, "document", where)
    heading = _refs(entry, "heading")
    locator = entry.get("locator") or "whole document"
    revision = str(entry.get("revision") or "1")
    descriptor = {
        "document": document,
        "heading": list(heading),
        "locator": locator,
        "revision": revision,
    }
    try:
        return SourceRef(
            ref_id=ref_id,
            document_id=document,
            heading_path=heading,
            locator=locator,
            excerpt_hash=canonical_digest(descriptor),
            source_revision=revision,
        )
    except ValueError as exc:
        raise PackageError(where, contract_message(exc)) from exc


def _must_preserve(entry: dict, index: int, location: str) -> MustPreserveAtom:
    where = f"{location}.must_preserve[{index}]"
    kind = _enum(_field(entry, "kind", where), MustPreserveKind, where, "kind")
    try:
        return MustPreserveAtom(
            atom_id=_field(entry, "id", where),
            kind=kind,
            text=_field(entry, "text", where),
            sources=_refs(entry, "sources"),
            evidence=_refs(entry, "evidence"),
            critical=bool(entry.get("critical", False)),
        )
    except ValueError as exc:
        raise PackageError(where, contract_message(exc)) from exc


def _selectable(entry: dict, index: int, location: str) -> SelectableAtom:
    where = f"{location}.selectable[{index}]"
    kind = _enum(_field(entry, "kind", where), SelectableKind, where, "kind")
    missions = tuple(
        _enum(raw, CognitiveMission, where, "missions") for raw in _refs(entry, "missions")
    )
    presentations = tuple(
        _enum(raw, Presentation, where, "presentations")
        for raw in _refs(entry, "presentations")
    )
    try:
        return SelectableAtom(
            atom_id=_field(entry, "id", where),
            kind=kind,
            text=_field(entry, "text", where),
            sources=_refs(entry, "sources"),
            missions=missions,
            presentations=presentations,
            evidence=_refs(entry, "evidence"),
            tags=_refs(entry, "tags"),
            prereqs=_refs(entry, "requires"),
        )
    except ValueError as exc:
        raise PackageError(where, contract_message(exc)) from exc


def _evidence(entry: dict, index: int, location: str) -> EvidenceSpec:
    where = f"{location}.evidence[{index}]"
    try:
        return EvidenceSpec(
            evidence_id=_field(entry, "id", where),
            description=_field(entry, "description", where),
            atom_refs=_refs(entry, "atoms"),
            required=bool(entry.get("required", True)),
        )
    except ValueError as exc:
        raise PackageError(where, contract_message(exc)) from exc


def _slot(entry: dict, index: int, location: str) -> GenerableSlot:
    where = f"{location}.slots[{index}]"
    try:
        return GenerableSlot(
            slot_id=_field(entry, "id", where),
            purpose=_field(entry, "purpose", where),
            allowed_atom_refs=_refs(entry, "atoms"),
            forbidden_claims=_refs(entry, "forbidden"),
            max_items=int(entry.get("max_items", 1)),
        )
    except ValueError as exc:
        raise PackageError(where, contract_message(exc)) from exc


def _missing(entry: dict, index: int, location: str) -> MissingData:
    where = f"{location}.missing[{index}]"
    affects = tuple(
        _enum(raw, MissingDataArea, where, "affects") for raw in _refs(entry, "affects")
    )
    try:
        return MissingData(
            data_id=_field(entry, "id", where),
            description=_field(entry, "description", where),
            affects=affects,
            blocking=bool(entry.get("blocking", False)),
            fallback=_field(entry, "fallback", where),
        )
    except ValueError as exc:
        raise PackageError(where, contract_message(exc)) from exc


def _objective(
    node: dict,
    node_id: str,
    schema_version: int,
    must_preserve: tuple[MustPreserveAtom, ...],
    location: str,
) -> LearningObjective:
    """The node's ``LearningObjective``, with its cross links read off the atoms.

    ``required_fact_refs`` and ``required_safety_refs`` are **not** authored: they are
    derived from ``must_preserve``, because a hand-kept second list of the same atom ids is
    a list that goes stale the first time an atom is renamed.
    """
    mission = _enum(_field(node, "mission", location), CognitiveMission, location, "mission")
    raw_functions = _refs(node, "source_functions")
    if not raw_functions:
        allowed = ", ".join(member.value for member in SourceFunction)
        raise PackageError(f"{location}.source_functions", f"needs at least one of: {allowed}")
    functions = frozenset(
        _enum(raw, SourceFunction, location, "source_functions") for raw in raw_functions
    )
    return LearningObjective(
        objective_id=node_id,
        objective_version=schema_version,
        mission=mission,
        source_functions=functions,
        required_fact_refs=tuple(
            atom.atom_id
            for atom in must_preserve
            if atom.critical and atom.kind is not MustPreserveKind.SAFETY_RULE
        ),
        required_safety_refs=tuple(
            atom.atom_id for atom in must_preserve if atom.kind is MustPreserveKind.SAFETY_RULE
        ),
    )


def build_pack(
    *,
    node: dict,
    node_id: str,
    pack_doc: dict,
    source_refs: tuple[SourceRef, ...],
    schema_version: int,
    location: str,
) -> NodeKnowledgePack:
    """Expand one authored pack document into the validated contract.

    Everything mechanical is filled in here -- the objective, both provenance digests, the
    cross links and the ``ready`` status -- so the file on disk holds teaching material and
    nothing else. The contract then applies its own cross-reference rules on construction,
    which is what makes a hand-written package hard to get subtly wrong: an evidence spec
    pointing at an atom that is not there fails right here, not three steps later against a
    database.
    """
    must_preserve = tuple(
        _must_preserve(entry, index, location)
        for index, entry in enumerate(pack_doc.get("must_preserve") or ())
    )
    selectable = tuple(
        _selectable(entry, index, location)
        for index, entry in enumerate(pack_doc.get("selectable") or ())
    )
    evidence = tuple(
        _evidence(entry, index, location)
        for index, entry in enumerate(pack_doc.get("evidence") or ())
    )
    slots = tuple(
        _slot(entry, index, location) for index, entry in enumerate(pack_doc.get("slots") or ())
    )
    missing = tuple(
        _missing(entry, index, location)
        for index, entry in enumerate(pack_doc.get("missing") or ())
    )
    objective = _objective(node, node_id, schema_version, must_preserve, location)

    # The semantic digest covers the authored material only. Provenance is excluded on
    # purpose: it carries this digest, and re-serialising a package must not move it.
    semantic = canonical_digest(pack_doc)
    bundle = canonical_digest(sorted(ref.excerpt_hash for ref in source_refs))

    try:
        return NodeKnowledgePack(
            status=PackStatus.READY,
            node_id=node_id,
            title=_field(node, "title", location),
            objective=objective,
            source_refs=source_refs,
            evidence_specs=evidence,
            must_preserve=must_preserve,
            selectable=selectable,
            generable_slots=slots,
            missing_data=missing,
            provenance=PackProvenance(
                node_id=node_id,
                schema_version=schema_version,
                source_bundle_hash=bundle,
                semantic_hash=semantic,
                generator=HANDWRITTEN_GENERATOR,
            ),
        )
    except ValueError as exc:
        raise PackageError(location, contract_message(exc)) from exc
