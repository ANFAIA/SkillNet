"""Request/response schemas for the rich-media artifact surface.

Built explicitly (no ``from_attributes`` blanket) so what travels to the client is an
enumerated list: ``spec_json`` is served (it carries the citations panel needs and is not
secret), but the on-disk ``asset_path`` never leaves the server — the client gets a
``has_asset`` flag and fetches the bytes through the asset route instead.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.models import MediaArtifact, MediaArtifactStatus, MediaKind
from src.services.media.activity_assets import make_activity_asset_ref


class MediaScope(str, enum.Enum):
    """Where an artefact is anchored — the three generation modes (roadmap §3).

    * ``node`` — grounded on ONE node's own source material and attached to it. This is the
      artefact the inline lesson component can reference.
    * ``course`` — a full overview of the WHOLE course (e.g. a long podcast covering every
      node's corpus). Not tied to any node.
    * ``standalone`` — a free-standing artefact, tied to neither a node nor the exhaustive
      course corpus: steered mainly by the learner's ``note`` (and optional ``query``),
      grounded on whatever of the course corpus that note matches. Also node-less.
    """

    NODE = "node"
    COURSE = "course"
    STANDALONE = "standalone"


class MediaArtifactCreate(BaseModel):
    """``POST /media/artifacts`` body: what to generate, in which mode, and how to steer it."""

    model_config = ConfigDict(use_enum_values=True)

    course_id: uuid.UUID
    node_id: uuid.UUID | None = None
    kind: MediaKind
    # The generation mode. Defaults are inferred from node_id when omitted (node when a
    # node_id is present, course otherwise) so older clients keep working unchanged.
    scope: MediaScope | None = None
    # A free-text personalization instruction the learner writes to steer the LLM
    # (e.g. "enfócalo para camareros nuevos"). Folded into the generator's steering prompt
    # and persisted, so it also seeds the parallel learner-memory note.
    note: str | None = None
    # Free-form generator input: format preset, language, steering prompt, optional
    # `query` to focus grounding retrieval. Opaque to the runner, read by the generator.
    spec: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _resolve_scope(self) -> MediaArtifactCreate:
        """Infer scope from node_id when omitted, then enforce the node_id ↔ scope contract.

        ``node`` requires a ``node_id``; ``course``/``standalone`` must NOT carry one (they
        are node-less by definition). Keeping the two consistent here means the route and
        the generator can trust ``scope`` without re-deriving it.
        """
        if self.scope is None:
            object.__setattr__(
                self,
                "scope",
                (MediaScope.NODE.value if self.node_id is not None else MediaScope.COURSE.value),
            )
        scope = self.scope.value if isinstance(self.scope, MediaScope) else self.scope
        if scope == MediaScope.NODE.value and self.node_id is None:
            raise ValueError("scope 'node' requires a node_id")
        if scope in (MediaScope.COURSE.value, MediaScope.STANDALONE.value) and self.node_id is not None:
            raise ValueError(f"scope '{scope}' must not carry a node_id")
        return self


class MediaArtifactAccepted(BaseModel):
    """``202`` from enqueue: the row exists and a background job is running."""

    artifact_id: uuid.UUID
    status: str


class MediaArtifactRead(BaseModel):
    """One artifact as the client may see it. No ``asset_path``."""

    id: uuid.UUID
    course_id: uuid.UUID
    node_id: uuid.UUID | None
    kind: str
    status: str
    spec_json: dict
    has_asset: bool
    asset_ref: str | None
    content_hash: str | None
    #: Short, user-safe failure text. Never a provider's raw exception string.
    error: str | None
    #: The stable failure code (``src.services.media.jobs``), for clients that want to
    #: word the failure themselves. ``None`` on rows that failed before it existed.
    error_code: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, artifact: MediaArtifact) -> MediaArtifactRead:
        return cls(
            id=artifact.id,
            course_id=artifact.course_id,
            node_id=artifact.node_id,
            kind=str(getattr(artifact.kind, "value", artifact.kind)),
            status=str(getattr(artifact.status, "value", artifact.status)),
            spec_json=dict(artifact.spec_json or {}),
            has_asset=artifact.asset_path is not None,
            asset_ref=(
                make_activity_asset_ref(artifact)
                if artifact.asset_path is not None
                and getattr(artifact.status, "value", artifact.status)
                == MediaArtifactStatus.DONE.value
                else None
            ),
            content_hash=artifact.content_hash,
            error=_safe_error(artifact),
            error_code=artifact.error_code,
            created_at=artifact.created_at,
            updated_at=artifact.updated_at,
        )


def _safe_error(artifact: MediaArtifact) -> str | None:
    """The failure text, with pre-existing raw exception strings held back.

    Failures recorded from now on store a short English sentence and a stable code, so
    ``error`` is safe to serve. Rows that failed *before* that still hold
    ``f"{type(exc).__name__}: {exc}"`` — a provider's raw text, which can carry an
    endpoint, a model name or an account identifier — and an upgrade in place keeps
    serving them. A row with no ``error_code`` is exactly that row: it says the same
    thing the new ones do, without the traceback.
    """
    if artifact.error and artifact.error_code is None:
        return "Generation failed."
    return artifact.error


__all__ = [
    "MediaScope",
    "MediaArtifactCreate",
    "MediaArtifactAccepted",
    "MediaArtifactRead",
    "MediaArtifactStatus",
]
