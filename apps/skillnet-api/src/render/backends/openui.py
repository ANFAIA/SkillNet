"""The ``openui`` dialect — the server-side gate on generated programs (§5.4).

A **strict subset** of OpenUI Lang, parsed in Python. Line-oriented, one declaration per
line, **positional** arguments in the order of the kit table, references as arrays of
ids:

    root = Stack([intro, steps, quiz], "md")
    intro = TextContent("Las devoluciones se aceptan durante 30 dias.", "lead")

Since the adoption of the real dependency (2026-07-26, ``docs/design/openui-adoption.md``)
this module has **one** job and no longer has two:

* It **no longer teaches the dialect.** ``library.prompt()`` does, from the frontend kit,
  through the build-step artefacts that ``src/render/prompt.py`` reads. There is exactly
  one place where the catalogue is declared, and it is not here.
* It **still validates**, and it is the last gate before anything is persisted or served.
  The frozen grammar below has no production for ``$state``, ``{objects}``, ``@builtins``,
  ternaries, arithmetic, ``Query()`` or ``Mutation()``, so reactivity is *inexpressible*
  rather than blacklisted — which is why this parser was kept when the browser got its
  own. Their parser accepts a stray ``Mutation("delete_all_users", {...})`` with
  ``meta.errors == []``; this one cannot represent it. ``src/render/gate.py`` is the cheap
  door in front, ``serialize`` produces the canonical text the browser is allowed to see.

The standard is wider than this subset: it accepts statements split over several lines,
literal newlines inside strings, inline nesting without an id, booleans, ``null``,
objects, arithmetic, ``//`` comments and markdown fences. In particular **escape rule 3
("a real line break closes a block") is ours, not the standard's** — it is what makes
``parse_partial`` trivial, and the prompt states it as a SkillNet rule for that reason.

The frozen grammar, which this file *is* the implementation of. It used to be exported as
``GRAMMAR`` because it was pasted into the prompt; the prompt now comes from
``library.prompt()``, so it lives here as the specification of the gate and nothing reads
it as data::

    program    = { line } ;
    line       = ident "=" call newline ;
    ident      = ("a".."z" | "A".."Z" | "_") { "a".."z" | "A".."Z" | "0".."9" | "_" } ;
    call       = comp_name "(" [ arg { "," arg } ] ")" ;
    comp_name  = "Stack" | "TextContent" | "Card" | "Callout" | "StepSequence"
               | "Table" | "CodeBlock" | "Chart" | "QuizItem" ;
    arg        = string | number | array | ident ;
    array      = "[" [ arg { "," arg } ] "]" ;
    string     = '"' { char | escape } '"' ;
    escape     = "\\" ( '"' | "\\" | "n" ) ;
    char       = <cualquier caracter excepto '"', '\\' y newline> ;
    number     = [ "-" ] digit { digit } [ "." digit { digit } ] ;

Two things the dialect does **not** carry, and how they are recovered:

* ``root`` — the id no other component lists among its children. Ties fall back to a
  component literally named ``root``, then to the first line.
* ``format`` — inferred from the component mix by :func:`infer_format`, unless the
  caller passes ``ui_format=`` (which is what the runtime does, since
  ``decide_formato`` already decided it). The inference and ``serialize`` agree, so
  ``parse(serialize(spec)) == spec`` holds without a header line, which the frozen
  grammar has no room for.
"""

from __future__ import annotations

import re
from typing import Any, NamedTuple, NoReturn

from pydantic import ValidationError as PydanticValidationError

from src.render.errors import RenderError, RenderParseError
from src.render.kit import (
    LLM_COMPONENT_NAMES,
    UI_KIT,
    ComponentSpec,
    PropKind,
    PropSpec,
)
from src.render.spec import (
    UI_SPEC_VERSION,
    Component,
    UISpec,
    flatten_validation_error,
    parse_spec,
)

_LINE_RE = re.compile(r"^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUMBER_RE = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")
_FENCE_RE = re.compile(r"^[ \t]*```")

#: Content-bearing components. Used only by :func:`infer_format`.
_CONTENT_TYPES = frozenset(UI_KIT.names) - {"Stack", "Card", "QuizItem"}


class _Ref(NamedTuple):
    """An ``ident`` argument: a reference to another component."""

    name: str


