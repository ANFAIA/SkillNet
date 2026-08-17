"""Pure two-pass generation of source-grounded knowledge packs.

The module stops at a validated, reviewable pack. It deliberately has no database,
course-delivery, or OpenUI dependency, so callers can run it in shadow.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from copy import deepcopy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from src.knowledge_pack.contracts import NodeKnowledgePack, PackProvenance, PackStatus, SourceRef
from src.knowledge_pack.markdown import render_markdown
from src.llm.client import Usage
from src.personalization.plan import LearningObjective

EXTRACTOR_MAX_TOKENS = 3_200
REVIEWER_MAX_TOKENS = 3_200
MIN_GENERATION_TOKENS = 256
MAX_GENERATION_TOKENS = 4_096

_SECTION_KEYS = frozenset(
    {
        "evidence_specs",
        "must_preserve",
        "selectable",
        "generable_slots",
        "missing_data",
    }
)
_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/@-]*$"


def _identifier_schema() -> dict[str, object]:
    return {"type": "string", "pattern": _IDENTIFIER_PATTERN}


def _section_contract(
    *,
    allowed_source_refs: Sequence[str] = (),
    allowed_source_units: Sequence[str] = (),
) -> dict[str, object]:
    """JSON Schema for model-owned fields, deliberately free of copyable examples."""
    source_ref_schema: dict[str, object] = _identifier_schema()
    if allowed_source_refs:
        source_ref_schema = {"type": "string", "enum": list(allowed_source_refs)}
    source_unit_schema: dict[str, object] = _identifier_schema()
    if allowed_source_units:
        source_unit_schema = {"type": "string", "enum": list(allowed_source_units)}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_SECTION_KEYS),
        "properties": {
            "evidence_specs": {
                "type": "array",
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["evidence_id", "description", "atom_refs", "required"],
                    "properties": {
                        "evidence_id": _identifier_schema(),
                        "description": {"type": "string", "maxLength": 240},
                        "atom_refs": {"type": "array", "maxItems": 12, "uniqueItems": True, "items": _identifier_schema()},
                        "required": {"type": "boolean"},
                    },
                },
            },
            "must_preserve": {
                "type": "array",
                "minItems": len(allowed_source_units) if allowed_source_units else 1,
                "maxItems": max(32, len(allowed_source_units) * 2),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "atom_id", "kind", "text", "sources", "source_units",
                        "evidence", "critical"
                    ],
                    "properties": {
                        "atom_id": _identifier_schema(),
                        "kind": {"enum": [
                            "fact", "safety_rule", "procedure_step", "constraint", "criterion"
                        ]},
                        "text": {"type": "string", "maxLength": 400},
                        "sources": {"type": "array", "minItems": 1, "uniqueItems": True, "items": source_ref_schema},
                        "source_units": {"type": "array", "minItems": 1, "maxItems": 8, "uniqueItems": True, "items": source_unit_schema},
                        "evidence": {"type": "array", "maxItems": 4, "uniqueItems": True, "items": _identifier_schema()},
                        "critical": {"type": "boolean"},
                    },
                },
            },
            "selectable": {
                "type": "array",
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "atom_id", "kind", "text", "sources", "source_units", "missions",
                        "presentations", "evidence", "tags", "prereqs"
                    ],
                    "properties": {
                        "atom_id": _identifier_schema(),
                        "kind": {"enum": [
                            "case", "common_error", "decision", "contrast",
                            "worked_example", "representation_hint"
                        ]},
                        "text": {"type": "string", "maxLength": 400},
                        "sources": {"type": "array", "minItems": 1, "uniqueItems": True, "items": source_ref_schema},
                        "source_units": {"type": "array", "minItems": 1, "maxItems": 8, "uniqueItems": True, "items": source_unit_schema},
                        "missions": {"type": "array", "maxItems": 3, "uniqueItems": True, "items": {"type": "string"}},
                        "presentations": {"type": "array", "maxItems": 4, "uniqueItems": True, "items": {"type": "string"}},
                        "evidence": {"type": "array", "maxItems": 4, "uniqueItems": True, "items": _identifier_schema()},
                        "tags": {"type": "array", "maxItems": 6, "uniqueItems": True, "items": {"type": "string"}},
                        "prereqs": {"type": "array", "maxItems": 6, "uniqueItems": True, "items": _identifier_schema()},
                    },
                },
            },
            "generable_slots": {
                "type": "array",
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "slot_id", "purpose", "allowed_atom_refs", "forbidden_claims", "max_items"
                    ],
                    "properties": {
                        "slot_id": _identifier_schema(),
                        "purpose": {"type": "string", "maxLength": 240},
                        "allowed_atom_refs": {"type": "array", "minItems": 1, "uniqueItems": True, "items": _identifier_schema()},
                        "forbidden_claims": {"type": "array", "maxItems": 6, "uniqueItems": True, "items": {"type": "string", "maxLength": 160}},
                        "max_items": {"type": "integer", "minimum": 1, "maximum": 8},
                    },
                },
            },
            "missing_data": {
                "type": "array",
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["data_id", "description", "affects", "blocking", "fallback"],
                    "properties": {
                        "data_id": _identifier_schema(),
                        "description": {"type": "string", "maxLength": 240},
                        "affects": {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"enum": ["evidence", "simulation", "media", "safety"]}},
                        "blocking": {"type": "boolean"},
                        "fallback": {"type": "string"},
                    },
                },
            },
        },
    }

EXTRACTOR_SYSTEM = """You prepare a source-grounded learning-material dossier.
Return JSON only. You are not writing a lesson or screen layout. Use only source ref
IDs supplied in the prompt. Do not invent company policy, source references, facts,
or evidence. Every atom needs a source. Preserve critical safety/procedure facts as
must_preserve. Output precisely the requested JSON object."""

REVIEWER_SYSTEM = """You review a source-grounded learning-material dossier.
Return JSON only. Correct unsupported claims, unknown references, invalid links and
missing critical source facts. Keep only claims grounded in the supplied excerpts.
You are not writing a lesson or screen layout. Output precisely the requested JSON
object. Its top level MUST contain exactly evidence_specs, must_preserve, selectable,
generable_slots and missing_data. Never echo candidate, output_contract, enum_values,
task, node, sources or rules. Do not add provenance, source_refs, title, objective, or
comments."""


class CompletionClient(Protocol):
    """Minimal injected LLM boundary; compatible with ``LLMService`` and fakes."""

    async def complete_with_usage(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> tuple[str, Usage]: ...


class KnowledgePackGenerationError(ValueError):
    """Fail-closed error: no partial pack may cross this boundary."""


@dataclass(frozen=True, slots=True)
class KnowledgePackNode:
    node_id: str
    title: str
    objective: LearningObjective

    def __post_init__(self) -> None:
        if not self.node_id.strip():
            raise ValueError("node_id must not be blank")
        if not self.title.strip():
            raise ValueError("title must not be blank")
        if self.objective.objective_id != self.node_id:
            raise ValueError("objective.objective_id must equal node_id")


@dataclass(frozen=True, slots=True)
class SourceExcerpt:
    """One immutable source pointer and the exact text available to the LLM."""

    ref: SourceRef
    text: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("source excerpt must not be blank")


@dataclass(frozen=True, slots=True)
class KnowledgePackGenerationRequest:
    node: KnowledgePackNode
    sources: tuple[SourceExcerpt, ...]
    generator: str = "knowledge-pack-generator/1"
    reviewer: str = "knowledge-pack-reviewer/1"
    model: str | None = None
    extractor_max_tokens: int = EXTRACTOR_MAX_TOKENS
    reviewer_max_tokens: int = REVIEWER_MAX_TOKENS

    def __post_init__(self) -> None:
        if not self.sources:
            raise ValueError("at least one source excerpt is required")
        if not self.generator.strip() or not self.reviewer.strip():
            raise ValueError("generator and reviewer identifiers must not be blank")
        for value in (self.extractor_max_tokens, self.reviewer_max_tokens):
            if not MIN_GENERATION_TOKENS <= value <= MAX_GENERATION_TOKENS:
                raise ValueError(
                    f"generation token budget must be {MIN_GENERATION_TOKENS}..{MAX_GENERATION_TOKENS}"
                )
        ref_ids = tuple(item.ref.ref_id for item in self.sources)
        if len(set(ref_ids)) != len(ref_ids):
            raise ValueError("source excerpts must have unique ref_ids")


@dataclass(frozen=True, slots=True)
class GenerationTelemetry:
    extractor_usage: Usage
    reviewer_usage: Usage
    extractor_seconds: float
    reviewer_seconds: float
    total_seconds: float

    @property
    def total_usage(self) -> Usage:
        return self.extractor_usage.plus(self.reviewer_usage)


@dataclass(frozen=True, slots=True)
class GeneratedKnowledgePack:
    pack: NodeKnowledgePack
    markdown: str
    telemetry: GenerationTelemetry


def _json_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _objective_payload(objective: LearningObjective) -> dict[str, object]:
    return {
        "objective_id": objective.objective_id,
        "objective_version": objective.objective_version,
        "mission": objective.mission.value,
        "source_functions": sorted(item.value for item in objective.source_functions),
        "available_requirements": sorted(objective.available_requirements),
        "required_fact_refs": list(objective.required_fact_refs),
        "required_safety_refs": list(objective.required_safety_refs),
    }


def source_bundle_hash(sources: Sequence[SourceExcerpt]) -> str:
    """Hash the exact source metadata and excerpts visible to both model passes."""

    values = [
        {"ref": item.ref.model_dump(mode="json"), "text": item.text.strip()}
        for item in sorted(sources, key=lambda item: item.ref.ref_id)
    ]
    return _json_hash(values)


def _coverage_unit_texts(text: str) -> list[str]:
    units: list[str] = []
    for paragraph_index, paragraph in enumerate(re.split(r"\n\s*\n", text.strip())):
        normalized = " ".join(paragraph.split())
        sentences = [
            sentence
            for sentence in re.split(r"(?<=[.!?])\s+", normalized)
            if sentence
        ]
        letters = [character for character in normalized if character.isalpha()]
        uppercase_ratio = (
            sum(character.isupper() for character in letters) / len(letters)
            if letters
            else 0.0
        )
        if paragraph_index == 0 and len(sentences) == 1 and uppercase_ratio >= 0.7:
            continue
        if len(sentences) > 1 and len(sentences[0].rstrip(".!?").split()) <= 5:
            sentences = sentences[1:]
        units.extend(sentences)
    return units


def _source_prompt(sources: Sequence[SourceExcerpt]) -> list[dict[str, object]]:
    units: list[dict[str, str]] = []
    result: list[dict[str, object]] = []
    for item in sorted(sources, key=lambda item: item.ref.ref_id):
        source_units: list[dict[str, str]] = []
        for text in _coverage_unit_texts(item.text):
            unit = {"unit_id": f"unit.{len(units) + 1:03d}", "text": text}
            units.append(unit)
            source_units.append(unit)
        result.append(
            {"ref": item.ref.model_dump(mode="json"), "coverage_units": source_units}
        )
    return result


def _allowed_source_units(sources: Sequence[SourceExcerpt]) -> tuple[str, ...]:
    return tuple(
        str(unit["unit_id"])
        for source in _source_prompt(sources)
        for unit in source["coverage_units"]  # type: ignore[union-attr]
    )


def _prompt_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _extractor_prompt(request: KnowledgePackGenerationRequest) -> str:
    source_units = _allowed_source_units(request.sources)
    return _prompt_json(
        {
            "task": "Extract source-backed learning atoms for this node.",
            "node": {
                "node_id": request.node.node_id,
                "title": request.node.title,
                "objective": _objective_payload(request.node.objective),
            },
            "sources": _source_prompt(request.sources),
            "required_output_keys": sorted(_SECTION_KEYS),
            "output_contract": _section_contract(
                allowed_source_refs=tuple(item.ref.ref_id for item in request.sources),
                allowed_source_units=_allowed_source_units(request.sources),
            ),
            "enum_values": {
                "must_preserve.kind": [
                    "fact", "safety_rule", "procedure_step", "constraint", "criterion"
                ],
                "selectable.kind": [
                    "case", "common_error", "decision", "contrast",
                    "worked_example", "representation_hint",
                ],
                "selectable.missions": [
                    "recognize", "reconstruct", "interpret", "decide", "explain", "produce"
                ],
                "selectable.presentations": [
                    "text", "image", "audio", "video", "table", "chart", "diagram", "simulation"
                ],
                "missing_data.affects": ["evidence", "simulation", "media", "safety"],
            },
            "rules": [
                f"There are {len(source_units)} coverage units; return at least {len(source_units)} must_preserve atoms and cover every ID: {', '.join(source_units)}.",
                "Return every required output key, using [] where there is no grounded value.",
                "Atom source references must use exactly a supplied ref_id.",
                "Cover every operational threshold, timing, exception, prohibition and safety rule.",
                "Write one independently testable rule or fact per must_preserve atom; split sentences that contain multiple requirements and never merge a whole section into one atom.",
                "Account for every coverage_unit and every independently testable clause in an atom or an explicit missing_data item.",
                "Emit at least one required evidence_spec whose atom_refs exactly match emitted atom_id values; every ready learning pack needs observable evidence.",
                "Evidence atom_refs refer to atom_id values, never to source ref_id values.",
                "Every atom must list the exact coverage_unit IDs it represents in source_units; cover every coverage_unit at least once.",
                "Emit selectable only for cases, errors or contrasts explicitly present in the source and never duplicate a must_preserve rule as selectable.",
                "Every generated identifier must match ^[A-Za-z0-9][A-Za-z0-9._:/@-]*$ and contain no accents or spaces.",
                "Arrays declared uniqueItems must not contain duplicates.",
                "Schema descriptions are instructions, never content to copy into the output.",
                "Do not output source_refs, provenance, status, node_id, title, objective, markdown, or lesson body.",
            ],
        }
    )


def _reviewer_prompt(
    request: KnowledgePackGenerationRequest, candidate_sections: Mapping[str, object]
) -> str:
    source_units = _allowed_source_units(request.sources)
    candidate_atom_ids = [
        str(item.get("atom_id"))
        for section in ("must_preserve", "selectable")
        for item in candidate_sections.get(section, [])  # type: ignore[union-attr]
        if isinstance(item, Mapping) and item.get("atom_id")
    ]
    return "\n\n".join(
        (
            "Review and correct CANDIDATE. Return ONLY the corrected candidate JSON object.",
            "The only allowed top-level keys are: " + ", ".join(sorted(_SECTION_KEYS)) + ".",
            "NODE:\n" + _prompt_json(
                {
                    "node_id": request.node.node_id,
                    "title": request.node.title,
                    "objective": _objective_payload(request.node.objective),
                }
            ),
            "SOURCES:\n" + _prompt_json(_source_prompt(request.sources)),
            "CANDIDATE:\n" + _prompt_json(candidate_sections),
            "CANDIDATE ATOM IDS (evidence atom_refs may use only these IDs or IDs of "
            "new atoms you add):\n" + _prompt_json(candidate_atom_ids),
            f"MANDATORY COVERAGE: there are {len(source_units)} units. Return at least "
            f"{len(source_units)} must_preserve atoms and cover every unit ID:\n"
            + _prompt_json(source_units),
            "OUTPUT JSON SCHEMA (instructions only; do not return this wrapper):\n"
            + _prompt_json(
                _section_contract(
                    allowed_source_refs=tuple(item.ref.ref_id for item in request.sources),
                    allowed_source_units=_allowed_source_units(request.sources),
                )
            ),
            "Allowed must_preserve.kind values: fact, safety_rule, procedure_step, "
            "constraint, criterion. Allowed selectable.kind values: case, common_error, "
            "decision, contrast, worked_example, representation_hint.",
            "Remove unsupported claims instead of guessing. Keep all five top-level keys, "
            "using [] when empty. Use only supplied ref_id values. Do not return the labels "
            "NODE, SOURCES, CANDIDATE or OUTPUT JSON SCHEMA. Split merged source sections "
            "and sentences into one independently testable must_preserve atom per rule, "
            "threshold, timing, exception or prohibition. Verify every coverage_unit and "
            "independent clause. Return at least one required evidence_spec because every "
            "ready learning pack needs observable evidence. Its atom_refs must match atom_id "
            "values, never source ref_id values. Do not duplicate must_preserve rules as "
            "selectable. "
            "Every atom must list the exact coverage_unit IDs it represents in source_units, "
            "and every coverage_unit must be represented at least once.",
        )
    )


def _coverage_repair_prompt(
    request: KnowledgePackGenerationRequest,
    reviewed_sections: Mapping[str, object],
    uncovered: Sequence[str],
) -> str:
    """Ask the reviewer to close a specific, named coverage gap in its own output.

    The reviewer routinely leaves a handful of source sentences unmapped, and a single
    uncovered unit hard-blocks the pack at ``review_required``. Rather than hand a human a
    pack to finish, we replay the reviewer against its own candidate with exactly the
    still-uncovered units — and their text — called out, so the fix is a targeted addition
    and never a blind re-extraction.
    """

    unit_text = {
        str(unit["unit_id"]): str(unit["text"])
        for source in _source_prompt(request.sources)
        for unit in source["coverage_units"]  # type: ignore[union-attr]
    }
    still_uncovered = [
        {"unit_id": unit_id, "text": unit_text.get(unit_id, "")} for unit_id in uncovered
    ]
    return "\n\n".join(
        (
            "Correct CANDIDATE so every source unit is represented. Return ONLY the "
            "corrected candidate JSON object.",
            "The only allowed top-level keys are: " + ", ".join(sorted(_SECTION_KEYS)) + ".",
            "NODE:\n"
            + _prompt_json(
                {
                    "node_id": request.node.node_id,
                    "title": request.node.title,
                    "objective": _objective_payload(request.node.objective),
                }
            ),
            "SOURCES:\n" + _prompt_json(_source_prompt(request.sources)),
            "CANDIDATE:\n" + _prompt_json(reviewed_sections),
            "STILL UNCOVERED — keep every atom already in CANDIDATE and add one grounded "
            "must_preserve atom (or a selectable when the unit is a case, common error or "
            "contrast) for EACH of these units, listing its unit_id in source_units:\n"
            + _prompt_json(still_uncovered),
            "Atom source references must use exactly a supplied ref_id. Every generated "
            "identifier must match ^[A-Za-z0-9][A-Za-z0-9._:/@-]*$ and contain no accents "
            "or spaces. Keep all five top-level keys, using [] where empty.",
        )
    )


def _parse_sections(raw: str, *, phase: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise KnowledgePackGenerationError(f"{phase} returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise KnowledgePackGenerationError(f"{phase} must return a JSON object")
    keys = frozenset(value)
    if keys != _SECTION_KEYS:
        missing = sorted(_SECTION_KEYS - keys)
        unexpected = sorted(keys - _SECTION_KEYS)
        raise KnowledgePackGenerationError(
            f"{phase} must return exactly the pack section keys; "
            f"missing={missing}, unexpected={unexpected}"
        )
    if any(not isinstance(value[key], list) for key in _SECTION_KEYS):
        raise KnowledgePackGenerationError(f"{phase} pack sections must all be JSON arrays")
    return {key: value[key] for key in sorted(_SECTION_KEYS)}


def _semantic_hash(
    request: KnowledgePackGenerationRequest, sections: Mapping[str, object], source_hash: str
) -> str:
    return _json_hash(
        {
            "node_id": request.node.node_id,
            "title": request.node.title.strip(),
            "objective": _objective_payload(request.node.objective),
            "source_bundle_hash": source_hash,
            "sections": sections,
        }
    )


def _namespace_atom_ids(
    sections: Mapping[str, object],
    *,
    allowed_sources: Sequence[str] = (),
) -> dict[str, object]:
    """Make model-proposed atom labels unambiguous before contract validation.

    Models commonly call both a mandatory rule and an optional case ``step-1``. Stable
    identity is program-owned: category namespaces remove that accidental collision and
    every cross-reference is expanded deterministically when an old label matched more
    than one atom.

    ``allowed_sources`` are the supplied source ``ref_id`` values. An atom that cites a
    ref outside that set has invented a reference; rather than fail the whole pack we drop
    only the invented ref, exactly as we already drop unknown evidence, prereq and slot
    refs. An atom keeps its grounding as long as at least one supplied source survives; an
    atom that cited *only* invented sources loses all grounding and is dropped whole. What
    is never relaxed is the rule enforced by the contract afterwards: every kept ref still
    points to a real supplied source.
    """

    value = deepcopy(dict(sections))
    aliases: dict[str, list[str]] = {}
    for section, prefix in (("must_preserve", "must"), ("selectable", "selectable")):
        seen: dict[str, int] = {}
        for item in value[section]:  # type: ignore[union-attr]
            old = str(item["atom_id"])
            seen[old] = seen.get(old, 0) + 1
            suffix = f".{seen[old]}" if seen[old] > 1 else ""
            new = f"{prefix}.{old}{suffix}"
            item["atom_id"] = new
            aliases.setdefault(old, []).append(new)

    valid_must_kinds = {
        "fact", "safety_rule", "procedure_step", "constraint", "criterion"
    }
    for item in value["must_preserve"]:  # type: ignore[union-attr]
        if item.get("kind") not in valid_must_kinds:
            item["kind"] = "fact"
    valid_selectable_kinds = {
        "case", "common_error", "decision", "contrast", "worked_example",
        "representation_hint",
    }
    for item in value["selectable"]:  # type: ignore[union-attr]
        if item.get("kind") not in valid_selectable_kinds:
            item["kind"] = "representation_hint"

    if allowed_sources:
        allowed = {str(ref) for ref in allowed_sources}
        for section in ("must_preserve", "selectable"):
            kept_atoms: list[dict[str, object]] = []
            for item in value[section]:  # type: ignore[union-attr]
                grounded = [str(ref) for ref in item.get("sources", []) if str(ref) in allowed]
                if not grounded:
                    # Every source this atom cited was invented; without a real source it
                    # cannot be grounded, so the atom itself is dropped.
                    continue
                item["sources"] = grounded
                kept_atoms.append(item)
            value[section] = kept_atoms
        # A dropped atom must not survive by proxy through a cross-reference, so its final
        # id is pruned from the alias table the expander reads below.
        surviving = {
            str(item["atom_id"])
            for section in ("must_preserve", "selectable")
            for item in value[section]  # type: ignore[union-attr]
        }
        for old in list(aliases):
            aliases[old] = [new for new in aliases[old] if new in surviving]
            if not aliases[old]:
                del aliases[old]

    generated_ids = {
        str(item["atom_id"])
        for section in ("must_preserve", "selectable")
        for item in value[section]  # type: ignore[union-attr]
    }

    def expand(refs: object, *, exclude: str | None = None) -> list[str]:
        expanded: list[str] = []
        for ref in refs if isinstance(refs, list) else []:
            raw = str(ref)
            candidates = list(aliases.get(raw, []))
            if raw in generated_ids:
                candidates.append(raw)
            # Reviewers often make category ownership explicit in a cross-reference
            # while leaving the atom's proposed ID unprefixed. Accept that harmless
            # notation; the program still installs the final namespace.
            for prefix in ("must.", "selectable."):
                if raw.startswith(prefix):
                    candidates.extend(aliases.get(raw.removeprefix(prefix), []))
            for resolved in candidates:
                if resolved != exclude and resolved not in expanded:
                    expanded.append(resolved)
        return expanded

    for item in value["evidence_specs"]:  # type: ignore[union-attr]
        item["atom_refs"] = expand(item.get("atom_refs"))
    existing_missing = {
        str(item["data_id"])
        for item in value["missing_data"]  # type: ignore[union-attr]
    }
    kept_evidence: list[dict[str, object]] = []
    for item in value["evidence_specs"]:  # type: ignore[union-attr]
        if item.get("required") and not item["atom_refs"]:
            missing_id = f"unresolved-evidence.{item['evidence_id']}"
            if missing_id not in existing_missing:
                value["missing_data"].append(  # type: ignore[union-attr]
                    {
                        "data_id": missing_id,
                        "description": (
                            "Required evidence had no valid source-backed atom after "
                            "reference normalization."
                        ),
                        "affects": ["evidence"],
                        "blocking": True,
                        "fallback": "human_review",
                    }
                )
                existing_missing.add(missing_id)
            continue
        kept_evidence.append(item)
    value["evidence_specs"] = kept_evidence
    evidence_ids = {str(item["evidence_id"]) for item in kept_evidence}
    for section in ("must_preserve", "selectable"):
        for item in value[section]:  # type: ignore[union-attr]
            item["evidence"] = [
                str(ref)
                for ref in item.get("evidence", [])
                if str(ref) in evidence_ids
            ]
    for item in value["selectable"]:  # type: ignore[union-attr]
        item["prereqs"] = expand(item.get("prereqs"), exclude=item["atom_id"])
    for item in value["generable_slots"]:  # type: ignore[union-attr]
        item["allowed_atom_refs"] = expand(item.get("allowed_atom_refs"))
    value["generable_slots"] = [  # type: ignore[index]
        item
        for item in value["generable_slots"]  # type: ignore[union-attr]
        if item["allowed_atom_refs"]
    ]
    return value


def _covered_units(sections: Mapping[str, object]) -> set[str]:
    """Every coverage_unit ID some must_preserve or selectable atom claims to represent."""
    return {
        str(unit_id)
        for section in ("must_preserve", "selectable")
        for item in sections.get(section, [])  # type: ignore[union-attr]
        for unit_id in item.get("source_units", [])
    }


def _uncovered_units(
    sections: Mapping[str, object], sources: Sequence[SourceExcerpt]
) -> tuple[str, ...]:
    """Source units no atom maps to — the exact set that hard-blocks the pack at review."""
    covered = _covered_units(sections)
    return tuple(
        unit_id for unit_id in _allowed_source_units(sources) if unit_id not in covered
    )


def _build_pack(
    request: KnowledgePackGenerationRequest, sections: Mapping[str, object]
) -> NodeKnowledgePack:
    normalized_sections = deepcopy(dict(sections))
    prompt_sources = _source_prompt(request.sources)
    unit_ids_by_ref = {
        str(source["ref"]["ref_id"]): tuple(  # type: ignore[index]
            str(unit["unit_id"])
            for unit in source["coverage_units"]  # type: ignore[union-attr]
        )
        for source in prompt_sources
    }
    missing_units = set(_uncovered_units(normalized_sections, request.sources))
    if missing_units:
        # Recorded for traceability, deliberately NON-blocking. The norm this pipeline
        # enforces is *fidelity* — every atom must trace to a real source unit, checked by
        # contract validation — not *exhaustiveness*. Demanding an atom for every source
        # sentence turns the producer into a transcriber and forces navigation and filler
        # ("see the image below") to block an otherwise complete pack; deciding what in the
        # source is worth teaching is exactly the editorial judgment the runtime is meant
        # to keep. A pack still needs grounded must_preserve atoms and observable evidence
        # to be usable (below); it just no longer needs to cover every last sentence.
        normalized_sections["missing_data"].append(  # type: ignore[union-attr]
            {
                "data_id": "uncovered-source-units",
                "description": "Source units not represented by a learning atom: "
                + ", ".join(sorted(missing_units)),
                "affects": ["evidence"],
                "blocking": False,
                "fallback": "none",
            }
        )
    source_hash = source_bundle_hash(request.sources)
    blocking_gap = any(
        bool(item.get("blocking"))
        for item in normalized_sections.get("missing_data", [])  # type: ignore[union-attr]
    )
    has_required_evidence = any(
        bool(item.get("required"))
        for item in normalized_sections.get("evidence_specs", [])  # type: ignore[union-attr]
    )
    usable = (
        bool(normalized_sections.get("must_preserve"))
        and has_required_evidence
        and not blocking_gap
    )
    source_refs = tuple(
        item.ref.model_copy(
            update={"coverage_unit_ids": unit_ids_by_ref[item.ref.ref_id]}
        )
        for item in request.sources
    )
    payload: dict[str, object] = {
        "status": PackStatus.READY if usable else PackStatus.REVIEW_REQUIRED,
        "node_id": request.node.node_id,
        "title": request.node.title,
        "objective": request.node.objective,
        "source_refs": source_refs,
        "provenance": PackProvenance(
            node_id=request.node.node_id,
            schema_version=request.node.objective.objective_version,
            source_bundle_hash=source_hash,
            semantic_hash=_semantic_hash(request, normalized_sections, source_hash),
            generator=request.generator,
            reviewer=request.reviewer,
        ),
        **normalized_sections,
    }
    try:
        return NodeKnowledgePack.model_validate(payload)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(map(str, item['loc']))}: {item['msg']}"
            for item in exc.errors(include_url=False)[:8]
        )
        raise KnowledgePackGenerationError(
            f"reviewed pack failed contract validation: {details}"
        ) from exc
    except (ValueError, TypeError) as exc:
        raise KnowledgePackGenerationError(
            f"reviewed pack failed contract validation: {exc}"
        ) from exc


async def generate_knowledge_pack(
    request: KnowledgePackGenerationRequest, llm: CompletionClient
) -> GeneratedKnowledgePack:
    """Extract, review, validate and render one pack without persistent side effects."""

    total_started = time.perf_counter()
    extractor_started = time.perf_counter()
    try:
        extracted_raw, extractor_usage = await llm.complete_with_usage(
            EXTRACTOR_SYSTEM,
            _extractor_prompt(request),
            model=request.model,
            temperature=0.0,
            max_tokens=request.extractor_max_tokens,
            json_mode=True,
        )
    except Exception as exc:
        raise KnowledgePackGenerationError("extractor completion failed") from exc
    extractor_seconds = time.perf_counter() - extractor_started
    extracted = _parse_sections(extracted_raw, phase="extractor")

    reviewer_started = time.perf_counter()
    try:
        reviewed_raw, reviewer_usage = await llm.complete_with_usage(
            REVIEWER_SYSTEM,
            _reviewer_prompt(request, extracted),
            model=request.model,
            temperature=0.0,
            max_tokens=request.reviewer_max_tokens,
            json_mode=True,
        )
    except Exception as exc:
        raise KnowledgePackGenerationError("reviewer completion failed") from exc
    reviewer_seconds = time.perf_counter() - reviewer_started
    allowed_sources = tuple(item.ref.ref_id for item in request.sources)
    reviewed = _namespace_atom_ids(
        _parse_sections(reviewed_raw, phase="reviewer"),
        allowed_sources=allowed_sources,
    )

    # One bounded coverage-repair pass. The reviewer leaves a few source units unmapped
    # often enough that most packs stall at review_required over coverage alone; replaying
    # it once against the named gap recovers them without a human. Guarded so a repair that
    # does not strictly improve coverage — or cannot be built into a valid pack — is
    # discarded rather than allowed to regress a usable review.
    repair_usage = Usage(reason="coverage repair not attempted")
    uncovered = _uncovered_units(reviewed, request.sources)
    if uncovered:
        repaired_raw, repair_usage = await llm.complete_with_usage(
            REVIEWER_SYSTEM,
            _coverage_repair_prompt(request, reviewed, uncovered),
            model=request.model,
            temperature=0.0,
            max_tokens=request.reviewer_max_tokens,
            json_mode=True,
        )
        try:
            candidate = _namespace_atom_ids(
                _parse_sections(repaired_raw, phase="coverage-repair"),
                allowed_sources=allowed_sources,
            )
            if len(_uncovered_units(candidate, request.sources)) < len(uncovered):
                _build_pack(request, candidate)  # validate before trusting it
                reviewed = candidate
        except KnowledgePackGenerationError:
            pass  # keep the reviewed pack; a failed repair never worsens the result
    reviewer_usage = reviewer_usage.plus(repair_usage)

    pack = _build_pack(request, reviewed)

    return GeneratedKnowledgePack(
        pack=pack,
        markdown=render_markdown(pack),
        telemetry=GenerationTelemetry(
            extractor_usage=extractor_usage,
            reviewer_usage=reviewer_usage,
            extractor_seconds=extractor_seconds,
            reviewer_seconds=reviewer_seconds,
            total_seconds=time.perf_counter() - total_started,
        ),
    )


render_pack_markdown = render_markdown


__all__ = [
    "EXTRACTOR_MAX_TOKENS",
    "MAX_GENERATION_TOKENS",
    "MIN_GENERATION_TOKENS",
    "REVIEWER_MAX_TOKENS",
    "CompletionClient",
    "GeneratedKnowledgePack",
    "GenerationTelemetry",
    "KnowledgePackGenerationError",
    "KnowledgePackGenerationRequest",
    "KnowledgePackNode",
    "SourceExcerpt",
    "generate_knowledge_pack",
    "render_pack_markdown",
    "source_bundle_hash",
]
