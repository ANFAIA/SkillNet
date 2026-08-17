"""The render ``cache_key`` of §3.4 — the exact checklist of §12.2.

The key must change with ``schema_version``, ``preset``, ``role_bucket``,
``scaffold_band``, ``effective_density`` and ``PROMPT_VERSION``; it must **not**
change with ``user_id`` (it is not an input at all) nor with ``mastery`` inside a
single ``scaffold_band``; and two profiles with a different ``role_title`` must
not share a key.

No DB, no network.
"""

import hashlib
import inspect
import uuid

import pytest

from src.llm.prompts.runtime import build_ui_prompt
from src.models import LearnerExperience, LearningProfile
from src.services.cache_key import (
    ROLE_BUCKET_MAX_LENGTH,
    accessibility_bucket,
    build_cache_key,
    cache_key_material,
    effective_density,
    role_bucket,
    slug,
)

NODE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

BASE = dict(
    node_id=NODE_ID,
    schema_version=3,
    preset="standard",
    experience_level="some",
    scaffold_band="neutral",
    effective_density=3,
    backend="openui",
    model="gpt-4o-mini",
    prompt_version="runtime/1",
    role_title="Dependiente",
    sector="retail",
    vector_bucket="",
)


def key(**overrides) -> str:
    return build_cache_key(**{**BASE, **overrides})


def test_accessibility_bucket_is_closed_versioned_and_non_identifying():
    assert accessibility_bucket(None) == "a1:rm0:hc0:et0"
    assert accessibility_bucket({"reduce_motion": True}) == "a1:rm1:hc0:et0"
    assert accessibility_bucket({"high_contrast": True}) == "a1:rm0:hc1:et0"
    assert accessibility_bucket({"extra_time": True}) == "a1:rm0:hc0:et1"
    assert accessibility_bucket({"unknown": "free prose"}) == "a1:rm0:hc0:et0"
    # Already represented by effective_density, so it cannot fragment twice.
    assert accessibility_bucket({"short_blocks": True}) == "a1:rm0:hc0:et0"


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_key_is_a_sha256_hex_digest():
    value = key()
    assert len(value) == 64
    assert all(c in "0123456789abcdef" for c in value)


def test_key_is_deterministic():
    assert key() == key()


def test_material_has_the_thirteen_fields_of_the_formula_in_order():
    material = cache_key_material(**BASE)
    assert material.split("|") == [
        str(NODE_ID),
        "3",
        "standard",
        "some",
        hashlib.sha256(b"dependiente|retail").hexdigest()[:ROLE_BUCKET_MAX_LENGTH],
        "neutral",
        "",
        "p2:balanced:standard:standard:when_useful",
        "a1:rm0:hc0:et0",
        "3",
        "openui",
        "gpt-4o-mini",
        "runtime/1",
    ]


# ---------------------------------------------------------------------------
# What MUST change the key
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("node_id", uuid.UUID("22222222-2222-2222-2222-222222222222")),
        ("schema_version", 4),
        ("preset", "fast"),
        ("experience_level", "experienced"),
        ("role_title", "Encargado de turno"),
        ("scaffold_band", "novice"),
        ("vector_bucket", "ejercicio:0.7"),
        ("accessibility_bucket", "a1:rm1:hc0:et0"),
        ("effective_density", 2),
        ("backend", "a2tl"),
        ("model", "gpt-4o"),
        ("prompt_version", "runtime/2"),
    ],
)
def test_every_input_of_the_formula_changes_the_key(field, value):
    assert key(**{field: value}) != key()


def test_prompt_version_invalidates_every_render_without_touching_the_db():
    """That is the whole point of the constant (§3.4)."""
    keys = {key(prompt_version=f"runtime/{n}") for n in range(1, 6)}
    assert len(keys) == 5


def test_two_role_titles_do_not_share_a_key():
    """The bug this field was added to fix: a shop assistant and a shift manager
    used to share a row, so the second got the first one's role framing."""
    assert key(role_title="Dependiente") != key(role_title="Cajero")


def test_same_role_in_different_sectors_does_not_reuse_a_different_prompt():
    """Every learner string in the prompt must also partition the shared cache.

    The cache key partitions by sector unconditionally (via `role_bucket`), even when the
    role/sector is ungrounded and therefore kept OUT of the prompt text: that is a waste
    (two entries, identical output) but never a correctness bug, and it is what the key
    assertion below guards. The prompt itself only carries the sector when the source
    grounds it, so the two prompts are compared against sources that mention each sector.
    """
    retail_prompt = build_ui_prompt(
        title="Atencion al cliente",
        summary="Resolver una incidencia",
        role_title="Dependiente",
        sector="retail",
        source_context="El dependiente de retail resuelve la incidencia en caja.",
    )
    hospitality_prompt = build_ui_prompt(
        title="Atencion al cliente",
        summary="Resolver una incidencia",
        role_title="Dependiente",
        sector="hosteleria",
        source_context="El dependiente de hosteleria resuelve la incidencia en sala.",
    )

    assert retail_prompt != hospitality_prompt
    assert key(role_title="Dependiente", sector="retail") != key(
        role_title="Dependiente", sector="hosteleria"
    )


