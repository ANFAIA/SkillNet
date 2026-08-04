"""Robust JSON extraction from LLM responses.

LLMs frequently wrap JSON in prose or markdown fences, or emit minor syntax
errors. These pure functions recover the JSON without another network call, so
they are fully unit-testable. Callers that still fail can re-prompt the model.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.core.exceptions import LLMError
from src.core.logging import get_logger

_logger = get_logger(__name__)

_CODE_BLOCK = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _extract_balanced(text: str, open_ch: str, close_ch: str) -> str | None:
    """Return the first balanced ``open_ch..close_ch`` span, respecting strings."""
    start = text.find(open_ch)
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
                return text[start : i + 1]
    return None


def parse_json_response(response: str) -> Any:
    """Parse an LLM response into a Python object, with recovery strategies.

    Order: direct parse -> fenced code block -> first balanced object/array ->
    cleanup (trailing commas). Raises ``LLMError`` if nothing parses.
    """
    if response is None:
        raise LLMError("Empty LLM response; expected JSON.")

    text = _THINK_BLOCK.sub("", response).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    block = _CODE_BLOCK.search(text)
    if block:
        candidate = block.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            text = candidate  # fall through with the fenced content

    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        span = _extract_balanced(text, open_ch, close_ch)
        if span:
            for candidate in (span, _TRAILING_COMMA.sub(r"\1", span)):
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue

    _logger.error("Could not parse JSON from LLM response. Raw (first 2000 chars): %s", text[:2000])
    raise LLMError("Could not parse JSON from LLM response.")
