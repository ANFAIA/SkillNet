"""Request/response schemas for click-to-explain (§8.4, §11.3)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator

from src.core.language import Language, normalize_language
from src.models import TERM_MAX_LENGTH

# Block context is normalized and clamped to 600 characters CENTERED on the term
# (§8.3). Anything the client sends beyond that is re-clamped server-side.
CONTEXT_MAX_CHARS = 600

# Generous ceiling on the raw context: the server trims it to CONTEXT_MAX_CHARS
# anyway, and rejecting a whole page of prose outright is friendlier than silently
# hashing something enormous.
_CONTEXT_HARD_LIMIT = 20_000


class ExplainRequest(BaseModel):
    """``POST /explain``.

    Two limits on ``term``, not one (§8.4): over ``TERM_MAX_LENGTH`` (140) is a
    422 — an accidental drag across half a paragraph is not a term. Between 61 and
    140 is explained but never persisted; that rule lives in
    ``explain_service.is_cacheable``, not here, because it changes behaviour rather
    than validity.
    """

    term: str = Field(min_length=1)
    context: str = Field(default="", max_length=_CONTEXT_HARD_LIMIT)
    node_id: uuid.UUID | None = None
    # ``None`` means "nobody asked", and it has to stay distinguishable from "asked for
    # Spanish". This field used to default to ``"es"``, so the server could not tell the
    # two apart and every request looked like an explicit Spanish one — which short-
    # circuits the whole resolution order in ``src/services/language_policy.py`` and
    # leaves an English course explaining its terms in Spanish. Resolving the real
    # language is ``ExplainService``'s job, because it is the one that knows the node.
    language: Language | None = None

    @field_validator("term")
    @classmethod
    def _term_within_limits(cls, value: str) -> str:
        """Enforce the hard limit on the *trimmed* term.

        Checked after trimming so 200 spaces around a 3-letter word is not a 422,
        and before anything else so an over-long selection never reaches the model.
        """
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("El termino no puede estar vacio")
        if len(trimmed) > TERM_MAX_LENGTH:
            raise ValueError(
                f"Seleccion demasiado larga ({len(trimmed)} caracteres); "
                f"el maximo es {TERM_MAX_LENGTH}"
            )
        return trimmed

    @field_validator("language", mode="before")
    @classmethod
    def _normalize_language(cls, value: object) -> Language | None:
        """A locale tag folded to a supported language, or ``None``.

        ``mode="before"`` so ``"language": null``, ``""`` and an unsupported locale are
        all "no request" rather than a 422 — the client sends the field either way, and a
        422 on a locale the deployment does not speak would refuse to explain a word over
        a preference. Folding through ``normalize_language`` also means ``en-US`` and
        ``en`` land on the same cached row instead of two, which the old
        ``.strip().lower()`` did not: it wrote ``en-us`` straight into the unique key.
        """
        return normalize_language(None if value is None else str(value))


class ExplainResult(BaseModel):
    """What one resolved explanation amounts to.

    Not the wire format of the endpoint (that is SSE), but the value the service
    settles on — returned to tests and carried in the final ``done`` event.
    """

    term: str
    term_normalized: str
    context_hash: str
    language: str
    explanation: str
    model: str
    cached: bool
    cacheable: bool
