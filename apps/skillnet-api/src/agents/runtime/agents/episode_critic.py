"""Pedagogy critic — a lean second perspective on a generated episode.

One review, one revision. This agent does NOT impose rigid rules (no "must have
exactly N screens", no mandatory component): it reviews whether the SHAPE of an
already-valid episode fits THIS material and domain, and returns concise, actionable
notes plus a boolean ``revise``. The caller (``critic_episode`` graph node) applies the
notes exactly once and never regresses a valid render to fallback if the revision fails.

Reuses the existing multi-agent infrastructure: the ``agents/`` package, ``tier_llm`` and
the runtime prompt module. It is gated by ``MULTI_AGENT_RENDER`` at the call site, so a
deployment without the flag keeps the single-agent behaviour untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.logging import get_logger
from src.llm.parsing import parse_json_response
from src.llm.prompts.runtime import (
    EPISODE_CRITIC_SYSTEM,
    build_episode_critic_prompt,
)

log = get_logger(__name__)

#: Cap the notes so a revision prompt stays small and the model cannot chase a dozen
#: contradictory nudges on its single revision turn.
_MAX_NOTES = 4


@dataclass(frozen=True)
class CriticVerdict:
    """The critic's advisory output. ``revise`` is only honoured when notes exist."""

    revise: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def actionable(self) -> bool:
        return self.revise and bool(self.notes)


async def run_episode_critic(
    *,
    title: str,
    summary: str,
    domain: str,
    program: str,
    screen_count: int,
    assessment_mode: str,
    llm: Any,
) -> CriticVerdict:
    """Review the pedagogy of a valid episode. Fail-open to "no revision" on any error.

    The critic never raises into the render graph: a provider hiccup or malformed JSON
    simply means the original (already valid) episode stands.
    """

    user_prompt = build_episode_critic_prompt(
        title=title,
        summary=summary,
        domain=domain,
        program=program,
        screen_count=screen_count,
        assessment_mode=assessment_mode,
    )
    try:
        raw, _usage = await llm.complete_with_usage(
            EPISODE_CRITIC_SYSTEM,
            user_prompt,
            temperature=0.2,
            max_tokens=512,
            json_mode=True,
        )
        payload = parse_json_response(raw, context="episode_critic")
    except Exception:  # noqa: BLE001 - the critic is optional; never break the render
        log.info("episode_critic_unavailable", exc_info=True)
        return CriticVerdict()

    if not isinstance(payload, dict):
        return CriticVerdict()
    revise = bool(payload.get("revise"))
    raw_notes = payload.get("notes")
    notes: list[str] = []
    if isinstance(raw_notes, (list, tuple)):
        for note in raw_notes:
            if isinstance(note, str) and note.strip():
                notes.append(note.strip())
            if len(notes) >= _MAX_NOTES:
                break
    return CriticVerdict(revise=revise, notes=tuple(notes))


__all__ = ["CriticVerdict", "run_episode_critic"]
