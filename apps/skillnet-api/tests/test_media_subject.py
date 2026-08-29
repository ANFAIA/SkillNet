"""Unit tests for the media subject: the course identity every artifact prompt carries.

The bug these are written against: a boxing course produced an infographic titled "Claves
para una vida saludable" and a deck titled "La Importancia de la Educacion Financiera".
The user prompt of all four families was the grounded bundle and nothing else, so when the
bundle came back empty the model was told to "speak in general" and did — about whatever it
liked, in ``done``, with nobody able to tell it was wrong.

Two things are checked here, and they are checked along the production path rather than by
resemblance: the subject the job runner already holds reaches the string the provider is
actually sent, and a generation with no subject *and* no passages refuses instead of
inventing a topic.
"""

import json

import pytest

from src.models import Course, CourseNode, MediaKind
from src.services.media.assets import AssetStore
from src.services.media.grounding import GroundedBundle, GroundedPassage
from src.services.media.jobs import (
    ERROR_NO_CONTEXT,
    MediaJobContext,
    classify_failure,
    error_message,
)
from src.services.media.podcast import generator as podcast_generator
from src.services.media.podcast import script as podcast_script
from src.services.media.podcast.voices import SynthesisResult
from src.services.media.infographic import generator as infographic_generator
from src.services.media.infographic import spec as infographic_spec
from src.services.media.slides import generator as slides_generator
from src.services.media.slides import spec as slides_spec
from src.services.media.subject import (
    MediaContextError,
    MediaSubject,
    build_user_context,
    subject_from,
    topic_rule,
)
from src.services.media.video import generator as video_generator
from src.services.media.video import narration as video_narration

COURSE_TITLE = "Boxeo para principiantes"
NODE_TITLE = "La guardia"
NODE_OUTCOME = "Mantener las manos altas sin bajar la barbilla"


def _course() -> Course:
    """A real ORM object, unattached: the field names must be the ones production reads."""
    return Course(
        title=COURSE_TITLE,
        description="Fundamentos del boxeo: guardia, desplazamiento y golpes basicos.",
        outcome="Poder entrenar con seguridad una sesion completa",
    )


def _node() -> CourseNode:
    return CourseNode(
        title=NODE_TITLE,
        summary="Como se coloca la guardia y por que protege la barbilla.",
        outcome=NODE_OUTCOME,
    )


def _bundle(*ids: str) -> GroundedBundle:
    return GroundedBundle(
        mode="chunks",
        passages=[
            GroundedPassage(citation_id=cid, text=f"pasaje {cid}", source_title="Manual")
            for cid in ids
        ],
    )


def _empty_bundle() -> GroundedBundle:
    return GroundedBundle(mode="empty", passages=[])


