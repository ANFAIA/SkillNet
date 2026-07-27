"""``UISpec`` — the canonical IR of §5.2 and the seven contract rules.

The IR is a **flat** list of components with references by id, because LLMs emit flat
lists far more reliably than nested trees and because a flat list makes incremental
parsing trivial (§5.2).

The seven rules, all enforced here:

1. ``root`` exists in ``components`` and is a container (``Stack`` or ``Card``).
2. Every id in ``children`` exists. Forward references are allowed.
3. No cycles in the ``children`` graph.
4. At most 12 components per spec, at most 5 children at the root level, and at most 64
   blocks in the tree those components EXPAND to (a shared id is painted once per
   reference, so the flat count alone bounds nothing).
5. ``QuizItem`` carries no correct answer and no explanation — those live in
   ``answer_key``.
6. ``props.text`` is plain text or inline markup, never HTML.
7. In the ``explanation`` and ``mixed`` formats the first child of ``root`` is a
   ``TextContent`` with ``variant="lead"`` or a ``Callout``. This is the slot where
   the "esto te sirve para X" line derived from ``goal`` (§6.2 Q2) lands.

Rules 5 and 6 are per-component and always run. Rules 1-4 and 7 are structural and
are **skipped in partial mode** (``context={"partial": True}``), which is what
``parse_partial`` needs: mid-stream a spec legitimately has dangling forward
references and no lead block yet.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator
from pydantic import ValidationError as PydanticValidationError

from src.models.node_render import UiFormat
from src.render.errors import RenderValidationError
from src.render.kit import (
    CONTAINER_NAMES,
    LEAD_VARIANT,
    UI_KIT,
    PropKind,
    PropSpec,
)

#: The only IR version this PR speaks.
UI_SPEC_VERSION = "skillnet-ui/1"

#: Contract rule 4 (§5.2). Not aesthetics: working memory handles 4-7 items.
MAX_COMPONENTS = 12
MAX_ROOT_CHILDREN = 5

#: Contract rule 4, painting half. Counting *components* is not enough: the list is a
#: DAG, so the same id may appear many times inside one ``children`` array and inside
#: many parents, and only the ROOT fan-out is bounded above. Twelve components therefore
#: expand exponentially in the tree the browser paints.
#:
#: MEASURED against ``@openuidev/lang-core`` 0.2.10, all with 12 components and
#: ``meta.statementCount == 12`` (so the client's rule-4 check does not fire):
#: ``a{i} = Card("n{i}", [a{i+1} x W])`` for i in 0..8 gives 334 B -> 1 025 elements,
#: 370 B -> 29 526 elements (4.1 MB of tree JSON), and at W=8 a 550-byte program kills
#: the tab with ``FATAL ERROR: Ineffective mark-compacts near heap limit`` after ~47 s.
#: A V8 heap OOM is not catchable, so the client cannot defend itself: the cap has to
#: stop the text from ever being served. 64 is the number the hand-written renderer used
#: as its render budget; the ten valid fixtures expand to 5 nodes at most.
MAX_RENDERED_NODES = 64

#: Contract rule 7 (§5.2).
FORMATS_REQUIRING_LEAD: frozenset[str] = frozenset({"explanation", "mixed"})

UI_FORMATS: tuple[str, ...] = tuple(m.value for m in UiFormat)

#: Contract rule 5 (§5.2): these never travel inside ``ui_spec``.
ANSWER_KEY_KEYS: frozenset[str] = frozenset(
    {
        "correct",
        "correct_order",
        "correct_answer",
        "answer",
        "answers",
        "blanks",
        "explanation",
        "rubric",
        "solution",
    }
)

#: Component ids must survive a round trip through the dialect, whose ``ident``
#: production (§5.4) is exactly this.
_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: Contract rule 6 (§5.2): no HTML in ``props.text``. Deliberately narrow — a bare
#: ``<`` used as "menor que" in prose is legal text, an actual tag is not.
_HTML_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>|<!--")


def _is_partial(info: ValidationInfo) -> bool:
    context = info.context if isinstance(info.context, Mapping) else None
    return bool(context and context.get("partial"))


def _check_value(prop: PropSpec, value: Any) -> str | None:
    """Return an error message when ``value`` does not match the kit's declared kind."""
    match prop.kind:
        case PropKind.STRING:
            if not isinstance(value, str):
                return f"prop '{prop.name}' must be a string"
        case PropKind.ENUM:
            if not isinstance(value, str):
                return f"prop '{prop.name}' must be a string"
            if value not in prop.choices:
                allowed = ", ".join(prop.choices)
                return f"prop '{prop.name}' must be one of: {allowed} (got {value!r})"
        case PropKind.STRING_LIST:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                return f"prop '{prop.name}' must be an array of strings"
        case PropKind.STRING_MATRIX:
            ok = isinstance(value, list) and all(
                isinstance(row, list) and all(isinstance(cell, str) for cell in row)
                for row in value
            )
            if not ok:
                return (
                    f"prop '{prop.name}' must be an array of arrays of strings "
                    '(e.g. [["1","2"],["3","4"]])'
                )
        case PropKind.NUMBER_LIST:
            ok = isinstance(value, list) and all(
                isinstance(v, int | float) and not isinstance(v, bool) for v in value
            )
            if not ok:
                return f"prop '{prop.name}' must be an array of numbers"
        case PropKind.REFS:  # pragma: no cover - refs never live in props
            return f"prop '{prop.name}' belongs in 'children', not in 'props'"
    return None


