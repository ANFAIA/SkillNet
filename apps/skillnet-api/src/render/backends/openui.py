"""The ``openui`` dialect — default render backend (§5.4).

Line-oriented, one declaration per line, **positional** arguments in the order of the
kit table, references as arrays of ids:

    root = Stack([intro, steps, quiz], "md")
    intro = TextContent("Las devoluciones se aceptan durante 30 dias.", "lead")

Chosen as the default for token density (~50 % less than the equivalent JSON) and
because line orientation makes ``parse_partial`` trivial: every ``\\n`` completes a
component.

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
    UIKit,
)
from src.render.spec import (
    FORMATS_REQUIRING_LEAD,
    MAX_COMPONENTS,
    MAX_ROOT_CHILDREN,
    UI_SPEC_VERSION,
    Component,
    UISpec,
    flatten_validation_error,
    parse_spec,
)

#: The frozen grammar of §5.4. The same text goes verbatim into ``prompt_fragment``.
GRAMMAR = r"""program    = { line } ;
line       = ident "=" call newline ;
ident      = ("a".."z" | "A".."Z" | "_") { "a".."z" | "A".."Z" | "0".."9" | "_" } ;
call       = comp_name "(" [ arg { "," arg } ] ")" ;
comp_name  = "Stack" | "TextContent" | "Card" | "Callout" | "StepSequence"
           | "Table" | "CodeBlock" | "Chart" | "QuizItem" ;
arg        = string | number | array | ident ;
array      = "[" [ arg { "," arg } ] "]" ;
string     = '"' { char | escape } '"' ;
escape     = "\" ( '"' | "\" | "n" ) ;
char       = <cualquier caracter excepto '"', '\' y newline> ;
number     = [ "-" ] digit { digit } [ "." digit { digit } ] ;"""

#: The three rules a small model breaks on day one (§5.4). One malformed fixture each.
ESCAPE_RULES: tuple[str, ...] = (
    '1. Comilla doble dentro de un texto: escribela \\". Nunca sin escapar.',
    "2. Arrays anidados permitidos y OBLIGATORIOS en Table.rows (array de arrays de "
    'texto): Table(["A", "B"], [["1", "2"], ["3", "4"]]).',
    "3. Ningun salto de linea literal dentro de un texto: escribe \\n. Cada salto de "
    "linea real cierra un bloque, asi que uno dentro de una comilla rompe el parseo.",
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


_PREAMBLE = """\
Responde UNICAMENTE con un programa en el dialecto OpenUI Lang descrito abajo.
Sin prosa antes ni despues, sin comentarios, sin JSON.
Una declaracion por linea, con esta forma exacta:

    id = Componente(argumento1, argumento2, ...)

Los argumentos son POSICIONALES y van en el orden de la ficha del componente.
El nombre de la variable ES el id del bloque, y es como lo referencia un contenedor.
Las referencias van sin comillas dentro de un array: Stack([intro, pasos], "md").
Se puede referenciar un id definido en una linea posterior."""


def _catalogue(kit: UIKit) -> str:
    lines = ["CATALOGO (cerrado: no existe ningun otro componente):"]
    for component in kit.llm_components:
        lines.append(f"  {component.signature}")
        lines.append(f"      {component.purpose}")
    return "\n".join(lines)


def _contract() -> str:
    return "\n".join(
        (
            "REGLAS DEL CONTRATO (un spec que las rompa se rechaza):",
            f"  - Como maximo {MAX_COMPONENTS} bloques en total.",
            f"  - Como maximo {MAX_ROOT_CHILDREN} elementos en el nivel raiz.",
            "  - El bloque raiz es un Stack o un Card, y ningun otro bloque lo referencia.",
            "  - En los formatos "
            + " y ".join(sorted(FORMATS_REQUIRING_LEAD))
            + ', el PRIMER hijo de la raiz es un TextContent con variant "lead" o un '
            "Callout: es el hueco de la linea que dice para que le sirve al aprendiz.",
            "  - QuizItem NO lleva la respuesta correcta ni la explicacion: eso viaja "
            "por separado.",
            "  - El texto es texto plano o marcado inline (**negrita**, *cursiva*, "
            "`literal`, enlaces). Nunca HTML.",
            "  - Sin bloques repetidos: no digas lo mismo dos veces en dos formatos.",
        )
    )


_EXAMPLE = """\
EJEMPLO COMPLETO (formato explanation con ejercicio, es decir mixed):
root = Stack([intro, pasos, quiz], "md")
intro = TextContent("Las devoluciones se aceptan durante 30 dias naturales.", "lead")
pasos = StepSequence("Proceso de devolucion", ["Verificar el producto", \
"Escanear el ticket", "Registrar en el sistema", "Emitir el reembolso"])
quiz = QuizItem("q1", "test", "apply", "Un cliente vuelve el dia 32. Que haces?", \
["Aceptar la devolucion", "Ofrecer garantia del fabricante", "Rechazar sin mas", \
"Llamar al encargado"])"""


class OpenUiLangBackend:
    """Reference implementation of :class:`~src.render.backends.base.RenderBackend`."""

    name = "openui"

    # -- prompt --------------------------------------------------------------------

    def prompt_fragment(self, kit: UIKit = UI_KIT) -> str:
        return "\n\n".join(
            (
                _PREAMBLE,
                _catalogue(kit),
                "GRAMATICA (EBNF, congelada):\n" + GRAMMAR,
                "REGLAS DE ESCAPE (las tres que se rompen siempre):\n"
                + "\n".join(f"  {rule}" for rule in ESCAPE_RULES),
                _contract(),
                _EXAMPLE,
            )
        )

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
        """Exact inverse of :meth:`parse` over the nine emittable components."""
        lines: list[str] = []
        for component in spec.components:
            kit_spec = UI_KIT.get(component.type)
            if kit_spec is None:
                raise RenderError(f"component type {component.type!r} is not in the kit")
            if not kit_spec.llm_emittable:
                raise RenderError(
                    f"{component.type} has no form in the {self.name} dialect: it only "
                    "reaches a spec through fallback_seed, which builds JSON directly"
                )
            args = [
                "[" + ", ".join(component.children) + "]"
                if prop.kind is PropKind.REFS
                else _render_value(component.props.get(prop.name), prop)
                for prop in kit_spec.props
            ]
            lines.append(f"{component.id} = {component.type}({', '.join(args)})")
        return "".join(f"{line}\n" for line in lines)


__all__ = ["ESCAPE_RULES", "GRAMMAR", "OpenUiLangBackend", "infer_format"]
