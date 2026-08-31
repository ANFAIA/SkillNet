"""Dependency providers for LLM and embedding services.

The single organization row may carry provider overrides in its ``settings``
jsonb; these take precedence over environment defaults. Building the services
here keeps provider resolution out of the business logic.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import select

from src.core.exceptions import LLMError
from src.deps.db import DBSession
from src.llm.client import LLMService, resolve_llm_config
from src.llm.embedding import EmbeddingService, resolve_embedding_config
from src.llm.fixtures import maybe_fixture_embedder, maybe_fixture_llm
from src.models import Organization


async def _org_settings(db: DBSession) -> dict[str, Any]:
    """The deployment's organization settings, for resolving the LLM provider.

    Unscoped on purpose: these dependencies exist to answer "which provider does this
    deployment use", and the provider is a property of the deployment (see
    ``services/settings_service.py``), not of whoever is asking. What is *not* on purpose
    is picking an arbitrary row when more than one organization exists — the public demo
    mints one per visit. ``created_at`` makes the pick deterministic and lands it on the
    organization ``bootstrap.py`` created, which is the one that actually holds the
    deployment's configuration.

    Anything genuinely per-organization must not be read here. It needs the caller's
    ``org_id``, the way ``course_orchestration._org_settings`` takes one.
    """
    result = await db.execute(
        select(Organization).order_by(Organization.created_at, Organization.id).limit(1)
    )
    org = result.scalar_one_or_none()
    return dict(org.settings) if org and org.settings else {}


async def get_llm_service(db: DBSession) -> LLMService:
    return maybe_fixture_llm(resolve_llm_config(await _org_settings(db)))


async def get_tutor_llm_service(db: DBSession) -> LLMService:
    return maybe_fixture_llm(
        resolve_llm_config(await _org_settings(db), purpose="tutor")
    )


async def get_generation_llm_service(db: DBSession) -> LLMService:
    return maybe_fixture_llm(
        resolve_llm_config(await _org_settings(db), purpose="generation")
    )


async def get_embedding_service(db: DBSession) -> EmbeddingService:
    return maybe_fixture_embedder(resolve_embedding_config(await _org_settings(db)))


async def get_optional_llm_service(db: DBSession) -> LLMService | None:
    """LLM service if one is configured, else ``None`` (grading degrades gracefully).

    Goes through ``maybe_fixture_llm`` too: this is the factory ``grade_open_answer``
    uses, so without it a fixture-mode probe or tie-break would attempt a real
    network call.
    """
    try:
        return maybe_fixture_llm(
            resolve_llm_config(await _org_settings(db), purpose="eval")
        )
    except LLMError:
        return None


LLMDep = Annotated[LLMService, Depends(get_llm_service)]
GenerationLLMDep = Annotated[LLMService, Depends(get_generation_llm_service)]
TutorLLMDep = Annotated[LLMService, Depends(get_tutor_llm_service)]
EmbeddingDep = Annotated[EmbeddingService, Depends(get_embedding_service)]
OptionalLLMDep = Annotated[LLMService | None, Depends(get_optional_llm_service)]
