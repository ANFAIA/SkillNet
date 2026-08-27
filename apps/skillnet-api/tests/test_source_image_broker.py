"""The source-image broker: matching, the rule, the three policies, and the cache key.

Pure unit tests (no DB). They pin the decision this feature implements — *diagrams get
rebuilt, screenshots get kept* — the two policy escapes on top of it, the fact that the
learner's ``images`` preference (and not the exclusive modality gate) is what suppresses
a placement, and the one guarantee that keeps this landing free: a course on ``auto``
with no source images produces exactly the cache key it produced before.
"""

from __future__ import annotations

import uuid

import pytest

from src.agents.runtime.media_broker import MediaOffer
from src.agents.runtime.source_image_broker import (
    KIND_DIAGRAM,
    KIND_PHOTO,
    KIND_SCREENSHOT,
    KIND_UNKNOWN,
    MAX_SOURCE_IMAGES_PER_NODE,
    POLICY_AUTO,
    POLICY_KEEP_ORIGINAL,
    POLICY_REBUILD,
    SourceImageCandidate,
    decide_source_images,
    decision_fingerprint,
    decision_prompt_addendum,
    match_source_images,
    suppress_competing_media,
)
from src.render.kit import UI_KIT
from src.render.spec import parse_spec
from src.services.node_render_service import build_render_key

_DOC = uuid.UUID("11111111-1111-1111-1111-111111111111")
_OTHER_DOC = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _image(
    image_id: str,
    *,
    document_id: uuid.UUID = _DOC,
    page: int = 3,
    heading: str = "Abrir una incidencia",
    kind: str = KIND_SCREENSHOT,
    description: str = "",
    width: int = 800,
    height: int = 600,
) -> SourceImageCandidate:
    return SourceImageCandidate(
        image_id=image_id,
        document_id=str(document_id),
        page=page,
        heading=heading,
        kind=kind,
        description=description,
        width=width,
        height=height,
        document_title="Manual de incidencias",
    )


def _prefs(**overrides: object) -> dict:
    base = {
        "version": 3,
        "web_presentation": "balanced",
        "modalities": [],
        "interaction": "standard",
        "detail": "standard",
        "images": "when_useful",
    }
    base.update(overrides)
    return base


# -- 1. matching: deterministic, no model -------------------------------------------


def test_an_image_belongs_to_the_node_that_cites_its_heading() -> None:
    mine = _image("a", heading="Abrir una incidencia")
    theirs = _image("b", heading="Cerrar una incidencia")
    matched = match_source_images(
        [mine, theirs],
        source_document_id=_DOC,
        source_headings=["Abrir una incidencia"],
    )
    assert [image.image_id for image in matched] == ["a"]


def test_headings_match_after_whitespace_and_case_normalization() -> None:
    matched = match_source_images(
        [_image("a", heading="  Abrir   una INCIDENCIA ")],
        source_document_id=_DOC,
        source_headings=["Abrir una incidencia"],
    )
    assert [image.image_id for image in matched] == ["a"]


def test_another_documents_image_never_matches() -> None:
    assert (
        match_source_images(
            [_image("a", document_id=_OTHER_DOC)],
            source_document_id=_DOC,
            source_headings=["Abrir una incidencia"],
        )
        == []
    )


def test_a_node_with_no_document_or_no_headings_matches_nothing() -> None:
    images = [_image("a")]
    assert match_source_images(
        images, source_document_id=None, source_headings=["Abrir una incidencia"]
    ) == []
    assert match_source_images(images, source_document_id=_DOC, source_headings=[]) == []


def test_the_larger_image_wins_and_page_proximity_breaks_ties() -> None:
    small = _image("small", width=100, height=100, page=3)
    big = _image("big", width=1200, height=900, page=40)
    near = _image("near", width=100, height=100, page=4)
    far = _image("far", width=100, height=100, page=90)
    matched = match_source_images(
        [far, small, big, near],
        source_document_id=_DOC,
        source_headings=["Abrir una incidencia"],
        limit=3,
    )
    # Larger first; then, among the equally sized, the ones nearest page 3 (the node's
    # first matched page) rather than the one on page 90.
    assert [image.image_id for image in matched] == ["big", "small", "near"]


def test_matching_is_capped_at_two_per_node() -> None:
    images = [_image(str(i), width=100 + i, height=100) for i in range(5)]
    matched = match_source_images(
        images, source_document_id=_DOC, source_headings=["Abrir una incidencia"]
    )
    assert len(matched) == MAX_SOURCE_IMAGES_PER_NODE == 2


