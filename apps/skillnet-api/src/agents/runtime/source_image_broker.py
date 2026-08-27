"""The **source-image** broker: what a lesson does with a picture the customer already had.

``source_images`` (migration 0026) keeps the images that were embedded in an uploaded
document, and migration 0027 classifies each one — ``screenshot`` | ``diagram`` |
``photo`` | ``unknown``. This module is the seam that decides, per node and per learner,
whether one of them is *placed* in the lesson or *rebuilt* by the generator.

The rule, and it is one sentence:

    **Diagrams get rebuilt. Screenshots get kept.**

A screenshot's information is spatial — where a control sits on a screen — and prose is
strictly worse than the picture, so the original is what the learner sees. A conceptual
diagram is usually better as interactive SkillNet content than as a photograph of a
diagram, so the generator gets its description and re-expresses it with the kit it
already has. A ``photo`` of the customer's real machine or real form is kept for the same
reason a screenshot is: it is evidence, not a drawing. ``unknown`` — which is *every*
image on a deployment with no ``VISION_MODEL`` — is kept, because nothing can be rebuilt
from a description that was never made.

On top of the rule sits ``courses.image_source_policy`` (migration 0028): ``auto`` is the
rule and nobody has to choose it, ``keep_original`` is "do not invent anything, show my
material" (a compliance policy a heuristic can never serve) and ``rebuild`` is everything
in SkillNet's own visual language.

Two things this broker deliberately does **not** share with ``media_broker``:

* **A source image is content, not a modality.** It does not go through
  :func:`~src.agents.runtime.media_broker.gate_offers`, which is exclusive and only fires
  for a learner who declared audio or visual. Routed through that gate the customer's own
  diagram would be invisible to most learners — hidden from exactly the people the manual
  was written for. It is gated here by the course policy, the image's ``kind`` and the
  learner's ``images`` preference, nothing else.
* **It may coexist with a podcast** on the same node (different senses), but never with a
  generated ``InfographicImage``: two competing images on one lesson is worse than either
  alone, and between the customer's real picture and one a model invented, the real one
  wins. :func:`suppress_competing_media` is what performs that removal.

Everything except :func:`source_images_for_node` is pure and unit-testable without a DB.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.personalization.preferences import (
    ImagePreference,
    LearningPreferences,
    normalize_learning_preferences,
)

#: The broker-scoped kit component that places a kept original (``src/render/kit.py``).
SOURCE_IMAGE_COMPONENT = "SourceImage"

#: The generated-image component a kept original evicts. Never both on one lesson.
COMPETING_MEDIA_COMPONENT = "InfographicImage"

#: At most this many originals on one node. Two pictures is already a lot for a lesson
#: screen; the third is decoration, and the cap is what keeps a figure-heavy manual from
#: turning a node into a gallery.
MAX_SOURCE_IMAGES_PER_NODE = 2

#: ``source_images.kind`` (migration 0027). Spelled out rather than imported from the
#: model so this module keeps working — treating everything as ``unknown``, which means
#: *keep* — on a database where 0027 has not been applied yet.
KIND_SCREENSHOT = "screenshot"
KIND_DIAGRAM = "diagram"
KIND_PHOTO = "photo"
KIND_UNKNOWN = "unknown"

#: The one kind the rule rebuilds. Everything else is evidence and gets kept.
REBUILDABLE_KINDS: frozenset[str] = frozenset({KIND_DIAGRAM})

#: ``courses.image_source_policy`` values, as plain strings (see ``CourseImageSourcePolicy``).
POLICY_AUTO = "auto"
POLICY_KEEP_ORIGINAL = "keep_original"
POLICY_REBUILD = "rebuild"
DEFAULT_POLICY = POLICY_AUTO


@dataclass(frozen=True, slots=True)
class SourceImageCandidate:
    """One stored image that could belong to a node, with the provenance a caption needs."""

    image_id: str
    document_id: str
    page: int
    heading: str
    kind: str = KIND_UNKNOWN
    description: str = ""
    width: int = 0
    height: int = 0
    document_title: str = ""

    @property
    def area(self) -> int:
        return max(self.width, 0) * max(self.height, 0)

    def caption(self) -> str:
        """``Fuente: Title > Section, pág. N`` — the provenance a learner reads.

        Reusing a customer's own picture is only defensible if the lesson can say where
        it came from, and it says it in the same shape a passage citation uses, so one
        screen never carries two kinds of citation. See ``GroundedPassage.marker``.

        One deliberate difference from that marker: **"pág.", with the accent.** The
        marker is prompt text a model reads; this is the line printed under the image in
        the lesson, and a learner reading a misspelled word in their own language notices
        it. Do not "fix" this back into agreement with the marker.
        """
        parts = f"Fuente: {self.document_title}" if self.document_title else "Fuente"
        if self.heading:
            parts += f" > {self.heading}"
        if self.page:
            parts += f", pág. {self.page}"
        return parts

    def alt_text(self) -> str:
        """The accessible description: what the vision model saw, or the provenance."""
        described = (self.description or "").strip()
        if described:
            return described
        return f"Imagen del documento de origen ({self.caption()})"


@dataclass(frozen=True, slots=True)
class SourceImageOffer:
    """A kept original: the bytes are placed in the lesson, with their provenance.

    ``document_id`` comes **last**, matching the frontend component's prop order. The
    asset route is document-scoped (``GET /documents/{document_id}/images/{image_id}``),
    so the client needs both ids; putting the one it can degrade without at the end means
    a three-argument program still maps ``image_id``/``alt``/``caption`` correctly and
    fails into a handled "unavailable" state rather than painting the caption as alt text.
    Nothing cross-checks this order automatically — the catalogue drift test skips
    broker-scoped components — so it is pinned by a test on each side.
    """

    image_id: str
    alt: str
    caption: str
    document_id: str = ""

    def fingerprint(self) -> str:
        return f"{SOURCE_IMAGE_COMPONENT}:{self.image_id}"


@dataclass(frozen=True, slots=True)
class SourceImageRebuild:
    """A described original the generator must re-express with the kit — never shown."""

    image_id: str
    description: str
    caption: str

    def fingerprint(self) -> str:
        return f"rebuild:{self.image_id}"


@dataclass(frozen=True, slots=True)
class SourceImageDecision:
    """What this node/learner/policy combination does with the node's source images."""

    policy: str = DEFAULT_POLICY
    kept: tuple[SourceImageOffer, ...] = ()
    rebuilt: tuple[SourceImageRebuild, ...] = ()
    #: How many candidates the node matched *before* the gate. Zero is what makes a node
    #: with no source images contribute nothing at all to the render cache key.
    considered: int = 0

    @property
    def is_empty(self) -> bool:
        return self.considered == 0


