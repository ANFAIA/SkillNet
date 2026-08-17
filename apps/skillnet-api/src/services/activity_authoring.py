"""Typed, server-owned authoring for generated Didact activities.

The OpenUI model is never asked to invent an activity UUID.  A small structured
authoring step chooses one of the planner's allowed Didact ids and drafts content; this
module validates it, moves assessment/simulation secrets to server-only storage and
materialises a stable :class:`ActivityDefinition` before the UI prompt is built.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.models.activity_definition import ActivityDefinition, ActivityFamily
from src.personalization.didact_catalog import (
    AuthoringStrategy,
    HostPort,
    load_didact_catalog,
)
from src.schemas.activity import ActivityDefinitionCreate, assert_public_payload
from src.services.activity_authoring_validators import (
    authoring_definition_contract,
    validate_component_definition,
    validate_evaluation_definition,
)
from src.services.activity_definitions import ActivityDefinitionService

AUTHORING_CONTRACT_VERSION = "activity-authoring/1"

# These keys may be returned anywhere in a draft.  They are recursively moved out of
# the public tree before Pydantic constructs ActivityDefinitionCreate.  Exact answers
# therefore cannot accidentally become part of the OpenUI prompt or API projection.
_PRIVATE_KEYS = frozenset(
    {
        "answer",
        "answers",
        "answer_key",
        "correct",
        "correct_answer",
        "correct_order",
        "solution",
        "solutions",
        "rubric",
        "evaluation",
        "evaluation_config",
        "expected",
        "expected_answer",
        "expected_answers",
        "accepted_answer",
        "accepted_answers",
        "correct_categories",
        "correct_matches",
        "correct_option_ids",
        "correct_value",
        "absolute_tolerance",
        "relative_tolerance",
        "simulation",
        "tests",
    }
)


class ActivityAuthoringDraft(BaseModel):
    """The only JSON shape accepted from the activity-authoring model."""

    model_config = ConfigDict(extra="forbid")

    component_id: str = Field(pattern=r"^didact\.[a-z0-9][a-z0-9.-]*$")
    definition: dict[str, Any]
    # Server-owned grounding refs (atom_ids + evidence_ids) replace whatever the model
    # cites, so this bound sizes the KNOWLEDGE PACK, not model output. A rich node's pack
    # legitimately carries 40+ atoms; the old cap of 32 rejected the whole activity for
    # those nodes and dropped them to a static Table, so it is widened to cover real packs.
    source_refs: list[str] = Field(default_factory=list, max_length=256)

    @field_validator("source_refs")
    @classmethod
    def unique_refs(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(ref.strip() for ref in value if ref.strip()))

    @model_validator(mode="after")
    def non_empty_definition(self) -> ActivityAuthoringDraft:
        if not self.definition:
            raise ValueError("definition must not be empty")
        return self


#: Prompt-echo keys a small model tends to copy back from the authoring *request* object.
#: They are never part of a Didact ``definition``; when the model flattens the contract it
#: mixes these wrappers in with the real definition fields, so they are stripped before the
#: definition is reconstructed. See ``_coerce_authoring_shape``.
_AUTHORING_WRAPPER_KEYS = frozenset(
    {
        "component_id",
        "selected_component_id",
        "candidate_component_ids",
        "definition",
        "definition_contract",
        "source_refs",
        "allowed_source_refs",
        "source",
        "title",
        "outcome",
    }
)


def _coerce_authoring_shape(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Fold predictable model drift back onto the ``{component_id, definition}`` contract.

    A small model at low temperature frequently (a) answers with ``selected_component_id``
    instead of ``component_id`` — the key it was *shown* in the request — and (b) inlines
    the ``definition_contract`` fields (``items``, ``gaps``, ``options``, ``pairs`` …) at the
    top level instead of nesting them under ``definition``, echoing the request wrapper keys
    (``title``, ``outcome``, ``source`` …) alongside them. Both were a dead ``ValidationError``
    that dropped the whole interactive activity and left the screen a static Table. Neither is
    a trust decision: the reconstructed definition is still validated against the component's
    real contract downstream, so a genuinely malformed draft is rejected exactly as before —
    only the recoverable shapes now survive.
    """

    normalized = dict(payload)
    if "component_id" not in normalized and isinstance(
        normalized.get("selected_component_id"), str
    ):
        normalized["component_id"] = normalized["selected_component_id"]
    definition = normalized.get("definition")
    if not isinstance(definition, dict) or not definition:
        rebuilt = {
            key: value
            for key, value in normalized.items()
            if key not in _AUTHORING_WRAPPER_KEYS
        }
        if rebuilt:
            normalized["definition"] = rebuilt
    return {
        key: value
        for key, value in normalized.items()
        if key in {"component_id", "definition", "source_refs"}
    }


