"""Activity-scoped, opaque access to SkillNet media artifacts."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config import settings
from src.models import MediaArtifact, MediaArtifactStatus
from src.models.activity_definition import ActivityDefinition
from src.repositories.media_artifact_repo import MediaArtifactRepository
from src.services.activity_ports import PortDeclined


@dataclass(frozen=True, slots=True)
class ResolvedActivityAsset:
    ref: str
    url: str
    mime_type: str
    alt: str
    long_description: str | None = None
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    transcript: list[dict[str, Any]] | None = None
    captions: list[dict[str, Any]] | None = None
    verified_region_ids: frozenset[str] = frozenset()

    def as_payload(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "url": self.url,
            "mime_type": self.mime_type,
            "alt": self.alt,
            "long_description": self.long_description,
            "width": self.width,
            "height": self.height,
            "duration_ms": self.duration_ms,
            "transcript": self.transcript,
            "captions": self.captions,
        }


def _sign(payload: bytes) -> bytes:
    return hmac.new(settings.SECRET_KEY.encode(), payload, hashlib.sha256).digest()[:20]


def make_activity_asset_ref(artifact: MediaArtifact) -> str:
    """Create a non-path reference bound to the artifact's owning scope."""
    payload = json.dumps(
        {
            "v": 1,
            "a": str(artifact.id),
            "o": str(artifact.org_id),
            "c": str(artifact.course_id),
            "n": str(artifact.node_id) if artifact.node_id else None,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    token = base64.urlsafe_b64encode(payload + _sign(payload)).decode().rstrip("=")
    return f"skasset_{token}"


def _decode(ref: str) -> dict[str, Any] | None:
    if not ref.startswith("skasset_"):
        return None
    token = ref.removeprefix("skasset_")
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        payload, signature = raw[:-20], raw[-20:]
        if not hmac.compare_digest(signature, _sign(payload)):
            return None
        value = json.loads(payload)
        return value if value.get("v") == 1 else None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _contains_ref(value: Any, ref: str) -> bool:
    if isinstance(value, dict):
        return any(_contains_ref(child, ref) for child in value.values())
    if isinstance(value, list):
        return any(_contains_ref(child, ref) for child in value)
    return value == ref


def _positive_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


class ActivityAssetResolver:
    """Resolve only completed artifacts explicitly referenced by one activity."""

    def __init__(self, repository: MediaArtifactRepository) -> None:
        self.repository = repository

    async def resolve(
        self, activity: ActivityDefinition, ref: str
    ) -> ResolvedActivityAsset | PortDeclined:
        token = _decode(ref)
        if token is None:
            return PortDeclined("invalid_asset_ref")
        if not _contains_ref(activity.public_definition or {}, ref):
            return PortDeclined("asset_not_declared_by_activity")
        try:
            artifact_id = uuid.UUID(token["a"])
        except (KeyError, ValueError, TypeError):
            return PortDeclined("invalid_asset_ref")
        artifact = await self.repository.get_scoped(artifact_id, activity.org_id)
        if artifact is None:
            return PortDeclined("asset_not_found")
        if (
            token.get("o") != str(activity.org_id)
            or token.get("c") != str(activity.course_id)
            or artifact.course_id != activity.course_id
            or token.get("n") != (str(artifact.node_id) if artifact.node_id else None)
            or (artifact.node_id is not None and artifact.node_id != activity.node_id)
        ):
            return PortDeclined("asset_scope_mismatch")
        if artifact.status != MediaArtifactStatus.DONE or not artifact.asset_path:
            return PortDeclined("asset_not_ready")

        spec = dict(artifact.spec_json or {})
        alt = spec.get("alt")
        if not isinstance(alt, str) or not alt.strip():
            return PortDeclined("asset_missing_alt")
        mime_type = spec.get("mime_type")
        if not isinstance(mime_type, str) or "/" not in mime_type:
            mime_type = mimetypes.guess_type(Path(artifact.asset_path).name)[0]
        if not mime_type:
            return PortDeclined("asset_unknown_mime")
        raw_transcript = spec.get("transcript")
        transcript = (
            [
                {
                    key: cue[key]
                    for key in ("id", "startMs", "endMs", "text", "speaker")
                    if key in cue
                }
                for cue in raw_transcript
                if isinstance(cue, dict)
            ]
            if isinstance(raw_transcript, list)
            else None
        )
        raw_captions = spec.get("captions")
        captions: list[dict[str, Any]] | None = None
        if isinstance(raw_captions, list):
            captions = []
            for index, raw in enumerate(raw_captions):
                if not isinstance(raw, dict) or not isinstance(raw.get("ref"), str):
                    continue
                captions.append(
                    {
                        "id": str(raw.get("id") or f"captions-{index + 1}"),
                        "kind": "captions",
                        "src": (
                            f"/api/v1/media/artifacts/{artifact.id}/asset/"
                            f"{raw['ref']}"
                        ),
                        "language": str(raw.get("language") or "es"),
                        "label": str(raw.get("label") or "Subtítulos"),
                        "default": bool(raw.get("default", index == 0)),
                    }
                )
        geometry = spec.get("grounded_geometry")
        verified_region_ids = frozenset(
            str(item)
            for item in (
                geometry.get("region_ids", [])
                if isinstance(geometry, dict) and geometry.get("verified") is True
                else []
            )
            if isinstance(item, str) and item
        )
        return ResolvedActivityAsset(
            ref=ref,
            url=f"/api/v1/media/artifacts/{artifact.id}/asset",
            mime_type=mime_type,
            alt=alt.strip(),
            long_description=spec.get("long_description")
            if isinstance(spec.get("long_description"), str)
            else None,
            width=_positive_int(spec.get("width")),
            height=_positive_int(spec.get("height")),
            duration_ms=_positive_int(spec.get("duration_ms")),
            transcript=transcript,
            captions=captions,
            verified_region_ids=verified_region_ids,
        )


__all__ = [
    "ActivityAssetResolver",
    "ResolvedActivityAsset",
    "make_activity_asset_ref",
]
