"""The name of the rung an answer stood on. One line, its own module, on purpose.

``tutor.py`` and ``admin.py`` both need it and ``tutor.py`` imports ``admin.py`` (it
re-exports the admin persona for the callers that predate the split), so the type cannot
live in either without a cycle. ``src/services/retrieval.py`` spells the same three values
out inline in ``GroundedContext``; that is deliberate, because the retrieval layer must not
import the prompt layer to describe what it found.
"""

from __future__ import annotations

from typing import Literal

#: The three rungs of the grounding ladder, best first. Persisted in
#: ``chat_messages.metadata`` and sent to the browser as a ``grounding`` SSE event, so the
#: bubble can say where the answer came from without the model having to be trusted to
#: say it.
Grounding = Literal["chunks", "chunks_fts", "document", "general"]

__all__ = ["Grounding"]
