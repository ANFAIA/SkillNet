"""Unit tests for the slide deck agent + generator (no LLM, no network).

Covers the two pure functions that carry the discipline — :func:`build_prompts` and
:func:`parse_deck` (strict-JSON validation, block-vocabulary enforcement, citation
filtering, field pinning) — and the generator's own logic (spec_json shape, citation
persistence, progress emission) with the LLM call monkeypatched.
"""

import json

import pytest

from src.models import MediaKind
from src.services.media.grounding import GroundedBundle, GroundedPassage
from src.services.media.jobs import MediaJobContext
from src.services.media.slides import spec as spec_mod
from src.services.media.slides.generator import SlidesGenerator
from src.services.media.slides.spec import (
    Slide,
    SlideDeck,
    build_prompts,
    filter_deck_citations,
    parse_deck,
)


def _bundle(*ids: str) -> GroundedBundle:
    return GroundedBundle(
        mode="chunks",
        passages=[
            GroundedPassage(citation_id=cid, text=f"pasaje {cid}", source_title="Manual")
            for cid in (ids or ("c1", "c2"))
        ],
    )


def _valid_payload() -> dict:
    return {
        "slides": [
            {
                "title": "Devoluciones",
                "subtitle": "Lo esencial",
                "composition": "split",
                "visual_brief": "Una caja abierta junto a un recibo",
                "blocks": [
                    {"type": "text", "text": "Aceptamos devoluciones.", "variant": "lead"},
                    {"type": "callout", "tone": "info", "text": "Con ticket."},
                ],
                "citation_ids": ["c1", "cX"],
            },
            {
                "title": "Plazos",
                "composition": "data",
                "blocks": [
                    {
                        "type": "chart",
                        "kind": "bar",
                        "title": "Dias por caso",
                        "labels": ["Normal", "Defectuoso"],
                        "values": [30, 60],
                    }
                ],
                "citation_ids": ["c2"],
            },
        ],
        "theme": "modelo",
        "language": "en",
    }


# --------------------------------------------------------------------------------------
# parse_deck
# --------------------------------------------------------------------------------------
def test_parse_deck_valid_with_kit_blocks() -> None:
    deck = parse_deck(
        json.dumps(_valid_payload()),
        valid_ids=["c1", "c2"],
        language="es",
        theme="default",
    )
    assert len(deck.slides) == 2
    assert deck.slides[0].blocks[0].type == "text"
    assert deck.slides[0].blocks[1].type == "callout"
    assert deck.slides[0].composition == "split"
    assert deck.slides[0].visual_brief == "Una caja abierta junto a un recibo"
    assert deck.slides[1].blocks[0].type == "chart"
    # Format/language/theme pinned to the caller, not the model's echo.
    assert deck.language == "es"
    assert deck.theme == "default"


def test_parse_deck_accepts_dense_grid_and_timeline_blocks() -> None:
    payload = {
        "slides": [
            {
                "title": "Capacidades",
                "composition": "grid",
                "blocks": [
                    {"type": "card", "title": "Comprender", "text": "Leer el contexto."},
                    {"type": "card", "title": "Actuar", "text": "Acordar el paso."},
                ],
            },
            {
                "title": "Proceso",
                "composition": "timeline",
                "blocks": [
                    {
                        "type": "timeline",
                        "label": "Ciclo",
                        "steps": ["Recibir", "Cerrar"],
                        "details": ["Recopilar contexto", "Confirmar el resultado"],
                    }
                ],
            },
        ]
    }

    deck = parse_deck(json.dumps(payload), valid_ids=[])

    assert [block.type for block in deck.slides[0].blocks] == ["card", "card"]
    assert deck.slides[1].blocks[0].type == "timeline"


def test_parse_deck_filters_citations() -> None:
    deck = parse_deck(json.dumps(_valid_payload()), valid_ids=["c1", "c2"])
    # cX is not in the bundle: dropped. c1/c2 kept.
    assert deck.slides[0].citation_ids == ["c1"]
    assert deck.slides[1].citation_ids == ["c2"]


def test_parse_deck_drops_unknown_block_types() -> None:
    payload = {
        "slides": [
            {
                "title": "S",
                "blocks": [
                    {"type": "text", "text": "ok"},
                    {"type": "hologram", "text": "no existe"},
                ],
                "citation_ids": [],
            }
        ],
    }
    deck = parse_deck(json.dumps(payload), valid_ids=[])
    # The unknown block was dropped before validation; the known one survives.
    assert [b.type for b in deck.slides[0].blocks] == ["text"]


def test_parse_deck_tolerates_json_wrapped_in_prose() -> None:
    inner = {"slides": [{"title": "Uno", "blocks": [], "citation_ids": []}]}
    raw = f"Aqui tienes:\n```json\n{json.dumps(inner)}\n```\ngracias"
    deck = parse_deck(raw, valid_ids=[])
    assert len(deck.slides) == 1
    assert deck.slides[0].composition == "auto"