# -- 2. the rule ---------------------------------------------------------------------


def test_auto_keeps_a_screenshot() -> None:
    decision = decide_source_images(
        [_image("a", kind=KIND_SCREENSHOT, description="El boton Guardar arriba a la derecha")],
        policy=POLICY_AUTO,
    )
    assert [offer.image_id for offer in decision.kept] == ["a"]
    assert decision.rebuilt == ()


def test_auto_rebuilds_a_diagram() -> None:
    decision = decide_source_images(
        [_image("a", kind=KIND_DIAGRAM, description="El ciclo de vida de una incidencia")],
        policy=POLICY_AUTO,
    )
    assert decision.kept == ()
    assert [item.image_id for item in decision.rebuilt] == ["a"]
    assert decision.rebuilt[0].description == "El ciclo de vida de una incidencia"


def test_auto_keeps_a_photo_it_is_evidence_not_a_drawing() -> None:
    decision = decide_source_images(
        [_image("a", kind=KIND_PHOTO, description="La maquina, vista frontal")],
        policy=POLICY_AUTO,
    )
    assert [offer.image_id for offer in decision.kept] == ["a"]


def test_unknown_kind_keeps_the_original() -> None:
    """No vision model -> no classification -> nothing to rebuild from. Keep the bytes."""
    decision = decide_source_images(
        [_image("a", kind=KIND_UNKNOWN, description="")], policy=POLICY_AUTO
    )
    assert [offer.image_id for offer in decision.kept] == ["a"]
    assert decision.rebuilt == ()


def test_a_diagram_with_no_description_is_kept_not_rebuilt() -> None:
    """The rebuild instruction *is* the description; without one there is nothing to say."""
    decision = decide_source_images(
        [_image("a", kind=KIND_DIAGRAM, description="")], policy=POLICY_AUTO
    )
    assert [offer.image_id for offer in decision.kept] == ["a"]
    assert decision.rebuilt == ()


# -- 3. the three policy values ------------------------------------------------------


def test_keep_original_keeps_even_a_diagram() -> None:
    decision = decide_source_images(
        [_image("a", kind=KIND_DIAGRAM, description="Un ciclo de vida")],
        policy=POLICY_KEEP_ORIGINAL,
    )
    assert [offer.image_id for offer in decision.kept] == ["a"]
    assert decision.rebuilt == ()


def test_rebuild_rebuilds_even_a_screenshot() -> None:
    decision = decide_source_images(
        [_image("a", kind=KIND_SCREENSHOT, description="El boton Guardar")],
        policy=POLICY_REBUILD,
    )
    assert decision.kept == ()
    assert [item.image_id for item in decision.rebuilt] == ["a"]


def test_rebuild_with_nothing_to_describe_shows_nothing_at_all() -> None:
    decision = decide_source_images(
        [_image("a", kind=KIND_UNKNOWN, description="")], policy=POLICY_REBUILD
    )
    assert decision.kept == ()
    assert decision.rebuilt == ()
    # But the node still *considered* an image, so the key still moves with the policy.
    assert decision.considered == 1


def test_an_unknown_policy_value_falls_back_to_the_rule() -> None:
    decision = decide_source_images([_image("a")], policy="nonsense")
    assert decision.policy == POLICY_AUTO


# -- 4. the learner's `images` preference (NOT the modality gate) --------------------


def test_a_learner_who_avoids_images_gets_nothing() -> None:
    decision = decide_source_images(
        [_image("a", kind=KIND_SCREENSHOT)],
        policy=POLICY_AUTO,
        preferences=_prefs(images="avoid"),
    )
    assert decision.kept == ()
    assert decision.rebuilt == ()


def test_avoid_still_gets_the_content_when_the_course_rebuilds() -> None:
    """A rebuild places no picture, so it is exactly what an ``avoid`` learner wants."""
    decision = decide_source_images(
        [_image("a", kind=KIND_DIAGRAM, description="Un ciclo de vida")],
        policy=POLICY_AUTO,
        preferences=_prefs(images="avoid"),
    )
    assert decision.kept == ()
    assert [item.image_id for item in decision.rebuilt] == ["a"]