class Component(BaseModel):
    """One node of the flat list. ``children`` is the refs array, never a prop."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    props: dict[str, Any] = Field(default_factory=dict)
    children: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_against_kit(self) -> Component:
        errors: list[str] = []
        if not _ID_RE.match(self.id):
            errors.append(
                f"component id {self.id!r} is not a valid identifier "
                "([A-Za-z_][A-Za-z0-9_]*)"
            )
        spec = UI_KIT.get(self.type)
        if spec is None:
            known = ", ".join(UI_KIT.names)
            raise ValueError(
                f"component {self.id!r}: unknown component type {self.type!r}. "
                f"The kit is closed: {known}"
            )

        declared = set(spec.prop_names)
        for name in self.props:
            if name in declared:
                continue
            if self.type == "QuizItem" and name in ANSWER_KEY_KEYS:
                errors.append(
                    f"component {self.id!r}: QuizItem must not carry {name!r} "
                    "(rule 5: the answer lives in answer_key)"
                )
            elif name in ANSWER_KEY_KEYS:
                errors.append(
                    f"component {self.id!r}: {name!r} is answer data and never "
                    "belongs in a ui_spec (rule 5)"
                )
            else:
                errors.append(
                    f"component {self.id!r}: unknown prop {name!r} for {self.type}"
                )

        for prop in spec.value_props:
            if prop.name not in self.props:
                errors.append(
                    f"component {self.id!r}: missing prop {prop.name!r} for {self.type}"
                )
                continue
            problem = _check_value(prop, self.props[prop.name])
            if problem:
                errors.append(f"component {self.id!r}: {problem}")

        children_prop = spec.children_prop
        if children_prop is None and self.children:
            errors.append(
                f"component {self.id!r}: {self.type} takes no children "
                f"(only {', '.join(CONTAINER_NAMES)} do)"
            )
        if not all(isinstance(child, str) and _ID_RE.match(child) for child in self.children):
            errors.append(f"component {self.id!r}: children must be component ids")

        # Rule 6: no HTML in props.text.
        text = self.props.get("text")
        if isinstance(text, str) and _HTML_RE.search(text):
            errors.append(
                f"component {self.id!r}: props.text must be plain text or inline "
                "markup, never HTML (rule 6)"
            )

        if errors:
            raise ValueError("; ".join(errors))
        return self


class UISpec(BaseModel):
    """The persisted IR. Serialized to ``node_renders.ui_spec`` verbatim."""

    model_config = ConfigDict(extra="forbid")

    VERSION: ClassVar[str] = UI_SPEC_VERSION

    version: str = UI_SPEC_VERSION
    format: str
    root: str
    components: list[Component] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_contract(self, info: ValidationInfo) -> UISpec:
        errors: list[str] = []
        if self.version != UI_SPEC_VERSION:
            errors.append(
                f"version must be {UI_SPEC_VERSION!r} (got {self.version!r})"
            )
        if self.format not in UI_FORMATS:
            errors.append(
                f"format must be one of: {', '.join(UI_FORMATS)} (got {self.format!r})"
            )

        by_id: dict[str, Component] = {}
        for component in self.components:
            if component.id in by_id:
                errors.append(f"duplicate component id {component.id!r}")
            by_id[component.id] = component

        if _is_partial(info):
            if errors:
                raise ValueError("; ".join(errors))
            return self

        # Rule 4: size limits.
        if len(self.components) > MAX_COMPONENTS:
            errors.append(
                f"rule 4: a spec holds at most {MAX_COMPONENTS} components "
                f"(got {len(self.components)})"
            )

        # Rule 1: root exists and is a container.
        root = by_id.get(self.root)
        if root is None:
            errors.append(f"root {self.root!r} is not in components (rule 1)")
        elif root.type not in CONTAINER_NAMES:
            errors.append(
                f"root {self.root!r} is a {root.type}. It must be one of "
                f"{', '.join(CONTAINER_NAMES)} (rule 1)"
            )

        # Rule 2: every reference resolves.
        for component in self.components:
            for child in component.children:
                if child not in by_id:
                    errors.append(
                        f"component {component.id!r} references unknown child "
                        f"{child!r} (rule 2)"
                    )

        # Rule 3: no cycles.
        cycles = _find_cycles(by_id)
        errors.extend(cycles)

        # Rule 4: the size of the EXPANDED tree, not of the flat list. Skipped when the
        # graph is not a DAG yet — a cycle makes the expansion infinite and rule 3 has
        # already rejected the spec anyway.
        if root is not None and not cycles:
            painted = _count_expanded(self.root, by_id, MAX_RENDERED_NODES)
            if painted > MAX_RENDERED_NODES:
                errors.append(
                    f"rule 4: the tree expands to more than {MAX_RENDERED_NODES} "
                    "blocks. Reuse fewer ids: a block referenced from several "
                    "parents, or twice inside one children array, is painted once "
                    "per reference"
                )

        if root is not None:
            # Rule 4: root fan-out.
            if len(root.children) > MAX_ROOT_CHILDREN:
                errors.append(
                    f"rule 4: the root level holds at most {MAX_ROOT_CHILDREN} "
                    f"elements (got {len(root.children)})"
                )
            # Rule 7: the lead slot.
            if self.format in FORMATS_REQUIRING_LEAD:
                errors.append(_check_lead_slot(self.format, root, by_id))

        errors = [e for e in errors if e]
        if errors:
            raise ValueError("; ".join(errors))
        return self

    # -- convenience ---------------------------------------------------------------

    @property
    def by_id(self) -> dict[str, Component]:
        return {c.id: c for c in self.components}

    def component(self, component_id: str) -> Component | None:
        for component in self.components:
            if component.id == component_id:
                return component
        return None

    @property
    def types(self) -> set[str]:
        return {c.type for c in self.components}


def _check_lead_slot(
    ui_format: str, root: Component, by_id: Mapping[str, Component]
) -> str | None:
    """Contract rule 7 (§5.2)."""
    suffix = (
        "a TextContent with variant='lead' or a Callout (rule 7: the goal line "
        "needs a slot)"
    )
    if not root.children:
        return f"format {ui_format!r} requires the first child of root to be {suffix}"
    first = by_id.get(root.children[0])
    if first is None:
        return None  # already reported by rule 2
    if first.type == "Callout":
        return None
    if first.type == "TextContent" and first.props.get("variant") == LEAD_VARIANT:
        return None
    got = first.type
    if got == "TextContent":
        got = f"TextContent variant={first.props.get('variant')!r}"
    return f"format {ui_format!r} requires the first child of root to be {suffix}. Got {got}"


def _count_expanded(root_id: str, by_id: Mapping[str, Component], cap: int) -> int:
    """Nodes in the tree ``root_id`` expands to, counting every reference separately.

    Memoised over the DAG, so it is O(V+E) however wide the fan-out, and clamped at
    ``cap + 1`` at every accumulation so the arithmetic cannot blow up either (12
    components with a 4 kB line can express W**N in the 1e26 range).

    Requires an acyclic graph: the caller only runs it when rule 3 found nothing.
    A dangling reference counts as one leaf; rule 2 rejects the spec for it anyway.
    """
    ceiling = cap + 1
    memo: dict[str, int] = {}
    # Explicit post-order stack rather than recursion: the flat list is only capped at
    # 12 by another rule that merely *reports*, so a hostile spec could otherwise pick
    # the recursion limit as its denial of service.
    stack: list[tuple[str, bool]] = [(root_id, False)]
    while stack:
        component_id, expanded = stack.pop()
        if component_id in memo:
            continue
        component = by_id.get(component_id)
        children = component.children if component is not None else []
        if not expanded:
            stack.append((component_id, True))
            for child in children:
                if child not in memo:
                    stack.append((child, False))
            continue
        total = 1
        for child in children:
            total = min(total + memo.get(child, 1), ceiling)
        memo[component_id] = total
    return memo[root_id]


def _find_cycles(by_id: Mapping[str, Component]) -> list[str]:
    """Contract rule 3 (§5.2). Iterative DFS with a three-colour marking."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour: dict[str, int] = dict.fromkeys(by_id, WHITE)
    errors: list[str] = []

    for start in by_id:
        if colour[start] != WHITE:
            continue
        stack: list[tuple[str, Iterable[str]]] = [(start, iter(by_id[start].children))]
        colour[start] = GREY
        while stack:
            node, children = stack[-1]
            advanced = False
            for child in children:
                if child not in by_id:
                    continue  # dangling: rule 2 reports it
                if colour[child] == GREY:
                    errors.append(
                        f"cycle in children: {node!r} -> {child!r} (rule 3)"
                    )
                    continue
                if colour[child] == WHITE:
                    colour[child] = GREY
                    stack.append((child, iter(by_id[child].children)))
                    advanced = True
                    break
            if not advanced:
                colour[node] = BLACK
                stack.pop()
    return errors


