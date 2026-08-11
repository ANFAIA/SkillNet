"""The per-learner narrative memory — a sectioned, human-readable "user.md".

This is the prose complement to the numeric learner model. ``format_vector`` and
``tutor_notes`` (``learner_profile_service``) stay a controlled vocabulary on purpose —
auditable, erasable, never LLM prose. This module holds the one field where that rule is
**deliberately reversed**: a short markdown notebook of how the learner actually uses the
app (what they ask the tutor, the steering they type when generating media, where they
struggle, what they prefer), written in plain language and read back by the tutor as
context. See ``docs/learner-memory.md`` for the design and the privacy decision.

Two halves, and the split is the whole point:

* Everything above :class:`LearnerMemoryService` is a **pure function** over markdown
  strings — no session, no network, no LLM. The curation (dedupe near-duplicates, cap the
  entries per section, supersede a stale line rather than append a near-copy) lives here so
  it is deterministic and unit-testable without a database, which this repo requires.
* :class:`LearnerMemoryService` is the thin DB layer: read ``learner_profiles.memory_md``,
  run the pure merge, write it back with a fresh ``memory_updated_at``.

**Privacy.** The notebook is the learner's own (GDPR right of access / rectification /
erasure via ``GET|PUT|DELETE /users/me/memory``). The admin never reads it. Only ONE writer
keeps a short slice of the user's own text verbatim — the media steering note — and it is
called out in the doc; every other writer stores a distilled observation, never raw chat.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone

from src.core.logging import get_logger
from src.repositories.learner_profile_repo import LearnerProfileRepository

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# The fixed shape of the notebook
# ---------------------------------------------------------------------------

#: The five section headings, in render order. FIXED: a writer names one of these or the
#: call is rejected, so the notebook can never sprout an ad-hoc section and the read-back
#: prompt knows exactly what it is looking at.
SECTIONS: tuple[str, ...] = (
    "Perfil declarado",
    "Cómo aprende",
    "Le cuesta / dudas frecuentes",
    "Preferencias de contenido",
    "Notas del tutor",
)
_SECTION_SET = frozenset(SECTIONS)

#: One entry is one short line. Longer than this and it stops being an observation and
#: starts being a transcript, which is the thing this notebook must never become.
ENTRY_MAX_CHARS = 240

#: Newest N entries kept per section; older ones drop off the top. Small on purpose — the
#: notebook is a summary, and the whole of it has to fit a prompt budget.
MAX_ENTRIES_PER_SECTION = 8

#: Hard ceiling on the whole notebook, enforced on write (PUT) and on read-back. A learner
#: editing their own memory can write what they like, but not without bound.
MAX_TOTAL_CHARS = 8_000

#: Two entries whose normalized token sets overlap by at least this share are "the same
#: thing said twice"; the newer supersedes the older instead of piling up next to it.
_DUP_JACCARD = 0.7

#: The body of an empty section. Rendered so the ``PUT`` view is a full skeleton, and
#: skipped on parse so it never round-trips back into a literal entry.
EMPTY_MARKER = "_(sin datos)_"

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


class UnknownSectionError(ValueError):
    """Raised when a writer names a section outside :data:`SECTIONS`."""


# ---------------------------------------------------------------------------
# Pure helpers: text hygiene
# ---------------------------------------------------------------------------


def clean_entry(text: str) -> str:
    """One printable line, whitespace collapsed, capped at :data:`ENTRY_MAX_CHARS`.

    Newlines collapse to spaces so a multi-line paste can never break the ``- `` bullet
    structure the parser relies on, and the cap keeps a runaway note from swallowing the
    section.
    """
    collapsed = _WS_RE.sub(" ", str(text)).strip()
    printable = "".join(ch for ch in collapsed if ch.isprintable())
    if len(printable) > ENTRY_MAX_CHARS:
        printable = printable[:ENTRY_MAX_CHARS].rstrip() + "…"
    return printable


def _normalize(text: str) -> str:
    """ASCII-folded, lowercased, punctuation-stripped — the form dedupe compares on."""
    folded = unicodedata.normalize("NFKD", text)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii").lower()
    return _WS_RE.sub(" ", _PUNCT_RE.sub(" ", ascii_only)).strip()


def _is_near_duplicate(a: str, b: str) -> bool:
    """Whether two entries say the same thing (so the newer should supersede the older).

    Three cheap tests, cheapest first: identical after normalization, one contained in the
    other (a note growing a suffix), or a high token-set overlap (the same fact reworded).
    """
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return na == nb
    if na == nb or na in nb or nb in na:
        return True
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / len(ta | tb)
    return overlap >= _DUP_JACCARD


# ---------------------------------------------------------------------------
# Pure helpers: parse / render the markdown
# ---------------------------------------------------------------------------


def blank_sections() -> dict[str, list[str]]:
    """A fresh, empty notebook as an ordered ``{section: []}`` map."""
    return {section: [] for section in SECTIONS}


def parse_sections(markdown: str | None) -> dict[str, list[str]]:
    """Markdown → ``{section: [entry, ...]}`` over the fixed sections.

    Robust to a freeform edit (a learner may have rewritten their own notebook via ``PUT``):
    text is split on ``## `` headings, a heading in :data:`SECTIONS` collects the bullet /
    non-blank lines under it, and anything under an unrecognized heading is simply dropped on
    the next :func:`render` — the notebook is normalized back to its five sections. Content
    before the first heading is ignored for the same reason. Each entry has its leading
    ``- ``/``* `` bullet stripped.
    """
    result = blank_sections()
    if not markdown:
        return result
    current: str | None = None
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        heading = _heading_of(line)
        if heading is not None:
            current = heading if heading in _SECTION_SET else None
            continue
        if current is None:
            continue
        entry = _strip_bullet(line)
        if entry and entry != EMPTY_MARKER:
            result[current].append(entry)
    return result


def _heading_of(line: str) -> str | None:
    """The heading text of a ``## Heading`` line, or ``None`` for a body line."""
    stripped = line.strip()
    if stripped.startswith("## "):
        return stripped[3:].strip()
    return None


