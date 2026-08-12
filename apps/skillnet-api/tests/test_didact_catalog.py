from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.personalization.didact_catalog import (
    SNAPSHOT_PATH,
    AvailabilityStatus,
    DidactCatalogError,
    EmissionStatus,
    HostPort,
    load_didact_catalog,
)


def test_catalog_covers_all_34_available_didact_types() -> None:
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    catalog = load_didact_catalog()

    expected = {item["id"] for item in snapshot["available_types"]}
    assert len(expected) == 34
    assert len(catalog.components) == 34
    assert set(catalog.by_type_id) == expected


def test_every_type_retains_its_neutral_manifest_identity() -> None:
    catalog = load_didact_catalog()

    for component in catalog.components:
        assert component.type_id.startswith("didact.")
        assert component.manifest_id.startswith("didact.")
        assert component.export_name
        assert component.name
        assert component.description
        assert component.maturity != "unknown"
        assert component.component_version != "unknown"


def test_total_catalogue_is_separate_from_openui_emission_readiness() -> None:
    catalog = load_didact_catalog()

    assert len(catalog.components) == 34
    assert {item.type_id for item in catalog.emittable} == {
        "didact.flashcard",
        "didact.hint-reveal",
        "didact.glossary-term",
        "didact.timeline-steps",
        "didact.worked-example",
        "didact.rubric",
        "didact.data-explorer",
        "didact.self-explanation-prompt",
        "didact.concept-map",
        "didact.drawing-response",
        "didact.equation-workbench",
        "didact.evidence-annotation",
        "didact.measurement-lab",
    }
    assert {item.renderer_symbol for item in catalog.emittable} == {
        "Flashcard",
        "HintReveal",
        "DidactGlossary",
        "DidactTimeline",
        "DidactWorkedExample",
        "DidactActivity",
    }
    assert all(item.renderer_available for item in catalog.emittable)
    assert all(item.availability_status is AvailabilityStatus.READY for item in catalog.emittable)
    assert all(item.emission_status is EmissionStatus.ENABLED for item in catalog.emittable)


def test_unadapted_types_remain_installed_but_await_a_renderer() -> None:
    catalog = load_didact_catalog()
    unadapted = [item for item in catalog.components if not item.renderer_available]

    assert len(unadapted) == 21
    assert all(item.availability_status is AvailabilityStatus.BLOCKED for item in unadapted)
    assert all(item.emission_status is EmissionStatus.DISABLED for item in unadapted)


def test_required_ports_are_inferred_by_capability_family() -> None:
    by_export = {item.export_name: item for item in load_didact_catalog().components}

    assert HostPort.EVALUATION in by_export["SingleChoiceQuiz"].required_ports
    assert HostPort.EXECUTION in by_export["CodeExercise"].required_ports
    assert HostPort.EVALUATION in by_export["CodeExercise"].required_ports
    assert HostPort.SIMULATION in by_export["SimulationLab"].required_ports
    assert HostPort.ASSETS in by_export["InteractiveMedia"].required_ports
    assert HostPort.PROGRESS in by_export["ProgressIndicator"].required_ports
    assert {
        HostPort.PERSISTENCE,
        HostPort.SCHEDULER,
    }.issubset(by_export["RetrievalPracticeSession"].required_ports)
    assert HostPort.ASSETS not in by_export["SingleChoiceQuiz"].required_ports


def test_host_ports_change_readiness_not_the_complete_inventory() -> None:
    all_ports = frozenset(HostPort)
    without_ports = load_didact_catalog(available_ports=())
    with_ports = load_didact_catalog(available_ports=all_ports)

    assert tuple(with_ports.by_type_id) == tuple(without_ports.by_type_id)
    assert len(with_ports.components) == len(without_ports.components) == 34
    assert [item.renderer_available for item in with_ports.components] == [
        item.renderer_available for item in without_ports.components
    ]
    assert without_ports.by_type_id["didact.self-explanation-prompt"].renderer_available
    assert without_ports.by_type_id["didact.self-explanation-prompt"].missing_ports == (
        HostPort.PERSISTENCE,
    )
    assert not without_ports.by_type_id["didact.self-explanation-prompt"].llm_emittable
    assert with_ports.by_type_id["didact.self-explanation-prompt"].llm_emittable


def test_duplicate_type_in_snapshot_fails_closed(tmp_path: Path) -> None:
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    snapshot["available_types"].append(snapshot["available_types"][0])
    snapshot["counts"]["available_types"] += 1
    broken = tmp_path / "didact_snapshot.json"
    broken.write_text(json.dumps(snapshot), encoding="utf-8")

    with pytest.raises(DidactCatalogError, match="duplicate or invalid"):
        load_didact_catalog(broken)


def test_unknown_manifest_reference_fails_closed(tmp_path: Path) -> None:
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    snapshot["available_types"][0]["manifest_id"] = "didact.missing"
    broken = tmp_path / "didact_snapshot.json"
    broken.write_text(json.dumps(snapshot), encoding="utf-8")

    with pytest.raises(DidactCatalogError, match="unknown manifest"):
        load_didact_catalog(broken)
