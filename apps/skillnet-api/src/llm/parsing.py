"""Robust JSON extraction from LLM responses.

LLMs frequently wrap JSON in prose or markdown fences, or emit minor syntax
errors. These pure functions recover the JSON without another network call, so
they are fully unit-testable. Callers that still fail can re-prompt the model.

Two recovery rules here were paid for by a generation that died at
``design_structure`` and are worth stating outright:

* **Reasoning wrappers are stripped before anything is parsed.** A model that
  thinks out loud restates the requested shape while it thinks, and the shape
  sketches in ``src/llm/prompts/generation.py`` are full of braces
  (``{"title": str, ...}``). Scanning the raw text for a balanced ``{...}``
  therefore locks onto a fragment of the *reasoning*, not the answer.
* **The first balanced span is not necessarily the answer.** The old code
  returned it regardless, so one brace in a sentence was enough to lose an
  otherwise perfect response. Every balanced span is now a candidate, only the
  ones that actually parse are considered, and the longest of those wins — the
  real payload encloses every fragment inside it, so it is the longest by
  construction.

When nothing parses the raw response goes into the log *and* into the error, in
the log under the greppable :data:`PARSE_FAILED` marker. An opaque "Could not
parse JSON" is unactionable: the next person needs to see what the provider
actually sent.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.core.exceptions import LLMError
from src.core.logging import get_logger

logger = get_logger(__name__)

_CODE_BLOCK = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")

#: Tag names that wrap a model's chain of thought in the *content* field. Not a
#: provider-specific list: every model family that has shipped visible thinking has
#: used one of these spellings, and stripping a tag no ordinary answer contains costs
#: nothing when the model never emits one.
REASONING_TAGS: tuple[str, ...] = (
    "think",
    "thinking",
    "reason",
    "reasoning",
    "reflection",
    "scratchpad",
)

_TAG_ALT = "|".join(REASONING_TAGS)
#: ``<think ...>...</think>``. The backreference keeps ``<think>`` from being closed by
#: ``</reasoning>``, so a stray closer stays visible to the rules below.
_CLOSED_REASONING = re.compile(
    rf"<(?P<tag>{_TAG_ALT})\b[^>]*>.*?</(?P=tag)\s*>", re.DOTALL | re.IGNORECASE
)
_OPEN_REASONING = re.compile(rf"<(?:{_TAG_ALT})\b[^>]*>", re.IGNORECASE)
_CLOSING_REASONING = re.compile(rf"</(?:{_TAG_ALT})\s*>", re.IGNORECASE)

#: How much of an unparseable response is written to the log and the error. Long enough
#: to see the shape and where it went wrong, short enough not to flood the log with a
#: 40 KB course.
RAW_PREVIEW_CHARS = 2000

#: Log marker for "the provider answered, and it was not JSON". Greppable, and
#: deliberately not shared with any other failure — the sibling of
#: ``src.llm.client.BUDGET_EXHAUSTED``, which is the *other* way a response arrives
#: unusable.
PARSE_FAILED = "llm.json_parse_failed"

#: Balanced spans examined per bracket type. Bounded because the scan is quadratic in
#: the worst case, and because a response needing a 25th candidate is not a response
#: with a recoverable payload.
MAX_CANDIDATE_SPANS = 24

_NOTHING = object()


def strip_reasoning(text: str) -> str:
    """Remove chain-of-thought wrappers, including the unterminated ones.

    Three shapes, all observed in the wild:

    1. ``<think>...</think>{"a": 1}`` — a closed block, dropped whole.
    2. ``...reasoning...</think>{"a": 1}`` — a *stray closer*. Chat templates that
       inject the opening tag themselves never echo it back, so the response starts
       mid-thought. Everything up to the last closer is thinking.
    3. ``<think>...`` with no closer — the answer was cut off mid-thought (a reasoning
       model that spent its whole ``max_tokens`` budget thinking; see
       ``src.llm.client.budget_for``). Everything from the tag on is thinking, which
       leaves nothing, and "nothing" is a far better diagnosis than "invalid JSON".
    """
    cleaned = _CLOSED_REASONING.sub(" ", text)

    last_closer = None
    for last_closer in _CLOSING_REASONING.finditer(cleaned):
        pass
    if last_closer is not None:
        cleaned = cleaned[last_closer.end() :]

    unterminated = _OPEN_REASONING.search(cleaned)
    if unterminated is not None:
        cleaned = cleaned[: unterminated.start()]

    return cleaned.strip()


def _balanced_span(
    text: str, open_ch: str, close_ch: str, search_from: int
) -> tuple[int, int] | None:
    """Bounds of the first balanced ``open_ch..close_ch`` span at or after ``search_from``.

    String-aware, so a brace inside a JSON string value never changes the depth.
    """
    start = text.find(open_ch, search_from)
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return start, i + 1
    return None


def _candidate_spans(text: str) -> list[str]:
    """Every balanced object/array span, outermost first, both bracket types."""
    spans: list[str] = []
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        search_from = 0
        for _ in range(MAX_CANDIDATE_SPANS):
            found = _balanced_span(text, open_ch, close_ch, search_from)
            if found is None:
                break
            start, end = found
            spans.append(text[start:end])
            # ``start + 1`` and not ``end``: nested spans are candidates too, and the
            # answer is sometimes nested inside a wrapper the model invented.
            search_from = start + 1
    return spans


def _best_parse(spans: list[str]) -> Any:
    """The longest span that parses, or :data:`_NOTHING`.

    Longest and not first, because a prose brace produces a short fragment while the
    real payload produces a long one — and because a bare ``[{...}, {...}]`` answer
    would otherwise be reduced to its first element, which parses perfectly and is the
    wrong answer.
    """
    best: tuple[int, Any] | None = None
    for span in spans:
        for candidate in (span, _TRAILING_COMMA.sub(r"\1", span)):
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if best is None or len(span) > best[0]:
                best = (len(span), value)
            break
    return _NOTHING if best is None else best[1]


def _parse_error(raw: str, context: str | None, detail: str) -> LLMError:
    """Log the raw response under :data:`PARSE_FAILED` and build the error to raise."""
    where = f" [{context}]" if context else ""
    total = len(raw)
    preview = raw[:RAW_PREVIEW_CHARS]
    extent = (
        f"{total} chars"
        if total <= RAW_PREVIEW_CHARS
        else f"first {RAW_PREVIEW_CHARS} of {total} chars"
    )
    logger.error(
        "%s%s: %s. Raw response (%s): %s", PARSE_FAILED, where, detail, extent, preview
    )
    return LLMError(
        f"Could not parse JSON from LLM response{where}: {detail}. "
        f"Raw response ({extent}): {preview}"
    )


def parse_json_response(response: str, *, context: str | None = None) -> Any:
    """Parse an LLM response into a Python object, with recovery strategies.

    Order: direct parse -> strip reasoning wrappers -> direct parse -> fenced code
    blocks -> the longest balanced object/array span that parses (trailing commas
    repaired). Raises :class:`LLMError` if nothing parses, carrying the raw response.

    ``context`` names the call site (``"design_structure"``) in the log line and the
    error, so a failure says *which* of the pipeline's five JSON calls broke.
    """
    if response is None or not response.strip():
        raise LLMError(
            f"Empty LLM response{f' [{context}]' if context else ''}; expected JSON. "
            "The provider returned no content (see llm.budget_exhausted if a reasoning "
            "model spent its token budget thinking)."
        )

    raw = response.strip()

    # A response that is already JSON is returned before anything is stripped from it.
    # Order matters: a lesson is free to contain the *text* "<think>" (Markdown about
    # prompting, say), and rewriting a valid payload to hunt for a wrapper it does not
    # have would be a fix that breaks the working case.
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    text = strip_reasoning(raw)
    if not text:
        raise _parse_error(
            response,
            context,
            "the response was chain-of-thought only, with no answer after it "
            "(cut off mid-thought)",
        )

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = [match.group(1).strip() for match in _CODE_BLOCK.finditer(text)]
    parsed = _best_parse(fenced)
    if parsed is not _NOTHING:
        return parsed

    parsed = _best_parse(_candidate_spans(text))
    if parsed is not _NOTHING:
        return parsed

    # Last resort: the same scan over the text as it arrived. Stripping is a heuristic,
    # and an unterminated ``<think>`` inside a string value would have truncated a
    # payload that was there all along.
    if text != raw:
        parsed = _best_parse(_candidate_spans(raw))
        if parsed is not _NOTHING:
            return parsed

    raise _parse_error(response, context, "no balanced JSON object or array parsed")