def authoring_draft_with_server_refs(
    payload: Mapping[str, Any],
    *,
    allowed_source_refs: Iterable[str],
) -> ActivityAuthoringDraft:
    """Replace model-authored citations with the exact server-owned grounding set.

    ``source_refs`` from the model is deliberately ignored before Pydantic sees it. This
    accepts harmless model drift such as objects or an empty list without ever trusting a
    model-selected citation. An empty server set cannot produce an evaluable activity.
    """

    refs = list(
        dict.fromkeys(
            str(ref).strip() for ref in allowed_source_refs if str(ref).strip()
        )
    )
    if not refs:
        raise ValueError("activity authoring requires server-owned source refs")
    normalized = _coerce_authoring_shape(payload)
    normalized["source_refs"] = refs
    return ActivityAuthoringDraft.model_validate(normalized)


class MaterializedActivity(BaseModel):
    """Safe state handed to the OpenUI generation step."""

    model_config = ConfigDict(extra="forbid")
    activity_id: uuid.UUID
    component_id: str
    public_definition: dict[str, Any]


def split_public_private(value: Any) -> tuple[Any, Any]:
    """Recursively split a model draft without trusting its chosen nesting."""

    if isinstance(value, Mapping):
        public: dict[str, Any] = {}
        private: dict[str, Any] = {}
        for raw_key, child in value.items():
            key = str(raw_key)
            if key.lower() in _PRIVATE_KEYS or key.lower().startswith("answer_key"):
                private[key] = child
                continue
            public_child, private_child = split_public_private(child)
            public[key] = public_child
            if private_child not in ({}, [], None):
                private[key] = private_child
        return public, private
    if isinstance(value, list):
        public_items: list[Any] = []
        private_items: list[Any] = []
        for index, child in enumerate(value):
            public_child, private_child = split_public_private(child)
            public_items.append(public_child)
            if private_child not in ({}, [], None):
                private_items.append({"index": index, "value": private_child})
        return public_items, private_items
    return value, None


def _family(required_ports: Iterable[HostPort]) -> ActivityFamily:
    ports = set(required_ports)
    if HostPort.EXECUTION in ports:
        return ActivityFamily.EXECUTION
    if HostPort.SIMULATION in ports:
        return ActivityFamily.SIMULATION
    if HostPort.ASSETS in ports or HostPort.MEDIA in ports:
        return ActivityFamily.MEDIA
    if HostPort.EVALUATION in ports:
        return ActivityFamily.ASSESSMENT
    return ActivityFamily.ARTIFACT


def _private_contract(
    private: dict[str, Any], required_ports: Iterable[HostPort]
) -> dict[str, Any]:
    """Normalise common answer spellings to the built-in evaluation port contract."""

    ports = set(required_ports)
    if HostPort.EVALUATION not in ports or "evaluation" in private:
        return private
    expected = None
    for key in ("correct_answer", "answer", "solution"):
        if key in private:
            expected = private[key]
            break
    if expected is None:
        return private
    mode = "set" if isinstance(expected, list) else "exact"
    return {**private, "evaluation": {"mode": mode, "expected": expected}}


def stable_definition_key(
    *, node_id: uuid.UUID, render_id: uuid.UUID, pack_hash: str, component_id: str
) -> str:
    """A bounded idempotency key tied to the exact render inputs."""

    canonical = ":".join((str(node_id), str(render_id), pack_hash or "raw", component_id))
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:32]
    return f"runtime:{node_id}:{digest}"


#: Keys whose string value is human-readable CONTENT the model must ground in the source
#: (as opposed to structural ids, modes and answer keys). Only these are compared against the
#: contract example, so reusing a structural id like ``item-1`` or a mode like ``assignments``
#: is never mistaken for un-substituted content.
_CONTENT_KEYS = frozenset(
    {
        "title",
        "question",
        "problem",
        "prompt",
        "content",
        "label",
        "before",
        "after",
        "instruction",
        "text",
    }
)
#: The answer-key subtree is structural/private and never compared for grounding.
_STRUCTURAL_SUBTREES = frozenset({"evaluation", "expected"})