def _strip_bullet(line: str) -> str:
    stripped = line.strip()
    if stripped[:2] in ("- ", "* "):
        return stripped[2:].strip()
    return stripped


def render(sections: dict[str, list[str]]) -> str:
    """``{section: [entry, ...]}`` → the canonical notebook markdown.

    Every section is emitted in :data:`SECTIONS` order, empty ones included (an empty one
    reads as ``_(sin datos)_``), so the shape is stable and the learner's ``PUT`` view is
    always the same skeleton. Deterministic: same input, same bytes.
    """
    blocks: list[str] = ["# Lo que SkillNet ha aprendido de ti", ""]
    for section in SECTIONS:
        blocks.append(f"## {section}")
        entries = sections.get(section) or []
        if entries:
            blocks.extend(f"- {entry}" for entry in entries)
        else:
            blocks.append(EMPTY_MARKER)
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"


def blank_markdown() -> str:
    """The empty notebook, rendered — what a learner with no history sees."""
    return render(blank_sections())


# ---------------------------------------------------------------------------
# Pure core: the merge (dedupe + supersede + cap)
# ---------------------------------------------------------------------------


def merge_entry(entries: Iterable[str], text: str) -> list[str]:
    """Add ``text`` to a section's entries with curation, returning the new list.

    The rules, in order:

    1. **Clean** the incoming text to one capped line (:func:`clean_entry`); an empty result
       is a no-op.
    2. **Supersede** near-duplicates: every existing entry that says the same thing
       (:func:`_is_near_duplicate`) is dropped, and the fresh wording is appended at the end.
       This is what keeps the notebook from growing three slightly-different copies of one
       fact — a stale line is replaced, never accumulated.
    3. **Cap** to the newest :data:`MAX_ENTRIES_PER_SECTION`.
    """
    cleaned = clean_entry(text)
    current = [e for e in entries if e]
    if not cleaned:
        return current
    kept = [e for e in current if not _is_near_duplicate(e, cleaned)]
    kept.append(cleaned)
    if len(kept) > MAX_ENTRIES_PER_SECTION:
        kept = kept[-MAX_ENTRIES_PER_SECTION:]
    return kept


def note_markdown(markdown: str | None, section: str, text: str) -> str:
    """Pure end-to-end: parse, merge one note into ``section``, re-render.

    Raises :class:`UnknownSectionError` for a section outside :data:`SECTIONS` — a typo in a
    writer must fail loud in tests, not silently create a sixth section.
    """
    if section not in _SECTION_SET:
        raise UnknownSectionError(section)
    sections = parse_sections(markdown)
    sections[section] = merge_entry(sections[section], text)
    return render(sections)


def normalize_for_storage(markdown: str) -> str:
    """A learner's freeform ``PUT`` → the canonical five-section notebook, size-capped.

    Their content is preserved (parsed into whatever sections it maps to and re-rendered);
    unknown sections drop away and the whole is capped at :data:`MAX_TOTAL_CHARS`, so a
    self-edit can reshape the notebook but not turn it into an unbounded scratch file.
    """
    canonical = render(parse_sections(markdown))
    if len(canonical) > MAX_TOTAL_CHARS:
        canonical = canonical[:MAX_TOTAL_CHARS].rstrip() + "\n…\n"
    return canonical


