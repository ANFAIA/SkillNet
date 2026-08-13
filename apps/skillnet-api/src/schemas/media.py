"""Request/response schemas for the rich-media artifact surface.

Built explicitly (no ``from_attributes`` blanket) so what travels to the client is an
enumerated list: ``spec_json`` is served (it carries the citations panel needs and is not
secret), but the on-disk ``asset_path`` never leaves the server — the client gets a
``has_asset`` flag and fetches the bytes through the asset route instead.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.models import MediaArtifact, MediaArtifactStatus, MediaKind
from src.services.media.activity_assets import make_activity_asset_ref


class MediaArtifactCreate(BaseModel):
    """``POST /media/artifacts`` body: what to generate, and the steering spec."""

    model_config = ConfigDict(use_enum_values=True)

    course_id: uuid.UUID
    node_id: uuid.UUID | None = None
    kind: MediaKind
    # Free-form generator input: format preset, language, steering prompt, optional
    # `query` to focus grounding retrieval. Opaque to the runner, read by the generator.
    spec: dict = Field(default_factory=dict)


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
    error: str | None
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
            error=artifact.error,
            created_at=artifact.created_at,
            updated_at=artifact.updated_at,
        )


__all__ = [
    "MediaArtifactCreate",
    "MediaArtifactAccepted",
    "MediaArtifactRead",
    "MediaArtifactStatus",
]