def test_scaffold_band_partitions_the_three_bands():
    keys = {key(scaffold_band=band) for band in ("novice", "neutral", "advanced")}
    assert len(keys) == 3


def test_short_blocks_changes_the_key_through_effective_density():
    dense = effective_density(4, {})
    short = effective_density(4, {"short_blocks": True})
    assert (dense, short) == (4, 2)
    assert key(effective_density=dense) != key(effective_density=short)


# ---------------------------------------------------------------------------
# What must NOT change the key
# ---------------------------------------------------------------------------


def test_user_id_is_not_an_input_of_the_key():
    """Not "ignored": absent. A ``user_id`` in the key (or in the lookup) makes the
    hit rate 0, which is the pillar of the cost model (§9.3)."""
    parameters = inspect.signature(build_cache_key).parameters
    assert "user_id" not in parameters
    with pytest.raises(TypeError):
        build_cache_key(user_id=uuid.uuid4(), **BASE)


def test_mastery_is_not_an_input_of_the_key():
    parameters = inspect.signature(build_cache_key).parameters
    assert "mastery" not in parameters
    assert "mastery_band" not in parameters


def test_key_is_stable_across_a_whole_node_as_mastery_climbs():
    """0 → 0.40 → 0.64 → 0.784 → 0.87 used to be four different keys inside one
    critical node; with ``scaffold_band`` it is one."""
    keys = {key(scaffold_band="neutral") for _ in (0.0, 0.40, 0.64, 0.784, 0.87)}
    assert len(keys) == 1


def test_two_learners_of_the_same_bucket_share_the_key():
    """Deliberate: that sharing is what makes the cost sustainable (§3.4)."""
    first = key(role_title="Dependiente", sector="retail")
    second = key(role_title="dependiente", sector="retail")
    assert first == second


def test_a_validated_knowledge_selection_partitions_the_render_cache():
    raw = key(knowledge_pack_key="")
    first = key(knowledge_pack_key=f"{'a' * 64}:{'b' * 64}")
    second = key(knowledge_pack_key=f"{'a' * 64}:{'c' * 64}")

    assert raw != first
    assert first != second
    assert key(knowledge_pack_key="") == raw


def test_live_selection_strategy_and_version_partition_the_render_cache():
    legacy = key(selection_policy_key="")
    top5 = key(selection_policy_key="selection-policy/1:top5/v1")
    progressive = key(
        selection_policy_key="selection-policy/1:progressive-3-5-catalog/v1"
    )

    assert legacy != top5
    assert top5 != progressive
    assert key(selection_policy_key="") == legacy


def test_longitudinal_decision_digest_partitions_only_when_supplied():
    baseline = key()
    errors = key(longitudinal_decision_digest="ld1:validated-errors")
    mechanics = key(longitudinal_decision_digest="ld1:mechanics")

    assert errors != baseline
    assert mechanics != errors
    assert key(longitudinal_decision_digest="") == baseline


def test_enum_members_and_their_values_key_the_same():
    """A row loaded through raw SQL must not land in a different bucket."""
    assert key(
        preset=LearningProfile.STANDARD, experience_level=LearnerExperience.SOME
    ) == key(preset="standard", experience_level="some")


# ---------------------------------------------------------------------------
# slug / role_bucket
# ---------------------------------------------------------------------------


def test_slug_folds_accents_case_and_separators():
    assert slug("Encargado de Turno") == "encargado-de-turno"
    assert slug("  Atención  al   Cliente ") == "atencion-al-cliente"
    assert slug("Jefe/a de equipo") == "jefe-a-de-equipo"


def test_slug_of_nothing_is_empty():
    assert slug(None) == ""
    assert slug("") == ""
    assert slug("!!!") == ""


def test_role_bucket_falls_back_to_sector_then_to_empty():
    assert role_bucket("Cajero", "retail") == "cajero"
    assert role_bucket(None, "Retail") == role_bucket(None, "retail")
    assert role_bucket(None, None) == ""


def test_role_bucket_keeps_the_legacy_slug_contract():
    long_title = "Responsable de prevencion de riesgos laborales"
    bucket = role_bucket(long_title)
    assert bucket == slug(long_title)[:ROLE_BUCKET_MAX_LENGTH]
    assert len(bucket) == ROLE_BUCKET_MAX_LENGTH == 24


def test_no_onboarding_means_an_empty_role_bucket_not_a_missing_field():
    material = cache_key_material(
        **{**BASE, "role_title": None, "sector": None}
    )
    assert material.split("|")[4] == ""


# ---------------------------------------------------------------------------
# effective_density
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("density", "accessibility", "expected"),
    [
        (1, None, 1),
        (3, None, 3),
        (5, {}, 5),
        (5, {"short_blocks": False}, 5),
        (5, {"short_blocks": True}, 2),
        (1, {"short_blocks": True}, 1),
        (2, {"short_blocks": True}, 2),
    ],
)
def test_effective_density_ceiling(density, accessibility, expected):
    assert effective_density(density, accessibility) == expected
