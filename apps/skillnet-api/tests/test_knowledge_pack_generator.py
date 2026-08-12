"""Tests for the pure, two-pass source-grounded knowledge-pack generator."""

from __future__ import annotations

import json
from collections.abc import Sequence

import pytest

from src.knowledge_pack import generator as generator_module
from src.knowledge_pack.contracts import SourceRef
from src.knowledge_pack.generator import (
    EXTRACTOR_MAX_TOKENS,
    REVIEWER_MAX_TOKENS,
    KnowledgePackGenerationError,
    KnowledgePackGenerationRequest,
    KnowledgePackNode,
    SourceExcerpt,
    generate_knowledge_pack,
    source_bundle_hash,
)
from src.llm.client import Usage
from src.personalization.plan import CognitiveMission, LearningObjective, SourceFunction

HASH_A = "a" * 64


def _sections(*, atom_text: str = "El alérgeno se marca antes de enviar.") -> dict[str, object]:
    return {
        "evidence_specs": [
            {
                "evidence_id": "allergen-marked",
                "description": "Marca el alérgeno antes de enviar.",
                "atom_refs": ["safety.allergen"],
                "required": True,
            }
        ],
        "must_preserve": [
            {
                "atom_id": "safety.allergen",
                "kind": "safety_rule",
                "text": atom_text,
                "sources": ["manual.allergens"],
                "source_units": ["unit.001"],
                "evidence": ["allergen-marked"],
                "critical": True,
            }
        ],
        "selectable": [
            {
                "atom_id": "case.allergy",
                "kind": "case",
                "text": "Una comensal comunica una alergia al pedir.",
                "sources": ["manual.allergens"],
                "missions": ["decide"],
                "evidence": ["allergen-marked"],
                "tags": ["allergen"],
                "prereqs": ["safety.allergen"],
            }
        ],
        "generable_slots": [],
        "missing_data": [],
    }


def _request() -> KnowledgePackGenerationRequest:
    objective = LearningObjective(
        objective_id="take-order",
        objective_version=2,
        mission=CognitiveMission.DECIDE,
        source_functions=frozenset({SourceFunction.PROCEDURE}),
        required_safety_refs=("safety:allergen",),
    )
    source = SourceExcerpt(
        ref=SourceRef(
            ref_id="manual.allergens",
            document_id="manual-sala",
            heading_path=("Sala", "Alergenos"),
            locator="p. 34",
            excerpt_hash=HASH_A,
            source_revision="rev-4",
        ),
        text="Antes de enviar, el alérgeno se marca en la línea del plato.",
    )
    return KnowledgePackGenerationRequest(
        node=KnowledgePackNode("take-order", "Tomar una comanda", objective),
        sources=(source,),
        model="fixture/knowledge-pack",
    )


