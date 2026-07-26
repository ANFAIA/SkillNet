"""The render layer of §5.

The LLM never produces HTML. The browser **does** now receive dialect text — but only
the canonical re-serialization of a spec this layer has already validated:

    node + profile + source -> LLM -> DIALECT (text)
        -> gate.check_program()   (size caps, no reactivity)
        -> backend.parse()        (frozen grammar + the 7 contract rules of §5.2)
        -> UISpec (jsonb audit row)
        -> backend.serialize()    -> node_renders.dialect -> <Renderer> in the browser

Public surface, and the only names the rest of the backend should import:

* :data:`~src.render.kit.UI_KIT` — the frozen catalogue (§5.3), source of truth for
  validation; the *prompt* catalogue comes from the frontend kit via
  :mod:`src.render.prompt`.
* :class:`~src.render.spec.UISpec` / :class:`~src.render.spec.Component` — the IR
  persisted in ``node_renders.ui_spec``, with the seven contract rules of §5.2.
* :func:`~src.render.gate.canonicalize` — untrusted output -> spec + the text to serve.
* :func:`~src.render.prompt.render_prompt` — the generated system prompt, and
  :func:`~src.render.prompt.catalog_version` for the provenance columns.
* :func:`~src.render.backends.get_render_backend` — dialect resolution by env var.
* :class:`~src.render.errors.RenderParseError` — what ``validate_ui`` catches.
"""

from src.render.backends import (
    RenderBackend,
    available_backends,
    get_render_backend,
)
from src.render.errors import RenderError, RenderParseError, RenderValidationError
from src.render.gate import (
    MAX_PROGRAM_BYTES,
    MAX_PROGRAM_LINES,
    assert_program_ok,
    canonicalize,
    check_program,
)
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
from src.render.prompt import (
    catalog_version,
    library_version,
    render_prompt,
)
from src.render.spec import (
    FORMATS_REQUIRING_LEAD,
    MAX_COMPONENTS,
    MAX_RENDERED_NODES,
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
    "MAX_PROGRAM_BYTES",
    "MAX_PROGRAM_LINES",
    "MAX_RENDERED_NODES",
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
    "assert_program_ok",
    "available_backends",
    "canonicalize",
    "catalog_version",
    "check_program",
    "get_render_backend",
    "library_version",
    "parse_spec",
    "render_prompt",
]
