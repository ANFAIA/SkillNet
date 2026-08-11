from scripts.personalization_sweep import compare_programs, safe_profile, summarize_render


def test_compare_programs_normalizes_trailing_whitespace() -> None:
    result = compare_programs("Text(\"hola\")  \n", "Text(\"hola\")")
    assert result["identical"] is True
    assert result["similarity"] == 1.0


def test_summarize_render_extracts_components_and_hash() -> None:
    result = summarize_render(
        {"render_id": "r1", "program": 'Stack(\n  Text("hola")\n)'}
    )
    assert result["components"] == ["Stack", "Text"]
    assert len(result["sha256"]) == 64
    assert result["program"].startswith("Stack(")


def test_safe_profile_drops_unapproved_fields() -> None:
    result = safe_profile({"role_title": "Camarero", "memory_md": "privado", "secret": "x"})
    assert result == {"role_title": "Camarero"}