class FakeLLM:
    def __init__(self, responses: Sequence[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def complete_with_usage(self, system_prompt: str, user_prompt: str, **kwargs: object):
        self.calls.append({"system": system_prompt, "user": user_prompt, **kwargs})
        response = self.responses.pop(0)
        call_number = len(self.calls)
        return response, Usage(tokens_in=100 * call_number, tokens_out=10 * call_number)


async def test_generator_extracts_reviews_validates_and_renders_a_grounded_pack() -> None:
    raw = json.dumps(_sections())
    llm = FakeLLM((raw, raw))
    request = _request()

    result = await generate_knowledge_pack(request, llm)

    assert result.pack.node_id == "take-order"
    assert result.pack.provenance.source_bundle_hash == source_bundle_hash(request.sources)
    assert result.pack.provenance.generator == "knowledge-pack-generator/1"
    assert result.pack.provenance.reviewer == "knowledge-pack-reviewer/1"
    assert result.pack.must_preserve[0].sources == ("manual.allergens",)
    assert result.pack.provenance.semantic_hash != result.pack.canonical_hash
    assert result.markdown.startswith("---\nformat: node-knowledge-pack/1")
    assert result.telemetry.total_usage == Usage(tokens_in=300, tokens_out=30)
    assert result.telemetry.extractor_seconds >= 0
    assert result.telemetry.reviewer_seconds >= 0
    assert result.telemetry.total_seconds >= (
        result.telemetry.extractor_seconds + result.telemetry.reviewer_seconds
    )
    assert len(llm.calls) == 2
    assert llm.calls[0]["max_tokens"] == EXTRACTOR_MAX_TOKENS
    assert llm.calls[1]["max_tokens"] == REVIEWER_MAX_TOKENS
    assert llm.calls[0]["json_mode"] is True
    assert llm.calls[1]["json_mode"] is True


async def test_reviewer_can_correct_the_extractor_before_contract_validation() -> None:
    extracted = json.dumps(_sections(atom_text="El alérgeno se puede anotar después."))
    reviewed = json.dumps(_sections())
    llm = FakeLLM((extracted, reviewed))

    result = await generate_knowledge_pack(_request(), llm)

    assert result.pack.must_preserve[0].text == "El alérgeno se marca antes de enviar."
    reviewer_prompt = str(llm.calls[1]["user"])
    assert "CANDIDATE:" in reviewer_prompt
    assert "El alérgeno se puede anotar después." in reviewer_prompt
    assert "Return ONLY the corrected candidate JSON object" in reviewer_prompt


async def test_program_owns_atom_namespaces_and_rewrites_ambiguous_references() -> None:
    duplicated = _sections()
    duplicated["selectable"][0]["atom_id"] = "safety.allergen"  # type: ignore[index]
    duplicated["evidence_specs"][0]["atom_refs"] = ["safety.allergen"]  # type: ignore[index]
    llm = FakeLLM((json.dumps(duplicated), json.dumps(duplicated)))

    result = await generate_knowledge_pack(_request(), llm)

    assert result.pack.must_preserve[0].atom_id == "must.safety.allergen"
    assert result.pack.selectable[0].atom_id == "selectable.safety.allergen"
    assert result.pack.evidence_specs[0].atom_refs == (
        "must.safety.allergen",
        "selectable.safety.allergen",
    )


async def test_reviewer_may_prefix_a_reference_without_prefixing_the_atom_id() -> None:
    reviewed = _sections()
    reviewed["evidence_specs"][0]["atom_refs"] = ["must.safety.allergen"]  # type: ignore[index]
    llm = FakeLLM((json.dumps(reviewed), json.dumps(reviewed)))

    result = await generate_knowledge_pack(_request(), llm)

    assert result.pack.evidence_specs[0].atom_refs == ("must.safety.allergen",)
    assert result.pack.status.value == "ready"


async def test_unknown_optional_internal_references_are_not_persisted() -> None:
    reviewed = _sections()
    reviewed["evidence_specs"] = []
    reviewed["must_preserve"][0]["evidence"] = ["example.stable-id"]  # type: ignore[index]
    llm = FakeLLM((json.dumps(reviewed), json.dumps(reviewed)))

    result = await generate_knowledge_pack(_request(), llm)

    assert result.pack.must_preserve[0].evidence == ()


async def test_unresolved_required_evidence_becomes_an_explicit_blocking_gap() -> None:
    reviewed = _sections()
    reviewed["evidence_specs"][0]["atom_refs"] = ["example.stable-id"]  # type: ignore[index]
    llm = FakeLLM((json.dumps(reviewed), json.dumps(reviewed)))

    result = await generate_knowledge_pack(_request(), llm)

    assert result.pack.evidence_specs == ()
    assert result.pack.status.value == "review_required"
    assert result.pack.missing_data[0].data_id == (
        "unresolved-evidence.allergen-marked"
    )
    assert result.pack.missing_data[0].blocking is True


async def test_pack_without_invariants_requires_review_instead_of_claiming_ready() -> None:
    reviewed = _sections()
    reviewed["must_preserve"] = []
    reviewed["evidence_specs"] = []
    reviewed["selectable"] = []
    llm = FakeLLM((json.dumps(reviewed), json.dumps(reviewed)))

    result = await generate_knowledge_pack(_request(), llm)

    assert result.pack.status.value == "review_required"


async def test_generator_rejects_hallucinated_source_references_after_review() -> None:
    extracted = json.dumps(_sections())
    hallucinated = _sections()
    hallucinated["must_preserve"][0]["sources"] = ["invented.source"]  # type: ignore[index]
    llm = FakeLLM((extracted, json.dumps(hallucinated)))

    with pytest.raises(KnowledgePackGenerationError, match="failed contract validation"):
        await generate_knowledge_pack(_request(), llm)

    assert len(llm.calls) == 2


def test_prompts_constrain_atom_sources_to_the_supplied_reference_ids() -> None:
    request = _request()

    extractor = json.loads(generator_module._extractor_prompt(request))
    source_items = extractor["output_contract"]["properties"]["must_preserve"][
        "items"
    ]["properties"]["sources"]["items"]
    assert source_items == {
        "type": "string",
        "enum": [request.sources[0].ref.ref_id],
    }

    reviewer = generator_module._reviewer_prompt(request, _sections())
    assert f'"enum":["{request.sources[0].ref.ref_id}"]' in reviewer
    assert "CANDIDATE ATOM IDS" in reviewer
    assert "MANDATORY COVERAGE: there are 1 units" in reviewer
    assert '"safety.allergen"' in reviewer
    assert "atom_refs must match atom_id values, never source ref_id values" in reviewer


def test_source_prompt_exposes_numbered_sentence_coverage_units() -> None:
    request = _request()

    prompt = json.loads(generator_module._extractor_prompt(request))
    source = prompt["sources"][0]

    assert "excerpt" not in source
    assert source["coverage_units"] == [
        {"unit_id": "unit.001", "text": request.sources[0].text}
    ]


def test_coverage_units_exclude_document_and_short_section_headings() -> None:
    units = generator_module._coverage_unit_texts(
        "PROTOCOLO GENERAL (Version 1)\n\nFase inicial. Haz A. Haz B."
    )

    assert units == ["Haz A.", "Haz B."]


def test_output_schema_bounds_dossier_size() -> None:
    contract = generator_module._section_contract(
        allowed_source_refs=("manual.allergens",)
    )

    assert contract["properties"]["must_preserve"]["minItems"] == 1
    assert contract["properties"]["must_preserve"]["maxItems"] == 32
    assert contract["properties"]["selectable"]["maxItems"] == 6
    assert contract["properties"]["generable_slots"]["maxItems"] == 4


async def test_pack_without_required_evidence_cannot_be_ready() -> None:
    reviewed = _sections()
    reviewed["evidence_specs"] = []
    reviewed["must_preserve"][0]["evidence"] = []  # type: ignore[index]
    llm = FakeLLM((json.dumps(reviewed), json.dumps(reviewed)))

    result = await generate_knowledge_pack(_request(), llm)

    assert result.pack.status.value == "review_required"


async def test_unknown_atom_kind_degrades_to_factual_metadata() -> None:
    reviewed = _sections()
    reviewed["must_preserve"][0]["kind"] = "operational_rule"  # type: ignore[index]
    llm = FakeLLM((json.dumps(reviewed), json.dumps(reviewed)))

    result = await generate_knowledge_pack(_request(), llm)

    assert result.pack.must_preserve[0].kind.value == "fact"


async def test_uncovered_source_unit_creates_a_blocking_review_gap() -> None:
    request = _request()
    source = SourceExcerpt(
        ref=request.sources[0].ref,
        text=request.sources[0].text + " Otra regla queda sin representar.",
    )
    request = KnowledgePackGenerationRequest(
        node=request.node,
        sources=(source,),
    )
    sections = _sections()
    llm = FakeLLM((json.dumps(sections), json.dumps(sections)))

    result = await generate_knowledge_pack(request, llm)

    assert result.pack.status.value == "review_required"
    assert result.pack.source_refs[0].coverage_unit_ids == ("unit.001", "unit.002")
    assert result.pack.missing_data[0].data_id == "uncovered-source-units"


async def test_generator_fails_closed_for_invalid_extractor_json_without_calling_reviewer() -> None:
    llm = FakeLLM(("not json", json.dumps(_sections())))

    with pytest.raises(KnowledgePackGenerationError, match="extractor returned invalid JSON"):
        await generate_knowledge_pack(_request(), llm)

    assert len(llm.calls) == 1


def test_request_rejects_unbounded_token_budgets() -> None:
    request = _request()

    with pytest.raises(ValueError, match="token budget"):
        KnowledgePackGenerationRequest(
            node=request.node,
            sources=request.sources,
            extractor_max_tokens=4_097,
        )
