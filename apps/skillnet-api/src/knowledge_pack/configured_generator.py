"""Adapter from persisted course nodes to the pure two-pass pack generator.

This module is the only place where today's ``CourseNode``/shape vocabulary is
translated into the versioned knowledge-pack contract.  The generator itself stays
framework-free and the runner stays provider-free.
"""

from __future__ import annotations

import hashlib

from src.agents.runtime.shape import analyze_shape
from src.knowledge_pack.generator import (
    EXTRACTOR_MAX_TOKENS,
    REVIEWER_MAX_TOKENS,
    CompletionClient,
    KnowledgePackGenerationRequest,
    KnowledgePackNode,
    SourceExcerpt,
    generate_knowledge_pack,
)
from src.knowledge_pack.node_source import draft_is_usable, seed_node_source
from src.models import Course, CourseNode
from src.personalization.plan import CognitiveMission, LearningObjective, SourceFunction
from src.render.kit import ContentFunction
from src.services.node_knowledge_pack_service import (
    CompletedKnowledgePack,
    KnowledgePackSnapshot,
)

_SOURCE_FUNCTIONS = {
    ContentFunction.ENUMERAR: SourceFunction.ENUMERATE,
    ContentFunction.PROCEDIMENTAR: SourceFunction.PROCEDURE,
    ContentFunction.CUANTIFICAR: SourceFunction.QUANTIFY,
    ContentFunction.CONTRASTAR: SourceFunction.CONTRAST,
    ContentFunction.VARIAR: SourceFunction.VARY,
    ContentFunction.EXPLORAR: SourceFunction.EXPLORE,
    ContentFunction.LOCALIZAR: SourceFunction.LOCATE,
    ContentFunction.EVALUAR: SourceFunction.ASSESS,
}

_MISSION_FOR_SOURCE = {
    SourceFunction.PROCEDURE: CognitiveMission.RECONSTRUCT,
    SourceFunction.QUANTIFY: CognitiveMission.INTERPRET,
    SourceFunction.EXPLORE: CognitiveMission.INTERPRET,
    SourceFunction.VARY: CognitiveMission.DECIDE,
    SourceFunction.CONTRAST: CognitiveMission.RECOGNIZE,
    SourceFunction.ENUMERATE: CognitiveMission.RECOGNIZE,
    SourceFunction.LOCATE: CognitiveMission.RECOGNIZE,
    SourceFunction.ASSESS: CognitiveMission.DECIDE,
}

GENERATOR_VERSION = "knowledge-pack/v3"


class ConfiguredKnowledgePackGenerator:
    """Generate a complete persisted pack through the configured LLM boundary."""

    def __init__(
        self,
        llm: CompletionClient,
        *,
        extractor_max_tokens: int = EXTRACTOR_MAX_TOKENS,
        reviewer_max_tokens: int = REVIEWER_MAX_TOKENS,
    ) -> None:
        self.llm = llm
        self.extractor_max_tokens = extractor_max_tokens
        self.reviewer_max_tokens = reviewer_max_tokens

    async def draft_source(self, *, course: Course, node: CourseNode) -> str:
        """Write a short reference brief for one node when no uploaded excerpt exists."""

        from src.llm.prompts.source import (
            NODE_SOURCE_WRITER_SYSTEM,
            build_node_source_prompt,
        )
        from src.services.document_service import _strip_code_fence

        text, _usage = await self.llm.complete_with_usage(
            NODE_SOURCE_WRITER_SYSTEM,
            build_node_source_prompt(
                course_title=getattr(course, "title", "") or "",
                course_idea=(
                    getattr(course, "description", None)
                    or getattr(course, "outcome", None)
                    or ""
                ),
                node_title=node.title,
                summary=getattr(node, "summary", None) or "",
                outcome=getattr(node, "outcome", None) or "",
            ),
            temperature=0.6,
            max_tokens=1_200,
        )
        text = _strip_code_fence(text.strip())
        if draft_is_usable(text):
            return text
        return seed_node_source(course=course, node=node)

    async def generate(
        self,
        *,
        course: Course,
        node: CourseNode,
        source_context: str,
        snapshot: KnowledgePackSnapshot,
    ) -> CompletedKnowledgePack:
        del course  # Course identity is already frozen into ``snapshot``.
        objective = objective_for_node(
            node, source_context=source_context, schema_version=snapshot.schema_version
        )
        excerpt_hash = hashlib.sha256(source_context.encode("utf-8")).hexdigest()
        document_id = str(node.source_document_id or node.id)
        ref_id = f"source:{document_id}:node:{node.id}"

        # Imported here to keep the contract's SourceRef constructor in one adapter.
        from src.knowledge_pack.contracts import SourceRef

        source_ref = SourceRef(
            ref_id=ref_id,
            document_id=document_id,
            heading_path=tuple(node.source_headings or ()),
            locator=" > ".join(node.source_headings or ()) or node.title,
            excerpt_hash=excerpt_hash,
            source_revision=snapshot.source_fingerprint,
        )
        result = await generate_knowledge_pack(
            KnowledgePackGenerationRequest(
                node=KnowledgePackNode(
                    node_id=str(node.id), title=node.title, objective=objective
                ),
                sources=(SourceExcerpt(ref=source_ref, text=source_context),),
                generator=snapshot.generator_version,
                reviewer=f"{snapshot.generator_version}/reviewer",
                extractor_max_tokens=self.extractor_max_tokens,
                reviewer_max_tokens=self.reviewer_max_tokens,
            ),
            self.llm,
        )
        pack = result.pack
        atoms = [
            {"category": category, **atom.model_dump(mode="json")}
            for category, values in (
                ("must_preserve", pack.must_preserve),
                ("selectable", pack.selectable),
            )
            for atom in values
        ]
        usage = result.telemetry.total_usage
        return CompletedKnowledgePack(
            markdown=result.markdown,
            pack_payload=pack.canonical_payload(),
            pack_hash=pack.canonical_hash,
            atoms=atoms,
            provenance=pack.provenance.model_dump(mode="json"),
            input_tokens=usage.tokens_in,
            output_tokens=usage.tokens_out,
            duration_ms=max(0, round(result.telemetry.total_seconds * 1000)),
        )


def objective_for_node(
    node: CourseNode, *, source_context: str, schema_version: int
) -> LearningObjective:
    """Derive the coarse objective deterministically from source shape and node data."""

    shape = analyze_shape(
        source_context=source_context,
        summary=node.summary or "",
        headings=tuple(node.source_headings or ()),
    )
    ordered = tuple(
        dict.fromkeys(_SOURCE_FUNCTIONS[signal.function] for signal in shape.signals)
    )
    if not ordered:
        ui_format = getattr(node.default_ui_format, "value", str(node.default_ui_format))
        fallback = {
            "chart": SourceFunction.QUANTIFY,
            "simulation": SourceFunction.EXPLORE,
            "exercise": SourceFunction.ASSESS,
        }.get(ui_format, SourceFunction.ENUMERATE)
        ordered = (fallback,)
    functions = frozenset(ordered)
    requirements = frozenset(
        {"numeric_series"} if SourceFunction.QUANTIFY in functions else set()
    )
    return LearningObjective(
        objective_id=str(node.id),
        objective_version=max(1, schema_version),
        mission=_MISSION_FOR_SOURCE[ordered[0]],
        source_functions=functions,
        available_requirements=requirements,
    )


__all__ = ["GENERATOR_VERSION", "ConfiguredKnowledgePackGenerator", "objective_for_node"]