def test_a_learner_who_declared_no_modality_still_sees_the_source_image() -> None:
    """The whole point of not routing this through ``gate_offers``.

    That gate is exclusive and fires only for a declared audio/visual learner, so a
    source image behind it would be invisible to the balanced default — the customer's
    own diagram hidden from the people the manual was written for.
    """
    for preference in ("when_useful", "prefer"):
        decision = decide_source_images(
            [_image("a")], policy=POLICY_AUTO, preferences=_prefs(images=preference)
        )
        assert [offer.image_id for offer in decision.kept] == ["a"], preference


# -- 5. composing with the modality gate --------------------------------------------


def test_a_kept_original_evicts_the_generated_infographic_but_not_the_podcast() -> None:
    podcast = MediaOffer(
        kind="podcast", component="PodcastPlayer", artifact_id="aaaa", title="Audio"
    )
    infographic = MediaOffer(
        kind="infographic", component="InfographicImage", artifact_id="bbbb", title="Info"
    )
    decision = decide_source_images([_image("a")], policy=POLICY_AUTO)
    assert [
        offer.component for offer in suppress_competing_media(decision, [podcast])
    ] == ["PodcastPlayer"]
    assert suppress_competing_media(decision, [infographic]) == []
    assert [
        offer.component
        for offer in suppress_competing_media(decision, [podcast, infographic])
    ] == ["PodcastPlayer"]


def test_a_rebuilt_image_leaves_the_infographic_alone() -> None:
    """Nothing is placed, so there are never two images competing."""
    infographic = MediaOffer(
        kind="infographic", component="InfographicImage", artifact_id="bbbb", title="Info"
    )
    decision = decide_source_images(
        [_image("a", kind=KIND_DIAGRAM, description="Un ciclo")], policy=POLICY_AUTO
    )
    assert suppress_competing_media(decision, [infographic]) == [infographic]


# -- 6. the cache key ----------------------------------------------------------------


class _Node:
    id = uuid.UUID("33333333-3333-3333-3333-333333333333")


class _Course:
    schema_version = 1
    intent_density = 3


def _key(**overrides: object) -> str:
    return build_render_key(
        node=_Node(),
        course=_Course(),
        profile=None,
        node_state=None,
        model_key="test-model",
        **overrides,  # type: ignore[arg-type]
    ).cache_key


def test_a_node_with_no_source_images_keeps_the_exact_key_it_had_before() -> None:
    """The one guarantee that makes this landing free: no existing render is invalidated."""
    empty = decide_source_images([], policy=POLICY_AUTO)
    assert decision_fingerprint(empty) == ""
    assert _key(source_image_fingerprint=decision_fingerprint(empty)) == _key()


def test_changing_the_policy_re_renders_a_course_that_has_source_images() -> None:
    candidates = [_image("a", kind=KIND_DIAGRAM, description="Un ciclo de vida")]
    keys = {
        policy: _key(
            source_image_fingerprint=decision_fingerprint(
                decide_source_images(candidates, policy=policy)
            )
        )
        for policy in (POLICY_AUTO, POLICY_KEEP_ORIGINAL, POLICY_REBUILD)
    }
    assert len(set(keys.values())) == 3
    assert _key() not in set(keys.values())


def test_the_chosen_images_are_in_the_fingerprint() -> None:
    one = decide_source_images([_image("a")], policy=POLICY_AUTO)
    other = decide_source_images([_image("b")], policy=POLICY_AUTO)
    assert decision_fingerprint(one) != decision_fingerprint(other)
    assert decision_fingerprint(one) == "srcimg:policy=auto,SourceImage:a"


def test_the_fingerprint_is_order_stable() -> None:
    candidates = [_image("a"), _image("b", page=4)]
    first = decide_source_images(candidates, policy=POLICY_AUTO)
    second = decide_source_images(candidates, policy=POLICY_AUTO)
    assert decision_fingerprint(first) == decision_fingerprint(second)


# -- 7. the prompt and the component -------------------------------------------------


def test_no_decision_means_no_prompt_block() -> None:
    assert decision_prompt_addendum(decide_source_images([], policy=POLICY_AUTO)) == ""


def test_the_addendum_pins_both_ids_in_the_frontend_prop_order() -> None:
    decision = decide_source_images([_image("a", description="El boton Guardar")], policy=POLICY_AUTO)
    addendum = decision_prompt_addendum(decision)
    assert (
        f'SourceImage("a", "El boton Guardar", '
        f'"Fuente: Manual de incidencias > Abrir una incidencia, pág. 3", "{_DOC}")'
    ) in addendum
    assert "image_id, alt, caption, document_id" in addendum