class _Scanner:
    """Single-line recursive-descent scanner over the ``call`` production."""

    def __init__(self, text: str, line_no: int, pos: int = 0) -> None:
        self.text = text
        self.line_no = line_no
        self.pos = pos

    # -- primitives ----------------------------------------------------------------

    def fail(self, message: str) -> NoReturn:
        raise RenderParseError(
            f"{message} (col {self.pos + 1})", line_no=self.line_no, line=self.text
        )

    @property
    def eof(self) -> bool:
        return self.pos >= len(self.text)

    def peek(self) -> str:
        return "" if self.eof else self.text[self.pos]

    def skip_ws(self) -> None:
        while not self.eof and self.text[self.pos] in " \t":
            self.pos += 1

    def expect(self, char: str) -> None:
        self.skip_ws()
        found = self.peek() or "end of line"
        if self.peek() != char:
            self.fail(f"expected {char!r}, found {found!r}")
        self.pos += 1

    # -- productions ---------------------------------------------------------------

    def comp_name(self) -> str:
        self.skip_ws()
        match = _IDENT_RE.match(self.text, self.pos)
        if match is None:
            self.fail("expected a component name")
        self.pos = match.end()
        return match.group()

    def string(self) -> str:
        self.pos += 1  # the opening quote
        out: list[str] = []
        while True:
            if self.eof:
                self.fail(
                    "unterminated text value: a string must close its quote on the "
                    'same line (write \\n for a line break, \\" for a quote)'
                )
            char = self.text[self.pos]
            if char == '"':
                self.pos += 1
                return "".join(out)
            if char == "\\":
                self.pos += 1
                if self.eof:
                    self.fail("unterminated escape at end of line")
                escaped = self.text[self.pos]
                if escaped == "n":
                    out.append("\n")
                elif escaped in ('"', "\\"):
                    out.append(escaped)
                else:
                    self.fail(
                        f"invalid escape '\\{escaped}': only \\\", \\\\ and \\n exist"
                    )
                self.pos += 1
                continue
            out.append(char)
            self.pos += 1

    def number(self) -> int | float:
        match = _NUMBER_RE.match(self.text, self.pos)
        if match is None:
            self.fail("expected a number")
        self.pos = match.end()
        raw = match.group()
        return float(raw) if "." in raw else int(raw)

    def array(self) -> list[Any]:
        self.expect("[")
        items: list[Any] = []
        self.skip_ws()
        if self.peek() == "]":
            self.pos += 1
            return items
        while True:
            items.append(self.value())
            self.skip_ws()
            char = self.peek()
            if char == ",":
                self.pos += 1
                self.skip_ws()
                if self.peek() == "]":
                    self.fail("trailing comma before ']'")
                continue
            if char == "]":
                self.pos += 1
                return items
            if not char:
                self.fail("unclosed array: expected ',' or ']' before the end of line")
            if char == ")":
                self.fail("unclosed array: expected ']' before ')'")
            self.fail(_SEPARATOR_HINT.format(expected="',' or ']'", found=char))

    def value(self) -> Any:
        self.skip_ws()
        char = self.peek()
        if not char:
            self.fail("expected a value")
        if char == '"':
            return self.string()
        if char == "[":
            return self.array()
        if char == "-" or char.isdigit():
            return self.number()
        match = _IDENT_RE.match(self.text, self.pos)
        if match is None:
            self.fail(f"unexpected character {char!r}")
        self.pos = match.end()
        return _Ref(match.group())

    def args(self) -> list[Any]:
        self.expect("(")
        items: list[Any] = []
        self.skip_ws()
        if self.peek() == ")":
            self.pos += 1
            return items
        while True:
            items.append(self.value())
            self.skip_ws()
            char = self.peek()
            if char == ",":
                self.pos += 1
                continue
            if char == ")":
                self.pos += 1
                return items
            if not char:
                self.fail(
                    "unclosed argument list: expected ',' or ')' before the end of line"
                )
            self.fail(_SEPARATOR_HINT.format(expected="',' or ')'", found=char))


_SEPARATOR_HINT = (
    "expected {expected}, found {found!r}; the usual cause is an unescaped double "
    'quote inside a text value, which must be written \\"'
)


def _normalize_lines(raw: str) -> list[str]:
    """Split on ``\\n`` only: a lone ``\\r`` is a legal ``char`` inside a string."""
    return raw.replace("\r\n", "\n").split("\n")


