"""Request and response schemas for the runtime employee surface (§11.3).

Two of these exist for a security reason rather than for convenience, and both mirror the
shape of ``src/schemas/probe.py``:

* :class:`NodeRenderRead` has **no** ``answer_key`` and **no** ``ui_spec``. It serves
  ``program`` — the canonical dialect ``backend.serialize`` produced from the already
  validated ``UISpec`` — because that is the only text a browser may parse (§5.1). The IR
  stays server-side as audit evidence (§3.4), and the model's own ``raw_dsl`` appears in no
  schema at all.
* :class:`NodeAnswerRequest.hints_used` is accepted and **ignored**. It is the field that
  decides whether ``correct_answer`` is revealed, so a number the client picks cannot
  govern it: ``hints_used: 3`` would be a free answer key. The count of record comes from
  ``node_attempts.hints_used``, which only ``POST /nodes/{id}/hint`` increments (§11.3).

Every model is built explicitly rather than with ``from_attributes``: an enumerated field
list is what makes "the key is not in here" reviewable, and a column added to
``node_renders`` later stays invisible until somebody adds it on purpose.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Free text the learner writes in ``POST /nodes/{id}/feedback``. One of only two places
#: where user text is persisted (§3.3), so it is bounded here.
UNCLEAR_MAX_CHARS = 1000

#: Fallback for ``estimated_minutes`` when the creator left it empty. The frontend types it
#: as a number, not ``number | null``.
DEFAULT_ESTIMATED_MINUTES = 6


# --- node list ---------------------------------------------------------------------


class NodeSummaryRead(BaseModel):
    """One row of ``GET /courses/{course_id}/nodes``."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    title: str
    summary: str | None = None
    criticality: str
    position: int
    state: str
    mastery: float
    locked: bool
    #: Ids of the unmet prerequisites. Naming *why* it is locked is what makes the lock
    #: actionable instead of a dead end.
    locked_by: list[uuid.UUID] = Field(default_factory=list)
    #: ``state == 'needs_review'`` (§7.4). The node stays visible in a "para practicar"
    #: section instead of disappearing.
    needs_practice: bool = False
    estimated_minutes: int = DEFAULT_ESTIMATED_MINUTES


class NodeListRead(BaseModel):
    """``GET /courses/{course_id}/nodes`` (§11.3)."""

    model_config = ConfigDict(extra="forbid")

    course_id: uuid.UUID
    delivery_mode: str
    schema_version: int
    nodes: list[NodeSummaryRead] = Field(default_factory=list)
    #: §7.5: every non-archived ``critical`` node mastered. ``recommended`` and
    #: ``contextual`` never block.
    can_complete: bool = False
    blocked_by: list[str] = Field(default_factory=list)
    progress_percent: int = 0


# --- render ------------------------------------------------------------------------


class NodeRenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: The only way the content of an open node changes (§5.5). Recomputes the ``cache_key``
    #: and repins ``active_render_id``.
    force: bool = False
    #: Admin only. Generates with the admin's profile, does not touch
    #: ``learner_node_states`` and persists ``is_preview = true``, which excludes it from
    #: the cache (§3.4) — that is what makes ``shadow`` mode safe.
    preview: bool = False


class NodeRenderAccepted(BaseModel):
    """``202`` from ``POST /nodes/{node_id}/render``.

    ``request_id`` is empty when ``cached`` is true: there is no stream to subscribe to
    because there is no work to do.
    """

    model_config = ConfigDict(extra="forbid")

    request_id: str = ""
    cached: bool = False
    render_id: uuid.UUID | None = None


class NodeRenderRead(BaseModel):
    """``GET /nodes/{node_id}/render``. ``answer_key`` can never appear here."""

    model_config = ConfigDict(extra="forbid")

    render_id: uuid.UUID
    node_id: uuid.UUID
    ui_format: str
    status: str
    backend: str
    cached: bool = False
    #: OpenUI Lang **text**, re-serialized from the validated spec. Never ``raw_dsl``.
    program: str

    @classmethod
    def of(cls, served: Any) -> NodeRenderRead:
        """Project a ``ServedRender``. The field list is the whole contract."""
        return cls(
            render_id=served.render_id,
            node_id=served.node_id,
            ui_format=served.ui_format,
            status=served.status,
            backend=served.backend,
            cached=served.cached,
            program=served.program,
        )


