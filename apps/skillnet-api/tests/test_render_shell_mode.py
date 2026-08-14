from __future__ import annotations

import uuid
from types import SimpleNamespace

from src.config import settings
from src.models.node_render import NodeRenderStatus
from src.render.spec import UISpec
from src.schemas.node import NodeRenderRead
from src.services.node_render_service import (
    ServedRender,
    generation_provenance_for_state,
    shell_mode_for_render,
)


def _render(
    *, status: NodeRenderStatus = NodeRenderStatus.READY, shell_mode: str | None = None
) -> SimpleNamespace:
    ui_spec: dict = {"components": []}
    if shell_mode is not None:
        ui_spec["generation"] = {
            "shell_mode": shell_mode,
            "generation_policy_key": "adaptive-episodes/v4",
            "episode_status": "ready" if shell_mode == "episode" else "declined",
        }
    return SimpleNamespace(
        id=uuid.uuid4(),
        node_id=uuid.uuid4(),
        ui_format="exercise",
        status=status,
        backend="openui",
        dialect='root = Stack([], "md")\n',
        cache_key="safety:bounded-screen/1:generation:adaptive-episodes/v4:abc",
        ui_spec=ui_spec,
    )


def test_shell_mode_comes_from_served_render_not_current_flag(monkeypatch) -> None:
    episode = _render(shell_mode="episode")
    legacy = _render(shell_mode="legacy_stepper")

    monkeypatch.setattr(settings, "ADAPTIVE_EPISODES", False)
    assert shell_mode_for_render(episode) == "episode"
    monkeypatch.setattr(settings, "ADAPTIVE_EPISODES", True)
    assert shell_mode_for_render(legacy) == "legacy_stepper"


def test_fallback_under_episode_policy_always_uses_legacy_shell() -> None:
    render = _render(status=NodeRenderStatus.FALLBACK, shell_mode="episode")

    assert shell_mode_for_render(render) == "legacy_stepper"


def test_persistence_provenance_distinguishes_ready_episode_and_fallback() -> None:
    state = {
        "episode_status": "ready",
        "episode_brief": {"episode_id": "opaque"},
        "generation_policy_key": "adaptive-episodes/v4",
    }

    assert generation_provenance_for_state(state, fallback=False) == {
        "shell_mode": "episode",
        "generation_policy_key": "adaptive-episodes/v4",
        "episode_status": "ready",
    }
    assert generation_provenance_for_state(state, fallback=True)["shell_mode"] == (
        "legacy_stepper"
    )


def test_support_only_is_still_episode_shell_but_fallback_is_legacy() -> None:
    state = {
        "episode_status": "support_only",
        "episode_brief": {"episode_id": "support"},
        "shell_mode": "episode",
        "generation_policy_key": "adaptive-episodes/v4",
    }

    ready = generation_provenance_for_state(state, fallback=False)
    fallback = generation_provenance_for_state(state, fallback=True)

    assert ready["shell_mode"] == "episode"
    assert ready["episode_status"] == "support_only"
    assert fallback["shell_mode"] == "legacy_stepper"


def test_old_or_declined_adaptive_row_without_marker_fails_closed_to_legacy() -> None:
    assert shell_mode_for_render(_render()) == "legacy_stepper"


def test_node_render_response_exposes_shell_mode_without_ui_spec() -> None:
    response = NodeRenderRead.of(ServedRender.of(_render(shell_mode="episode"), cached=True))

    assert response.shell_mode == "episode"
    assert "ui_spec" not in response.model_dump()


def test_generation_provenance_is_accepted_but_not_serialized_as_openui_ir() -> None:
    spec = UISpec.model_validate(
        {
            "version": "skillnet-ui/1",
            "format": "exercise",
            "root": "root",
            "components": [
                {
                    "id": "root",
                    "type": "Stack",
                    "props": {"gap": "md"},
                    "children": [],
                }
            ],
            "generation": {
                "shell_mode": "episode",
                "generation_policy_key": "adaptive-episodes/v4",
                "episode_status": "ready",
            },
        }
    )

    assert spec.generation is not None and spec.generation.shell_mode == "episode"
    assert "generation" not in spec.model_dump(mode="json")