EMPTY_DECISION = SourceImageDecision()


# --------------------------------------------------------------------------------------
# 1. Matching: which stored images belong to this node. Deterministic, pure.
# --------------------------------------------------------------------------------------


def _normalize_heading(value: str) -> str:
    return " ".join((value or "").split()).casefold()


def match_source_images(
    images: Iterable[SourceImageCandidate],
    *,
    source_document_id: uuid.UUID | str | None,
    source_headings: Sequence[str],
    limit: int = MAX_SOURCE_IMAGES_PER_NODE,
) -> list[SourceImageCandidate]:
    """The images that belong to a node, best first and capped. Pure.

    An image belongs to a node when it comes from the node's own source document *and*
    sits under one of the headings the node was built from — the same ``source_headings``
    the node stores, because headings survive re-ingestion and chunk ids do not. No
    embedding, no model: a node either cites that section or it does not.

    Order is "prefer the larger", with page proximity breaking ties: among equally sized
    images the one nearest the node's first matched page wins, so a node keeps figures
    that sit together instead of one from page 3 and one from page 40. Page and id break
    what is left, so the result is stable across calls and across processes.

    A decorative row must never reach this function — :meth:`SourceImageRepository.
    list_for_document` excludes them by default and :func:`source_images_for_node` relies
    on that — but one that does is dropped here too, because "the logo in every page
    header" is not this node's illustration under any policy.
    """
    if source_document_id is None or limit <= 0:
        return []
    document_key = str(source_document_id)
    wanted = {_normalize_heading(heading) for heading in source_headings if heading}
    if not wanted:
        return []

    matched = [
        image
        for image in images
        if str(image.document_id) == document_key
        and _normalize_heading(image.heading) in wanted
    ]
    if not matched:
        return []

    anchor = min(image.page for image in matched)
    matched.sort(
        key=lambda image: (
            -image.area,
            abs(image.page - anchor),
            image.page,
            image.image_id,
        )
    )
    return matched[:limit]


# --------------------------------------------------------------------------------------
# 2. The gate: policy x kind x the learner's `images` preference. Pure.
# --------------------------------------------------------------------------------------


def _normalize_policy(value: object) -> str:
    raw = str(getattr(value, "value", value) or "").strip()
    return raw if raw in {POLICY_AUTO, POLICY_KEEP_ORIGINAL, POLICY_REBUILD} else DEFAULT_POLICY


def _rebuilds(candidate: SourceImageCandidate, policy: str) -> bool:
    """Whether this image is re-expressed by the generator instead of being placed.

    ``rebuild`` rebuilds anything it can describe; ``auto`` rebuilds only a classified
    diagram; ``keep_original`` never rebuilds. In every case a rebuild needs a
    description — "the source had an image showing X" is the whole instruction, and
    without X there is nothing to say that would not invite the model to invent it.
    """
    if policy == POLICY_KEEP_ORIGINAL:
        return False
    if not (candidate.description or "").strip():
        return False
    if policy == POLICY_REBUILD:
        return True
    return (candidate.kind or KIND_UNKNOWN) in REBUILDABLE_KINDS


