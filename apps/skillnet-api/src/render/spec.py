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
from typing import Any, ClassVar, Literal

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
MAX_TABLE_ROWS = 4
MAX_TABLE_CELL_CHARS = 160
MAX_TABLE_TOTAL_CHARS = 480

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


#: Above this many characters, a value in an enum slot is not a mistyped choice — it is
#: the block's prose in the wrong argument. Measured on ``epi-taller`` (2026-07-27):
#: ``Callout("Cuidado con el estado del EPI. Un EPI dañado no protege.", ...)``. ``Callout``
#: is the only block in the kit whose *first* argument is the enum and whose second is the
#: text, so it is the only one that invites the swap, and telling the model to pick one of
#: three tones when it has put a sentence there sends it to fix the wrong argument. Every
#: real choice in the kit is at most 12 characters (``true_false``, ``understand``), so
#: this cannot fire on a near miss.
_ENUM_PROSE_CHARS = 24


def _check_value(prop: PropSpec, value: Any, signature: str = "") -> str | None:
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
                if len(value) > _ENUM_PROSE_CHARS:
                    where = f" The signature is {signature}." if signature else ""
                    return (
                        f"prop '{prop.name}' has a whole sentence in it, so the "
                        "arguments are in the wrong order: they are positional."
                        f"{where} '{prop.name}' takes one of: {allowed}"
                    )
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


def _table_shape_errors(component: Component) -> list[str]:
    """A ``Table`` whose rows do not line up with its headers.

    ``PropKind.STRING_MATRIX`` only checks that ``rows`` is a list of lists of strings, so
    until 2026-07-28 a table could declare one header and hand back a single row holding
    fourteen cells — and the gate would serve it. That is not a hypothetical: it is what
    the real ``Los catorce alergenos obligatorios`` node produced when it was told to use
    one column, and it paints as one row running off the side of the screen.

    Reported per component with both numbers in the message, because "row 1 has 14 cells
    and there is 1 header" is a repair the model can make in one attempt, while a silently
    broken table is a screen nobody finds until an employee is looking at it.
    """
    if component.type != "Table":
        return []
    headers = component.props.get("headers")
    rows = component.props.get("rows")
    if not isinstance(headers, list) or not isinstance(rows, list):
        return []  # already reported by the kit's own type check
    width = len(headers)
    if width == 0:
        return [
            f"component {component.id!r}: Table needs at least one header"
        ]
    problems: list[str] = []
    if len(rows) > MAX_TABLE_ROWS:
        problems.append(
            f"component {component.id!r}: Table has {len(rows)} rows but a learning "
            f"screen allows at most {MAX_TABLE_ROWS}. Preserve required coverage in a "
            "compact non-tabular representation; never make the learner scroll through "
            "a reference list"
        )
    table_chars = 0
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            continue  # the kit's STRING_MATRIX check owns this one
        for column, cell in enumerate(row, start=1):
            if not isinstance(cell, str):
                continue
            table_chars += len(cell)
            if len(cell) > MAX_TABLE_CELL_CHARS:
                problems.append(
                    f"component {component.id!r}: Table row {index} column {column} "
                    f"has {len(cell)} characters but a cell allows at most "
                    f"{MAX_TABLE_CELL_CHARS}"
                )
        if len(row) != width:
            problems.append(
                f"component {component.id!r}: row {index} of the Table has "
                f"{len(row)} cells but there {'is' if width == 1 else 'are'} "
                f"{width} header{'' if width == 1 else 's'}. Every row is its own "
                "array with one cell per header — a one-column table is "
                '[["a"], ["b"], ["c"]], not [["a", "b", "c"]]'
            )
    if table_chars > MAX_TABLE_TOTAL_CHARS:
        problems.append(
            f"component {component.id!r}: Table cells contain {table_chars} characters "
            f"but a learning screen allows at most {MAX_TABLE_TOTAL_CHARS}"
        )
    # One message is enough to fix all of them, and N of them would crowd out every other
    # error in a repair prompt that has exactly one attempt to spend.
    return problems[:1]


