"""Response schemas for the pre-assessment (§7.1, §11.3).

These exist for one reason: **``answer_key`` must never leave the server** (§5.2
rule 5, §14.1). ``ProbeService.start_probe`` handed its caller the whole
``node_probes`` row, answer key included, and trusted every future route not to
serialize it. Trust is not a mechanism — the routes that would serve a probe are
B5, so the leak would have been introduced by code that has not been written yet
and reviewed against a promise made in a different file.

``ProbeSessionRead.from_session`` is the only sanctioned way to turn a
``ProbeSession`` into a response body: it enumerates the fields that may travel,
so a column added to ``node_probes`` later is invisible here until somebody adds
it on purpose. ``tests/test_probe_answer_key_privacy.py`` dumps the model and
asserts the key is absent, in both directions (field names and values).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ProbeRead(BaseModel):
    """One ``node_probes`` row as the client may see it.

    Deliberately **not** ``from_attributes`` over the ORM row: an explicit
    constructor is what makes "the key is not in this list" reviewable. There is no
    ``answer_key``, and there never can be one by accident.
    """

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    node_id: uuid.UUID
    schema_version: int
    attempt_no: int
    # Whether this attempt counts against the one-scored-probe rule (§3.4).
    scored: bool
    score: float | None = None
    mastered: bool | None = None
    tiebreak_used: bool = False
    created_at: datetime | None = None
    completed_at: datetime | None = None


class ProbeSessionRead(BaseModel):
    """``POST /nodes/{node_id}/probe`` (§11.3).

    ``items`` are the answer-free props of ``served_items`` (which itself runs every
    item through ``public_props``), so the correct option is stripped twice: once
    because it lives in another column, once in case a generator misplaced it.
    """

    model_config = ConfigDict(extra="forbid")

    probe: ProbeRead | None = None
    items: list[dict[str, Any]] = []
    reused: bool = False
    verdict: str | None = None
    diagnostic: bool = False

    @classmethod
    def from_session(cls, session: Any) -> ProbeSessionRead:
        """Project a ``ProbeService.ProbeSession`` onto the wire.

        ``probe`` is ``None`` on the one path that has no row to report: a learner
        who is past the probe with no scored attempt and no stored attempt at all.
        """
        row = session.probe
        return cls(
            probe=None
            if row is None
            else ProbeRead(
                id=row.id,
                node_id=row.node_id,
                schema_version=row.schema_version,
                attempt_no=row.attempt_no,
                scored=row.scored,
                score=row.score,
                mastered=row.mastered,
                tiebreak_used=row.tiebreak_used,
                created_at=getattr(row, "created_at", None),
                completed_at=row.completed_at,
            ),
            items=list(session.items),
            reused=session.reused,
            verdict=session.verdict,
            diagnostic=session.diagnostic,
        )


__all__ = ["ProbeRead", "ProbeSessionRead"]
