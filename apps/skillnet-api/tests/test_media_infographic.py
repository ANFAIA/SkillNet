"""Unit tests for the infographic content agent + generator (no LLM, no network).

Covers the pure :func:`build_prompts` / :func:`parse_infographic` (strict-JSON validation,
citation filtering, field pinning) and the generator's own logic (spec-only shape, facts as
data, citation persistence, progress emission) with the LLM call monkeypatched.
"""

import json

import pytest

from src.models import MediaKind
from src.services.media.grounding import GroundedBundle, GroundedPassage
from src.services.media.infographic import generator as generator_mod
from src.services.media.infographic import spec as spec_mod
from src.services.media.infographic.generator import InfographicGenerator
from src.services.media.subject import MediaContextError, MediaSubject
from src.services.media.infographic.spec import (
    Infographic,
    InfographicSection,
    build_prompts,
    filter_infographic_citations,
    parse_infographic,
)
from src.services.media.jobs import MediaJobContext


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
        "title": "Devoluciones en un vistazo",
        "subtitle": "Politica de la tienda",
        "sections": [
            {
                "heading": "Plazo estandar",
                "stat": "30 dias",
                "one_line": "Desde la fecha de compra con ticket.",
                "citation_ids": ["c1", "cX"],
            },
            {
                "heading": "Producto defectuoso",
                "stat": "60 dias",
                "one_line": "Devolucion gratuita y plazo ampliado.",
                "citation_ids": ["c2"],
            },
        ],
        "orientation": "landscape",
        "layout": "comparison",
        "style": "vivo",
        "language": "en",
    }


# --------------------------------------------------------------------------------------
# parse_infographic
# --------------------------------------------------------------------------------------
def test_parse_infographic_valid() -> None:
    info = parse_infographic(
        json.dumps(_valid_payload()),
        valid_ids=["c1", "c2"],
        language="es",
        style="default",
        orientation="portrait",
    )
    assert info.title == "Devoluciones en un vistazo"
    assert len(info.sections) == 2
    assert info.sections[0].stat == "30 dias"
    # Fields pinned to caller, not model echo.
    assert info.language == "es"
    assert info.style == "default"
    assert info.orientation == "portrait"
    assert info.layout == "comparison"


def test_parse_infographic_filters_citations() -> None:
    info = parse_infographic(json.dumps(_valid_payload()), valid_ids=["c1", "c2"])
    assert info.sections[0].citation_ids == ["c1"]  # cX dropped
    assert info.sections[1].citation_ids == ["c2"]


def test_parse_infographic_allows_missing_stat() -> None:
    payload = {
        "title": "T",
        "sections": [{"heading": "H", "one_line": "una frase", "citation_ids": []}],
    }
    info = parse_infographic(json.dumps(payload), valid_ids=[])
    assert info.sections[0].stat is None


def test_parse_infographic_rejects_no_sections() -> None:
    with pytest.raises(ValueError, match="no sections"):
        parse_infographic(json.dumps({"title": "T", "sections": []}), valid_ids=[])


def test_parse_infographic_rejects_non_json() -> None:
    with pytest.raises(ValueError, match="not JSON"):
        parse_infographic("lo siento", valid_ids=[])


def test_parse_infographic_rejects_missing_title() -> None:
    payload = {"sections": [{"heading": "H", "one_line": "x", "citation_ids": []}]}
    with pytest.raises(ValueError, match="invalid infographic"):
        parse_infographic(json.dumps(payload), valid_ids=[])


# --------------------------------------------------------------------------------------
# filter_infographic_citations
# --------------------------------------------------------------------------------------
def test_filter_infographic_citations_dedupes_and_drops() -> None:
    info = Infographic(
        title="T",
        sections=[
            InfographicSection(heading="A", one_line="x", citation_ids=["c1", "c9", "c1"]),
            InfographicSection(heading="B", one_line="y", citation_ids=["c99"]),
        ],
    )
    cleaned = filter_infographic_citations(info, {"c1", "c2"})
    assert cleaned.sections[0].citation_ids == ["c1"]
    assert cleaned.sections[1].citation_ids == []


# --------------------------------------------------------------------------------------
# build_prompts
# --------------------------------------------------------------------------------------
def _subject() -> MediaSubject:
    """The identity the job runner always has — a boxing course, the bug that started this."""
    return MediaSubject(
        course_title="Boxeo para principiantes",
        node_title="La guardia",
        node_objective="Mantener las manos altas sin bajar la barbilla",
    )


def test_build_prompts_lists_valid_ids_and_injects_context() -> None:
    system, user = build_prompts(
        _bundle("c1", "c2"),
        subject=_subject(),
        language="es",
        style="default",
        orientation="portrait",
    )
    assert "c1, c2" in system
    assert "JSON" in system
    assert "8-18 palabras" in system
    assert "flow" in system
    assert "pasaje c1" in user


