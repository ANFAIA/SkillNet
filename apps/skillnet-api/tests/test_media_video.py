"""Unit tests for the Video Overview narration agent + generator (no LLM/TTS/network).

Covers the pure functions that carry the narration discipline — :func:`build_prompts`,
:func:`parse_lines`, :func:`align_narration` (strict-JSON validation, citation filtering,
one-line-per-slide alignment with slide fallback) — and the generator's own logic
(spec_json shape, per-slide narration/citation/audio_ref persistence, progress emission,
clip storage) with the deck agent, the narration agent and the TTS path monkeypatched.
"""

import json

import pytest

from src.models import MediaKind
from src.services.media.assets import AssetStore
from src.services.media.grounding import GroundedBundle, GroundedPassage
from src.services.media.jobs import MediaJobContext
from src.services.media.podcast import script as podcast_script
from src.services.media.podcast.voices import SynthesisResult
from src.services.media.slides.spec import (
    CalloutBlock,
    Slide,
    SlideDeck,
    TextBlock,
)
from src.services.media.video import generator as generator_mod
from src.services.media.video.generator import VideoGenerator, _summarize_voice_paths
from src.services.media.video.narration import (
    NarrationLine,
    NarrationScript,
    align_narration,
    build_prompts,
    fallback_narration,
    parse_lines,
)
from src.services.media.video.voice import narration_script


def _bundle(*ids: str) -> GroundedBundle:
    return GroundedBundle(
        mode="chunks",
        passages=[
            GroundedPassage(citation_id=cid, text=f"pasaje {cid}", source_title="Manual")
            for cid in (ids or ("c1", "c2"))
        ],
    )


def _deck() -> SlideDeck:
    return SlideDeck(
        slides=[
            Slide(
                title="Devoluciones",
                subtitle="Lo esencial",
                blocks=[TextBlock(text="Aceptamos devoluciones en 30 dias.")],
                citation_ids=["c1"],
            ),
            Slide(
                title="Defectuosos",
                blocks=[CalloutBlock(tone="info", text="Gratis y 60 dias.")],
                citation_ids=["c2"],
            ),
        ]
    )


# --------------------------------------------------------------------------------------
# parse_lines
# --------------------------------------------------------------------------------------
def test_parse_lines_valid_and_filters_citations() -> None:
    raw = json.dumps(
        {
            "lines": [
                {"text": "Aqui explicamos las devoluciones.", "citation_ids": ["c1", "cX"]},
                {"text": "Y los productos defectuosos.", "citation_ids": ["c2"]},
            ],
            "language": "es",
        }
    )
    lines = parse_lines(raw, valid_ids=["c1", "c2"])
    assert [line.text for line in lines] == [
        "Aqui explicamos las devoluciones.",
        "Y los productos defectuosos.",
    ]
    # cX is not in the bundle: dropped. c1/c2 kept.
    assert [line.citation_ids for line in lines] == [["c1"], ["c2"]]


def test_parse_lines_drops_malformed_but_keeps_the_rest() -> None:
    raw = json.dumps(
        {
            "lines": [
                {"text": "", "citation_ids": []},  # empty -> invalid, dropped
                {"text": "Sobrevive.", "citation_ids": []},
                "no soy un objeto",  # not a dict, dropped
            ]
        }
    )
    lines = parse_lines(raw, valid_ids=[])
    assert [line.text for line in lines] == ["Sobrevive."]


def test_parse_lines_tolerates_json_wrapped_in_prose() -> None:
    inner = {"lines": [{"text": "Uno", "citation_ids": []}]}
    raw = f"Claro:\n```json\n{json.dumps(inner)}\n```\ngracias"
    lines = parse_lines(raw, valid_ids=[])
    assert len(lines) == 1


def test_parse_lines_rejects_non_json() -> None:
    with pytest.raises(ValueError, match="not JSON"):
        parse_lines("lo siento", valid_ids=[])


def test_parse_lines_rejects_no_usable_lines() -> None:
    with pytest.raises(ValueError, match="no lines"):
        parse_lines(json.dumps({"lines": []}), valid_ids=[])