def _content_texts(value: Any) -> list[str]:
    """Human-readable content leaves, keyed by ``_CONTENT_KEYS``; ids/modes/answers skipped."""

    out: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key) in _STRUCTURAL_SUBTREES:
                continue
            if str(key) in _CONTENT_KEYS and isinstance(child, str):
                text = child.strip()
                if text:
                    out.append(text)
            else:
                out.extend(_content_texts(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            out.extend(_content_texts(child))
    return out


def assert_grounded_activity_draft(draft: ActivityAuthoringDraft) -> None:
    """Runtime grounding gate: reject a draft that echoes the contract example placeholders.

    Kept OUT of ``validate_authoring_draft`` (which is pure shape/boundary validation, and is
    exercised with the raw contract example by the shell-contract tests) and called from the
    runtime authoring node instead, so a live draft that copied the example is declined to a
    grounded fallback while the structural contract itself stays a valid shape.
    """

    _reject_unsubstituted_example(draft.component_id, draft.definition)


def _reject_unsubstituted_example(component_id: str, definition: Mapping[str, Any]) -> None:
    """Reject a draft that copied the contract's example placeholders instead of grounding.

    The authoring contract ships example values ("Concepto A", "Ejemplo B", "término A",
    "Segundo paso"...) the model must REPLACE with real source content. A small model at low
    temperature sometimes echoes them verbatim, which passes every shape validator yet
    produces an activity of pure nonsense — exactly the "classify cases that make no sense for
    the topic" the owner reported. The example is server-owned, so any verbatim reuse of its
    content leaves is a reliable non-grounding signal: two or more distinct echoed leaves means
    the model did not author from the source, so authoring declines to a grounded fallback
    rather than serving invented items.
    """

    try:
        contract = authoring_definition_contract(component_id)
    except Exception:  # noqa: BLE001 - a missing contract is handled by shape validation
        return
    example_leaves = {text.casefold() for text in _content_texts(contract) if len(text) >= 4}
    if not example_leaves:
        return
    echoed = {
        text.casefold()
        for text in _content_texts(definition)
        if len(text) >= 4 and text.casefold() in example_leaves
    }
    if len(echoed) >= 2:
        raise ValueError(
            "activity content not grounded: contract example placeholders were not "
            f"substituted ({sorted(echoed)})"
        )


def validate_authoring_draft(
    draft: ActivityAuthoringDraft,
    *,
    allowed_component_ids: Iterable[str],
    allowed_source_refs: Iterable[str],
) -> tuple[dict[str, Any], dict[str, Any], list[str], ActivityFamily]:
    """Validate selection, grounding references and the public/private boundary."""

    allowed = frozenset(allowed_component_ids)
    if draft.component_id not in allowed:
        raise ValueError(f"component_id {draft.component_id!r} was not shortlisted")
    component = load_didact_catalog().by_type_id.get(draft.component_id)
    if component is None:
        raise ValueError(f"unknown Didact component {draft.component_id!r}")
    if component.authoring_strategy is not AuthoringStrategy.SERVER_ACTIVITY:
        raise ValueError(
            f"component {draft.component_id!r} does not support server activity authoring"
        )
    permitted_refs = frozenset(allowed_source_refs)
    if not permitted_refs:
        raise ValueError("rich activity authoring requires grounded source refs")
    if not draft.source_refs:
        raise ValueError("rich activity draft must cite at least one allowed source ref")
    unknown_refs = sorted(set(draft.source_refs) - permitted_refs)
    if unknown_refs:
        raise ValueError(f"unknown source_refs: {unknown_refs}")

    public, private = split_public_private(draft.definition)
    assert isinstance(public, dict) and isinstance(private, dict)
    assert_public_payload(public)
    validate_component_definition(draft.component_id, public)
    if HostPort.ASSETS in component.required_ports:
        asset_ref = public.get("assetRef")
        if not isinstance(asset_ref, str) or asset_ref not in permitted_refs:
            raise ValueError("assetRef must copy an allowed opaque SkillNet asset ref")
        if asset_ref not in draft.source_refs:
            raise ValueError("source_refs must include the selected opaque asset ref")
    normalized_private = _private_contract(private, component.required_ports)
    validate_evaluation_definition(draft.component_id, public, normalized_private)
    required_ports = [port.value for port in component.required_ports]
    return (
        public,
        normalized_private,
        required_ports,
        _family(component.required_ports),
    )


async def materialize_authored_activity(
    service: ActivityDefinitionService,
    *,
    org_id: uuid.UUID,
    course_id: uuid.UUID,
    node_id: uuid.UUID,
    render_id: uuid.UUID,
    knowledge_pack_id: uuid.UUID | None,
    pack_hash: str,
    draft: ActivityAuthoringDraft,
    allowed_component_ids: Iterable[str],
    allowed_source_refs: Iterable[str],
) -> MaterializedActivity:
    public, private, required_ports, family = validate_authoring_draft(
        draft,
        allowed_component_ids=allowed_component_ids,
        allowed_source_refs=allowed_source_refs,
    )
    row: ActivityDefinition = await service.create(
        org_id=org_id,
        body=ActivityDefinitionCreate(
            course_id=course_id,
            node_id=node_id,
            source_render_id=render_id,
            source_knowledge_pack_id=knowledge_pack_id,
            definition_key=stable_definition_key(
                node_id=node_id,
                render_id=render_id,
                pack_hash=pack_hash,
                component_id=draft.component_id,
            ),
            component_id=draft.component_id,
            family=family,
            public_definition=public,
            private_definition=private,
            required_ports=required_ports,
            provenance={
                "contract_version": AUTHORING_CONTRACT_VERSION,
                "pack_hash": pack_hash or None,
                "source_refs": draft.source_refs,
            },
        ),
    )
    return MaterializedActivity(
        activity_id=row.id,
        component_id=row.component_id,
        public_definition=dict(row.public_definition or {}),
    )


def build_activity_authoring_prompts(
    *,
    candidates: Iterable[str],
    title: str,
    outcome: str | None,
    source_context: str,
    allowed_source_refs: Iterable[str],
) -> tuple[str, str]:
    """Bounded prompts: no UUID and no existing private definition crosses this call."""

    candidate_list = list(dict.fromkeys(candidates))
    if not candidate_list:
        raise ValueError("activity authoring requires one candidate")
    # One structured call gets one exact contract. Asking a small model to choose between
    # eight unrelated schemas and then infer the selected shape caused valid candidates
    # such as DataExplorer to be rejected on every attempt.
    selected_candidate = candidate_list[0]
    definition_contract = authoring_definition_contract(selected_candidate)
    refs = list(dict.fromkeys(allowed_source_refs))
    system = (
        "Disenas UNA actividad educativa Didact anclada en la fuente. Devuelve SOLO un "
        "objeto JSON con EXACTAMENTE tres claves de nivel superior y ninguna mas: "
        '{"component_id": "<el candidato indicado>", "definition": { ... }, '
        '"source_refs": ["..."]}. '
        "El contenido del contrato (items, gaps, options, pairs, categories, prompt, "
        "evaluation, etc.) va DENTRO de definition, nunca al nivel superior. NO repitas "
        "las claves de la peticion (title, outcome, selected_component_id, source, "
        "definition_contract): son solo tu entrada. "
        "Copia exactamente la estructura del contrato de definition y sustituye solo sus "
        "valores de ejemplo por contenido de la fuente. No inventes UUID ni activity_id. "
        "Incluye respuestas, rubricas, transiciones o tests dentro de definition: el "
        "servidor los separara antes de servir la actividad. No uses hechos ausentes de la "
        "fuente: cada item, par, categoria u opcion debe corresponder a un hecho concreto "
        "del dossier, no a conocimiento general del tema. Cita al menos un source_ref "
        "permitido. Si no hay datos suficientes, no inventes series, cifras, afirmaciones "
        "ni URLs: devuelve definition vacia ({}) para que el servidor decline."
    )
    user = json.dumps(
        {
            "title": title,
            "outcome": outcome,
            "candidate_component_ids": [selected_candidate],
            "selected_component_id": selected_candidate,
            "definition_contract": definition_contract,
            "allowed_source_refs": refs,
            "source": source_context,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return system, user


__all__ = [
    "AUTHORING_CONTRACT_VERSION",
    "ActivityAuthoringDraft",
    "assert_grounded_activity_draft",
    "authoring_draft_with_server_refs",
    "MaterializedActivity",
    "build_activity_authoring_prompts",
    "materialize_authored_activity",
    "split_public_private",
    "stable_definition_key",
    "validate_authoring_draft",
]