def _skippable(line: str) -> bool:
    """Blank lines and markdown fences are not content, so they are dropped.

    The grammar has no production for either; a model that wraps its answer in a
    fenced block is still emitting a valid program, and failing on the fence would
    burn the single repair attempt on punctuation.
    """
    return not line.strip() or _FENCE_RE.match(line) is not None


def _parse_line(line: str, line_no: int) -> tuple[str, str, list[Any]]:
    """``ident "=" call`` → ``(ident, comp_name, args)``."""
    head = _LINE_RE.match(line)
    if head is None:
        raise RenderParseError(
            "expected a declaration of the form: id = Componente(argumentos)",
            line_no=line_no,
            line=line,
        )
    scanner = _Scanner(line, line_no, head.end())
    comp_name = scanner.comp_name()
    args = scanner.args()
    scanner.skip_ws()
    if not scanner.eof:
        scanner.fail(f"unexpected trailing text after ')': {line[scanner.pos :]!r}")
    return head.group(1), comp_name, args


def _component_from_call(
    ident: str, comp_name: str, args: list[Any], line_no: int, line: str
) -> Component:
    spec: ComponentSpec | None = UI_KIT.get(comp_name)
    if spec is None or not spec.llm_emittable:
        raise RenderParseError(
            f"unknown component {comp_name!r}; the catalogue is closed: "
            f"{', '.join(LLM_COMPONENT_NAMES)}",
            line_no=line_no,
            line=line,
        )
    if len(args) != len(spec.props):
        raise RenderParseError(
            f"{comp_name} takes {len(spec.props)} positional arguments — "
            f"{spec.signature} — got {len(args)}",
            line_no=line_no,
            line=line,
        )

    props: dict[str, Any] = {}
    children: list[str] = []
    for prop, value in zip(spec.props, args, strict=True):
        if prop.kind is PropKind.REFS:
            if not isinstance(value, list) or not all(isinstance(v, _Ref) for v in value):
                raise RenderParseError(
                    f"{comp_name} argument {prop.name!r} must be an array of component "
                    "ids without quotes, e.g. [intro, steps]",
                    line_no=line_no,
                    line=line,
                )
            children = [ref.name for ref in value]
        else:
            props[prop.name] = _unwrap(value)

    try:
        return Component(id=ident, type=comp_name, props=props, children=children)
    except PydanticValidationError as exc:
        raise RenderParseError(
            "; ".join(flatten_validation_error(exc)), line_no=line_no, line=line
        ) from exc


def _unwrap(value: Any) -> Any:
    """Keep ``_Ref`` distinguishable so kit validation rejects it as a value."""
    if isinstance(value, _Ref):
        return {"$ref": value.name}
    if isinstance(value, list):
        return [_unwrap(item) for item in value]
    return value


def _pick_root(components: list[Component]) -> str:
    if not components:
        return ""
    referenced = {child for component in components for child in component.children}
    unreferenced = [c.id for c in components if c.id not in referenced]
    if len(unreferenced) == 1:
        return unreferenced[0]
    if any(c.id == "root" for c in components):
        return "root"
    if unreferenced:
        return unreferenced[0]
    return components[0].id


def infer_format(components: list[Component]) -> str:
    """Recover ``UISpec.format`` from the component mix.

    The dialect has no header line (the grammar is frozen at ``program = { line }``),
    so the format is either supplied by the caller or derived here. Deterministic and
    total, which is what makes the round trip exact.
    """
    types = {c.type for c in components}
    has_quiz = "QuizItem" in types
    content = types & _CONTENT_TYPES
    if has_quiz and content:
        return "mixed"
    if has_quiz:
        return "exercise"
    if "Chart" in types:
        return "chart"
    return "explanation"


def _quote(text: str) -> str:
    """The three escape rules, applied in the only safe order."""
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r\n", "\\n")
        .replace("\r", "\\n")
        .replace("\n", "\\n")
    )
    return f'"{escaped}"'


