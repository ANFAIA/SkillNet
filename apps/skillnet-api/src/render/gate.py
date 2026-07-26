"""The server-side gate on generated dialect (§5.2, security review of 2026-07-26).

Structural parsing moved to the browser when the real OpenUI dependency was adopted,
but three responsibilities did **not** move, because the model output is untrusted
content derived from a customer PDF:

1. ``answer_key`` never reaches the client. Enforced structurally: rule 5 of §5.2 keeps
   answer data out of the ``UISpec``, and the browser is served text re-serialized *from
   that spec* (:func:`canonicalize`), never the raw model output. A ``UISpec`` cannot
   represent an answer key, so the property holds by construction rather than by check.
2. Size caps, before anything expensive happens.
3. Rejecting reactivity — state, ``Query``, ``Mutation``, ``Action``, builtins — while
   ``settings.RENDER_ALLOW_REACTIVE`` is off, which is the shipped profile.

The reactivity check is deliberately **light and textual**: it does not re-implement a
parser. It blanks every string literal first and then checks the remaining *skeleton*
against the alphabet the frozen grammar of §5.4 can produce. That order matters and it
is the whole trick:

* A keyword grep over the raw text has measured false positives on legitimate prose —
  a lesson that says *"en SQL una Query() se escribe con SELECT"* or *"cuesta $300"* is
  valid content, and rejecting it would be a bug (SEGURIDAD-MUTACIONES.md, control 4).
* Once the strings are blanked, ``$``, ``@``, ``{``, ``?``, ``+`` and ``:`` cannot be
  prose. They can only be state, builtins, objects, ternaries, arithmetic or named
  arguments — none of which exist in this dialect.

This gate is the cheap outer door; the real structural gate is
``OpenUiLangBackend.parse`` (the frozen grammar has no production for any of the above,
so reactivity is *inexpressible*, not blacklisted). The value of the gate is that it
fails with a message the repair prompt can act on, before parsing, and that it also
guards the *canonical* text on the way out.
"""

from __future__ import annotations

import re
import string

from src.config import settings
from src.render.backends import get_render_backend
from src.render.backends.base import RenderBackend
from src.render.errors import RenderValidationError
from src.render.spec import MAX_COMPONENTS, UISpec

#: A 12-component spec with long prose is ~4 kB; 16 kB is generous and still bounds the
#: work a poisoned document can ask of the parser and of the browser.
MAX_PROGRAM_BYTES = 16_384

#: 12 components (rule 4) + a fenced block + blank lines + slack for a repair attempt.
MAX_PROGRAM_LINES = MAX_COMPONENTS + 8

#: One component per line, so a line is one component's worth of text.
MAX_LINE_BYTES = 4_096

#: Everything the frozen grammar of §5.4 can emit outside a string literal. Note what is
#: absent: ``$ @ { } ? : + * / < > ! % ; & | ' \`` and the backtick.
_SKELETON_ALPHABET = frozenset(
    string.ascii_letters + string.digits + '_ \t\r\n=(),[].-"'
)

#: Reserved calls of the real language. Hard-wired in ``lang-core``'s ``RESERVED_CALLS``,
#: so *their* parser accepts them with ``meta.errors == []`` even when no tool is
#: registered; ours has no production for them. Named here only for the error message.
_RESERVED_CALL_RE = re.compile(r"\b(Query|Mutation|Action)\s*\(")

#: Literals the real language has and this dialect does not (§5.4 / prompt rule 4).
_FOREIGN_LITERAL_RE = re.compile(r"\b(true|false|null)\b")

#: Markdown fences are tolerated by the parser (a model that wraps its answer is still
#: emitting a valid program), so the gate has to tolerate them too or it would reject
#: what the parser accepts.
_FENCE_RE = re.compile(r"^[ \t]*```")

_CHAR_NAMES = {
    "$": "state variables ($var)",
    "@": "builtins and actions (@Count, @Run, @OpenUrl)",
    "{": "objects ({k: v})",
    "}": "objects ({k: v})",
    "?": "ternaries (cond ? a : b)",
    ":": "named arguments and objects",
    "+": "arithmetic and string concatenation",
    "*": "arithmetic",
    "/": "arithmetic and // comments",
    "<": "comparisons",
    ">": "comparisons",
    "!": "negation",
    "'": "single-quoted strings",
    "`": "template strings",
    ";": "statement separators",
}


