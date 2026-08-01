"""The generated OpenUI prompt and catalogue artefacts (§5.4, revised 2026-07-26).

Since the adoption of the real OpenUI dependency, the component catalogue is declared
**once**, in the frontend kit (``apps/skillnet-web/src/components/courses/kit/``), and
the system prompt is produced by ``library.prompt()`` — *their* code, not ours. Python
cannot call it (the backend has no Node at request time), so a build step writes two
versioned artefacts that this module reads as data:

* ``openui_prompt.txt`` — the exact system prompt for the ``genera_ui`` call.
* ``openui_catalog.json`` — ``library.toSpec()`` plus the digests that make drift loud.

Regenerate them with, from ``apps/skillnet-web``::

    node scripts/generate-openui-prompt.mjs          # rewrite the artefacts
    node scripts/generate-openui-prompt.mjs --check  # CI: fail if stale

Two digests, two different failures:

* ``catalog_digest`` — over the *normalised* catalogue (component order, positional prop
  order, prop kinds, enum values). :func:`catalog_digest_from_kit` recomputes it from
  ``src/render/kit.py``, so if the TypeScript kit and the Python validator stop agreeing,
  ``tests/test_render_prompt_artifact.py`` fails. That is the alarm that also fires the
  day ``@openuidev`` changes the shape of ``toSpec()``.
* ``prompt_sha256`` — over the prompt bytes, so hand-editing ``openui_prompt.txt``
  (instead of the kit) is caught too.

:func:`catalog_version` is what ``node_renders.catalog_version`` records: a render must
be explainable months later, and "which catalogue was this generated against" is half of
that answer (§3.4). It is also the value to pass as ``prompt_version`` into
:func:`src.services.cache_key.build_cache_key`, so a catalogue change invalidates cached
renders instead of silently serving a program written for the old signatures.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.render.errors import RenderError
from src.render.kit import CONTAINER_NAMES, UI_KIT, PropKind, UIKit
from src.render.spec import UI_SPEC_VERSION

_HERE = Path(__file__).parent

PROMPT_PATH = _HERE / "openui_prompt.txt"
CATALOG_PATH = _HERE / "openui_catalog.json"

#: How to fix every error this module raises.
REGENERATE_HINT = (
    "regenerate the artefacts: cd apps/skillnet-web && "
    "node scripts/generate-openui-prompt.mjs"
)

#: The library's entry component. Hard-coded on purpose: contract rule 1 (§5.2) says the
#: root is a container, and the digest must break if the kit ever declares another one.
CATALOG_ROOT = "Stack"

#: ``PropKind`` -> the token used in the canonical catalogue text. The build step derives
#: the same tokens from the zod schemas, which is what lets the two sides be compared
#: without Python knowing anything about zod: ``ref[]`` covers both
#: ``z.array(z.any())`` and ``z.array(z.string())`` on a ``children`` prop, because that
#: choice is cosmetic, while a renamed, reordered or retyped prop is not.
_KIND_TOKENS: dict[PropKind, str] = {
    PropKind.STRING: "string",
    PropKind.NUMBER: "number",
    PropKind.ENUM: "enum",
    PropKind.STRING_LIST: "string[]",
    PropKind.STRING_MATRIX: "string[][]",
    PropKind.NUMBER_LIST: "number[]",
    PropKind.REFS: "ref[]",
}


@dataclass(frozen=True, slots=True)
class CatalogArtifact:
    """``openui_catalog.json`` plus the prompt text, parsed and frozen."""

    prompt: str
    catalog_id: str
    root: str
    catalog_source: str
    catalog_version: str
    catalog_digest: str
    prompt_sha256: str
    canonical_catalog: str
    library_versions: Mapping[str, str | None]
    #: One entry per component the model may emit, in positional order.
    prompt_components: tuple[Mapping[str, Any], ...]
    #: The components the browser can render (the emittable ones plus ``Markdown``).
    #: ``None`` when the kit did not export a render library.
    render_components: tuple[str, ...] | None

    @property
    def component_names(self) -> tuple[str, ...]:
        return tuple(str(component["name"]) for component in self.prompt_components)

    def props_of(self, name: str) -> tuple[Mapping[str, Any], ...]:
        for component in self.prompt_components:
            if component["name"] == name:
                return tuple(component["props"])
        return ()


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RenderError(
            f"missing render artefact {path.name}: {REGENERATE_HINT}",
            code="RENDER_ARTIFACT_MISSING",
            status_code=500,
        ) from exc


@lru_cache(maxsize=1)
def load_artifact() -> CatalogArtifact:
    """Read and validate both artefacts. Cached: they are immutable at runtime."""
    prompt = _read(PROMPT_PATH)
    try:
        raw = json.loads(_read(CATALOG_PATH))
    except json.JSONDecodeError as exc:
        raise RenderError(
            f"{CATALOG_PATH.name} is not valid JSON: {REGENERATE_HINT}",
            code="RENDER_ARTIFACT_INVALID",
            status_code=500,
        ) from exc

    missing = [
        key
        for key in (
            "catalog_id",
            "root",
            "catalog_source",
            "catalog_version",
            "catalog_digest",
            "prompt_sha256",
            "canonical_catalog",
            "prompt_components",
        )
        if key not in raw
    ]
    if missing:
        raise RenderError(
            f"{CATALOG_PATH.name} lacks {', '.join(missing)}: {REGENERATE_HINT}",
            code="RENDER_ARTIFACT_INVALID",
            status_code=500,
        )

    render_components = raw.get("render_components")
    return CatalogArtifact(
        prompt=prompt,
        catalog_id=str(raw["catalog_id"]),
        root=str(raw["root"]),
        catalog_source=str(raw["catalog_source"]),
        catalog_version=str(raw["catalog_version"]),
        catalog_digest=str(raw["catalog_digest"]),
        prompt_sha256=str(raw["prompt_sha256"]),
        canonical_catalog=str(raw["canonical_catalog"]),
        library_versions=dict(raw.get("library_versions") or {}),
        prompt_components=tuple(raw["prompt_components"]),
        render_components=tuple(render_components) if render_components else None,
    )


def render_prompt() -> str:
    """The system prompt for ``genera_ui``, exactly as ``library.prompt()`` wrote it."""
    return load_artifact().prompt


def catalog_version() -> str:
    """``"skillnet-ui/1+<digest12>"`` — persisted in ``node_renders.catalog_version``."""
    return load_artifact().catalog_version


def library_version() -> str:
    """``"@openuidev/lang-core@0.2.10; @openuidev/react-lang@0.2.9"`` for the audit row.

    The browser parses and renders the program with these packages, so "what was shown
    to this employee" is only answerable together with them.
    """
    versions = load_artifact().library_versions
    return "; ".join(
        f"{name}@{version}"
        for name, version in sorted(versions.items())
        if version and name.startswith("@openuidev/")
    )


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_catalog_from_kit(kit: UIKit = UI_KIT, root: str = CATALOG_ROOT) -> str:
    """The canonical catalogue text as ``src/render/kit.py`` sees it.

    Byte-identical to ``openui_catalog.json``'s ``canonical_catalog`` while the
    TypeScript kit and this one agree. Only the components the model may emit are in
    it: ``Markdown`` is server-authored and is deliberately outside the prompt.
    """
    if root not in CONTAINER_NAMES:
        raise RenderError(
            f"catalogue root {root!r} is not a container ({', '.join(CONTAINER_NAMES)})",
            code="RENDER_ARTIFACT_INVALID",
            status_code=500,
        )
    lines = [f"catalog: {kit_catalog_id()}", f"root: {root}"]
    for component in kit.llm_components:
        props = []
        for prop in component.props:
            token = _KIND_TOKENS[prop.kind]
            if prop.kind is PropKind.ENUM:
                token = f"enum({'|'.join(prop.choices)})"
            props.append(f"{prop.name}:{token}")
        lines.append(f"{component.name}({', '.join(props)})")
    return "\n".join(lines) + "\n"


def kit_catalog_id() -> str:
    """The IR version doubles as the catalogue id; both sides must agree on it."""
    return UI_SPEC_VERSION


def catalog_digest_from_kit(kit: UIKit = UI_KIT) -> str:
    return digest(canonical_catalog_from_kit(kit))


def artefact_drift(kit: UIKit = UI_KIT) -> list[str]:
    """Every way the artefacts and the Python kit can disagree. Empty == in sync.

    Used by ``tests/test_render_prompt_artifact.py``; also worth calling from a startup
    self-check, because a stale artefact means the model is being taught signatures the
    validator will reject.
    """
    artifact = load_artifact()
    problems: list[str] = []

    if artifact.catalog_id != kit_catalog_id():
        problems.append(
            f"catalog_id {artifact.catalog_id!r} != {kit_catalog_id()!r}"
        )
    if artifact.root != CATALOG_ROOT:
        problems.append(f"catalogue root {artifact.root!r} != {CATALOG_ROOT!r}")

    expected_catalog = canonical_catalog_from_kit(kit)
    if artifact.canonical_catalog != expected_catalog:
        problems.append(
            "the catalogue in the artefact is not the one in src/render/kit.py:\n"
            f"--- artefact ---\n{artifact.canonical_catalog}"
            f"--- kit ---\n{expected_catalog}"
        )
    if artifact.catalog_digest != digest(artifact.canonical_catalog):
        problems.append(
            "catalog_digest does not hash canonical_catalog (hand-edited artefact?)"
        )
    if artifact.catalog_version != f"{artifact.catalog_id}+{artifact.catalog_digest[:12]}":
        problems.append(f"catalog_version {artifact.catalog_version!r} is not id+digest12")
    if artifact.prompt_sha256 != digest(artifact.prompt):
        problems.append(
            "prompt_sha256 does not hash openui_prompt.txt (hand-edited prompt?)"
        )
    if artifact.render_components is not None and set(artifact.render_components) != set(
        kit.names
    ):
        problems.append(
            f"the browser renders {sorted(artifact.render_components)} but the kit holds "
            f"{sorted(kit.names)}"
        )
    return problems


__all__ = [
    "CATALOG_PATH",
    "CATALOG_ROOT",
    "PROMPT_PATH",
    "REGENERATE_HINT",
    "CatalogArtifact",
    "artefact_drift",
    "canonical_catalog_from_kit",
    "catalog_digest_from_kit",
    "catalog_version",
    "digest",
    "kit_catalog_id",
    "library_version",
    "load_artifact",
    "render_prompt",
]
