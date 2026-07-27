"""Per-organization feature choices, in one place.

The pattern is the one ``resolve_llm_config`` already established for the provider: the
environment sets what a fresh install does, and the organization's own settings override
it. An admin should not need the person who deployed the tool in order to change how
their own organization works.

Pure functions over the ``organizations.settings`` dict, deliberately: they are read from
request handlers, from background tasks and from tests, and none of those should have to
build an ORM object to ask a yes/no question.
"""

from __future__ import annotations

from typing import Any

#: Key in ``organizations.settings``. Absent means "never chosen", which is not the same
#: as ``False`` and is why the default lives here rather than in a column default.
CHAT_GENERATIVE_UI = "chat_generative_ui"


def chat_generative_ui_enabled(org_settings: dict[str, Any] | None) -> bool:
    """Whether the tutor may lay its answers out in the SkillNet kit.

    **On unless the admin turns it off.** It is the product, and it already degrades on
    its own: a model that returns a program the gate rejects gets the prose answer
    instead, with no hole in the page. So this switch is not a safety net — the fallback
    is. It exists so an admin can *choose*, for the two reasons an admin actually has:
    their model is not good enough at the dialect to be worth the attempt, or they do not
    want to pay for a second call per answer.

    Anything other than an explicit ``False`` reads as on. A malformed value in a JSONB
    column should not silently disable a feature nobody asked to disable.
    """
    if not org_settings:
        return True
    return org_settings.get(CHAT_GENERATIVE_UI) is not False


__all__ = ["CHAT_GENERATIVE_UI", "chat_generative_ui_enabled"]
