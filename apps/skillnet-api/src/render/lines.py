"""Where one declaration actually ends: physical lines -> logical lines (§5.4).

Until 2026-07-27 this repository held that *a declaration never continues on the next
line*, and rejected the program when one did. **That was our bug, for the second time**,
and it is the same shape as the one commit 79ede73 fixed: we taught the model a rule the
real language does not have and then charged it a repair attempt for obeying the real
language instead.

The evidence is ``@openuidev/lang-core@0.2.10`` itself. Its statement splitter
(``dist/index.mjs``, ``function split(tokens)``) documents the rule in one sentence:

    Each statement has the form `identifier = expression`. Statements are
    separated by newlines at depth 0 (**newlines inside brackets are ignored**).

and implements exactly that — a ``Newline`` token ends a statement only when the bracket
depth is zero, and is skipped otherwise. The browser therefore *does* accept

    lista = Card("Los 14 alergenos", [
        TextContent("cereales con gluten", "body"),
        TextContent("crustaceos", "body")
    ])

and our parser did not. Measured against ``groq/openai/gpt-oss-120b`` on the
``alergenos-hosteleria`` brief (2026-07-27, ``bench_out/failures/quality-20260727-030727``),
that shape was the model's **first** instinct on both passes, and both times it cost the
whole repair budget: attempt 0 was refused for the line count the wrapping produced, the
model dutifully re-emitted the same program on one line, and only then did it hear about
the real problem (19 blocks). One defect, two attempts, no attempts left.

What is **not** relaxed, and why:

* **A text value still closes its quote on the physical line that opened it.** The real
  language allows a literal newline inside a string; SkillNet rule 1 does not, the prompt
  states it as ours, and it is what keeps :meth:`~src.render.backends.openui
  .OpenUiLangBackend.parse_partial` cheap — a half-streamed string can be dropped by
  looking at one line instead of by re-scanning the program. So when a line ends inside a
  string the logical line ends there too, and ``string()`` reports the unterminated value
  against the line that really opened it.
* **A stray ``{`` does not open anything.** The dialect has no objects, so a model that
  writes ``clave = {`` (measured: ``atencion-reclamaciones`` r2) must hear
  "objects are not part of this dialect" against *that* line, not have the next three
  lines silently swallowed into it.
* **Depth never goes negative.** A stray ``)`` at depth 0 is a defect on its own line;
  letting it drive the depth below zero would make the following declaration a
  continuation of it and move the error somewhere it cannot be understood.

The joiner is the unit of measurement for the gate as well (``src/render/gate.py``):
counting *physical* lines is what let a ten-declaration program be refused as "23 lines"
because the model put a blank line between each pair.
"""

from __future__ import annotations

import re
from typing import NamedTuple

#: A fenced-code marker. A model that wraps its answer in ``` is still emitting a valid
#: program, so the fence is not content — at depth 0. Inside an open bracket a line that
#: looks like a fence is far more likely to be content than a fence, but neither case is
#: reachable from a real model; it is joined, and the parser names it.
_FENCE_RE = re.compile(r"^[ \t]*```")

#: Brackets that make a newline a *continuation* rather than a separator. ``{`` is
#: deliberately absent: see the module docstring.
_OPEN = "(["
_CLOSE = ")]"


class LogicalLine(NamedTuple):
    """One declaration's worth of text, however many physical lines it was written on."""

    #: The physical lines joined by a single space, each already stripped. A space is
    #: always a safe joiner: the only token that could span the break is a string, and a
    #: string may not (see the module docstring), so no token is ever glued or split.
    text: str
    #: 1-based number of the **first** physical line. This is the number the model is
    #: told, because it is the line it has to go and look at.
    line_no: int
    #: How many physical lines were consumed, blank ones included. Only used to keep the
    #: numbering of everything after it honest.
    span: int
    #: Whether every bracket this line opened was closed again. ``False`` only for the
    #: last line of a truncated or malformed program.
    closed: bool


def scan_line(line: str, depth: int) -> tuple[int, bool]:
    """Bracket depth after ``line``, and whether the line ended inside a text value.

    Strings are skipped whole (honouring ``\\"`` and ``\\\\``) so that a parenthesis in
    prose — *"gases (C)"*, which the extintor source really contains — cannot open a
    continuation.
    """
    inside = False
    escaped = False
    for char in line:
        if inside:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                inside = False
            continue
        if char == '"':
            inside = True
        elif char in _OPEN:
            depth += 1
        elif char in _CLOSE:
            depth = max(0, depth - 1)
    return depth, inside


def is_blank_or_fence(line: str) -> bool:
    """A physical line the grammar has no production for and that carries no content."""
    return not line.strip() or _FENCE_RE.match(line) is not None


def normalize_lines(raw: str) -> list[str]:
    """Split on ``\\n`` only: a lone ``\\r`` is a legal ``char`` inside a string."""
    return raw.replace("\r\n", "\n").split("\n")


def logical_lines(raw: str) -> list[LogicalLine]:
    """Every declaration in ``raw``, one entry each, blank lines and fences dropped.

    Total and non-raising: anything this cannot make sense of comes back as a
    :class:`LogicalLine` for the parser to reject with a message, because a joiner that
    raised would move error reporting into a place with no line context.
    """
    physical = normalize_lines(raw)
    out: list[LogicalLine] = []
    index = 0
    while index < len(physical):
        if is_blank_or_fence(physical[index]):
            index += 1
            continue
        start = index
        pieces = [physical[index].strip()]
        depth, in_string = scan_line(physical[index], 0)
        index += 1
        # A line that ended inside a text value is finished here whatever the depth says:
        # the unterminated string is the defect, and it belongs to the line that opened it.
        while depth > 0 and not in_string and index < len(physical):
            if physical[index].strip():
                pieces.append(physical[index].strip())
            depth, in_string = scan_line(physical[index], depth)
            index += 1
        out.append(
            LogicalLine(
                text=" ".join(pieces),
                line_no=start + 1,
                span=index - start,
                closed=depth == 0 and not in_string,
            )
        )
    return out


__all__ = [
    "LogicalLine",
    "is_blank_or_fence",
    "logical_lines",
    "normalize_lines",
    "scan_line",
]
