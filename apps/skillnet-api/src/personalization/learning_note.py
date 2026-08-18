"""The learner's free-text "how I like to learn" note (personalization steering).

One small nullable field on the learner profile where a person says HOW they like a
lesson explained ("me gustan las metaforas", "me gusta entender las bases"). It steers
only the FORM of the explanation, never the facts: it is injected into the episode
generation prompt as bounded *data* (a style hint), and it partitions the render cache so
two learners with different notes get different renders and changing your note re-renders.

Two learners who write the *same* note share a render (same fingerprint), exactly like the
media-offer fingerprint: personalization here is by note content, not by user id.
"""

from __future__ import annotations

import hashlib
import re

#: Length cap for the note. Small on purpose: it is a style preference, not a document, and
#: it travels literally into a shared generation prompt.
LEARNING_NOTE_MAX_CHARS = 500


def normalize_learning_note(note: str | None) -> str:
    """Trim, collapse whitespace and length-cap the note; ``""`` when empty/blank.

    The same normalization is used for storage steering and for the cache fingerprint, so a
    note that differs only by trailing spaces or repeated blanks does not fork the cache.
    """
    if not note:
        return ""
    collapsed = re.sub(r"\s+", " ", str(note)).strip()
    if not collapsed:
        return ""
    return collapsed[:LEARNING_NOTE_MAX_CHARS]


def learning_note_fingerprint(note: str | None) -> str:
    """A stable short fingerprint of the note, or ``""`` when there is no note.

    Empty (the default) leaves every pre-existing cache key untouched: a learner with no
    note keeps sharing the neutral render. A non-empty note widens the key so its render is
    partitioned from the neutral one and from learners with a different note.
    """
    normalized = normalize_learning_note(note)
    if not normalized:
        return ""
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return f"note:{digest}"