def test_parse_deck_rejects_no_slides() -> None:
    with pytest.raises(ValueError, match="no slides"):
        parse_deck(json.dumps({"slides": []}), valid_ids=[])


def test_parse_deck_rejects_non_json() -> None:
    with pytest.raises(ValueError, match="not JSON"):
        parse_deck("lo siento", valid_ids=[])


def test_parse_deck_rejects_chart_without_values() -> None:
    payload = {
        "slides": [
            {
                "title": "S",
                "blocks": [
                    {"type": "chart", "kind": "bar", "title": "t", "labels": ["a"], "values": []}
                ],
                "citation_ids": [],
            }
        ]
    }
    with pytest.raises(ValueError, match="invalid deck"):
        parse_deck(json.dumps(payload), valid_ids=[])


# --------------------------------------------------------------------------------------
# filter_deck_citations
# --------------------------------------------------------------------------------------
def test_filter_deck_citations_dedupes_and_drops() -> None:
    deck = SlideDeck(
        slides=[
            Slide(title="A", citation_ids=["c1", "c9", "c1"]),
            Slide(title="B", citation_ids=["c99"]),
        ]
    )
    cleaned = filter_deck_citations(deck, {"c1", "c2"})
    assert cleaned.slides[0].citation_ids == ["c1"]
    assert cleaned.slides[1].citation_ids == []


# --------------------------------------------------------------------------------------
# build_prompts
# --------------------------------------------------------------------------------------
def test_build_prompts_lists_valid_ids_and_injects_context() -> None:
    system, user = build_prompts(_bundle("c1", "c2"), language="es", theme="default")
    assert "c1, c2" in system
    assert "JSON" in system
    assert "No propongas ni describas imagenes" in system
    assert "comparison" in system
    assert "60-120 palabras" in system
    assert "marco 16:9 fijo" in system
    assert 'composition="grid"' in system
    assert '"type":"timeline"' in system
    assert "pasaje c1" in user
    assert "Manual" in user


def test_build_prompts_handles_empty_bundle() -> None:
    system, user = build_prompts(
        GroundedBundle(mode="empty", passages=[]), language="es", theme="default"
    )
    assert "No hay fuentes citables" in system
    assert "general" in user.lower()


# --------------------------------------------------------------------------------------
# SlidesGenerator.generate — spec_json shape, citation persistence, progress
# --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generator_persists_slides_citations_and_emits_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate_deck(bundle, **kwargs):
        assert kwargs["language"] == "es"
        return parse_deck(json.dumps(_valid_payload()), valid_ids=["c1", "c2"])

    monkeypatch.setattr(spec_mod, "generate_deck", fake_generate_deck)

    steps: list[tuple[str, dict]] = []

    async def report(step: str, extra: dict) -> None:
        steps.append((step, extra))

    ctx = MediaJobContext(
        kind=MediaKind.SLIDES,
        spec={"language": "es", "theme": "default"},
        bundle=_bundle("c1", "c2"),
        progress=report,
    )
    produced = await SlidesGenerator().generate(ctx)

    # Presentations are deliberately spec-only: components render all visual structure.
    assert produced.data is None
    assert produced.ext is None
    spec = produced.spec_json
    assert spec["generator"] == "slides"
    assert spec["grounding_mode"] == "chunks"
    assert len(spec["slides"]) == 2
    assert spec["has_cover"] is False
    # Per-slide citation ids persisted for the parallel panel.
    assert [s["citation_ids"] for s in spec["slides"]] == [["c1"], ["c2"]]
    assert [s["composition"] for s in spec["slides"]] == ["split", "data"]
    assert all("image_ref" not in slide for slide in spec["slides"])
    # Citation metadata resolves each id.
    assert {c["citation_id"] for c in spec["citations"]} == {"c1", "c2"}
    assert [s[0] for s in steps] == ["guion", "listo"]


@pytest.mark.asyncio
async def test_generator_ignores_legacy_cover_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate_deck(bundle, **kwargs):
        return parse_deck(json.dumps(_valid_payload()), valid_ids=["c1", "c2"])

    monkeypatch.setattr(spec_mod, "generate_deck", fake_generate_deck)

    ctx = MediaJobContext(
        kind=MediaKind.SLIDES,
        spec={"language": "es", "cover": True},
        bundle=_bundle("c1", "c2"),
    )
    produced = await SlidesGenerator().generate(ctx)
    assert produced.data is None
    assert produced.spec_json["has_cover"] is False


@pytest.mark.asyncio
async def test_generator_without_progress_reporter_is_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate_deck(bundle, **kwargs):
        return parse_deck(json.dumps(_valid_payload()), valid_ids=[])

    monkeypatch.setattr(spec_mod, "generate_deck", fake_generate_deck)

    ctx = MediaJobContext(kind=MediaKind.SLIDES, spec={}, bundle=_bundle())
    produced = await SlidesGenerator().generate(ctx)
    assert produced.spec_json["generator"] == "slides"
