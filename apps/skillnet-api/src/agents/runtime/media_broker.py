"""The media **broker**: offer a node's ready rich-media artefacts to the episode generator.

The episode generator normally emits only the frozen OpenUI catalogue. This broker is the
one seam that lets it place a *grounded reference* to an already-generated media artefact
(a podcast, an infographic) inside a lesson — but only when three things are true at once:

1. a ``MediaArtifact`` of that kind exists for the node and is READY (``status == done``),
2. the learner's declared preference asks for that modality (audio → podcast,
   visual → infographic), and
3. (implicitly) the artefact is grounded in the node's own content — it was generated from
   the node, so the reference is never to an unrelated or invented asset.

The broker never fabricates an id: every offer carries the real ``artifact_id`` of a stored
row, and the corresponding broker-scoped kit component (:data:`kit.PodcastPlayer` /
``InfographicImage``) is what the validator accepts. If the model misuses the offer the
normal gate rejects the program and the runtime falls back — the offer only *widens* what
may be emitted, it does not weaken validation.

Everything here is split into a tiny async lookup (:func:`ready_media_for_node`) and pure,
unit-testable functions (:func:`gate_offers`, :func:`offers_prompt_addendum`,
:func:`offers_fingerprint`) so the gating logic needs no DB.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import MediaArtifact, MediaArtifactStatus, MediaKind
from src.personalization.preferences import (
    CompanionModality,
    ImagePreference,
    LearningPreferences,
    ModalityPreference,
    WebPresentationPreference,
    normalize_learning_preferences,
)

#: Which broker-scoped kit component references each media kind.
MEDIA_COMPONENT_BY_KIND: dict[str, str] = {
    MediaKind.PODCAST.value: "PodcastPlayer",
    MediaKind.INFOGRAPHIC.value: "InfographicImage",
}


@dataclass(frozen=True, slots=True)
class MediaOffer:
    """One artefact the broker offers the generator: a real, ready, grounded reference."""

    kind: str
    component: str
    artifact_id: str
    title: str

    def fingerprint(self) -> str:
        return f"{self.component}:{self.artifact_id}"


async def ready_media_for_node(
    db: AsyncSession, *, node_id: uuid.UUID, org_id: uuid.UUID
) -> dict[str, MediaOffer]:
    """The newest READY podcast/infographic artefact for a node, keyed by kind.

    Org-scoped like every media read. Only ``done`` rows with an asset are returned, so an
    offer always points at bytes the asset route can serve. Newest wins when a node has
    been regenerated.
    """
    rows = (
        await db.execute(
            select(MediaArtifact)
            .where(
                MediaArtifact.node_id == node_id,
                MediaArtifact.org_id == org_id,
                MediaArtifact.status == MediaArtifactStatus.DONE,
                MediaArtifact.kind.in_(
                    [MediaKind.PODCAST, MediaKind.INFOGRAPHIC]
                ),
            )
            .order_by(MediaArtifact.created_at.desc())
        )
    ).scalars().all()

    offers: dict[str, MediaOffer] = {}
    for row in rows:
        kind = str(getattr(row.kind, "value", row.kind))
        component = MEDIA_COMPONENT_BY_KIND.get(kind)
        if component is None or kind in offers:
            continue
        if not row.asset_path:
            continue
        spec = row.spec_json or {}
        title = str(spec.get("title") or "") or (
            "Audio overview" if kind == MediaKind.PODCAST.value else "Infografía"
        )
        offers[kind] = MediaOffer(
            kind=kind,
            component=component,
            artifact_id=str(row.id),
            title=title,
        )
    return offers


def _prefers_audio(prefs: LearningPreferences) -> bool:
    return (
        CompanionModality.AUDIO in prefs.modalities
        or prefs.modality is ModalityPreference.AUDIO
    )


def _prefers_visual(prefs: LearningPreferences) -> bool:
    return (
        prefs.web_presentation is WebPresentationPreference.VISUAL
        or prefs.images is ImagePreference.PREFER
        or prefs.modality is ModalityPreference.VISUAL
    )


def _preferred_kind(prefs: LearningPreferences) -> str | None:
    """The single media kind this learner should be offered, or ``None`` for no offer.

    Exclusive by construction — a learner is never mapped to both modalities:

    * audio preference       → podcast,
    * both audio and visual  → podcast (an explicit companion-audio preference is the
      stronger, opt-in signal, and audio is the one persona whose contrast we protect),
    * visual preference only → infographic,
    * neither declared       → ``None`` (a balanced learner gets no pushed media; the
      sensible default is to stay out of the way rather than force an artefact on a
      learner who declared no modality at all).
    """
    if _prefers_audio(prefs):
        return MediaKind.PODCAST.value
    if _prefers_visual(prefs):
        return MediaKind.INFOGRAPHIC.value
    return None


def gate_offers(
    ready: Mapping[str, MediaOffer],
    preferences: LearningPreferences | Mapping[str, object] | None,
) -> list[MediaOffer]:
    """Pick the ONE ready artefact matching the learner's modality preference. Pure.

    Exclusive gating: an audio learner is offered the podcast and never the infographic, a
    visual learner the infographic and never the podcast, a learner who declared both gets
    the podcast only, and a balanced learner (neither declared) gets nothing. The broker
    therefore never places both modalities on the same lesson — the returned list holds at
    most one offer, and only when its artefact is actually ready for this node.
    """
    prefs = normalize_learning_preferences(preferences)
    preferred = _preferred_kind(prefs)
    if preferred is None:
        return []
    offer = ready.get(preferred)
    return [offer] if offer is not None else []


def offers_fingerprint(offers: Sequence[MediaOffer]) -> str:
    """A compact, order-stable key of the offered artefacts, for the render cache key.

    Empty when nothing is offered, so a node/learner with no media offer keeps the exact
    cache key it had before the broker existed.
    """
    if not offers:
        return ""
    return "media:" + ",".join(offer.fingerprint() for offer in offers)


def offers_prompt_addendum(offers: Sequence[MediaOffer]) -> str:
    """The grounded whitelist block appended to the episode scope when offers exist.

    It explicitly widens the closed scope with the broker-scoped component(s), pins the real
    ``artifact_id`` the model must copy verbatim, and caps usage at one per artefact so the
    lesson references the asset rather than trying to reproduce it.
    """
    if not offers:
        return ""
    lines = [
        "",
        "## Material multimedia disponible para este nodo (broker)",
        "",
        (
            "Para ESTE nodo existe material multimedia ya generado y verificado, elegido "
            "porque coincide con la preferencia de modalidad de este aprendiz. INCLUYE en la "
            "leccion UNO (y solo uno) de cada componente listado abajo: es contenido de "
            "apoyo que el aprendiz espera ver. Usa EXACTAMENTE el artifact_id indicado (nunca "
            "lo inventes ni lo modifiques) y colocalo donde refuerce la leccion (por ejemplo "
            "cerca del cierre o junto al concepto que ilustra), nunca como unico contenido de "
            "la pantalla:"
        ),
        "",
    ]
    for offer in offers:
        if offer.component == "PodcastPlayer":
            lines.append(
                f'- PodcastPlayer("{offer.artifact_id}", "{offer.title}") '
                "— reproductor del audio-overview de este nodo. Argumentos POSICIONALES: "
                "primero el artifact_id, luego el titulo."
            )
        elif offer.component == "InfographicImage":
            lines.append(
                f'- InfographicImage("{offer.artifact_id}", "{offer.title}") '
                "— imagen de la infografia de este nodo. Argumentos POSICIONALES: primero el "
                "artifact_id, luego un alt descriptivo."
            )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "MEDIA_COMPONENT_BY_KIND",
    "MediaOffer",
    "ready_media_for_node",
    "gate_offers",
    "offers_fingerprint",
    "offers_prompt_addendum",
]