def _didact_parallel_list_errors(component: Component) -> list[str]:
    """Validate flat parallel arrays used instead of unsupported object arrays."""

    if component.type == "DidactGlossary":
        terms = component.props.get("terms")
        definitions = component.props.get("definitions")
        if isinstance(terms, list) and isinstance(definitions, list):
            if not terms:
                return [f"component {component.id!r}: DidactGlossary needs at least one term"]
            if len(terms) != len(definitions):
                return [
                    f"component {component.id!r}: DidactGlossary has {len(terms)} terms "
                    f"but {len(definitions)} definitions; arrays must be parallel"
                ]
    if component.type == "DidactTimeline":
        steps = component.props.get("steps")
        details = component.props.get("details")
        if isinstance(steps, list) and isinstance(details, list):
            if not steps:
                return [f"component {component.id!r}: DidactTimeline needs at least one step"]
            if details and len(steps) != len(details):
                return [
                    f"component {component.id!r}: DidactTimeline has {len(steps)} steps "
                    f"but {len(details)} details; use [] or one detail per step"
                ]
    if component.type == "DidactWorkedExample":
        steps = component.props.get("steps")
        if isinstance(steps, list) and not steps:
            return [f"component {component.id!r}: DidactWorkedExample needs at least one step"]
    if component.type == "LearningExperience":
        experience_id = component.props.get("experience_id")
        implementation_ref = component.props.get("implementation_ref")
        definition_ref = component.props.get("definition_ref")
        if not isinstance(experience_id, str) or not experience_id.strip():
            return [
                f"component {component.id!r}: LearningExperience needs a non-empty experience_id"
            ]
        if not isinstance(implementation_ref, str) or "@" not in implementation_ref:
            return [
                f"component {component.id!r}: LearningExperience implementation_ref must pin a version"
            ]
        if not isinstance(definition_ref, str) or not definition_ref.strip():
            return [
                f"component {component.id!r}: LearningExperience needs a non-empty definition_ref"
            ]
    if component.type == "DidactActivity":
        activity_id = component.props.get("activity_id")
        component_id = component.props.get("component_id")
        if not isinstance(activity_id, str) or not activity_id.strip():
            return [f"component {component.id!r}: DidactActivity needs a non-empty activity_id"]
        if not isinstance(component_id, str) or not component_id.startswith("didact."):
            return [f"component {component.id!r}: DidactActivity component_id must start with 'didact.'"]
    return []


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
            problem = _check_value(prop, self.props[prop.name], spec.signature)
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

        errors.extend(_table_shape_errors(self))
        errors.extend(_didact_parallel_list_errors(self))

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


class GenerationProvenance(BaseModel):
    """Server-only provenance stored beside the validated IR, never in dialect text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    shell_mode: Literal["legacy_stepper", "episode"]
    generation_policy_key: str = Field(min_length=1, max_length=120)
    episode_status: Literal["ready", "support_only", "declined", "not_requested"]


class UISpec(BaseModel):
    """The persisted IR. Serialized to ``node_renders.ui_spec`` verbatim."""

    model_config = ConfigDict(extra="forbid")

    VERSION: ClassVar[str] = UI_SPEC_VERSION

    version: str = UI_SPEC_VERSION
    format: str
    root: str
    components: list[Component] = Field(default_factory=list)
    # Accepted when an archived DB row is revalidated, but excluded from ordinary model
    # dumps and therefore from OpenUI serialization/golden fixtures. `_persist` alone adds
    # it to the server-side JSONB after the UI contract has passed.
    generation: GenerationProvenance | None = Field(default=None, exclude=True)

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
                f"rule 4: a spec holds at most {MAX_COMPONENTS} blocks "
                f"(got {len(self.components)}){_crowded_parent(self.components)}. "
                "A sub-component written inline inside a children array is a block too. "
                "A list of N items is ONE block — a StepSequence, a Table, or a single "
                "TextContent whose text carries the list — never one block per item"
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


def _crowded_parent(components: list[Component]) -> str:
    """``" - 'lista' alone holds 14 of them"`` - or ``""`` when nothing stands out.

    No ``"; "`` anywhere in the returned text: ``flatten_validation_error`` splits on it,
    and half a sentence arriving as its own bullet is how a clear message becomes two
    unclear ones.

    Rule 4's bare count is a number the model can only obey by deleting something, and
    measured it deletes the wrong thing: on ``alergenos-hosteleria`` (2026-07-27) the
    over-count was 14 one-line ``TextContent`` blocks inside a single ``Card``, i.e. a
    bullet list the kit has no component for, and "got 19" pointed at none of that. The
    fix is one clause naming the container that holds the most children, because that
    container is the list, and merging it is the whole repair.

    Silent at or below :data:`MAX_ROOT_CHILDREN` children, and that threshold is the
    point: a container holding more than a whole root level's worth of blocks is a list,
    and nothing else is. Measured on the same run, ``devoluciones-tienda`` also blew rule
    4 — with eighteen blocks spread flat across the program, the fullest container being
    the root with four. Naming the root there would have been a guess, and a guess in a
    message the repair loop replays verbatim is how the loop stops converging.
    """
    if not components:
        return ""
    fullest = max(components, key=lambda component: len(component.children))
    if len(fullest.children) <= MAX_ROOT_CHILDREN:
        return ""
    return f" - {fullest.id!r} alone holds {len(fullest.children)} of them"


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