class NodeRenderPending(BaseModel):
    """``202`` from ``GET /nodes/{node_id}/render`` while there is nothing pinned yet."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["generating", "pending"] = "pending"
    request_id: str | None = None


class NodeRenderHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    render_id: uuid.UUID
    created_at: datetime | None = None
    ui_format: str
    status: str


class NodeRenderHistoryRead(BaseModel):
    """``GET /nodes/{node_id}/renders`` — "ver la version anterior" (§5.5)."""

    model_config = ConfigDict(extra="forbid")

    renders: list[NodeRenderHistoryItem] = Field(default_factory=list)


# --- probe -------------------------------------------------------------------------


class ProbeAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probe_id: uuid.UUID
    item_id: str
    answer: Any = None
    latency_ms: int | None = None


class ProbeAnswerResult(BaseModel):
    """``POST /nodes/{node_id}/probe/answer`` (§11.3)."""

    model_config = ConfigDict(extra="forbid")

    item_id: str
    score: float
    passed: bool
    #: ``null`` until every required item has been answered.
    verdict: str | None = None
    estimate: float | None = None
    next_item_id: str | None = None
    #: ``"prefetch"`` tells the client to fire ``POST /render`` in the background — the
    #: productive-wait overlap of §9.1. ``"skip"`` means the node was mastered.
    render_hint: str | None = None
    feedback: str | None = None


# --- answer, hint, feedback, events -------------------------------------------------


class NodeAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    render_id: uuid.UUID
    item_id: str
    answer: Any = None
    #: **Informative only.** See the module docstring: the server derives the real count
    #: from ``node_attempts``.
    hints_used: int = 0
    latency_ms: int | None = None


class NodeAttemptResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float
    passed: bool
    feedback: str | None = None
    #: Populated only when the item is passed or the *server-side* hint quota is spent.
    correct_answer: dict[str, Any] | None = None
    mastery: float
    state: str
    consecutive_correct: int = 0
    consecutive_failed: int = 0
    next: Literal["retry", "next_item", "next_node"] = "next_item"
    #: §7.4: at the 4th failure after 3 hints the worked solution is shown and the node
    #: enters the practice queue.
    show_worked_solution: bool = False


class NodeHintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    render_id: uuid.UUID
    item_id: str


class NodeHintResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hint: str
    hints_used: int
    hints_remaining: int


class NodeFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    difficulty: Literal["easy", "ok", "hard"]
    unclear: str | None = None

    @field_validator("unclear")
    @classmethod
    def _bound_unclear(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        return trimmed[:UNCLEAR_MAX_CHARS]


class NodeEventInput(BaseModel):
    """One instrumentation event (§3.3).

    ``metadata`` is not accepted: the repository composes it from ``element_id`` and ``ms``
    and nothing else, because ``learning_events.metadata`` must never hold user text.
    """

    model_config = ConfigDict(extra="forbid")

    type: str
    element: str | None = None
    node_id: uuid.UUID | None = None
    element_id: str | None = None
    ms: int | None = None


class NodeEventsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[NodeEventInput] = Field(default_factory=list, max_length=100)


# --- state and waive ---------------------------------------------------------------


class NodeWaiveRequest(BaseModel):
    """``POST /nodes/{node_id}/waive`` (§7.4).

    ``user_id`` is an addition to the body §11.3 sketches. The table there shows only
    ``{"reason"?}``, but the endpoint is admin-only and its purpose is "a human who has seen
    this person work accredits them" — so without naming a learner the only thing an admin
    could waive is their own state, which is not the feature. Omitted, it still defaults to
    the caller, so the documented shape keeps working.
    """

    model_config = ConfigDict(extra="forbid")

    reason: str | None = None
    user_id: uuid.UUID | None = None


class NodeStateRead(BaseModel):
    """``POST /nodes/{node_id}/waive`` (§7.4) and the state half of the answer flow."""

    model_config = ConfigDict(extra="forbid")

    node_id: uuid.UUID
    state: str
    mastery: float
    probe_score: float | None = None
    consecutive_correct: int = 0
    consecutive_failed: int = 0
    hints_used: int = 0
    attempts_count: int = 0
    scaffold_band: str = "neutral"
    needs_practice: bool = False
    waived_by: uuid.UUID | None = None
    waived_at: datetime | None = None
    active_render_id: uuid.UUID | None = None

    @classmethod
    def of(cls, state: Any) -> NodeStateRead:
        value = getattr(state.state, "value", state.state)
        return cls(
            node_id=state.node_id,
            state=str(value),
            mastery=float(state.mastery or 0.0),
            probe_score=state.probe_score,
            consecutive_correct=int(state.consecutive_correct or 0),
            consecutive_failed=int(state.consecutive_failed or 0),
            hints_used=int(state.hints_used or 0),
            attempts_count=int(state.attempts_count or 0),
            scaffold_band=str(state.scaffold_band or "neutral"),
            needs_practice=str(value) == "needs_review",
            waived_by=state.waived_by,
            waived_at=state.waived_at,
            active_render_id=state.active_render_id,
        )


__all__ = [
    "DEFAULT_ESTIMATED_MINUTES",
    "UNCLEAR_MAX_CHARS",
    "NodeAnswerRequest",
    "NodeAttemptResult",
    "NodeEventInput",
    "NodeEventsRequest",
    "NodeFeedbackRequest",
    "NodeHintRequest",
    "NodeHintResult",
    "NodeListRead",
    "NodeRenderAccepted",
    "NodeRenderHistoryItem",
    "NodeRenderHistoryRead",
    "NodeRenderPending",
    "NodeRenderRead",
    "NodeRenderRequest",
    "NodeStateRead",
    "NodeSummaryRead",
    "NodeWaiveRequest",
    "ProbeAnswerRequest",
    "ProbeAnswerResult",
]
