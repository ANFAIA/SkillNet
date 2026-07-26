"""The render layer of §5.

The LLM never produces HTML and the browser never receives generated markup:

    node + profile + source -> LLM -> DIALECT (text) -> backend.parse() -> UISpec (jsonb)

Public surface, and the only names the rest of the backend should import:

* :data:`~src.render.kit.UI_KIT` — the frozen catalogue (§5.3), source of truth for
  both the prompt and validation.
* :class:`~src.render.spec.UISpec` / :class:`~src.render.spec.Component` — the IR
  persisted in ``node_renders.ui_spec``, with the seven contract rules of §5.2.
* :func:`~src.render.backends.get_render_backend` — dialect resolution by env var.
* :class:`~src.render.errors.RenderParseError` — what ``validate_ui`` catches.
"""

from src.render.backends import (
    RenderBackend,
    available_backends,
    get_render_backend,
)
from src.render.errors import RenderError, RenderParseError, RenderValidationError
from src.render.kit import (
    COMPONENT_NAMES,
    CONTAINER_NAMES,
    LLM_COMPONENT_NAMES,
    UI_KIT,
    ComponentSpec,
    PropKind,
    PropSpec,
    UIKit,
)
from src.render.spec import (
    FORMATS_REQUIRING_LEAD,
    MAX_COMPONENTS,
    MAX_ROOT_CHILDREN,
    UI_FORMATS,
    UI_SPEC_VERSION,
    Component,
    UISpec,
    parse_spec,
)

__all__ = [
    "COMPONENT_NAMES",
    "CONTAINER_NAMES",
    "FORMATS_REQUIRING_LEAD",
    "LLM_COMPONENT_NAMES",
    "MAX_COMPONENTS",
    "MAX_ROOT_CHILDREN",
    "UI_FORMATS",
    "UI_KIT",
    "UI_SPEC_VERSION",
    "Component",
    "ComponentSpec",
    "PropKind",
    "PropSpec",
    "RenderBackend",
    "RenderError",
    "RenderParseError",
    "RenderValidationError",
    "UIKit",
    "UISpec",
    "available_backends",
    "get_render_backend",
    "parse_spec",
]
