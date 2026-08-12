"""The render ``cache_key`` of §3.4 — one pure function, no session, no LLM.

``node_renders.cache_key`` is ``UNIQUE`` **globally**: two learners whose profile
hashes to the same key share the row, and that sharing is what makes the cost
model work. Two consequences that are easy to get wrong:

* ``user_id`` is **not** in the key and **not** in the lookup. Put it in either
  and the hit rate is 0 (§9.3).
* ``mastery`` is **not** in the key. ``scaffold_band`` is, and it is frozen when
  the probe closes, so the key cannot move under the learner mid-node (§3.3).

``PROMPT_VERSION`` lives in ``src/llm/prompts/runtime.py`` and is passed in rather
than imported, so this module stays importable with nothing else in place and the
version is visible at every call site.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from collections.abc import Mapping
from typing import Any

#: ``role_bucket`` is truncated to this many characters (§3.4).
ROLE_BUCKET_MAX_LENGTH = 24

#: Ceiling applied to ``intent_density`` when ``accessibility.short_blocks`` is on.
SHORT_BLOCKS_DENSITY_CEILING = 2

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def _plain(value: Any) -> str:
    """Enum-or-string → plain string, so a row loaded via raw SQL keys the same."""
    if value is None:
        return ""
    return str(getattr(value, "value", value))


def slug(value: str | None) -> str:
    """ASCII-fold, lowercase, collapse everything else into single hyphens.

    ``"Encargado de Turno"`` and ``"encargado  de  turno"`` must land in the same
    bucket, or the cache fragments on typing style rather than on role.
    """
    if not value:
        return ""
    folded = unicodedata.normalize("NFKD", str(value))
    ascii_only = folded.encode("ascii", "ignore").decode("ascii").lower()
    return _NON_SLUG.sub("-", ascii_only).strip("-")


def role_bucket(role_title: str | None = None, sector: str | None = None) -> str:
    """Stable legacy bucket used by prompt context and diagnostics."""
    role = slug(role_title)
    industry = slug(sector)
    return (role or industry)[:ROLE_BUCKET_MAX_LENGTH]


def _profile_cache_bucket(
    role_title: str | None = None, sector: str | None = None
) -> str:
    """Partition cache by every declared string that reaches the prompt.

    Keep :func:`role_bucket` stable because it is also prompt context.  The cache-only
    bucket can safely add sector without invalidating packaged LLM fixtures.
    """
    role = slug(role_title)
    industry = slug(sector)
    if not role or not industry:
        return role_bucket(role_title, sector)
    material = f"{role}|{industry}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:ROLE_BUCKET_MAX_LENGTH]


def effective_density(
    intent_density: int, accessibility: Mapping[str, Any] | None = None
) -> int:
    """``min(intent_density, 2)`` when ``short_blocks`` is on, else unchanged (§3.1).

    This is how ``users.accessibility`` is honoured **without** the flag or its
    origin ever reaching the LLM: the model only sees a length budget.
    """
    if accessibility and accessibility.get("short_blocks"):
        return min(int(intent_density), SHORT_BLOCKS_DENSITY_CEILING)
    return int(intent_density)


def cache_key_material(
    *,
    node_id: uuid.UUID | str,
    schema_version: int,
    preset: Any,
    experience_level: Any,
    scaffold_band: str,
    effective_density: int,
    backend: str,
    model: str,
    prompt_version: Any,
    role_title: str | None = None,
    sector: str | None = None,
    vector_bucket: str = "",
    preference_bucket: str = "p1:balanced:standard:when_useful",
) -> str:
    """The exact pipe-joined string that gets hashed. Exposed for debugging."""
    return "|".join(
        (
            str(node_id),
            str(schema_version),
            _plain(preset),
            _plain(experience_level),
            _profile_cache_bucket(role_title, sector),
            _plain(scaffold_band),
            vector_bucket or "",
            preference_bucket,
            str(effective_density),
            _plain(backend),
            _plain(model),
            _plain(prompt_version),
        )
    )


def build_cache_key(
    *,
    node_id: uuid.UUID | str,
    schema_version: int,
    preset: Any,
    experience_level: Any,
    scaffold_band: str,
    effective_density: int,
    backend: str,
    model: str,
    prompt_version: Any,
    role_title: str | None = None,
    sector: str | None = None,
    vector_bucket: str = "",
    preference_bucket: str = "p1:balanced:standard:when_useful",
) -> str:
    """``sha256`` of :func:`cache_key_material`, hex.

    ``vector_bucket`` is ``""`` during the calibration period, which is what makes
    the first three nodes of a new learner share a key with everyone else in the
    same declared bucket (§6.4).
    """
    material = cache_key_material(
        node_id=node_id,
        schema_version=schema_version,
        preset=preset,
        experience_level=experience_level,
        scaffold_band=scaffold_band,
        effective_density=effective_density,
        backend=backend,
        model=model,
        prompt_version=prompt_version,
        role_title=role_title,
        sector=sector,
        vector_bucket=vector_bucket,
        preference_bucket=preference_bucket,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