# --------------------------------------------------------------------------------------
# align_narration + fallback
# --------------------------------------------------------------------------------------
def test_align_narration_one_line_per_slide_exactly() -> None:
    deck = _deck()
    # Model returned only one line for a two-slide deck: the second is filled from the slide.
    lines = [NarrationLine(text="Narracion 1", citation_ids=["c1"])]
    aligned = align_narration(deck, lines)
    assert len(aligned) == 2
    assert aligned[0].text == "Narracion 1"
    # Slide 2 had no subtitle -> falls back to its first callout block text.
    assert aligned[1].text == "Gratis y 60 dias."
    assert aligned[1].citation_ids == ["c2"]


def test_align_narration_truncates_extra_lines() -> None:
    deck = _deck()
    lines = [
        NarrationLine(text="1"),
        NarrationLine(text="2"),
        NarrationLine(text="3 sobra"),
    ]
    aligned = align_narration(deck, lines)
    assert [line.text for line in aligned] == ["1", "2"]


def test_fallback_narration_prefers_subtitle_then_block_then_title() -> None:
    assert (
        fallback_narration(Slide(title="T", subtitle="Sub", blocks=[])) == "Sub"
    )
    assert (
        fallback_narration(
            Slide(title="T", blocks=[TextBlock(text="Cuerpo")])
        )
        == "Cuerpo"
    )
    assert fallback_narration(Slide(title="Solo titulo", blocks=[])) == "Solo titulo"


# --------------------------------------------------------------------------------------
# build_prompts
# --------------------------------------------------------------------------------------
def test_build_prompts_asks_for_exactly_n_lines_and_lists_ids() -> None:
    system, user = build_prompts(_deck(), _bundle("c1", "c2"), language="es")
    assert "EXACTAMENTE 2 lineas" in system
    assert "c1, c2" in system
    # Slide summaries carry the on-slide text into the user prompt.
    assert "Devoluciones" in user
    assert "pasaje c1" in user


def test_build_prompts_handles_empty_bundle() -> None:
    system, user = build_prompts(
        _deck(), GroundedBundle(mode="empty", passages=[]), language="es"
    )
    assert "No hay fuentes citables" in system


# --------------------------------------------------------------------------------------
# voice: one-turn single-host script
# --------------------------------------------------------------------------------------
def test_narration_script_is_single_host_brief() -> None:
    script = narration_script("Una frase corta.", language="es")
    assert len(script.turns) == 1
    assert script.turns[0].speaker == "A"
    assert script.format is podcast_script.PodcastFormat.THE_BRIEF
    assert script.target_seconds >= 4


# --------------------------------------------------------------------------------------
# _summarize_voice_paths
# --------------------------------------------------------------------------------------
def test_summarize_voice_paths() -> None:
    assert _summarize_voice_paths([]) == "none"
    assert _summarize_voice_paths(["fallback", "fallback"]) == "fallback"
    assert _summarize_voice_paths(["dialogue", "cache"]) == "mixed"