def decide_source_images(
    candidates: Sequence[SourceImageCandidate],
    *,
    policy: object = DEFAULT_POLICY,
    preferences: LearningPreferences | Mapping[str, object] | None = None,
) -> SourceImageDecision:
    """Split a node's matched images into *kept originals* and *rebuild instructions*. Pure.

    Three inputs and no others:

    * the course's ``image_source_policy``,
    * each image's ``kind``,
    * the learner's ``images`` preference — ``avoid`` places no picture at all;
      ``when_useful`` (the default) and ``prefer`` both allow one. It is deliberately not
      routed through the media broker's exclusive modality gate: a source image is
      content, not a modality, and gating it that way would hide the customer's own
      diagram from every learner who declared nothing.

    ``avoid`` suppresses *placing* an image; it does not suppress a **rebuild**, because a
    rebuild produces a ``StepSequence``, a ``Table`` or a sentence — no image at all,
    which is exactly what that learner asked for. So an ``avoid`` learner on
    ``keep_original`` gets nothing (the org forbids inventing, the learner forbids
    pictures) while on ``rebuild`` they still get the content, in words.
    """
    resolved = _normalize_policy(policy)
    if not candidates:
        return SourceImageDecision(policy=resolved)

    prefs = normalize_learning_preferences(preferences)
    place_images = prefs.images is not ImagePreference.AVOID

    kept: list[SourceImageOffer] = []
    rebuilt: list[SourceImageRebuild] = []
    for candidate in candidates:
        if _rebuilds(candidate, resolved):
            rebuilt.append(
                SourceImageRebuild(
                    image_id=candidate.image_id,
                    description=(candidate.description or "").strip(),
                    caption=candidate.caption(),
                )
            )
            continue
        if resolved == POLICY_REBUILD:
            # The org said "our own visual language". With nothing to describe there is
            # no rebuild to ask for either, so this image simply does not appear.
            continue
        if not place_images:
            continue
        kept.append(
            SourceImageOffer(
                image_id=candidate.image_id,
                alt=candidate.alt_text(),
                caption=candidate.caption(),
                document_id=candidate.document_id,
            )
        )

    return SourceImageDecision(
        policy=resolved,
        kept=tuple(kept),
        rebuilt=tuple(rebuilt),
        considered=len(candidates),
    )


def suppress_competing_media(decision: SourceImageDecision, media_offers: Sequence):
    """Drop a generated ``InfographicImage`` when a real source image is being placed.

    Two images competing on one lesson is worse than either alone, and the choice between
    them is not close: one is the organization's own material, the other is one a model
    invented from it. A ``PodcastPlayer`` is untouched — audio and a picture are different
    senses and reinforce each other rather than compete.

    Returns the (possibly shortened) list; the input is never mutated.
    """
    if not decision.kept:
        return list(media_offers)
    return [
        offer
        for offer in media_offers
        if str(getattr(offer, "component", "") or "") != COMPETING_MEDIA_COMPONENT
    ]


# --------------------------------------------------------------------------------------
# 3. Cache key and prompt. Pure.
# --------------------------------------------------------------------------------------


def decision_fingerprint(decision: SourceImageDecision) -> str:
    """A compact, order-stable key of the decision, for the render cache key.

    **Empty whenever the node matched no source image at all**, so every course on
    ``auto`` with nothing to place produces exactly the ``cache_key`` it produced before
    this landed — no existing render is invalidated.

    When the node *does* have candidates the policy itself is part of the key, so flipping
    the setting in the course settings re-renders instead of serving the stale lesson —
    including the case where the flip changes nothing but the prompt (``rebuild``) or
    removes the only picture (``keep_original`` -> ``rebuild`` with no description).
    """
    if decision.is_empty:
        return ""
    parts = [f"policy={decision.policy}"]
    parts.extend(offer.fingerprint() for offer in decision.kept)
    parts.extend(item.fingerprint() for item in decision.rebuilt)
    return "srcimg:" + ",".join(parts)


