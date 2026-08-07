"""Frontend tool-calling instructions shared by the tutor and admin prompts.

Both ``tutor.py`` and ``admin.py`` need this block and ``tutor.py`` imports
``admin.py`` (it re-exports the admin persona), so the constant cannot live in
either without a cycle.  Same pattern as ``grounding.py``.

The model is taught to emit ``ACTION: {...}`` lines at the end of its prose when
the user expressly asks for a UI change.  The backend strips those lines before
persisting the answer and emits them as ``action`` SSE events that the frontend
dispatches through its tool registry (``lib/toolRegistry.ts``).
"""

from __future__ import annotations

FRONTEND_TOOLS_BLOCK = """\
Herramientas de la interfaz:
Puedes pedir cambios en la interfaz del usuario anadiendo UNA linea ACTION al final de tu
respuesta. Solo cuando el usuario lo pida expresamente. Formato exacto:

ACTION: {"tool": "<nombre>", "args": {<argumentos>}}

Herramientas disponibles:
- set_locale: cambia el idioma. args: {"locale": "es"} o {"locale": "en"}
- set_theme: cambia el tema visual. args: {"theme": "light"}, {"theme": "dark"} o {"theme": "system"}
- set_sidebar_collapsed: colapsa o expande la barra lateral. args: {"collapsed": true} o {"collapsed": false}

Reglas:
- Solo una linea ACTION por respuesta, siempre al final.
- Solo cuando el usuario pida el cambio. No lo hagas por tu cuenta.
- Responde confirmando el cambio en texto normal ANTES de la linea ACTION."""

__all__ = ["FRONTEND_TOOLS_BLOCK"]