def _number(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RenderError(f"{value!r} is not a number")
    return str(value)


def _render_value(value: Any, prop: PropSpec) -> str:
    match prop.kind:
        case PropKind.STRING | PropKind.ENUM:
            if not isinstance(value, str):
                raise RenderError(f"prop {prop.name!r} must be a string, got {value!r}")
            return _quote(value)
        case PropKind.STRING_LIST:
            if not isinstance(value, list):
                raise RenderError(f"prop {prop.name!r} must be an array, got {value!r}")
            return "[" + ", ".join(_quote(str(item)) for item in value) + "]"
        case PropKind.STRING_MATRIX:
            if not isinstance(value, list):
                raise RenderError(f"prop {prop.name!r} must be an array, got {value!r}")
            rows = [
                "[" + ", ".join(_quote(str(cell)) for cell in row) + "]" for row in value
            ]
            return "[" + ", ".join(rows) + "]"
        case PropKind.NUMBER_LIST:
            if not isinstance(value, list):
                raise RenderError(f"prop {prop.name!r} must be an array, got {value!r}")
            return "[" + ", ".join(_number(item) for item in value) + "]"
        case PropKind.REFS:  # pragma: no cover - handled by the caller
            raise RenderError("refs are serialized from Component.children")


class OpenUiLangBackend:
    """Reference implementation of :class:`~src.render.backends.base.RenderBackend`."""

    name = "openui"

    # -- parsing -------------------------------------------------------------------

    def parse(self, raw: str, *, ui_format: str | None = None) -> UISpec:
        """Parse a complete program. Raises ``RenderParseError``."""
        components: list[Component] = []
        for line_no, line in enumerate(_normalize_lines(raw), start=1):
            if _skippable(line):
                continue
            ident, comp_name, args = _parse_line(line, line_no)
            components.append(_component_from_call(ident, comp_name, args, line_no, line))

        if not components:
            raise RenderParseError(
                "empty program: expected at least one 'id = Componente(...)' line"
            )

        return parse_spec(
            {
                "version": UI_SPEC_VERSION,
                "format": ui_format or infer_format(components),
                "root": _pick_root(components),
                "components": [c.model_dump() for c in components],
            }
        )

    def parse_partial(self, raw: str, *, ui_format: str | None = None) -> UISpec:
        """Tolerant parse of a stream prefix. Never raises.

        Drops the trailing line while it is still half-written, and silently skips any
        line that does not parse — mid-stream a truncated line is normal, not an error.
        """
        lines = _normalize_lines(raw)
        if not raw.endswith("\n"):
            lines = lines[:-1]

        components: list[Component] = []
        index: dict[str, int] = {}
        for line_no, line in enumerate(lines, start=1):
            if _skippable(line):
                continue
            try:
                ident, comp_name, args = _parse_line(line, line_no)
                component = _component_from_call(ident, comp_name, args, line_no, line)
            except (RenderError, PydanticValidationError, ValueError):
                continue
            if component.id in index:
                components[index[component.id]] = component
            else:
                index[component.id] = len(components)
                components.append(component)

        payload = {
            "version": UI_SPEC_VERSION,
            "format": ui_format or infer_format(components),
            "root": _pick_root(components),
            "components": [c.model_dump() for c in components],
        }
        try:
            return parse_spec(payload, partial=True)
        except RenderError:
            # Cannot happen with the payload above; the contract is "never raises".
            return UISpec.model_construct(
                version=UI_SPEC_VERSION,
                format=str(payload["format"]),
                root=str(payload["root"]),
                components=components,
            )

    # -- serialization -------------------------------------------------------------

    def serialize(self, spec: UISpec) -> str:
        """Spec -> the canonical program text. The only thing the browser may receive.

        Covers the **whole** kit, ``Markdown`` included, which ``parse`` still refuses:
        the asymmetry is the point. The model may not emit ``Markdown``; the server
        authors it for ``fallback_seed``, and now that the browser is served dialect
        instead of JSON, the fallback needs a dialect form too. The frontend library
        therefore registers ten components while the prompt catalogue advertises nine.
        """
        lines: list[str] = []
        for component in spec.components:
            kit_spec = UI_KIT.get(component.type)
            if kit_spec is None:
                raise RenderError(f"component type {component.type!r} is not in the kit")
            args = [
                "[" + ", ".join(component.children) + "]"
                if prop.kind is PropKind.REFS
                else _render_value(component.props.get(prop.name), prop)
                for prop in kit_spec.props
            ]
            lines.append(f"{component.id} = {component.type}({', '.join(args)})")
        return "".join(f"{line}\n" for line in lines)


__all__ = ["OpenUiLangBackend", "infer_format"]
