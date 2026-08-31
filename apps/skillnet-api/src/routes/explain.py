"""``POST /explain`` — click-to-explain (§8.4, §11.3).

The two failures that are knowable before a single token is generated are real HTTP
statuses, not in-band SSE errors: 422 for a selection over 140 characters (a pydantic
validator on ``ExplainRequest``) and 429 for the rate limit. Anything that goes wrong
once the stream has started is an ``error`` event, because the status line is gone.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from src.deps.auth import CurrentUser
from src.deps.db import DBSession
from src.llm.client import LLMService, resolve_llm_config
from src.llm.fixtures import maybe_fixture_llm
from src.models import Organization
from src.schemas.explain import ExplainRequest
from src.services.explain_service import ExplainService, check_rate_limit

router = APIRouter(tags=["Explain"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


async def _org_settings(db: DBSession) -> dict[str, Any]:
    """Provider overrides carried by the single organization row.

    Duplicated from ``src.deps.llm`` (four lines) rather than imported, because that
    module is owned by another batch and a shared ``runtime_fast`` provider would be
    two agents editing the same lines of the same file.
    """
    result = await db.execute(select(Organization).limit(1))
    org = result.scalar_one_or_none()
    return dict(org.settings) if org and org.settings else {}


async def get_runtime_fast_llm(db: DBSession) -> LLMService:
    """The ``runtime_fast`` tier (§8.4): a one-sentence gloss never needs the big model.

    Goes through ``maybe_fixture_llm`` like every other construction site, so the whole
    feature runs with ``LLM_MODEL=fixture/local`` and no API key.
    """
    return maybe_fixture_llm(
        resolve_llm_config(await _org_settings(db), purpose="runtime_fast")
    )


RuntimeFastLLMDep = Annotated[LLMService, Depends(get_runtime_fast_llm)]


@router.post("/explain")
async def explain(
    request: ExplainRequest,
    user: CurrentUser,
    db: DBSession,
    llm: RuntimeFastLLMDep,
    accept_language: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """Stream a one-sentence, context-aware explanation of the selected term.

    ``CurrentUser`` rather than ``EmployeeUser``: an admin reviewing a node sees the
    same clickable prose, and the rate limit is per user either way.

    The header is read here and nowhere else on this route because it is the last resort
    of the order in ``src/services/language_policy.py``: the body's own ``language`` and
    the clicked node's course both outrank it.
    """
    check_rate_limit(user.id)
    service = ExplainService(db, llm)
    return StreamingResponse(
        service.stream(user, request, accept_language=accept_language),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