def flatten_validation_error(exc: PydanticValidationError) -> list[str]:
    """Turn a pydantic error into the flat ``list[str]`` the repair prompt wants."""
    messages: list[str] = []
    for error in exc.errors():
        message = str(error.get("msg", "")).removeprefix("Value error, ").strip()
        location = ".".join(str(part) for part in error.get("loc", ()))
        if message:
            messages.extend(part.strip() for part in message.split("; ") if part.strip())
        else:
            messages.append(f"{location}: invalid value")
    return messages or ["invalid UI spec"]


def parse_spec(data: Mapping[str, Any], *, partial: bool = False) -> UISpec:
    """Validate a raw dict into a ``UISpec``, raising ``RenderValidationError``."""
    try:
        return UISpec.model_validate(dict(data), context={"partial": partial})
    except PydanticValidationError as exc:
        raise RenderValidationError(flatten_validation_error(exc)) from exc


__all__ = [
    "ANSWER_KEY_KEYS",
    "FORMATS_REQUIRING_LEAD",
    "MAX_COMPONENTS",
    "MAX_RENDERED_NODES",
    "MAX_ROOT_CHILDREN",
    "UI_FORMATS",
    "UI_SPEC_VERSION",
    "Component",
    "UISpec",
    "flatten_validation_error",
    "parse_spec",
]
