"""Pure, experimental OpenUI prompt scopes.

The production generator still consumes the complete generated prompt.  This module
only builds an inspectable fragment for selection experiments; importing it has no
effect on runtime routing, prompts, validation, or cache keys.

The generated catalogue artefact remains the source of truth.  A scope preserves the
small structural/support vocabulary every generated screen may need and adds a caller's
shortlist plus any explicitly required components (for example, the planned assessment
block).  Components are serialized in catalogue order, so the same set always produces
the same bytes regardless of retrieval order.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from src.render.prompt import CatalogArtifact, digest, load_artifact

PROMPT_SLICE_SCHEMA = "component-scope/1"
RUNTIME_SCOPE_POLICY_VERSION = "renderer-safe-ranked/1"

# These are capabilities of the OpenUI screen shell, not recommendations for the central
# learning activity.  ``Stack`` is the root contract, ``TextContent`` can carry the lead,
# ``Card`` groups a closed case, and ``Callout`` preserves a safety rule or exception.
BASE_SCOPE_COMPONENTS: tuple[str, ...] = (
    "Stack",
    "TextContent",
    "Card",
    "Callout",
)


class PromptSliceError(ValueError):
    """The requested scope cannot be represented by the catalogue artefact."""


class UnknownPromptComponent(PromptSliceError):
    """One or more caller-provided component ids are absent from the catalogue."""

    def __init__(self, component_ids: Iterable[str]) -> None:
        self.component_ids = tuple(sorted(set(component_ids)))
        super().__init__(
            "unknown prompt component ids: " + ", ".join(self.component_ids)
        )


class PromptSliceCatalogDrift(PromptSliceError):
    """The artefact cannot supply the structural components or canonical signatures."""


@dataclass(frozen=True, slots=True)
class PromptSlice:
    """A closed prompt fragment and the provenance needed to reproduce it."""

    prompt: str
    schema_version: str
    source_catalog_id: str
    source_catalog_version: str
    root: str
    requested_component_ids: tuple[str, ...]
    additional_required_component_ids: tuple[str, ...]
    included_component_ids: tuple[str, ...]
    canonical_signatures: str
    digest: str
    version: str
    prompt_sha256: str


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    """Trim ids and preserve first occurrence for an honest request trace."""
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _canonical_lines(artifact: CatalogArtifact) -> Mapping[str, str]:
    """Index the already-normalized signatures exported by the frontend build."""
    lines: dict[str, str] = {}
    for line in artifact.canonical_catalog.splitlines():
        if line.startswith(("catalog:", "root:")) or "(" not in line:
            continue
        name = line.split("(", 1)[0]
        lines[name] = line
    return lines


def _prompt_component_index(
    artifact: CatalogArtifact,
) -> Mapping[str, Mapping[str, Any]]:
    return {
        str(component["name"]): component for component in artifact.prompt_components
    }


def _prompt_text(
    *, artifact: CatalogArtifact, component_ids: tuple[str, ...]
) -> str:
    components = _prompt_component_index(artifact)
    lines = [
        "## SkillNet Component Scope (closed)",
        "",
        (
            "Para esta generacion solo puedes emitir los componentes enumerados abajo. "
            "No uses ningun otro componente del catalogo general."
        ),
        f"La raiz sigue siendo {artifact.root}.",
        "",
        "### Component Signatures",
        "",
    ]
    for component_id in component_ids:
        component = components[component_id]
        signature = str(component["signature"])
        description = str(component.get("description") or "").strip()
        lines.append(f"{signature} — {description}" if description else signature)
    return "\n".join(lines) + "\n"


def scoped_catalog_prompt(scope: PromptSlice, *, artifact: CatalogArtifact | None = None) -> str:
    """Replace the full signature table and remove examples outside the closed scope."""
    source = artifact or load_artifact()
    start_marker = "## Component Signatures"
    end_marker = "## Hoisting & Streaming"
    before, separator, remainder = source.prompt.partition(start_marker)
    if not separator:
        raise PromptSliceCatalogDrift("prompt lacks Component Signatures section")
    _old_signatures, separator, after = remainder.partition(end_marker)
    if not separator:
        raise PromptSliceCatalogDrift("prompt lacks Hoisting & Streaming section")
    signatures = scope.prompt.split("### Component Signatures\n\n", 1)[1]
    narrowed = before + start_marker + "\n\n" + signatures + "\n" + end_marker + after
    # The generated full-catalogue example can contain components deliberately absent
    # from this slice. Keeping it would make the boundary semantically open even though
    # its signature table is closed.
    examples_marker = "## Examples"
    rules_marker = "## Important Rules"
    example_before, separator, example_rest = narrowed.partition(examples_marker)
    if separator:
        _examples, rules_separator, rules_after = example_rest.partition(rules_marker)
        if not rules_separator:
            raise PromptSliceCatalogDrift("prompt lacks Important Rules section")
        narrowed = example_before + rules_marker + rules_after
    return narrowed


def resolve_runtime_prompt(
    shortlist: Iterable[str],
    *,
    additional_required: Iterable[str] = (),
    enabled: bool,
    artifact: CatalogArtifact | None = None,
) -> tuple[str, PromptSlice | None]:
    """Choose the production prompt path explicitly for flags and A/B experiments."""
    source = artifact or load_artifact()
    if not enabled:
        return source.prompt, None
    scope = build_prompt_slice(
        shortlist, additional_required=additional_required, artifact=source
    )
    return scoped_catalog_prompt(scope, artifact=source), scope


def build_prompt_slice(
    shortlist: Iterable[str],
    *,
    additional_required: Iterable[str] = (),
    artifact: CatalogArtifact | None = None,
) -> PromptSlice:
    """Build a deterministic closed component scope without changing the live prompt.

    ``shortlist`` contains the candidates selected by an experiment.  Structural/support
    components are always added.  ``additional_required`` is for requirements decided
    elsewhere, such as ``QuizItem`` or ``DragOrder``.  Unknown ids fail loudly instead of
    being dropped, because a silently smaller scope would invalidate an A/B comparison.
    """
    source = artifact or load_artifact()
    requested = _unique(shortlist)
    required = _unique(additional_required)
    available = source.component_names
    available_set = set(available)

    missing_base = tuple(name for name in BASE_SCOPE_COMPONENTS if name not in available_set)
    if missing_base:
        raise PromptSliceCatalogDrift(
            "catalogue lacks base scope components: " + ", ".join(missing_base)
        )
    unknown = tuple(name for name in (*requested, *required) if name not in available_set)
    if unknown:
        raise UnknownPromptComponent(unknown)

    wanted = set(BASE_SCOPE_COMPONENTS) | set(requested) | set(required)
    included = tuple(name for name in available if name in wanted)
    canonical_index = _canonical_lines(source)
    missing_signatures = tuple(name for name in included if name not in canonical_index)
    if missing_signatures:
        raise PromptSliceCatalogDrift(
            "canonical catalogue lacks signatures for: "
            + ", ".join(missing_signatures)
        )

    canonical_lines = [
        f"scope: {PROMPT_SLICE_SCHEMA}",
        f"catalog: {source.catalog_id}",
        f"root: {source.root}",
        *(canonical_index[name] for name in included),
    ]
    canonical = "\n".join(canonical_lines) + "\n"
    scope_digest = digest(canonical)
    prompt = _prompt_text(artifact=source, component_ids=included)
    return PromptSlice(
        prompt=prompt,
        schema_version=PROMPT_SLICE_SCHEMA,
        source_catalog_id=source.catalog_id,
        source_catalog_version=source.catalog_version,
        root=source.root,
        requested_component_ids=requested,
        additional_required_component_ids=required,
        included_component_ids=included,
        canonical_signatures=canonical,
        digest=scope_digest,
        version=f"{PROMPT_SLICE_SCHEMA}+{scope_digest[:12]}",
        prompt_sha256=digest(prompt),
    )


def build_didact_prompt_slice(
    type_ids: Iterable[str],
    *,
    additional_required: Iterable[str] = (),
    artifact: CatalogArtifact | None = None,
) -> PromptSlice:
    """Expose schemas only after the Didact host boundary accepts the shortlist.

    Importing the projector lazily avoids making the neutral inventory depend on the
    rendering package. All 34 types remain available to retrieval, while this function
    fails closed for missing renderers, disabled emission, or unsatisfied host ports.
    """

    from src.personalization.didact_descriptors import openui_names_for_shortlist

    return build_prompt_slice(
        openui_names_for_shortlist(type_ids),
        additional_required=additional_required,
        artifact=artifact,
    )


__all__ = [
    "BASE_SCOPE_COMPONENTS",
    "PROMPT_SLICE_SCHEMA",
    "RUNTIME_SCOPE_POLICY_VERSION",
    "PromptSlice",
    "PromptSliceCatalogDrift",
    "PromptSliceError",
    "UnknownPromptComponent",
    "build_didact_prompt_slice",
    "build_prompt_slice",
    "resolve_runtime_prompt",
    "scoped_catalog_prompt",
]
