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

**Letters are not reactivity, in any script.** Until 2026-07-27 the skeleton alphabet was
spelled out in ASCII, so ``conclusión = TextContent(...)`` was refused here as though the
``ó`` were a state sigil, with a message that named the character and not the identifier.
Measured against ``groq/llama-3.1-8b-instant``, that single misclassification cost every
pass of the ``atencion-reclamaciones`` brief. The parser folds an accented id to ASCII
(``src/render/backends/openui.py``); this gate's job is to keep the *punctuation* out, and
it now does only that.

Two of the three size caps also changed on that date, because they were counting the
wrong thing. The unit is now the **logical** line of ``src/render/lines.py`` — one
declaration, however many physical lines it was written on, blank lines and fences
excluded. Counting physical lines had refused a ten-declaration program as "23 lines"
because the model put a blank line between each pair, and had refused a five-declaration
program as "25 lines" because it wrapped a children array. Neither program was oversized;
both messages sent the model to shorten a lesson that was already the right length. The
numbers themselves are unchanged.

This gate is the cheap outer door; the real structural gate is
``OpenUiLangBackend.parse`` (the frozen grammar has no production for any of the above,
so reactivity is *inexpressible*, not blacklisted). The value of the gate is that it
fails with a message the repair prompt can act on, before parsing, and that it also
guards the *canonical* text on the way out.
"""

from __future__ import annotations

import re
import string
import unicodedata

from src.config import settings
from src.render.backends import get_render_backend
from src.render.backends.base import RenderBackend
from src.render.errors import RenderError, RenderValidationError
from src.render.lines import logical_lines
from src.render.spec import MAX_COMPONENTS, UISpec

#: A 12-component spec with long prose is ~4 kB; 16 kB is generous and still bounds the
#: work a poisoned document can ask of the parser and of the browser. This is the only
#: cap that short-circuits: past it, nothing is parsed at all.
MAX_PROGRAM_BYTES = 16_384

#: 12 declarations (rule 4) + slack for a repair attempt. Counted in **logical** lines,
#: so blank lines, fences and a wrapped children array cost nothing — see the module
#: docstring for what counting physical lines cost instead.
MAX_PROGRAM_LINES = MAX_COMPONENTS + 8

#: One declaration per logical line, so a logical line is one component's worth of text.
#: Applied to the joined line rather than to each physical fragment: the joined line is
#: what the scanner walks, so it is the length that bounds the work.
MAX_LINE_BYTES = 4_096

#: Everything the frozen grammar of §5.4 can emit outside a string literal, plus every
#: **letter**, in any script (see the module docstring: a letter cannot be reactivity, and
#: refusing accented ids here is what broke the Spanish corpus). Note what is still
#: absent, and is the whole point: ``$ @ { } ? : + * / < > ! % ; & | ' \`` and the
#: backtick.
_SKELETON_ASCII = frozenset(string.ascii_letters + string.digits + '_ \t\r\n=(),[].-"')


def _is_dialect_char(char: str) -> bool:
    """Whether ``char`` can appear outside a string literal in a valid program.

    ``isalpha()`` covers every script; a combining mark is not alphanumeric, so the
    decomposed spelling of an accent is admitted explicitly. Both forms are folded to
    ASCII by the parser before anything is persisted or served.
    """
    return char in _SKELETON_ASCII or char.isalpha() or unicodedata.combining(char) != 0


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


def check_program_bytes(text: str) -> list[str]:
    """The one cap that refuses to look any further. Nothing past this is parsed."""
    size = len(text.encode("utf-8"))
    if size > MAX_PROGRAM_BYTES:
        return [f"program is {size} bytes; the cap is {MAX_PROGRAM_BYTES}"]
    return []


def check_size(text: str) -> list[str]:
    """Size caps. Independent of the security profile: always enforced.

    The two line caps count **declarations**, not physical lines, and say "declarations"
    in the message: a model told it wrote 25 lines when it wrote 5 declarations goes and
    deletes content that was never the problem.
    """
    problems: list[str] = check_program_bytes(text)
    lines = logical_lines(text)
    if len(lines) > MAX_PROGRAM_LINES:
        problems.append(
            f"program has {len(lines)} declarations; the cap is {MAX_PROGRAM_LINES} "
            f"(rule 4 allows {MAX_COMPONENTS} blocks)"
        )
    for logical in lines:
        length = len(logical.text.encode("utf-8"))
        if length > MAX_LINE_BYTES:
            problems.append(
                f"line {logical.line_no}: the declaration is {length} bytes; the cap "
                f"is {MAX_LINE_BYTES}"
            )
    return problems


def check_static_only(text: str) -> list[str]:
    """Reject reactivity on the string-blanked skeleton. One message per line, at most.

    Physical lines here, not logical ones: the number in the message has to be the number
    of the line the offending character is really on, and a stray ``{`` is precisely the
    character the joiner refuses to let open a continuation.
    """
    problems: list[str] = []
    skeleton = strip_string_literals(text)
    for line_no, line in enumerate(skeleton.split("\n"), start=1):
        if not line.strip() or _FENCE_RE.match(line):
            continue
        foreign = sorted({char for char in line if not _is_dialect_char(char)})
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

    **Gate problems and parse problems are reported together.** There is exactly one
    repair attempt (``MAX_UI_RETRIES``), so every error the model does not hear about on
    the first refusal is an error it gets to make again on the second. Measured on
    ``alergenos-hosteleria`` (2026-07-27): attempt 0 was refused for its line count alone,
    the model fixed exactly that, and attempt 1 was refused for the 19 blocks nobody had
    mentioned — one defect, two attempts, no attempts left. Only the byte cap still
    short-circuits, because past it there is a real reason not to parse.
    """
    oversized = check_program_bytes(raw)
    if oversized:
        raise RenderValidationError(oversized)

    problems = check_program(raw)
    resolved = backend or get_render_backend()
    try:
        spec = resolved.parse(raw, ui_format=ui_format)
    except RenderError as exc:
        found = list(getattr(exc, "errors", None) or [str(exc)])
        problems.extend(message for message in found if message not in problems)
        raise RenderValidationError(problems) from exc
    if problems:
        raise RenderValidationError(problems)

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
    "check_program_bytes",
    "check_size",
    "check_static_only",
    "strip_string_literals",
]
