"""Click-to-explain: cache lookup, generation, SSE (§8.3, §8.4).

The whole point of the feature is that the explanation is **contextual**, so the
cache key is ``(org_id, term_normalized, context_hash, language)`` and never just the
term. Everything that decides that key is a pure function in this module, so it can
be tested without a database:

* ``normalize_term`` / ``normalize_context`` — whitespace and case;
* ``center_context`` — the 600-character window **centered on the term**, not the
  first 600 characters (§8.3: in a long block the clicked term could otherwise fall
  outside the context the model is shown, which is the worst possible failure);
* ``context_hash`` — ``sha256(normalized_block_text)[:16]`` (§3.4);
* ``is_cacheable`` — <=60 characters **and** <=4 tokens, the only shape that is ever
  written to a row that has no ``user_id`` (§3.4).

Wire format of ``POST /explain`` (SSE):

* ``token`` — ``{"content": "<the full cleaned text so far>"}``. Full text, not a
  delta: §8.4 requires the cache-hit path to emit "a single ``token`` event with the
  complete text", and ``clean_explanation`` can rewrite the prefix of what was
  already sent when it strips a leaked label. One contract for both paths.
* ``done`` — the ``ExplainResult`` dump, so the client can settle on the final text
  and knows whether it came from cache.
* ``error`` — ``{"detail"}``. Only after the stream has started; anything knowable
  up front (422 too long, 429 rate limit) is a real HTTP status from the route.

The word-click **glimpse** is deliberately PLAIN TEXT: a one-sentence answer needs no
kit, and forcing it through OpenUI made a single sentence read as an oversized lead. The
richer, block-based explanation lives in the "Ver más" modal, which reaches the tutor
(``POST /chat``) and gets generative UI there. So this endpoint emits no ``ui`` event.
"""

from __future__ import annotations

import re
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AppError, LLMError
from src.core.logging import get_logger
from src.core.sse import format_sse
from src.llm.client import LLMService
from src.llm.prompts.explain import (
    EXPLAIN_MAX_TOKENS,
    EXPLAIN_TEMPERATURE,
    build_explain_messages,
    clean_explanation,
)
from src.models import (
    TERM_CACHEABLE_MAX_LENGTH,
    TERM_CACHEABLE_MAX_TOKENS,
    Course,
    CourseNode,
    Organization,
    User,
)
from src.repositories.term_explanation_repo import TermExplanationRepository
from src.schemas.explain import CONTEXT_MAX_CHARS, ExplainRequest, ExplainResult
from src.services.language_policy import prompt_language, resolve_language

logger = get_logger(__name__)

CONTEXT_HASH_LENGTH = 16

# §8.4: 30 explanations per user per minute, in the memory of the process. Deliberately
# not Redis-backed: with N workers the effective ceiling is 30*N, which is still a
# ceiling, and the alternative is a new infrastructure dependency for a nicety.
RATE_LIMIT_PER_MINUTE = 30
RATE_LIMIT_WINDOW_SECONDS = 60.0
RATE_LIMIT_MESSAGE = "Demasiadas consultas seguidas"

# The map is bounded three ways, because "in the memory of the process" is only
# acceptable while that memory cannot grow without limit: a long-lived worker in a
# 5000-employee organization would otherwise keep one deque per user who ever
# clicked a word, forever.
#
# 1. a user whose window empties loses their entry immediately;
# 2. every RATE_LIMIT_WINDOW_SECONDS one call sweeps the entries of users who have
#    gone quiet (amortized: one pass per minute, not one per request);
# 3. a hard ceiling evicts the least recently seen windows, so even a burst of
#    distinct user ids inside a single window cannot grow the map unboundedly.
RATE_LIMIT_MAX_TRACKED_USERS = 20_000

_WHITESPACE = re.compile(r"\s+")

_recent_requests: dict[uuid.UUID, deque[float]] = {}
_last_sweep: float | None = None


def normalize_term(term: str) -> str:
    """``trim().toLowerCase()`` (§8.4), plus collapsing internal whitespace.

    The collapse matters because a two-word selection is taken from the DOM and can
    carry a line break in the middle; without it the same phrase selected across a
    wrap would miss the cache forever. It cannot change meaning, only hit rate.
    """
    return _WHITESPACE.sub(" ", term).strip().lower()


def normalize_context(text: str) -> str:
    """``replace(/\\s+/g,' ').trim()`` — the frontend does the same to the block text."""
    return _WHITESPACE.sub(" ", text).strip()