# --------------------------------------------------------------------------------------
# VideoGenerator.generate — spec_json shape, persistence, progress, clip storage
# --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generator_persists_slides_narration_and_stores_clips(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    async def fake_generate_deck(bundle, **kwargs):
        assert kwargs["language"] == "es"
        return _deck()

    async def fake_generate_narration(deck, bundle, **kwargs):
        return NarrationScript(
            lines=[
                NarrationLine(text="Locucion 1", citation_ids=["c1"]),
                NarrationLine(text="Locucion 2", citation_ids=["c2"]),
            ],
            language="es",
        )

    seen_texts: list[str] = []

    async def fake_synthesize(text, **kwargs):
        seen_texts.append(text)
        # Distinct bytes per line -> distinct content hashes / audio_refs.
        return SynthesisResult(
            data=f"MP3-{text}".encode(), ext="mp3", voice_path="fallback"
        )

    image_sizes: list[str] = []

    async def fake_image(prompt, *, size, **kwargs):
        image_sizes.append(size)
        # Distinct bytes per slide title -> distinct content hashes / image_refs.
        return f"PNG-{prompt[:48]}".encode()

    monkeypatch.setattr(generator_mod.slides_spec, "generate_deck", fake_generate_deck)
    monkeypatch.setattr(
        generator_mod.narration_mod, "generate_narration", fake_generate_narration
    )
    monkeypatch.setattr(
        generator_mod.voice_mod, "synthesize_narration", fake_synthesize
    )
    monkeypatch.setattr(generator_mod, "generate_image", fake_image)

    steps: list[tuple[str, dict]] = []

    async def report(step: str, extra: dict) -> None:
        steps.append((step, extra))

    store = AssetStore(tmp_path)
    ctx = MediaJobContext(
        kind=MediaKind.VIDEO,
        spec={"language": "es", "theme": "default"},
        bundle=_bundle("c1", "c2"),
        progress=report,
    )
    produced = await VideoGenerator(asset_store=store).generate(ctx)

    # Spec-only to the spine: the clips are stored by the generator, not handed back.
    assert produced.data is None
    spec = produced.spec_json
    assert spec["generator"] == "video"
    assert spec["grounding_mode"] == "chunks"
    assert spec["voice_path"] == "fallback"
    assert len(spec["slides"]) == 2

    slides = spec["slides"]
    assert [s["narration"] for s in slides] == ["Locucion 1", "Locucion 2"]
    assert [s["narration_citation_ids"] for s in slides] == [["c1"], ["c2"]]
    # The shown-slide citation ids (from the deck) are preserved too.
    assert [s["citation_ids"] for s in slides] == [["c1"], ["c2"]]
    # Each slide references a stored clip that actually exists on disk with those bytes.
    for s in slides:
        assert s["audio_ext"] == "mp3"
        path = store.path_for(s["audio_ref"], "mp3")
        assert path.exists()
        assert path.read_bytes() == f"MP3-{s['narration']}".encode()
    # Distinct lines -> distinct clips.
    assert slides[0]["audio_ref"] != slides[1]["audio_ref"]

    # Each slide also references a landscape illustration stored on disk.
    assert image_sizes == ["1536x1024", "1536x1024"]
    for s in slides:
        assert s["image_ext"] == "png"
        assert store.path_for(s["image_ref"], "png").exists()

    # Citation metadata resolves each id.
    assert {c["citation_id"] for c in spec["citations"]} == {"c1", "c2"}
    # The five progress steps fired in order (voz + ilustraciones between narracion/listo).
    assert [s[0] for s in steps] == [
        "diapositivas",
        "narracion",
        "voz",
        "ilustraciones",
        "listo",
    ]
    assert steps[-1][1]["voice_path"] == "fallback"
    assert seen_texts == ["Locucion 1", "Locucion 2"]


@pytest.mark.asyncio
async def test_generator_without_progress_reporter_is_silent(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    async def fake_generate_deck(bundle, **kwargs):
        return _deck()

    async def fake_generate_narration(deck, bundle, **kwargs):
        return NarrationScript(
            lines=[NarrationLine(text="a"), NarrationLine(text="b")], language="es"
        )

    async def fake_synthesize(text, **kwargs):
        return SynthesisResult(data=b"X", ext="mp3", voice_path="dialogue")

    async def fake_image(prompt, *, size, **kwargs):
        return b"PNG"

    monkeypatch.setattr(generator_mod.slides_spec, "generate_deck", fake_generate_deck)
    monkeypatch.setattr(
        generator_mod.narration_mod, "generate_narration", fake_generate_narration
    )
    monkeypatch.setattr(
        generator_mod.voice_mod, "synthesize_narration", fake_synthesize
    )
    monkeypatch.setattr(generator_mod, "generate_image", fake_image)

    # No progress reporter: emit() must be a no-op, not a crash.
    ctx = MediaJobContext(kind=MediaKind.VIDEO, spec={}, bundle=_bundle())
    produced = await VideoGenerator(asset_store=AssetStore(tmp_path)).generate(ctx)
    assert produced.spec_json["generator"] == "video"
    # Both slides shared the same bytes -> deduped to one clip, both refs identical.
    slides = produced.spec_json["slides"]
    assert slides[0]["audio_ref"] == slides[1]["audio_ref"]