def test_build_prompts_carries_the_course_and_node_identity() -> None:
    """A sheet for a boxing course must be told it is about boxing, bundle or no bundle."""
    system, user = build_prompts(
        _bundle("c1"),
        subject=_subject(),
        language="es",
        style="default",
        orientation="portrait",
    )
    assert "Boxeo para principiantes" in system
    assert "Boxeo para principiantes" in user
    assert "La guardia" in user
    assert "Mantener las manos altas sin bajar la barbilla" in user


def test_build_prompts_without_passages_stays_on_the_subject() -> None:
    system, user = build_prompts(
        GroundedBundle(mode="empty", passages=[]),
        subject=_subject(),
        language="es",
        style="default",
        orientation="portrait",
    )
    assert "No hay fuentes citables" in system
    assert "habla en general" not in user
    assert "Boxeo para principiantes" in user


def test_build_prompts_refuses_when_there_is_no_context_at_all() -> None:
    with pytest.raises(MediaContextError):
        build_prompts(
            GroundedBundle(mode="empty", passages=[]),
            subject=None,
            language="es",
            style="default",
            orientation="portrait",
        )


# --------------------------------------------------------------------------------------
# InfographicGenerator.generate — spec-only shape, citation persistence, progress
# --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generator_persists_sections_citations_and_emits_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate(bundle, **kwargs):
        return parse_infographic(json.dumps(_valid_payload()), valid_ids=["c1", "c2"])

    monkeypatch.setattr(spec_mod, "generate_infographic", fake_generate)

    prompts: list[tuple[str, str]] = []

    async def fake_image(prompt, *, size, **kwargs):
        prompts.append((prompt, size))
        return b"PNG-POSTER"

    monkeypatch.setattr(generator_mod, "generate_image", fake_image)

    steps: list[tuple[str, dict]] = []

    async def report(step: str, extra: dict) -> None:
        steps.append((step, extra))

    ctx = MediaJobContext(
        kind=MediaKind.INFOGRAPHIC,
        spec={"language": "es", "style": "default"},
        bundle=_bundle("c1", "c2"),
        progress=report,
    )
    produced = await InfographicGenerator().generate(ctx)

    # The NotebookLM portrait poster is the artifact's main asset.
    assert produced.data == b"PNG-POSTER"
    assert produced.ext == "png"
    # Rendered as a portrait, from a prompt carrying the extracted facts.
    assert prompts and prompts[0][1] == "1024x1536"
    assert "30 dias" in prompts[0][0]
    assert "pure white background" in prompts[0][0]
    assert "no gradients" in prompts[0][0]
    assert "ONLY this exact supplied copy" in prompts[0][0]
    spec = produced.spec_json
    assert spec["generator"] == "infographic"
    assert spec["grounding_mode"] == "chunks"
    assert spec["has_image"] is True
    assert spec["layout"] == "comparison"
    # The facts stay in spec_json for the parallel citations panel.
    assert len(spec["sections"]) == 2
    assert spec["sections"][0]["stat"] == "30 dias"
    assert [s["citation_ids"] for s in spec["sections"]] == [["c1"], ["c2"]]
    assert {c["citation_id"] for c in spec["citations"]} == {"c1", "c2"}
    assert [s[0] for s in steps] == ["datos", "imagen", "listo"]


@pytest.mark.asyncio
async def test_generator_degrades_to_spec_only_when_image_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate(bundle, **kwargs):
        return parse_infographic(json.dumps(_valid_payload()), valid_ids=["c1", "c2"])

    async def failing_image(prompt, *, size, **kwargs):
        raise RuntimeError("image provider down")

    monkeypatch.setattr(spec_mod, "generate_infographic", fake_generate)
    monkeypatch.setattr(generator_mod, "generate_image", failing_image)

    ctx = MediaJobContext(
        kind=MediaKind.INFOGRAPHIC, spec={"language": "es"}, bundle=_bundle("c1", "c2")
    )
    produced = await InfographicGenerator().generate(ctx)

    # A failed image is not a failed job: no bytes, but the facts still ship.
    assert produced.data is None
    assert produced.spec_json["has_image"] is False
    assert len(produced.spec_json["sections"]) == 2


@pytest.mark.asyncio
async def test_generator_without_progress_reporter_is_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate(bundle, **kwargs):
        return parse_infographic(json.dumps(_valid_payload()), valid_ids=[])

    async def fake_image(prompt, *, size, **kwargs):
        return b"PNG-POSTER"

    monkeypatch.setattr(spec_mod, "generate_infographic", fake_generate)
    monkeypatch.setattr(generator_mod, "generate_image", fake_image)

    ctx = MediaJobContext(kind=MediaKind.INFOGRAPHIC, spec={}, bundle=_bundle())
    produced = await InfographicGenerator().generate(ctx)
    assert produced.spec_json["generator"] == "infographic"
