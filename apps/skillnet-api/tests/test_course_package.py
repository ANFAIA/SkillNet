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
from src.services.course_package.format import HANDWRITTEN_GENERATOR

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
