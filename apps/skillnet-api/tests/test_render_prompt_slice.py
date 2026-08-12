"""Pure contracts for experimental closed component prompt scopes."""

from __future__ import annotations

from dataclasses import replace
import re

import pytest

from src.render.prompt import digest, load_artifact
from src.render.prompt_slice import (
    BASE_SCOPE_COMPONENTS,
    PROMPT_SLICE_SCHEMA,
    PromptSliceCatalogDrift,
    UnknownPromptComponent,
    build_prompt_slice,
    scoped_catalog_prompt,
    resolve_runtime_prompt,
)


def test_scope_keeps_shell_support_and_requested_components_in_catalogue_order() -> None:
    scope = build_prompt_slice(
        ["HintReveal", "Flashcard"], additional_required=["QuizItem"]
    )

    expected = tuple(
        name
        for name in load_artifact().component_names
        if name in {*BASE_SCOPE_COMPONENTS, "HintReveal", "Flashcard", "QuizItem"}
    )
    assert scope.included_component_ids == expected
    assert scope.requested_component_ids == ("HintReveal", "Flashcard")
    assert scope.additional_required_component_ids == ("QuizItem",)
    assert scope.root == "Stack"


def test_same_sets_produce_identical_bytes_digest_and_version() -> None:
    first = build_prompt_slice(
        ["HintReveal", "Flashcard", "HintReveal"],
        additional_required=["QuizItem", "QuizItem"],
    )
    second = build_prompt_slice(
        ["Flashcard", "HintReveal"], additional_required=["QuizItem"]
    )

    assert first.prompt == second.prompt
    assert first.canonical_signatures == second.canonical_signatures
    assert first.digest == second.digest
    assert first.version == second.version


def test_canonical_signatures_are_selected_verbatim_from_the_source_artifact() -> None:
    artifact = load_artifact()
    scope = build_prompt_slice(["Flashcard"], artifact=artifact)

    source_lines = set(artifact.canonical_catalog.splitlines())
    scoped_component_lines = [
        line
        for line in scope.canonical_signatures.splitlines()
        if "(" in line
    ]
    assert scoped_component_lines
    assert set(scoped_component_lines) <= source_lines
    assert any(line.startswith("Flashcard(") for line in scoped_component_lines)
    assert not any(line.startswith("HintReveal(") for line in scoped_component_lines)


def test_prompt_only_serializes_signatures_inside_the_scope() -> None:
    scope = build_prompt_slice(["Flashcard"])

    advertised = set(re.findall(r"(?m)^([A-Z][A-Za-z0-9]*)\(", scope.prompt))
    assert advertised == set(scope.included_component_ids)
    assert "HintReveal(" not in scope.prompt
    assert "catalogo general" in scope.prompt


def test_unknown_shortlist_and_required_ids_fail_loudly_and_together() -> None:
    with pytest.raises(UnknownPromptComponent) as excinfo:
        build_prompt_slice(["NotAComponent"], additional_required=["AlsoMissing"])

    assert excinfo.value.component_ids == ("AlsoMissing", "NotAComponent")
    assert "AlsoMissing" in str(excinfo.value)
    assert "NotAComponent" in str(excinfo.value)


def test_missing_base_component_is_catalogue_drift_not_a_caller_error() -> None:
    artifact = load_artifact()
    without_stack = replace(
        artifact,
        prompt_components=tuple(
            component
            for component in artifact.prompt_components
            if component["name"] != "Stack"
        ),
    )

    with pytest.raises(PromptSliceCatalogDrift, match="Stack"):
        build_prompt_slice(["Flashcard"], artifact=without_stack)


def test_missing_canonical_signature_is_detected() -> None:
    artifact = load_artifact()
    canonical = "\n".join(
        line
        for line in artifact.canonical_catalog.splitlines()
        if not line.startswith("Flashcard(")
    ) + "\n"

    with pytest.raises(PromptSliceCatalogDrift, match="Flashcard"):
        build_prompt_slice(
            ["Flashcard"], artifact=replace(artifact, canonical_catalog=canonical)
        )


def test_scope_hashes_and_versions_its_own_canonical_payload() -> None:
    scope = build_prompt_slice(["Flashcard"])

    assert scope.schema_version == PROMPT_SLICE_SCHEMA
    assert scope.digest == digest(scope.canonical_signatures)
    assert scope.prompt_sha256 == digest(scope.prompt)
    assert re.fullmatch(r"component-scope/1\+[0-9a-f]{12}", scope.version)
    assert scope.source_catalog_version == load_artifact().catalog_version


def test_empty_shortlist_still_yields_the_safe_screen_shell() -> None:
    scope = build_prompt_slice([])

    assert scope.included_component_ids == BASE_SCOPE_COMPONENTS
    assert scope.requested_component_ids == ()


def test_scoped_runtime_prompt_replaces_full_catalogue_and_leaky_examples() -> None:
    scope = build_prompt_slice(["Flashcard"], additional_required=["QuizItem"])
    prompt = scoped_catalog_prompt(scope)

    signatures = prompt.split("## Component Signatures", 1)[1].split(
        "## Hoisting & Streaming", 1
    )[0]
    assert "Flashcard(" in signatures
    assert "QuizItem(" in signatures
    assert "HintReveal(" not in signatures
    assert "StepSequence(" not in signatures
    assert "## Examples" not in prompt
    # Safety and answer-key rules from the generated artefact still survive.
    assert "SkillNet 13" in prompt


def test_runtime_flag_compares_full_catalogue_with_closed_shortlist() -> None:
    artifact = load_artifact()
    full, full_scope = resolve_runtime_prompt(
        ["Flashcard"], additional_required=["QuizItem"], enabled=False
    )
    narrowed, narrowed_scope = resolve_runtime_prompt(
        ["Flashcard"], additional_required=["QuizItem"], enabled=True
    )

    assert full == artifact.prompt
    assert full_scope is None
    assert narrowed_scope is not None
    assert len(narrowed) < len(full)
    assert "HintReveal(" in full
    assert "HintReveal(" not in narrowed
    assert narrowed_scope.version.startswith("component-scope/1+")