def test_a_kept_original_carries_the_document_id_the_asset_route_needs() -> None:
    """``GET /documents/{document_id}/images/{image_id}`` — one id cannot address it."""
    decision = decide_source_images([_image("a")], policy=POLICY_AUTO)
    assert decision.kept[0].document_id == str(_DOC)


def test_the_addendum_for_a_rebuild_describes_without_claiming_to_show() -> None:
    decision = decide_source_images(
        [_image("a", kind=KIND_DIAGRAM, description="El ciclo de vida de una incidencia")],
        policy=POLICY_AUTO,
    )
    addendum = decision_prompt_addendum(decision)
    assert "El ciclo de vida de una incidencia" in addendum
    assert "SourceImage(" not in addendum
    assert "NO uses SourceImage" in addendum


def test_source_image_is_not_in_the_model_emittable_catalogue() -> None:
    """Broker-scoped: validated by the kit, never advertised in the frozen catalogue.

    This is what keeps ``openui_catalog.json`` (and its drift digest) untouched.
    """
    assert "SourceImage" not in UI_KIT.llm_names
    assert "SourceImage" in UI_KIT.names
    spec = UI_KIT.get("SourceImage")
    assert spec is not None
    assert spec.broker_scoped is True
    # Prop ORDER is load-bearing and nothing cross-checks it automatically: the
    # catalogue drift test skips broker-scoped components, so this assertion and the
    # frontend's own `propOrder` test are the only alarm. `document_id` is LAST so a
    # three-argument program still maps the first three correctly and degrades into a
    # handled "unavailable" state instead of painting the caption as alt text.
    assert spec.prop_names == ("image_id", "alt", "caption", "document_id")


def test_a_program_carrying_a_source_image_validates() -> None:
    payload = {
        "version": "skillnet-ui/1",
        "format": "explanation",
        "root": "root",
        "components": [
            {"id": "root", "type": "Stack", "props": {"gap": "md"}, "children": ["a", "img"]},
            {"id": "a", "type": "TextContent", "props": {"text": "Guia.", "variant": "lead"}},
            {
                "id": "img",
                "type": "SourceImage",
                "props": {
                    "image_id": "abc",
                    "alt": "El boton Guardar",
                    "caption": "Fuente: Manual > Abrir, pág. 3",
                    "document_id": "def",
                },
            },
        ],
    }
    spec = parse_spec(payload)
    assert "SourceImage" in {component.type for component in spec.components}


# -- 8. the setting: editable afterwards, never asked at creation --------------------


def test_creation_never_asks_for_the_policy() -> None:
    """The rule decides. The setting exists for the two cases the rule cannot serve."""
    from src.schemas.course import CourseCreate, CourseRead, CourseUpdate

    assert "image_source_policy" not in CourseCreate.model_fields
    assert "image_source_policy" in CourseUpdate.model_fields
    assert CourseRead.model_fields["image_source_policy"].default == POLICY_AUTO


def test_a_course_that_predates_the_column_projects_as_auto() -> None:
    from types import SimpleNamespace

    from src.routes.courses import _image_source_policy

    assert _image_source_policy(SimpleNamespace()) == POLICY_AUTO  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_update_casts_and_rejects_the_policy_like_tutor_style() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.core.exceptions import ValidationError
    from src.models import ArtifactGeneratePolicy, CourseImageSourcePolicy
    from src.services.course_service import CourseService

    def _repo(course):
        return SimpleNamespace(
            session=SimpleNamespace(),
            get_scoped=AsyncMock(return_value=course),
            update=AsyncMock(side_effect=lambda course, **kwargs: course),
        )

    course = SimpleNamespace(
        id=uuid.uuid4(),
        image_source_policy=CourseImageSourcePolicy.AUTO,
        artifact_generate_policy=ArtifactGeneratePolicy.ADMIN,
    )
    repo = _repo(course)
    updated = await CourseService(repo).update(
        course_id=course.id,
        org_id=uuid.uuid4(),
        changes={"image_source_policy": "keep_original"},
    )
    assert updated is course
    repo.update.assert_awaited_once_with(
        course, image_source_policy=CourseImageSourcePolicy.KEEP_ORIGINAL
    )

    with pytest.raises(ValidationError):
        await CourseService(_repo(course)).update(
            course_id=course.id,
            org_id=uuid.uuid4(),
            changes={"image_source_policy": "whatever"},
        )
