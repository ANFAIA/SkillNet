"""The admin decides, and the default is the product.

Which model an organization uses is the admin's choice — that is what the provider
settings are for — so whether to attempt a kit layout with that model has to be theirs
too. A model that is weak at the dialect, or an admin who does not want to pay for a
second call per answer, needs a switch rather than a support request.

What this pins is the default and the shape of "off", because both are easy to get
subtly wrong in a JSONB column where a key can simply be absent.
"""

from __future__ import annotations

import pytest

from src.services.org_features import CHAT_GENERATIVE_UI, chat_generative_ui_enabled


def test_it_is_on_when_nobody_has_chosen():
    """Absent is not the same as False. A fresh organization gets the product."""
    assert chat_generative_ui_enabled({}) is True
    assert chat_generative_ui_enabled(None) is True
    assert chat_generative_ui_enabled({"llm_model": "deepseek/deepseek-chat"}) is True


def test_it_is_off_only_when_explicitly_turned_off():
    assert chat_generative_ui_enabled({CHAT_GENERATIVE_UI: False}) is False


def test_it_is_on_when_explicitly_turned_on():
    assert chat_generative_ui_enabled({CHAT_GENERATIVE_UI: True}) is True


@pytest.mark.parametrize("junk", ["false", "no", 0, "", None, [], {}])
def test_junk_in_the_column_does_not_disable_the_feature(junk):
    """Only a real `False` counts. A string `"false"` written by hand, or a null left by
    a partial migration, must not silently switch off a feature nobody asked to switch
    off — the failure would be invisible, because prose answers look fine."""
    assert chat_generative_ui_enabled({CHAT_GENERATIVE_UI: junk}) is True


def test_the_key_is_the_one_the_service_writes():
    """Guards against the setting being written under one name and read under another,
    which would look exactly like a switch that does nothing."""
    from src.services import settings_service

    assert settings_service.CHAT_GENERATIVE_UI == CHAT_GENERATIVE_UI