def center_context(context: str, term: str, max_chars: int = CONTEXT_MAX_CHARS) -> str:
    """Clamp normalized block text to ``max_chars`` **centered on the term**.

    Idempotent: a context already within the limit is returned untouched, so the
    client-side window and this server-side re-clamp agree on the same string and
    therefore on the same ``context_hash``.
    """
    normalized = normalize_context(context)
    if len(normalized) <= max_chars:
        return normalized

    needle = normalize_term(term)
    position = normalized.lower().find(needle) if needle else -1
    if position < 0:
        return normalized[:max_chars].strip()

    center = position + len(needle) // 2
    start = max(0, center - max_chars // 2)
    start = min(start, len(normalized) - max_chars)
    return normalized[start : start + max_chars].strip()


def context_hash(normalized_context: str) -> str:
    """``sha256(normalized_block_text)[:16]`` (§3.4)."""
    return sha256(normalized_context.encode()).hexdigest()[:CONTEXT_HASH_LENGTH]


def token_count(term_normalized: str) -> int:
    return len(term_normalized.split())


def is_cacheable(term_normalized: str) -> bool:
    """<=60 characters and <=4 tokens (§3.4, §8.4).

    Longer selections are explained and served but never written: the row has no
    ``user_id``, no retention window of its own and no delete endpoint, so storing a
    sentence a person chose to select would contradict the privacy promise of §3.3.
    """
    return (
        len(term_normalized) <= TERM_CACHEABLE_MAX_LENGTH
        and token_count(term_normalized) <= TERM_CACHEABLE_MAX_TOKENS
    )


def _sweep_expired_windows(cutoff: float) -> None:
    """Forget every user whose whole window is older than ``cutoff``.

    An expired window carries no information: rebuilding it costs one ``deque()``
    and forgetting it is the difference between a bounded map and a leak.
    """
    stale = [
        user_id
        for user_id, window in _recent_requests.items()
        if not window or window[-1] <= cutoff
    ]
    for user_id in stale:
        del _recent_requests[user_id]


def _evict_oldest_windows() -> None:
    """Backstop for the ceiling: drop the least recently seen windows.

    Only reachable when more than ``RATE_LIMIT_MAX_TRACKED_USERS`` distinct users
    are active inside one window, which in this product means an attack rather than
    a Monday morning. Dropping a live window is a lenient failure (the evicted user
    gets a fresh allowance) and that is the right trade: the alternative is the
    process running out of memory, which limits everybody.
    """
    overflow = len(_recent_requests) - RATE_LIMIT_MAX_TRACKED_USERS
    if overflow <= 0:
        return
    def last_seen(user_id: uuid.UUID) -> float:
        window = _recent_requests[user_id]
        return window[-1] if window else 0.0

    oldest = sorted(_recent_requests, key=last_seen)
    for user_id in oldest[:overflow]:
        del _recent_requests[user_id]


def check_rate_limit(user_id: uuid.UUID, *, now: float | None = None) -> None:
    """Sliding window of ``RATE_LIMIT_PER_MINUTE`` per user. Raises ``AppError`` 429.

    Never grows the map for a caller it is about to reject, and never leaves an
    empty deque behind: the entry only exists while the user has requests inside
    the window.
    """
    global _last_sweep

    moment = time.monotonic() if now is None else now
    cutoff = moment - RATE_LIMIT_WINDOW_SECONDS

    if _last_sweep is None or moment - _last_sweep >= RATE_LIMIT_WINDOW_SECONDS:
        _sweep_expired_windows(cutoff)
        _last_sweep = moment

    # ``get``, not ``setdefault``: a rejected request must not be the reason a new
    # entry appears, and an expired one must not survive the check below.
    window = _recent_requests.get(user_id, deque())
    while window and window[0] <= cutoff:
        window.popleft()
    if not window:
        _recent_requests.pop(user_id, None)

    if len(window) >= RATE_LIMIT_PER_MINUTE:
        raise AppError(
            message=RATE_LIMIT_MESSAGE, code="RATE_LIMITED", status_code=429
        )

    window.append(moment)
    _recent_requests[user_id] = window
    if len(_recent_requests) > RATE_LIMIT_MAX_TRACKED_USERS:
        _evict_oldest_windows()


def tracked_rate_limit_users() -> int:
    """Size of the in-memory window map. For tests and for a future metric."""
    return len(_recent_requests)


def reset_rate_limits() -> None:
    """Drop every window. For tests and for a clean process restart."""
    global _last_sweep

    _recent_requests.clear()
    _last_sweep = None


class ExplainService:
    """One explanation per call: cache hit, or generate and (maybe) persist."""

    def __init__(
        self,
        db: AsyncSession,
        llm: LLMService,
        repo: TermExplanationRepository | None = None,
    ) -> None:
        self.db = db
        self.llm = llm
        # Injectable so the service is testable against an in-memory store: nothing
        # here needs real SQL to be worth testing.
        self.repo = repo if repo is not None else TermExplanationRepository(db)

    async def stream(
        self,
        user: User,
        request: ExplainRequest,
        *,
        accept_language: str | None = None,
    ) -> AsyncIterator[str]:
        """SSE for one term. Always terminates with ``done`` or ``error``.

        ``accept_language`` is the browser's header, the weakest step of the order in
        ``src/services/language_policy.py``: it only decides when neither the request nor
        the lesson's own course says anything.
        """
        term_normalized = normalize_term(request.term)
        context = center_context(request.context, request.term)
        digest = context_hash(context)
        cacheable = is_cacheable(term_normalized)

        try:
            node_id, node_title, node_summary, course = await self._node_context(
                user, request.node_id
            )
            # Resolved before the cache lookup, because the resolved value *is* part of
            # the row's unique key: looking up under the requested tag and writing under
            # the resolved one is how the two would drift apart.
            language = resolve_language(
                requested=request.language,
                course=course,
                org_settings=await self._org_settings(user),
                accept_language_header=accept_language,
            )

            hit = await self.repo.find(
                org_id=user.org_id,
                term_normalized=term_normalized,
                context_hash=digest,
                language=language,
            )
            if hit is not None:
                # ~10 ms, zero tokens. The single token event carries the whole text.
                await self.repo.touch(hit)
                await self._commit()
                yield format_sse("token", {"content": hit.explanation})
                yield format_sse(
                    "done",
                    ExplainResult(
                        term=request.term,
                        term_normalized=term_normalized,
                        context_hash=digest,
                        language=language,
                        explanation=hit.explanation,
                        model=hit.model,
                        cached=True,
                        cacheable=cacheable,
                    ).model_dump(),
                )
                return

            messages = build_explain_messages(
                request.term,
                context,
                node_title=node_title,
                node_summary=node_summary,
                language=prompt_language(language),
            )
            accumulated = ""
            emitted = ""
            async for delta in self.llm.stream(
                messages,
                temperature=EXPLAIN_TEMPERATURE,
                max_tokens=EXPLAIN_MAX_TOKENS,
            ):
                accumulated += delta
                cleaned = clean_explanation(accumulated)
                if cleaned and cleaned != emitted:
                    emitted = cleaned
                    yield format_sse("token", {"content": cleaned})

            explanation = clean_explanation(accumulated).strip()
            if not explanation:
                yield format_sse(
                    "error", {"detail": "El modelo no devolvio ninguna explicacion."}
                )
                return

            if cacheable:
                await self.repo.record(
                    org_id=user.org_id,
                    node_id=node_id,
                    term=request.term,
                    term_normalized=term_normalized,
                    context_hash=digest,
                    language=language,
                    explanation=explanation,
                    model=self.llm.model,
                )
                await self._commit()

            if explanation != emitted:
                yield format_sse("token", {"content": explanation})
            yield format_sse(
                "done",
                ExplainResult(
                    term=request.term,
                    term_normalized=term_normalized,
                    context_hash=digest,
                    language=language,
                    explanation=explanation,
                    model=self.llm.model,
                    cached=False,
                    cacheable=cacheable,
                ).model_dump(),
            )

        except Exception as exc:  # noqa: BLE001 - the stream must end cleanly
            detail = exc.message if isinstance(exc, AppError) else str(exc)
            level = logger.warning if isinstance(exc, LLMError) else logger.error
            level("Explain failed for %r: %s", term_normalized, exc, exc_info=True)
            await self._rollback()
            yield format_sse("error", {"detail": detail})

    async def _node_context(
        self, user: User, node_id: uuid.UUID | None
    ) -> tuple[uuid.UUID | None, str | None, str | None, Course | None]:
        """Resolve ``node_id`` to its title, summary and course, scoped to the caller's org.

        A node from another organization is dropped entirely — not 404'd. The node is
        only prompt colour and a nullable FK; refusing to explain a word because a
        stale id came along would be a worse outcome than explaining it without the
        lesson title. A read of ``course_nodes`` rather than a repository call
        because ``course_node_repo`` belongs to another batch.

        The course comes back because it carries the language of the material the term
        was clicked in, which outranks anything the browser guesses. A missing course is
        not an error for the same reason a missing node is not: the word still gets
        explained, one step further down the resolution order.
        """
        if node_id is None:
            return None, None, None, None
        result = await self.db.execute(
            select(CourseNode).where(
                CourseNode.id == node_id, CourseNode.org_id == user.org_id
            )
        )
        node = result.scalar_one_or_none()
        if node is None:
            logger.info("Explain got an unknown node_id %s; ignoring it", node_id)
            return None, None, None, None
        course_id = getattr(node, "course_id", None)
        course = None
        if course_id is not None:
            found = await self.db.execute(select(Course).where(Course.id == course_id))
            course = found.scalar_one_or_none()
        return node.id, node.title, node.summary, course

    async def _org_settings(self, user: User) -> dict:
        """The caller's organization settings, or ``{}`` when there are none.

        One step of a chain that always has an answer below it, so "no settings" and "no
        language in the settings" are the same non-event and neither is worth an error.
        """
        org_id = getattr(user, "org_id", None)
        if org_id is None or self.db is None:
            return {}
        found = await self.db.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = found.scalar_one_or_none()
        settings = getattr(org, "settings", None)
        return dict(settings) if settings else {}

    async def _commit(self) -> None:
        if self.db is not None:
            await self.db.commit()

    async def _rollback(self) -> None:
        if self.db is None:
            return
        try:
            await self.db.rollback()
        except Exception as exc:  # noqa: BLE001 - rollback failure must not mask the cause
            logger.error("Could not roll back after a failed explain: %s", exc)