def render_for_prompt(markdown: str | None, *, max_chars: int = 1_500) -> str:
    """The notebook trimmed for injection into a prompt: empty sections dropped, capped.

    Returns ``""`` when there is nothing worth injecting (a brand-new learner), so the
    caller can skip the block entirely rather than paste an empty skeleton into the turn.
    """
    sections = parse_sections(markdown)
    blocks: list[str] = []
    for section in SECTIONS:
        entries = sections.get(section) or []
        if not entries:
            continue
        blocks.append(f"## {section}")
        blocks.extend(f"- {entry}" for entry in entries)
    if not blocks:
        return ""
    text = "\n".join(blocks)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n… (memoria recortada)"
    return text


# ---------------------------------------------------------------------------
# The DB-backed service
# ---------------------------------------------------------------------------


class LearnerMemoryService:
    """Read/curate/write ``learner_profiles.memory_md``. The pure core does the thinking.

    The repository flushes; the route owns the transaction (repo convention of this repo).
    Every method takes ``user_id`` (+ ``org_id`` where a row may need creating) rather than a
    ``User`` ORM object, so it composes with both the request path and the background writers
    without dragging the whole model in.
    """

    def __init__(self, profiles: LearnerProfileRepository) -> None:
        self.profiles = profiles

    async def get(self, user_id: uuid.UUID) -> str:
        """The learner's notebook as canonical markdown; the empty skeleton if none yet."""
        profile = await self.profiles.get_by_user(user_id)
        stored = getattr(profile, "memory_md", None) if profile else None
        return stored if stored else blank_markdown()

    async def get_for_prompt(
        self, user_id: uuid.UUID, *, max_chars: int = 1_500
    ) -> str:
        """The trimmed, no-empty-sections view for a prompt; ``""`` when there is nothing."""
        profile = await self.profiles.get_by_user(user_id)
        stored = getattr(profile, "memory_md", None) if profile else None
        return render_for_prompt(stored, max_chars=max_chars)

    async def note(
        self,
        *,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        section: str,
        text: str,
        source: str,
        now: datetime | None = None,
    ) -> str:
        """Merge one distilled observation into ``section`` and persist. Returns the notebook.

        ``source`` (``"media"``, ``"tutor"``, ...) is provenance for the logs only; it is not
        written into the notebook, so the stored markdown stays clean and round-trips through
        a learner's ``PUT`` unchanged. Creates the profile row if the learner has none yet.
        """
        profile = await self.profiles.get_or_create(user_id=user_id, org_id=org_id)
        updated = note_markdown(profile.memory_md, section, text)
        if updated == (profile.memory_md or blank_markdown()):
            # A pure no-op (an exact duplicate note) does not deserve a write or a bumped
            # timestamp; the notebook already says this.
            return updated
        profile.memory_md = updated
        profile.memory_updated_at = _utcnow(now)
        await self.profiles.session.flush()
        logger.info(
            "learner-memory note: user=%s section=%r source=%s", user_id, section, source
        )
        return updated

    async def set(
        self, *, user_id: uuid.UUID, markdown: str, now: datetime | None = None
    ) -> str:
        """Replace the notebook with the learner's own edited markdown (GDPR rectification).

        Normalized back to the canonical five sections and size-capped; returns ``404`` fuel
        (``None``-safe: raises if there is no profile, which the route turns into a 404).
        """
        profile = await self.profiles.get_by_user(user_id)
        if profile is None:
            raise LookupError("learner_profile")
        profile.memory_md = normalize_for_storage(markdown)
        profile.memory_updated_at = _utcnow(now)
        await self.profiles.session.flush()
        return profile.memory_md

    async def clear(self, *, user_id: uuid.UUID, now: datetime | None = None) -> None:
        """Erase just the notebook (GDPR erasure of this field). Idempotent.

        Full erasure of the whole learner profile is ``DELETE /users/me/learner-profile``;
        this blanks only ``memory_md``, so a learner can wipe what the app "remembers" about
        them without discarding their onboarding and progress.
        """
        profile = await self.profiles.get_by_user(user_id)
        if profile is None:
            return
        profile.memory_md = None
        profile.memory_updated_at = _utcnow(now)
        await self.profiles.session.flush()


def _utcnow(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


__all__ = [
    "SECTIONS",
    "ENTRY_MAX_CHARS",
    "MAX_ENTRIES_PER_SECTION",
    "MAX_TOTAL_CHARS",
    "UnknownSectionError",
    "LearnerMemoryService",
    "blank_markdown",
    "blank_sections",
    "clean_entry",
    "merge_entry",
    "note_markdown",
    "normalize_for_storage",
    "parse_sections",
    "render",
    "render_for_prompt",
]
