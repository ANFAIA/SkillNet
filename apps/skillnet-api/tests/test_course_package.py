"""Reading a course package: what it accepts, and what it must refuse.

No database and no key: a package is validated on the host while it is being written, so
these run under ``pytest -m "not integration"`` like the rest of the pure-contract tests.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.knowledge_pack.contracts import MustPreserveKind, PackStatus
from src.knowledge_pack.markdown import render_markdown
from src.services.course_package import PACKAGE_FORMAT, read_package
from src.services.course_package.export import _pack_document, slugify
from src.services.course_package.format import HANDWRITTEN_GENERATOR
from src.services.course_package.read import review_notes

COURSE = {
    "format": PACKAGE_FORMAT,
    "package": "ticketing-basics",
    "title": "Ticketing basics",
    "sources": [
        {"ref": "src.manual", "document": "operations-manual", "locator": "pp. 12-14"}
    ],
    "nodes": [
        {
            "id": "selling",
            "title": "Selling at the desk",
            "summary": "Take a walk-up sale from request to printed ticket.",
            "criticality": "critical",
            "mission": "decide",
            "source_functions": ["procedure"],
        },
        {
            "id": "refunds",
            "title": "Refunds",
            "summary": "When a refund is allowed.",
            "mission": "decide",
            "source_functions": ["contrast"],
            "requires": ["selling"],
        },
    ],
}

SELLING_PACK = {
    "must_preserve": [
        {
            "id": "a.confirm",
            "kind": "procedure_step",
            "text": "Confirm the session before taking payment.",
            "sources": ["src.manual"],
            "critical": True,
            "evidence": ["e.sale"],
        },
        {
            "id": "a.no-reprint",
            "kind": "safety_rule",
            "text": "A printed ticket is never reprinted without voiding the first.",
            "sources": ["src.manual"],
        },
    ],
    "selectable": [
        {
            "id": "s.declined",
            "kind": "common_error",
            "text": "The card is declined after the ticket printed.",
            "sources": ["src.manual"],
            "missions": ["decide"],
        }
    ],
    "evidence": [
        {
            "id": "e.sale",
            "description": "The learner completes a sale in the right order.",
            "atoms": ["a.confirm"],
        }
    ],
}

REFUNDS_PACK = {
    "must_preserve": [
        {
            "id": "a.window",
            "kind": "constraint",
            "text": "Refunds are only possible before the session starts.",
            "sources": ["src.manual"],
            "evidence": ["e.decide"],
        }
    ],
    "evidence": [
        {
            "id": "e.decide",
            "description": "The learner decides whether a refund applies.",
            "atoms": ["a.window"],
        }
    ],
}


def _write(root: Path, course: dict, packs: dict[str, dict]) -> Path:
    directory = root / "package"
    (directory / "packs").mkdir(parents=True, exist_ok=True)
    (directory / "course.json").write_text(json.dumps(course), encoding="utf-8")
    for slug, pack in packs.items():
        (directory / "packs" / f"{slug}.json").write_text(json.dumps(pack), encoding="utf-8")
    return directory


def _valid(root: Path) -> Path:
    return _write(root, COURSE, {"selling": SELLING_PACK, "refunds": REFUNDS_PACK})


def test_reads_a_valid_package(tmp_path: Path) -> None:
    package = read_package(_valid(tmp_path))

    assert package.ok, [error.args[0] for error in package.errors]
    assert package.slug == "ticketing-basics"
    assert [node.slug for node in package.nodes] == ["selling", "refunds"]
    assert package.nodes[1].requires == ("selling",)


def test_mechanical_fields_are_derived_not_authored(tmp_path: Path) -> None:
    """The author writes teaching material; ids, digests and cross links are filled in."""
    package = read_package(_valid(tmp_path))
    pack = package.nodes[0].pack

    assert pack.status is PackStatus.READY
    assert pack.provenance.generator == HANDWRITTEN_GENERATOR
    # A generated pack carries ``node_id=str(node.id)``; a hand-written one must not invent
    # a second convention for the same field.
    assert pack.objective.objective_id == str(package.nodes[0].uuid)
    # Read off must_preserve, so renaming an atom cannot leave a stale second list behind.
    assert pack.objective.required_fact_refs == ("a.confirm",)
    assert pack.objective.required_safety_refs == ("a.no-reprint",)
    assert len(pack.provenance.semantic_hash) == 64
    assert pack.source_refs[0].excerpt_hash != pack.provenance.source_bundle_hash


def test_identifiers_are_the_same_on_every_machine(tmp_path: Path) -> None:
    """Installing the same package twice, anywhere, must land on the same ids.

    ``node_renders.cache_key`` is keyed partly on ``node_id``: ids minted per install would
    throw away every pre-generated screen the moment a package moved between machines.
    """
    first = read_package(_valid(tmp_path / "a"))
    second = read_package(_valid(tmp_path / "b"))

    assert first.uuid == second.uuid
    assert [node.uuid for node in first.nodes] == [node.uuid for node in second.nodes]
    assert first.nodes[0].uuid != first.nodes[1].uuid


def test_markdown_projects_from_the_contract(tmp_path: Path) -> None:
    """The dossier is derived, which is why the package does not carry a copy of it."""
    package = read_package(_valid(tmp_path))
    markdown = render_markdown(package.nodes[0].pack)

    assert "Confirm the session before taking payment." in markdown
    assert render_markdown(package.nodes[0].pack) == markdown


def test_reports_every_fault_in_one_pass(tmp_path: Path) -> None:
    course = json.loads(json.dumps(COURSE))
    course["nodes"][0]["mission"] = "memorize"
    course["nodes"][1]["requires"] = ["does-not-exist"]
    refunds = json.loads(json.dumps(REFUNDS_PACK))
    refunds["evidence"][0]["atoms"] = ["a.typo"]
    directory = _write(tmp_path, course, {"selling": SELLING_PACK, "refunds": refunds})
    (directory / "packs" / "orphan.json").write_text("{}", encoding="utf-8")

    package = read_package(directory)
    locations = [error.location for error in package.errors]

    assert "packs/selling.json.mission" in locations
    assert "packs/refunds.json" in locations
    # A broken pack must not hide a broken graph: fixing one would then uncover the other.
    assert "course.json.nodes[refunds].requires" in locations
    assert "packs/orphan.json" in locations


def test_invalid_mission_names_the_valid_values(tmp_path: Path) -> None:
    """An authoring error says what to write instead, without reading the source."""
    course = json.loads(json.dumps(COURSE))
    course["nodes"][0]["mission"] = "memorize"
    directory = _write(tmp_path, course, {"selling": SELLING_PACK, "refunds": REFUNDS_PACK})

    package = read_package(directory)
    message = next(error.message for error in package.errors if "mission" in error.location)

    assert "decide" in message and "explain" in message


def test_rejects_an_unknown_package_format(tmp_path: Path) -> None:
    course = json.loads(json.dumps(COURSE))
    course["format"] = "course-package/99"
    directory = _write(tmp_path, course, {"selling": SELLING_PACK, "refunds": REFUNDS_PACK})

    package = read_package(directory)

    assert not package.ok
    assert package.errors[0].location == "course.json"


def test_atom_without_a_source_is_refused(tmp_path: Path) -> None:
    """Grounding is the point of a pack, so an uncited claim cannot reach the database."""
    pack = json.loads(json.dumps(SELLING_PACK))
    pack["must_preserve"][0]["sources"] = []
    directory = _write(tmp_path, COURSE, {"selling": pack, "refunds": REFUNDS_PACK})

    package = read_package(directory)

    assert not package.ok
    assert any("must cite at least one source" in error.message for error in package.errors)


def test_safety_rules_are_not_listed_as_facts(tmp_path: Path) -> None:
    pack = json.loads(json.dumps(SELLING_PACK))
    pack["must_preserve"][1]["critical"] = True
    directory = _write(tmp_path, COURSE, {"selling": pack, "refunds": REFUNDS_PACK})

    objective = read_package(directory).nodes[0].pack.objective

    assert objective.required_safety_refs == ("a.no-reprint",)
    assert "a.no-reprint" not in objective.required_fact_refs
    kinds = {atom.atom_id: atom.kind for atom in read_package(directory).nodes[0].pack.must_preserve}
    assert kinds["a.no-reprint"] is MustPreserveKind.SAFETY_RULE


def test_export_then_read_is_lossless(tmp_path: Path) -> None:
    """A pack that leaves the database and comes back must be the same pack.

    ``pack_hash`` is the identity the runtime and the auditor match against, so a round trip
    that changed it would silently install a course other than the one that was exported.
    """
    original = read_package(_valid(tmp_path)).nodes[0].pack
    document = _pack_document(original.canonical_payload())

    course = json.loads(json.dumps(COURSE))
    course["uuid"] = "1d5f0f1e-9a3c-4e21-8f77-2b6c9d40aa11"
    course["nodes"][0]["uuid"] = original.node_id
    directory = _write(tmp_path / "round-trip", course, {"selling": document})
    (directory / "packs" / "refunds.json").write_text(json.dumps(REFUNDS_PACK), encoding="utf-8")

    package = read_package(directory)

    assert package.ok, [error.args[0] for error in package.errors]
    assert package.nodes[0].pack.canonical_hash == original.canonical_hash
    # Provenance travels verbatim rather than being minted again on the way through.
    assert package.nodes[0].pack.provenance == original.provenance


def test_pinned_identifiers_win_over_derived_ones(tmp_path: Path) -> None:
    """An exported course keeps the ids it already has, or a re-install is a new course."""
    pinned = "9c1f7b2a-3d84-4c05-9e6b-70a1c2d3e4f5"
    course = json.loads(json.dumps(COURSE))
    course["uuid"] = "1d5f0f1e-9a3c-4e21-8f77-2b6c9d40aa11"
    course["nodes"][0]["uuid"] = pinned
    directory = _write(tmp_path, course, {"selling": SELLING_PACK, "refunds": REFUNDS_PACK})

    package = read_package(directory)

    assert str(package.uuid) == course["uuid"]
    assert str(package.nodes[0].uuid) == pinned
    assert package.nodes[0].pack.objective.objective_id == pinned
    # The node that pins nothing still derives, so the two styles coexist in one package.
    assert package.nodes[1].uuid == read_package(_valid(tmp_path / "b")).nodes[1].uuid


def test_a_node_may_cite_its_own_sources(tmp_path: Path) -> None:
    """Export writes per-node sources; flattening them would cross-cite the neighbours."""
    pack = json.loads(json.dumps(SELLING_PACK))
    pack["sources"] = [{"ref": "src.local", "document": "till-guide", "locator": "p. 3"}]
    for atom in pack["must_preserve"]:
        atom["sources"] = ["src.local"]
    pack["selectable"][0]["sources"] = ["src.local"]
    directory = _write(tmp_path, COURSE, {"selling": pack, "refunds": REFUNDS_PACK})

    package = read_package(directory)

    assert package.ok, [error.args[0] for error in package.errors]
    assert [ref.ref_id for ref in package.nodes[0].pack.source_refs] == ["src.local"]
    assert [ref.ref_id for ref in package.nodes[1].pack.source_refs] == ["src.manual"]


def test_slugify_makes_a_filesystem_safe_node_id() -> None:
    assert slugify("Cómo aprende tu cerebro") == "como-aprende-tu-cerebro"
    assert slugify("¿Qué es el cashless?") == "que-es-el-cashless"
    assert slugify("!!!") == "node"


def test_navigation_mode_travels_with_the_package(tmp_path: Path) -> None:
    """A course exported as sequential must not come back as free.

    Same class of setting as ``tutor_style`` and ``image_policy``: a decision a person
    made about this course, not state the system derived. Dropping it installs a course
    that silently stops asking to be walked in order — and the loss is invisible, because
    ``free`` is a perfectly valid mode and nothing looks broken.
    """
    course = json.loads(json.dumps(COURSE))
    course["navigation_mode"] = "sequential"
    directory = _write(tmp_path, course, {"selling": SELLING_PACK, "refunds": REFUNDS_PACK})

    assert read_package(directory).navigation_mode == "sequential"
    # Absent — every package exported before migration 0034 — means the column default,
    # which is what those courses had. Not a reason to force anything.
    assert read_package(_valid(tmp_path / "b")).navigation_mode is None

def test_image_policy_travels_with_the_package(tmp_path: Path) -> None:
    """An exported course must not lose how it treats the images from its own document.

    ``image_source_policy`` is a per-course setting like ``tutor_style``: a package that
    dropped it would install a course that silently treats its screenshots differently
    from the course it was exported from.
    """
    course = json.loads(json.dumps(COURSE))
    course["image_policy"] = "keep_original"
    directory = _write(tmp_path, course, {"selling": SELLING_PACK, "refunds": REFUNDS_PACK})

    assert read_package(directory).image_policy == "keep_original"
    # Absent means "leave whatever the target already has", not "force the default".
    assert read_package(_valid(tmp_path / "b")).image_policy is None


def test_review_notes_flag_claims_about_product_behaviour(tmp_path: Path) -> None:
    """The one class of claim a package author cannot check by rereading their own file.

    A claim about what the product does or does not do is about software, while the source
    is a document — so it has to be pointed at a sentence, by a person. The first
    hand-authored package rested a whole course thesis on one of these, and the rewrite
    moved it out of the atoms and into an evidence gate, where it survived a review pass.
    """
    pack = json.loads(json.dumps(SELLING_PACK))
    pack["selectable"][0]["text"] = "El sistema no avisa de nada cuando esto pasa."
    pack["evidence"][0]["description"] = "Clasificar en lo que el sistema bloquea o pasa en silencio."
    directory = _write(tmp_path, COURSE, {"selling": pack, "refunds": REFUNDS_PACK})

    notes = review_notes(directory)
    phrases = [phrase.lower() for _, phrase in notes]

    assert any("no avisa" in p for p in phrases)
    # The evidence gate is checked too: that is where the claim hid the second time.
    assert any("pasa en silencio" in p for p in phrases)
    assert all(":" in location for location, _ in notes)


def test_review_notes_are_not_errors(tmp_path: Path) -> None:
    """A package full of behaviour claims still lints clean: a reviewer decides, not lint."""
    pack = json.loads(json.dumps(SELLING_PACK))
    pack["selectable"][0]["text"] = "El sistema no comprueba el importe."
    directory = _write(tmp_path, COURSE, {"selling": pack, "refunds": REFUNDS_PACK})

    assert read_package(directory).ok
    assert review_notes(directory)


def test_review_notes_stay_quiet_on_ordinary_material(tmp_path: Path) -> None:
    assert review_notes(_valid(tmp_path)) == []
