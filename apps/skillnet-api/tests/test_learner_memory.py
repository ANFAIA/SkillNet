"""Unit tests for the learner-memory curation core — no DB, no network, no LLM.

Everything here exercises the pure functions of ``src.services.learner_memory``: the merge
rules (dedupe, supersede, cap), the markdown round-trip (parse → render), and the trimmed
prompt view. The DB-backed :class:`LearnerMemoryService` is covered by the integration
suite; the thinking it delegates to lives here.
"""

from __future__ import annotations

import pytest

from src.services.learner_memory import (
    ENTRY_MAX_CHARS,
    MAX_ENTRIES_PER_SECTION,
    SECTIONS,
    UnknownSectionError,
    blank_markdown,
    clean_entry,
    merge_entry,
    normalize_for_storage,
    note_markdown,
    parse_sections,
    render,
    render_for_prompt,
)


def test_blank_markdown_has_every_section_in_order() -> None:
    md = blank_markdown()
    positions = [md.index(f"## {section}") for section in SECTIONS]
    assert positions == sorted(positions)
    assert md.count("_(sin datos)_") == len(SECTIONS)


def test_clean_entry_collapses_whitespace_and_newlines() -> None:
    assert clean_entry("  hola   \n  mundo  ") == "hola mundo"


def test_clean_entry_caps_length() -> None:
    out = clean_entry("x" * (ENTRY_MAX_CHARS + 50))
    assert len(out) <= ENTRY_MAX_CHARS + 1  # the ellipsis
    assert out.endswith("…")


def test_merge_appends_a_distinct_entry() -> None:
    entries = merge_entry([], "Prefiere ejemplos de cocina")
    entries = merge_entry(entries, "Le gustan las tablas")
    assert entries == ["Prefiere ejemplos de cocina", "Le gustan las tablas"]


def test_merge_dedupes_exact_repeat() -> None:
    entries = merge_entry([], "Prefiere ejemplos de cocina")
    entries = merge_entry(entries, "Prefiere ejemplos de cocina")
    assert entries == ["Prefiere ejemplos de cocina"]


def test_merge_supersedes_near_duplicate_and_keeps_newest_wording() -> None:
    # Same fact reworded / accented differently: the old line is dropped, the new one
    # lands at the end (supersede, not accumulate).
    entries = merge_entry([], "Pidio enfoque practico en el podcast")
    entries = merge_entry(entries, "Pidió enfoque práctico en el podcast otra vez")
    assert len(entries) == 1
    assert entries[0] == "Pidió enfoque práctico en el podcast otra vez"


def test_merge_treats_substring_as_duplicate() -> None:
    entries = merge_entry([], "usa el tutor")
    entries = merge_entry(entries, "usa el tutor con frecuencia por las tardes")
    assert len(entries) == 1
    assert "frecuencia" in entries[0]


def test_merge_keeps_unrelated_entries() -> None:
    entries = merge_entry([], "Prefiere vídeo")
    entries = merge_entry(entries, "Trabaja en cafetería")
    assert len(entries) == 2


def test_merge_caps_to_newest_n() -> None:
    entries: list[str] = []
    for i in range(MAX_ENTRIES_PER_SECTION + 5):
        entries = merge_entry(entries, f"observacion distinta numero {i}")
    assert len(entries) == MAX_ENTRIES_PER_SECTION
    # The newest survives, the oldest fell off the top.
    assert any("numero 12" in e for e in entries)
    assert not any(e.endswith("numero 0") for e in entries)


def test_merge_ignores_empty_text() -> None:
    entries = merge_entry(["algo"], "   \n  ")
    assert entries == ["algo"]


def test_parse_render_round_trip_is_stable() -> None:
    md = note_markdown(None, "Preferencias de contenido", "Prefiere infografías")
    again = render(parse_sections(md))
    assert md == again


def test_note_markdown_rejects_unknown_section() -> None:
    with pytest.raises(UnknownSectionError):
        note_markdown(None, "Sección inventada", "texto")


def test_note_markdown_places_entry_under_the_named_section() -> None:
    md = note_markdown(None, "Notas del tutor", "Necesita más ejemplos")
    section_body = md.split("## Notas del tutor", 1)[1]
    assert "- Necesita más ejemplos" in section_body
    # And it did not leak into another section.
    other = md.split("## Notas del tutor", 1)[0]
    assert "Necesita más ejemplos" not in other


def test_parse_survives_freeform_edit_and_drops_unknown_sections() -> None:
    freeform = (
        "# título\n\n"
        "## Preferencias de contenido\n"
        "- me gusta el audio\n"
        "texto suelto sin viñeta\n\n"
        "## Sección que no existe\n"
        "- esto se descarta\n"
    )
    sections = parse_sections(freeform)
    assert sections["Preferencias de contenido"] == [
        "me gusta el audio",
        "texto suelto sin viñeta",
    ]
    # Unknown headings contribute nothing to the canonical shape.
    canonical = render(sections)
    assert "no existe" not in canonical
    assert "se descarta" not in canonical


def test_normalize_for_storage_caps_total_size() -> None:
    huge = "## Notas del tutor\n" + "\n".join(f"- linea {i}" for i in range(5000))
    out = normalize_for_storage(huge)
    assert len(out) <= 8_050  # MAX_TOTAL_CHARS + the trailing ellipsis line


def test_render_for_prompt_drops_empty_sections_and_is_empty_when_nothing() -> None:
    assert render_for_prompt(None) == ""
    assert render_for_prompt(blank_markdown()) == ""
    md = note_markdown(None, "Cómo aprende", "Repite los ejercicios varias veces")
    prompt = render_for_prompt(md)
    assert "## Cómo aprende" in prompt
    assert "## Perfil declarado" not in prompt  # empty → dropped


def test_render_for_prompt_truncates_to_max_chars() -> None:
    md = None
    for i in range(MAX_ENTRIES_PER_SECTION):
        md = note_markdown(md, "Notas del tutor", f"nota bastante larga numero {i} " * 5)
    prompt = render_for_prompt(md, max_chars=120)
    assert len(prompt) <= 160
    assert "memoria recortada" in prompt