class _CapturingLLM:
    """Stands in for :class:`LLMService` and keeps the exact prompts the provider got."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.system = ""
        self.user = ""

    async def complete(self, system: str, user: str, **_kwargs: object) -> str:
        self.system = system
        self.user = user
        return self.reply


# --------------------------------------------------------------------------------------
# MediaSubject / subject_from
# --------------------------------------------------------------------------------------
def test_subject_from_reads_the_fields_production_stores() -> None:
    subject = subject_from(_course(), _node())
    assert subject.course_title == COURSE_TITLE
    assert subject.course_outcome == "Poder entrenar con seguridad una sesion completa"
    assert subject.node_title == NODE_TITLE
    assert subject.node_objective == NODE_OUTCOME
    assert not subject.is_empty()


def test_subject_from_without_a_node_is_course_only() -> None:
    subject = subject_from(_course(), None)
    assert subject.course_title == COURSE_TITLE
    assert subject.node_title == ""
    assert subject.headline() == f'el curso "{COURSE_TITLE}"'


def test_subject_from_nothing_is_empty() -> None:
    subject = subject_from(None, None)
    assert subject.is_empty()
    assert subject.as_prompt_block() == ""
    assert topic_rule(subject) == ""


def test_subject_block_lists_only_the_fields_that_exist() -> None:
    block = MediaSubject(course_title=COURSE_TITLE).as_prompt_block()
    assert f"Curso: {COURSE_TITLE}" in block
    assert "Leccion" not in block


def test_free_text_is_clipped_before_it_reaches_a_prompt() -> None:
    """Identity is identity, not source material: the passages get the token budget."""
    wordy = Course(title=COURSE_TITLE, description="x" * 5000)
    assert 0 < len(subject_from(wordy, None).course_description) < 1000


def test_job_context_derives_the_subject_from_its_course_and_node() -> None:
    """The runner already builds the context with both; this is the field it feeds."""
    ctx = MediaJobContext(
        kind=MediaKind.PODCAST,
        spec={},
        bundle=_empty_bundle(),
        course=_course(),
        node=_node(),
    )
    assert ctx.subject().course_title == COURSE_TITLE
    assert ctx.subject().node_objective == NODE_OUTCOME


# --------------------------------------------------------------------------------------
# build_user_context
# --------------------------------------------------------------------------------------
def test_user_context_puts_the_identity_before_the_passages() -> None:
    context = build_user_context(_bundle("c1"), subject_from(_course(), _node()))
    assert context.index(COURSE_TITLE) < context.index("pasaje c1")
    assert NODE_TITLE in context
    assert NODE_OUTCOME in context


def test_user_context_without_passages_keeps_the_subject_and_says_so() -> None:
    context = build_user_context(_empty_bundle(), subject_from(_course(), None))
    assert COURSE_TITLE in context
    assert "No hay pasajes de origen citables" in context
    # The sentence that caused the bug must not come back.
    assert "habla en general" not in context


def test_user_context_refuses_when_there_is_nothing_at_all() -> None:
    with pytest.raises(MediaContextError):
        build_user_context(_empty_bundle(), None)


def test_user_context_accepts_an_unknown_grounding_mode() -> None:
    """A new value in ``GroundingMode`` must not need a change here."""
    bundle = GroundedBundle(
        mode="something_new",  # type: ignore[arg-type]
        passages=[GroundedPassage(citation_id="c1", text="pasaje c1", source_title="Manual")],
    )
    assert "pasaje c1" in build_user_context(bundle, None)


def test_user_context_places_extra_sections_between_identity_and_passages() -> None:
    context = build_user_context(
        _bundle("c1"), subject_from(_course(), None), sections=["DIAPOSITIVAS (1):"]
    )
    assert context.index(COURSE_TITLE) < context.index("DIAPOSITIVAS (1):")
    assert context.index("DIAPOSITIVAS (1):") < context.index("pasaje c1")


# --------------------------------------------------------------------------------------
# The failure is recorded the way every other media failure is
# --------------------------------------------------------------------------------------
def test_missing_context_is_its_own_failure_code() -> None:
    code, message = classify_failure(MediaContextError())
    assert code == ERROR_NO_CONTEXT
    assert message == error_message(ERROR_NO_CONTEXT)
    # Not blamed on the provider: no retry against the same course would help.
    assert "provider" not in message.lower()


# --------------------------------------------------------------------------------------
# Each family's LLM wrapper actually sends the identity (the real call path)
# --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_slides_agent_sends_the_identity_to_the_model() -> None:
    llm = _CapturingLLM(
        json.dumps(
            {
                "slides": [
                    {"title": "Guardia", "blocks": [{"type": "text", "text": "Manos arriba."}]}
                ]
            }
        )
    )
    await slides_spec.generate_deck(
        _bundle("c1"), subject=subject_from(_course(), _node()), llm=llm
    )
    assert COURSE_TITLE in llm.user
    assert NODE_TITLE in llm.user
    assert COURSE_TITLE in llm.system


@pytest.mark.asyncio
async def test_infographic_agent_sends_the_identity_to_the_model() -> None:
    llm = _CapturingLLM(
        json.dumps(
            {"title": "Guardia", "sections": [{"heading": "Manos", "one_line": "Arriba."}]}
        )
    )
    await infographic_spec.generate_infographic(
        _bundle("c1"), subject=subject_from(_course(), _node()), llm=llm
    )
    assert COURSE_TITLE in llm.user
    assert NODE_TITLE in llm.user
    assert COURSE_TITLE in llm.system


@pytest.mark.asyncio
async def test_podcast_agent_sends_the_identity_to_the_model() -> None:
    llm = _CapturingLLM(json.dumps({"turns": [{"speaker": "A", "text": "Hola."}]}))
    await podcast_script.generate_script(
        _bundle("c1"), subject=subject_from(_course(), _node()), llm=llm
    )
    assert COURSE_TITLE in llm.user
    assert NODE_TITLE in llm.user
    assert COURSE_TITLE in llm.system


@pytest.mark.asyncio
async def test_narration_agent_sends_the_identity_to_the_model() -> None:
    deck = slides_spec.SlideDeck(
        slides=[slides_spec.Slide(title="Guardia", blocks=[slides_spec.TextBlock(text="Alta.")])]
    )
    llm = _CapturingLLM(json.dumps({"lines": [{"text": "Sube las manos."}]}))
    await video_narration.generate_narration(
        deck, _bundle("c1"), subject=subject_from(_course(), _node()), llm=llm
    )
    assert COURSE_TITLE in llm.user
    assert NODE_TITLE in llm.user
    assert COURSE_TITLE in llm.system


# --------------------------------------------------------------------------------------
# Each generator forwards the context's subject (the link between runner and agent)
# --------------------------------------------------------------------------------------
def _ctx(kind: MediaKind) -> MediaJobContext:
    return MediaJobContext(
        kind=kind, spec={}, bundle=_bundle("c1"), course=_course(), node=_node()
    )


@pytest.mark.asyncio
async def test_slides_generator_forwards_the_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    async def fake_generate_deck(bundle, **kwargs):
        seen.update(kwargs)
        return slides_spec.SlideDeck(slides=[slides_spec.Slide(title="Guardia")])

    monkeypatch.setattr(slides_generator.spec_mod, "generate_deck", fake_generate_deck)
    await slides_generator.SlidesGenerator().generate(_ctx(MediaKind.SLIDES))
    assert seen["subject"].course_title == COURSE_TITLE
    assert seen["subject"].node_title == NODE_TITLE


@pytest.mark.asyncio
async def test_infographic_generator_forwards_the_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict = {}

    async def fake_generate_infographic(bundle, **kwargs):
        seen.update(kwargs)
        return infographic_spec.Infographic(
            title="Guardia",
            sections=[infographic_spec.InfographicSection(heading="Manos", one_line="Arriba.")],
        )

    async def fake_image(prompt, **kwargs):
        return b"PNG"

    monkeypatch.setattr(
        infographic_generator.spec_mod, "generate_infographic", fake_generate_infographic
    )
    monkeypatch.setattr(infographic_generator, "generate_image", fake_image)
    await infographic_generator.InfographicGenerator().generate(_ctx(MediaKind.INFOGRAPHIC))
    assert seen["subject"].course_title == COURSE_TITLE
    assert seen["subject"].node_title == NODE_TITLE


@pytest.mark.asyncio
async def test_podcast_generator_forwards_the_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    async def fake_generate_script(bundle, **kwargs):
        seen.update(kwargs)
        return podcast_script.PodcastScript(
            turns=[podcast_script.PodcastTurn(speaker="A", text="Hola.")],
            format=podcast_script.PodcastFormat.DEEP_DIVE,
            target_seconds=120,
        )

    async def fake_synthesize(script):
        return SynthesisResult(data=b"MP3", ext="mp3", voice_path="fallback")

    monkeypatch.setattr(podcast_generator.script_mod, "generate_script", fake_generate_script)
    monkeypatch.setattr(podcast_generator.voices_mod, "synthesize_podcast", fake_synthesize)
    await podcast_generator.PodcastGenerator().generate(_ctx(MediaKind.PODCAST))
    assert seen["subject"].course_title == COURSE_TITLE
    assert seen["subject"].node_title == NODE_TITLE


@pytest.mark.asyncio
async def test_video_generator_forwards_the_subject_to_both_stages(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    deck_kwargs: dict = {}
    narration_kwargs: dict = {}

    async def fake_generate_deck(bundle, **kwargs):
        deck_kwargs.update(kwargs)
        return slides_spec.SlideDeck(slides=[slides_spec.Slide(title="Guardia")])

    async def fake_generate_narration(deck, bundle, **kwargs):
        narration_kwargs.update(kwargs)
        return video_narration.NarrationScript(
            lines=[video_narration.NarrationLine(text="Sube las manos.")]
        )

    async def fake_synthesize(text, **kwargs):
        return SynthesisResult(data=b"MP3", ext="mp3", voice_path="fallback")

    async def fake_image(prompt, *, size, **kwargs):
        return b"PNG"

    monkeypatch.setattr(video_generator.slides_spec, "generate_deck", fake_generate_deck)
    monkeypatch.setattr(
        video_generator.narration_mod, "generate_narration", fake_generate_narration
    )
    monkeypatch.setattr(video_generator.voice_mod, "synthesize_narration", fake_synthesize)
    monkeypatch.setattr(video_generator, "generate_image", fake_image)

    await video_generator.VideoGenerator(asset_store=AssetStore(tmp_path)).generate(
        _ctx(MediaKind.VIDEO)
    )
    assert deck_kwargs["subject"].course_title == COURSE_TITLE
    assert narration_kwargs["subject"].node_title == NODE_TITLE