def strip_string_literals(text: str) -> str:
    """Blank every ``"..."`` literal, honouring ``\\"`` and ``\\\\``.

    The result is the *skeleton*: same length in lines, same code characters, zero
    content. An unterminated literal swallows the rest of its line, which is what
    ``parse`` will complain about anyway.
    """
    out: list[str] = []
    inside = False
    escaped = False
    for char in text:
        if inside:
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                inside = False
                out.append('"')
                continue
            if char == "\n":  # unterminated literal: the line ends here
                inside = False
                out.append("\n")
                continue
            continue
        if char == '"':
            inside = True
            out.append('"')
            continue
        out.append(char)
    return "".join(out)


def check_size(text: str) -> list[str]:
    """Size caps. Independent of the security profile: always enforced."""
    problems: list[str] = []
    size = len(text.encode("utf-8"))
    if size > MAX_PROGRAM_BYTES:
        problems.append(
            f"program is {size} bytes; the cap is {MAX_PROGRAM_BYTES}"
        )
    lines = text.splitlines()
    if len(lines) > MAX_PROGRAM_LINES:
        problems.append(
            f"program has {len(lines)} lines; the cap is {MAX_PROGRAM_LINES} "
            f"(rule 4 allows {MAX_COMPONENTS} components)"
        )
    for line_no, line in enumerate(lines, start=1):
        length = len(line.encode("utf-8"))
        if length > MAX_LINE_BYTES:
            problems.append(
                f"line {line_no}: {length} bytes; the cap is {MAX_LINE_BYTES}"
            )
    return problems


def check_static_only(text: str) -> list[str]:
    """Reject reactivity on the string-blanked skeleton. One message per line, at most."""
    problems: list[str] = []
    skeleton = strip_string_literals(text)
    for line_no, line in enumerate(skeleton.split("\n"), start=1):
        if not line.strip() or _FENCE_RE.match(line):
            continue
        foreign = sorted({char for char in line if char not in _SKELETON_ALPHABET})
        if foreign:
            described = ", ".join(
                f"{char!r} ({_CHAR_NAMES[char]})" if char in _CHAR_NAMES else repr(char)
                for char in foreign
            )
            problems.append(
                f"line {line_no}: {described} is not part of the SkillNet dialect; "
                "only text in double quotes, numbers, arrays and bare ids are allowed"
            )
            continue
        reserved = _RESERVED_CALL_RE.search(line)
        if reserved:
            problems.append(
                f"line {line_no}: {reserved.group(1)}(...) is a tool call and this "
                "dialect has no tool calls; the screen is static"
            )
            continue
        literal = _FOREIGN_LITERAL_RE.search(line)
        if literal:
            problems.append(
                f"line {line_no}: {literal.group(1)!r} does not exist in this dialect; "
                "use text in double quotes, a number or an array"
            )
    return problems


def check_program(text: str, *, allow_reactive: bool | None = None) -> list[str]:
    """Every reason to refuse this program before parsing it. Empty == acceptable."""
    if allow_reactive is None:
        allow_reactive = bool(getattr(settings, "RENDER_ALLOW_REACTIVE", False))
    problems = check_size(text)
    if not allow_reactive:
        problems.extend(check_static_only(text))
    return problems


def assert_program_ok(text: str, *, allow_reactive: bool | None = None) -> None:
    """Raise ``RenderValidationError`` with the messages the repair prompt needs."""
    problems = check_program(text, allow_reactive=allow_reactive)
    if problems:
        raise RenderValidationError(problems)


def canonicalize(
    raw: str,
    *,
    ui_format: str | None = None,
    backend: RenderBackend | None = None,
) -> tuple[UISpec, str]:
    """Untrusted output -> validated ``UISpec`` -> the canonical program to serve.

    The second element is the **only** text that may reach the browser. Never send the
    model's own bytes: ``<Renderer response>`` takes text, and shipping the raw output
    would put attacker-directed text straight into the reactive runtime, past both of
    the switches the render is configured with (no ``toolProvider``, no ``onAction``).
    Re-serializing from the spec is what makes that impossible rather than forbidden.
    """
    assert_program_ok(raw)
    resolved = backend or get_render_backend()
    spec = resolved.parse(raw, ui_format=ui_format)
    program = resolved.serialize(spec)
    # Clean by construction: a UISpec cannot hold state, a tool call or an answer key.
    # Asserted anyway, because this is the byte stream the employee's browser parses.
    assert_program_ok(program)
    return spec, program


__all__ = [
    "MAX_LINE_BYTES",
    "MAX_PROGRAM_BYTES",
    "MAX_PROGRAM_LINES",
    "assert_program_ok",
    "canonicalize",
    "check_program",
    "check_size",
    "check_static_only",
    "strip_string_literals",
]
