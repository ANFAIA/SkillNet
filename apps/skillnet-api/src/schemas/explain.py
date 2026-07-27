"""Request/response schemas for click-to-explain (§8.4, §11.3)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator

from src.models import TERM_MAX_LENGTH

# Block context is normalized and clamped to 600 characters CENTERED on the term
# (§8.3). Anything the client sends beyond that is re-clamped server-side.
CONTEXT_MAX_CHARS = 600

# Generous ceiling on the raw context: the server trims it to CONTEXT_MAX_CHARS
# anyway, and rejecting a whole page of prose outright is friendlier than silently
# hashing something enormous.
_CONTEXT_HARD_LIMIT = 20_000

_DEFAULT_LANGUAGE = "es"


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
    # Optional on the wire (§11.3), never ``None`` once parsed: the normalizer below
    # folds a missing, blank or explicit-null value into the column default.
    language: str = Field(default=_DEFAULT_LANGUAGE, max_length=8)

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
    def _normalize_language(cls, value: object) -> str:
        """Lower-cased tag; ``null``, ``""`` and whitespace all mean the default.

        ``mode="before"`` so an explicit ``"language": null`` in the JSON body is a
        default rather than a 422 — the client sends the field either way.
        """
        if value is None or not str(value).strip():
            return _DEFAULT_LANGUAGE
        return str(value).strip().lower()


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