def decision_prompt_addendum(decision: SourceImageDecision) -> str:
    """The block appended to the node's scoped prompt: place these, re-express those.

    Written the way :func:`~src.agents.runtime.media_broker.offers_prompt_addendum` writes
    its whitelist — an explicit widening of the closed scope, with real ids the model must
    copy verbatim — plus the half that has no component at all: for a rebuilt image the
    model is told *what the source showed* and asked to express it with the kit it already
    has, and told plainly that it must not claim to be showing a picture it is not
    showing.
    """
    if not decision.kept and not decision.rebuilt:
        return ""
    lines: list[str] = ["", "## Imagenes del documento de origen (broker)", ""]

    if decision.kept:
        lines.extend(
            [
                (
                    "El documento del que nace este nodo ya TRAIA estas imagenes. No son "
                    "material generado: son el material del cliente, y aqui valen mas que "
                    "cualquier ilustracion inventada. INCLUYE en la leccion UNO (y solo "
                    "uno) de cada SourceImage listado abajo, con EXACTAMENTE los ids "
                    "indicados (nunca los inventes ni los modifiques) y el caption tal "
                    "cual, que es su procedencia. Colocalo junto al concepto que ilustra, "
                    "nunca como unico contenido de la pantalla:"
                ),
                "",
            ]
        )
        for offer in decision.kept:
            lines.append(
                f'- SourceImage("{offer.image_id}", "{offer.alt}", "{offer.caption}", '
                f'"{offer.document_id}") — Argumentos POSICIONALES, en este orden: '
                "image_id, alt, caption, document_id."
            )
        lines.append("")

    if decision.rebuilt:
        lines.extend(
            [
                (
                    "Ademas, el documento traia estas otras imagenes que NO se van a "
                    "mostrar: son diagramas conceptuales y este curso los reconstruye con "
                    "el kit. Expresa lo que muestran usando los componentes que ya tienes "
                    "(StepSequence, Table, Callout, una frase que diga donde esta cada "
                    "cosa). NO uses SourceImage para ellas, NO digas que hay una imagen y "
                    "NO afirmes estar mostrando algo que no estas mostrando:"
                ),
                "",
            ]
        )
        for item in decision.rebuilt:
            lines.append(f"- El original mostraba: {item.description} ({item.caption})")
        lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# 4. The one impure step: load this node's candidates.
# --------------------------------------------------------------------------------------


def _candidate_from_row(row: object, *, document_title: str = "") -> SourceImageCandidate:
    """Project a ``SourceImage`` row into the pure candidate the rest of the module uses.

    ``kind`` is read with ``getattr`` and a default of ``unknown`` on purpose: the column
    arrives with migration 0027 and ``unknown`` is the *safe* verdict — it keeps the
    original rather than rebuilding from a description that may not exist.
    """
    kind = getattr(row, "kind", None)
    return SourceImageCandidate(
        image_id=str(getattr(row, "id", "")),
        document_id=str(getattr(row, "document_id", "")),
        page=int(getattr(row, "page", 0) or 0),
        heading=str(getattr(row, "heading", "") or ""),
        kind=str(getattr(kind, "value", kind) or KIND_UNKNOWN),
        description=str(getattr(row, "description", "") or ""),
        width=int(getattr(row, "width", 0) or 0),
        height=int(getattr(row, "height", 0) or 0),
        document_title=document_title,
    )


async def source_images_for_node(
    db: AsyncSession, *, node: object, org_id: uuid.UUID
) -> list[SourceImageCandidate]:
    """This node's matched, non-decorative source images. Org-scoped, capped, ordered.

    Returns ``[]`` — one cheap early exit, no query — for the overwhelmingly common node
    that has no source document or no headings, which is what keeps this landing free for
    every course that was created from an idea rather than from a file.
    """
    document_id = getattr(node, "source_document_id", None)
    headings = list(getattr(node, "source_headings", None) or ())
    if document_id is None or not headings:
        return []

    from src.repositories.document_repo import DocumentRepository
    from src.repositories.source_image_repo import SourceImageRepository

    rows = await SourceImageRepository(db).list_for_document(document_id)
    rows = [row for row in rows if getattr(row, "org_id", org_id) == org_id]
    if not rows:
        return []

    document = await DocumentRepository(db).get_by_id(document_id)
    title = str(getattr(document, "title", "") or "")
    candidates = [_candidate_from_row(row, document_title=title) for row in rows]
    return match_source_images(
        candidates,
        source_document_id=document_id,
        source_headings=headings,
    )


__all__ = [
    "COMPETING_MEDIA_COMPONENT",
    "DEFAULT_POLICY",
    "EMPTY_DECISION",
    "KIND_DIAGRAM",
    "KIND_PHOTO",
    "KIND_SCREENSHOT",
    "KIND_UNKNOWN",
    "MAX_SOURCE_IMAGES_PER_NODE",
    "POLICY_AUTO",
    "POLICY_KEEP_ORIGINAL",
    "POLICY_REBUILD",
    "REBUILDABLE_KINDS",
    "SOURCE_IMAGE_COMPONENT",
    "SourceImageCandidate",
    "SourceImageDecision",
    "SourceImageOffer",
    "SourceImageRebuild",
    "decide_source_images",
    "decision_fingerprint",
    "decision_prompt_addendum",
    "match_source_images",
    "source_images_for_node",
    "suppress_competing_media",
]
