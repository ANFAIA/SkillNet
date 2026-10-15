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

from src.core.language import Language, normalize_language

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


#: Key in ``organizations.settings``. Absent means "never chosen", so the fallback in
#: ``src.core.language`` decides — which is what every organization created before this
#: existed gets, unchanged.
ORG_LANGUAGE = "language"


def org_language(org_settings: dict[str, Any] | None) -> Language | None:
    """The language this organization generates in by default, if it chose one.

    ``None`` rather than ``DEFAULT_LANGUAGE`` on purpose: the callers need to tell "this
    organization asked for Spanish" from "nobody ever asked", because only the first one
    should win over a language inferred from the source material. Collapsing the two here
    would make every course built from an English document come out in Spanish.

    An unrecognised value reads as "never chosen" instead of raising. This is a JSONB
    column that a future admin form will write into, and a typo there should cost the
    default, not a 500 on every generation.
    """
    if not org_settings:
        return None
    return normalize_language(org_settings.get(ORG_LANGUAGE))


#: Keys in ``organizations.settings`` for sharing bug reports with the SkillNet team.
#: Off unless the admin turns it on: a report leaves the deployment only by their choice.
SHARE_BUG_REPORTS = "share_bug_reports"
#: A random id this deployment makes up the first time sharing is turned on. It lets the
#: relay count repeats; it identifies nobody.
BUG_REPORT_INSTANCE_ID = "bug_report_instance_id"


def share_bug_reports_enabled(org_settings: dict[str, Any] | None) -> bool:
    """Only an explicit ``True`` counts. Anything else, including a malformed value, is off."""
    if not org_settings:
        return False
    return org_settings.get(SHARE_BUG_REPORTS) is True


def bug_report_instance_id(org_settings: dict[str, Any] | None) -> str | None:
    if not org_settings:
        return None
    value = org_settings.get(BUG_REPORT_INSTANCE_ID)
    return value if isinstance(value, str) and value else None


__all__ = [
    "BUG_REPORT_INSTANCE_ID",
    "SHARE_BUG_REPORTS",
    "bug_report_instance_id",
    "share_bug_reports_enabled",
    "CHAT_GENERATIVE_UI",
    "ORG_LANGUAGE",
    "chat_generative_ui_enabled",
    "org_language",
]
